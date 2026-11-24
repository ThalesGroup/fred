# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""CP receipts, Temporal retries and SQL-fenced Word template preparation."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fred_sdk.contracts.capability.preparation import (
    CapabilityObjects,
    PreparationContext,
    PreparationResult,
)
from sqlalchemy import DateTime, Integer, String, Text, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from .analysis import TemplateAnalysis, analysis_messages, parse_analysis
from .docmap import build_map, render_map, render_parts
from .store import WordTemplateBase, _default_sessionmaker

logger = logging.getLogger(__name__)


class WordTemplatePreparation(WordTemplateBase):
    __tablename__ = "cap_word_template_preparations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    space_id: Mapped[str] = mapped_column(String(36))
    runtime_id: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))
    attempt: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pending_writes: Mapped[int] = mapped_column(Integer, default=0)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_path: Mapped[str | None] = mapped_column(String(255), nullable=True)


_objects: CapabilityObjects | None = None
_writes: set[asyncio.Task[None]] = set()


def bind_objects(objects: CapabilityObjects) -> None:
    global _objects
    _objects = objects


def objects() -> CapabilityObjects:
    if _objects is None:
        raise RuntimeError("Word template object storage is unavailable")
    return _objects


def _done(task: asyncio.Task[None]) -> None:
    _writes.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.warning("Word preparation object write outcome is unknown")


async def _reserve(
    ctx: PreparationContext, *, retire: bool = False
) -> async_sessionmaker:
    factory = async_sessionmaker(ctx.database, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(
            insert(WordTemplatePreparation)
            .values(
                id=str(ctx.work.preparation_id),
                space_id=str(ctx.work.space_id),
                runtime_id=ctx.work.runtime_id,
                sha256=ctx.work.sha256,
                state="retired" if retire else "pending",
                pending_writes=0,
            )
            .on_conflict_do_nothing()
        )
    return factory


def _input(content: bytes) -> tuple[str, str]:
    if len(content) > 50 * 1024 * 1024:
        raise ValueError("Word template exceeds 50 MiB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValueError("Word template is not a readable DOCX archive") from exc
    with archive:
        members = archive.infolist()
        if (
            len(members) > 10000
            or sum(member.file_size for member in members) > 128 * 1024 * 1024
        ):
            raise ValueError("Word template expanded content exceeds its bound")
        if any(
            member.file_size > 32 * 1024 * 1024
            or (
                member.file_size > 1024 * 1024
                and member.file_size > 100 * max(member.compress_size, 1)
            )
            for member in members
        ):
            raise ValueError("Word template contains an oversized compressed member")
    mapping = build_map(content)
    return render_map(mapping), render_parts(mapping)[:3000]


async def prepare(ctx: PreparationContext) -> PreparationResult:
    factory = await _reserve(ctx)
    identity = str(ctx.work.preparation_id)
    attempt = str(uuid4())
    async with factory() as session, session.begin():
        row = (
            await session.execute(
                select(WordTemplatePreparation)
                .where(WordTemplatePreparation.id == identity)
                .with_for_update()
            )
        ).scalar_one()
        if (row.space_id, row.runtime_id, row.sha256) != (
            str(ctx.work.space_id),
            ctx.work.runtime_id,
            ctx.work.sha256,
        ):
            raise ValueError("Word preparation identity mismatch")
        if row.state == "ready":
            return PreparationResult(reference=identity)
        if row.state == "retired":
            raise ValueError("Word preparation retired")
        if row.lease_until is not None and row.lease_until > datetime.now(UTC):
            raise RuntimeError("Word preparation has an active attempt")
        row.attempt = attempt
        row.lease_until = datetime.now(UTC) + timedelta(minutes=20)
    try:
        if ctx.text is None:
            raise RuntimeError("Word preparation requires Knowledge Flow text")
        if hashlib.sha256(ctx.content).hexdigest() != ctx.work.sha256:
            raise ValueError("Word preparation file mismatch")
        mapping, parts = await asyncio.to_thread(_input, ctx.content)
        messages = analysis_messages(mapping, parts)
        answer = await ctx.text.complete(
            str(messages[0].content), str(messages[1].content)
        )
        analysis = parse_analysis(answer).model_dump_json()
        path = f"{identity}/{attempt}/template.docx"
        await objects().check()
        async with factory() as session, session.begin():
            result = await session.execute(
                update(WordTemplatePreparation)
                .where(
                    WordTemplatePreparation.id == identity,
                    WordTemplatePreparation.state == "pending",
                    WordTemplatePreparation.attempt == attempt,
                )
                .values(pending_writes=WordTemplatePreparation.pending_writes + 1)
            )
            if result.rowcount != 1:
                raise RuntimeError("Word preparation lost ownership")

        async def write() -> None:
            await objects().write(path, ctx.content)
            async with factory() as session, session.begin():
                await session.execute(
                    update(WordTemplatePreparation)
                    .where(
                        WordTemplatePreparation.id == identity,
                    )
                    .values(pending_writes=WordTemplatePreparation.pending_writes - 1)
                )

        task = asyncio.create_task(write())
        _writes.add(task)
        task.add_done_callback(_done)
        await asyncio.shield(task)
        async with factory() as session, session.begin():
            result = await session.execute(
                update(WordTemplatePreparation)
                .where(
                    WordTemplatePreparation.id == identity,
                    WordTemplatePreparation.state == "pending",
                    WordTemplatePreparation.attempt == attempt,
                )
                .values(
                    state="ready", analysis=analysis, object_path=path, lease_until=None
                )
            )
            if result.rowcount != 1:
                raise RuntimeError("Word preparation lost ownership")
        return PreparationResult(reference=identity)
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                update(WordTemplatePreparation)
                .where(
                    WordTemplatePreparation.id == identity,
                    WordTemplatePreparation.state == "pending",
                    WordTemplatePreparation.attempt == attempt,
                )
                .values(lease_until=None)
            )


async def retire(ctx: PreparationContext) -> None:
    factory = await _reserve(ctx, retire=True)
    identity = str(ctx.work.preparation_id)
    async with factory() as session, session.begin():
        row = (
            await session.execute(
                select(WordTemplatePreparation)
                .where(WordTemplatePreparation.id == identity)
                .with_for_update()
            )
        ).scalar_one()
        if (row.space_id, row.runtime_id, row.sha256) != (
            str(ctx.work.space_id),
            ctx.work.runtime_id,
            ctx.work.sha256,
        ):
            raise ValueError("Word preparation identity mismatch")
        row.state = "retired"
        row.analysis = None
        row.object_path = None
        pending = row.pending_writes
    if pending:
        raise RuntimeError("Word preparation has unfinished object writes")
    await objects().delete(identity)


async def read(reference: str, sha256: str) -> tuple[bytes, TemplateAnalysis]:
    identity = str(UUID(reference))
    async with _default_sessionmaker()() as session:
        row = (
            await session.execute(
                select(WordTemplatePreparation).where(
                    WordTemplatePreparation.id == identity,
                    WordTemplatePreparation.sha256 == sha256,
                    WordTemplatePreparation.state == "ready",
                )
            )
        ).scalar_one_or_none()
        if row is None or row.object_path is None or row.analysis is None:
            raise ValueError("Prepared Word template is unavailable")
        path, analysis = row.object_path, row.analysis
    content = await objects().read(path)
    if hashlib.sha256(content).hexdigest() != sha256:
        raise ValueError("Prepared Word template changed")
    return content, TemplateAnalysis.model_validate(json.loads(analysis))
