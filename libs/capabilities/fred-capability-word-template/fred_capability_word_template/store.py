# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Persistence: five `cap_word_template_*` tables on the capability's
own metadata, without foreign keys: sessions (the pinned base), batches (the
operation log, with its author), analyses (per base sha256), snapshots (a
replay cache, never the source of truth), and images (per session). Reached
through an overridable provider (`get_word_template_store`).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import (
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    delete,
    func,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Shared by `capability.py` (save time, chat time) and `router.py` (export).
WORD_TEMPLATE_CAPABILITY_ID = "word_template"
# Templates are stored under `<prefix>.<uuid>.docx`: a re-upload never
# overwrites the bytes a session pinned, and the extension passes the asset
# slot's `accepted_types` check when an agent copy re-submits the file.
WORD_TEMPLATE_ASSET_PREFIX = "word_template"

Batch = list[dict[str, Any]]
BaseKind = Literal["template"]
BatchAuthor = Literal["model", "collaborator"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --- Owned tables ------------------------------------------------------------


class WordTemplateBase(DeclarativeBase):
    """Isolated declarative base for the word_template capability's tables."""


class WordTemplateSession(WordTemplateBase):
    """One chat session's selected library template. It is selected until
    the first edit pins it (``pinned_at`` set). ``user_id`` is the owner, set once by the first
    write; ``team_id``/``agent_instance_id`` are write provenance, used to
    fetch a library template at export time."""

    __tablename__ = "cap_word_template_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_instance_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    template_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_content: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class WordTemplateBatch(WordTemplateBase):
    """One applied batch of operations, in order, and its author."""

    __tablename__ = "cap_word_template_batches"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    operations: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    author: Mapped[str] = mapped_column(
        String(16), nullable=False, default="model", server_default="model"
    )


class WordTemplateAnalysis(WordTemplateBase):
    """The template analysis, keyed by the base document's sha256."""

    __tablename__ = "cap_word_template_analyses"

    template_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    analysis: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class WordTemplateSnapshot(WordTemplateBase):
    """The session's document after batches 1..``seq`` (a replay cache).
    ``digest`` identifies the template key + log prefix it was built from."""

    __tablename__ = "cap_word_template_snapshots"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    docx: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class WordTemplateImage(WordTemplateBase):
    """An image the model may place in the session's document, referenced
    as ``![caption](img:<image_id>)``. ``image_id`` is short ("img1") because
    the model copies it into a tool call."""

    __tablename__ = "cap_word_template_images"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "sha256", name="uq_cap_word_template_images_sha256"
        ),
    )

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    image_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    context_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


# --- Records -------------------------------------------------------------------


@dataclass(frozen=True)
class BaseRef:
    """The library template a session's document is built on."""

    kind: BaseKind
    ref: str

    @property
    def identity(self) -> str:
        """Stable text identity for snapshot digests and pod caches."""
        return self.ref


@dataclass
class SessionState:
    session_id: str
    user_id: str
    team_id: str | None = None
    agent_instance_id: str | None = None
    template_key: str | None = None
    pinned_at: datetime | None = None
    updated_at: datetime | None = None
    batch_count: int = 0

    @property
    def base(self) -> BaseRef | None:
        """The selected template, if any."""
        if self.template_key:
            return BaseRef("template", self.template_key)
        return None


@dataclass(frozen=True)
class ImageInfo:
    """One session image, without its bytes."""

    image_id: str
    filename: str
    content_type: str
    sha256: str
    size: int
    context_text: str | None = None


def new_image_id(existing_ids: Collection[str]) -> str:
    """The next short, per-session image id ("img1", "img2", ...)."""
    n = len(existing_ids) + 1
    while f"img{n}" in existing_ids:
        n += 1
    return f"img{n}"


@dataclass(frozen=True)
class Writer:
    """Who writes: provenance stamped on the session row."""

    user_id: str
    team_id: str | None = None
    agent_instance_id: str | None = None


@dataclass(frozen=True)
class BatchRecord:
    """One batch of the log with its position and author."""

    seq: int
    author: BatchAuthor
    operations: Batch


@dataclass(frozen=True)
class Snapshot:
    """A persisted replay of batches 1..``seq`` (see ``WordTemplateSnapshot``)."""

    seq: int
    digest: str
    docx: bytes


class BatchConflict(Exception):
    """The session's log changed since the batch was validated (another
    batch was appended at the same time): nothing was appended."""


class AssetInUse(Exception):
    """An image is part of the session's current document."""


# --- Store contract --------------------------------------------------------------


class WordTemplateStore(ABC):
    @abstractmethod
    async def get_session(
        self, session_id: str
    ) -> SessionState | None:  # pragma: no cover - interface
        """The session's template state, with its batch count, or None."""

    @abstractmethod
    async def claim_session(
        self, session_id: str, user_id: str
    ) -> str:  # pragma: no cover - interface
        """The session's owner; ``user_id`` becomes it when there is none yet."""

    @abstractmethod
    async def select_base(
        self,
        session_id: str,
        base: BaseRef,
        writer: Writer,
        *,
        expected_count: int,
        base_content: bytes | None = None,
    ) -> None:  # pragma: no cover - interface
        """Record the session's selected base (not pinned). ``BatchConflict``
        when the log is no longer ``expected_count`` batches long."""

    @abstractmethod
    async def append_batch(
        self,
        session_id: str,
        base: BaseRef,
        operations: Batch,
        writer: Writer,
        *,
        expected_count: int,
        author: BatchAuthor = "model",
        base_content: bytes | None = None,
    ) -> int:  # pragma: no cover - interface
        """Append one batch validated against a log of ``expected_count``
        batches (``BatchConflict`` otherwise); pins ``base`` if nothing is
        pinned yet. Returns the batch's ``seq``."""

    @abstractmethod
    async def list_batches(
        self, session_id: str
    ) -> list[Batch]:  # pragma: no cover - interface
        """The session's batches, oldest first."""

    @abstractmethod
    async def list_batch_records(
        self, session_id: str
    ) -> list[BatchRecord]:  # pragma: no cover - interface
        """The session's batches with their seq and author, oldest first."""

    @abstractmethod
    async def drop_last_batch(
        self, session_id: str, *, expected_count: int | None = None
    ) -> Batch | None:  # pragma: no cover - interface
        """Remove and return the last batch, and the session's snapshot;
        unpins the template when no batch is left. None when there was
        nothing to drop. With ``expected_count``, ``BatchConflict`` when the
        log does not hold exactly that many batches (nothing dropped)."""

    @abstractmethod
    async def get_analysis(
        self, content_sha256: str
    ) -> str | None:  # pragma: no cover - interface
        """The cached analysis of the base whose bytes hash to this."""

    @abstractmethod
    async def put_analysis(
        self, content_sha256: str, analysis_json: str
    ) -> None:  # pragma: no cover - interface
        ...

    @abstractmethod
    async def get_base_content(
        self, session_id: str, template_key: str
    ) -> bytes | None:  # pragma: no cover - interface
        """The persisted platform base selected for this session."""

    @abstractmethod
    async def delete_image(
        self, session_id: str, image_id: str
    ) -> bool:  # pragma: no cover - interface
        """Delete one session image. False when there was no such image."""

    @abstractmethod
    async def put_image(
        self,
        session_id: str,
        *,
        filename: str,
        content_type: str,
        sha256: str,
        content: bytes,
        context_text: str | None = None,
    ) -> ImageInfo:  # pragma: no cover - interface
        """Store an image under the next short id, or return the one already
        stored with the same bytes in this session."""

    @abstractmethod
    async def list_images(
        self, session_id: str
    ) -> list[ImageInfo]:  # pragma: no cover - interface
        """The session's images, oldest first, without their bytes."""

    @abstractmethod
    async def get_image(
        self, session_id: str, image_id: str
    ) -> tuple[ImageInfo, bytes] | None:  # pragma: no cover - interface
        """One image with its bytes, or None."""

    @abstractmethod
    async def get_images(
        self, session_id: str, image_ids: Collection[str]
    ) -> dict[str, bytes]:  # pragma: no cover - interface
        """The bytes of the given images, by id, in one lookup; an unknown
        id is absent."""

    @abstractmethod
    async def get_snapshot(
        self, session_id: str
    ) -> Snapshot | None:  # pragma: no cover - interface
        """The session's persisted document snapshot, or None."""

    @abstractmethod
    async def put_snapshot(
        self, session_id: str, seq: int, digest: str, docx: bytes
    ) -> None:  # pragma: no cover - interface
        """Store (replace) the session's snapshot. Best effort: callers
        ignore failures, a missing snapshot only means a replay."""


# --- SQL implementation ------------------------------------------------------------


def _state(row: WordTemplateSession, batch_count: int) -> SessionState:
    return SessionState(
        session_id=row.session_id,
        user_id=row.user_id,
        team_id=row.team_id,
        agent_instance_id=row.agent_instance_id,
        template_key=row.template_key,
        pinned_at=row.pinned_at,
        updated_at=row.updated_at,
        batch_count=batch_count,
    )


def _set_base(row: WordTemplateSession, base: BaseRef) -> None:
    row.template_key = base.ref


def _selected_base(row: WordTemplateSession) -> BaseRef | None:
    if row.template_key:
        return BaseRef("template", row.template_key)
    return None


def _stamp(row: WordTemplateSession, writer: Writer, now: datetime) -> None:
    if writer.team_id is not None:
        row.team_id = writer.team_id
    if writer.agent_instance_id is not None:
        row.agent_instance_id = writer.agent_instance_id
    row.updated_at = now


_IMAGE_INFO_COLUMNS = (
    WordTemplateImage.image_id,
    WordTemplateImage.filename,
    WordTemplateImage.content_type,
    WordTemplateImage.sha256,
    WordTemplateImage.size,
    WordTemplateImage.context_text,
)


def _image_info(row: Any) -> ImageInfo:
    return ImageInfo(
        image_id=row.image_id,
        filename=row.filename,
        content_type=row.content_type,
        sha256=row.sha256,
        size=row.size,
        context_text=row.context_text,
    )


class SqlWordTemplateStore(WordTemplateStore):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def _session_row(
        self, session: AsyncSession, session_id: str, writer: Writer, now: datetime
    ) -> WordTemplateSession:
        await session.execute(
            text(
                "INSERT INTO cap_word_template_sessions (session_id, user_id, updated_at) "
                "VALUES (:session_id, :user_id, :updated_at) "
                "ON CONFLICT (session_id) DO NOTHING"
            ),
            {"session_id": session_id, "user_id": writer.user_id, "updated_at": now},
        )
        row = await session.scalar(
            select(WordTemplateSession)
            .where(WordTemplateSession.session_id == session_id)
            .with_for_update()
        )
        assert row is not None
        _stamp(row, writer, now)
        return row

    async def get_session(self, session_id: str) -> SessionState | None:
        async with self._sessionmaker() as session:
            row = await session.get(WordTemplateSession, session_id)
            if row is None:
                return None
            count = await session.scalar(
                select(func.count()).where(WordTemplateBatch.session_id == session_id)
            )
            return _state(row, int(count or 0))

    async def claim_session(self, session_id: str, user_id: str) -> str:
        # Concurrent first writes claim together: the loser re-reads.
        for attempt in range(2):
            try:
                async with self._sessionmaker() as session, session.begin():
                    row = await session.get(WordTemplateSession, session_id)
                    if row is None:
                        row = WordTemplateSession(
                            session_id=session_id, user_id=user_id, updated_at=_utcnow()
                        )
                        session.add(row)
                    return row.user_id
            except IntegrityError:
                if attempt == 1:
                    raise
        raise AssertionError("unreachable")  # pragma: no cover

    async def select_base(
        self,
        session_id: str,
        base: BaseRef,
        writer: Writer,
        *,
        expected_count: int,
        base_content: bytes | None = None,
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            row = await self._session_row(session, session_id, writer, _utcnow())
            count = await session.scalar(
                select(func.count()).where(WordTemplateBatch.session_id == session_id)
            )
            if int(count or 0) != expected_count:
                raise BatchConflict(session_id)
            current = _selected_base(row)
            if int(count or 0) > 0 and current != base:
                raise BatchConflict(session_id)
            if base.ref.startswith("prepared-") and base_content is None:
                raise ValueError("Platform Word base bytes are missing")
            _set_base(row, base)
            row.base_content = (
                base_content if base.ref.startswith("prepared-") else None
            )

    async def append_batch(
        self,
        session_id: str,
        base: BaseRef,
        operations: Batch,
        writer: Writer,
        *,
        expected_count: int,
        author: BatchAuthor = "model",
        base_content: bytes | None = None,
    ) -> int:
        try:
            async with self._sessionmaker() as session, session.begin():
                now = _utcnow()
                row = await self._session_row(session, session_id, writer, now)
                current = _selected_base(row)
                if current is not None and current != base:
                    raise BatchConflict(session_id)
                if row.pinned_at is None:
                    _set_base(row, base)
                    if base.ref.startswith("prepared-"):
                        if base_content is None:
                            raise ValueError("Platform Word base bytes are missing")
                        row.base_content = base_content
                    else:
                        row.base_content = None
                    row.pinned_at = now
                last = await session.scalar(
                    select(func.max(WordTemplateBatch.seq)).where(
                        WordTemplateBatch.session_id == session_id
                    )
                )
                if int(last or 0) != expected_count:
                    raise BatchConflict(session_id)
                seq = expected_count + 1
                session.add(
                    WordTemplateBatch(
                        session_id=session_id,
                        seq=seq,
                        operations=json.dumps(operations, ensure_ascii=False),
                        created_at=now,
                        author=author,
                    )
                )
            return seq
        except IntegrityError as exc:
            # Two appends raced past the count check: same primary key.
            raise BatchConflict(session_id) from exc

    async def get_base_content(
        self, session_id: str, template_key: str
    ) -> bytes | None:
        async with self._sessionmaker() as session:
            return await session.scalar(
                select(WordTemplateSession.base_content).where(
                    WordTemplateSession.session_id == session_id,
                    WordTemplateSession.template_key == template_key,
                )
            )

    async def list_batches(self, session_id: str) -> list[Batch]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(WordTemplateBatch.operations)
                .where(WordTemplateBatch.session_id == session_id)
                .order_by(WordTemplateBatch.seq)
            )
            return [json.loads(raw) for raw in result.scalars().all()]

    async def list_batch_records(self, session_id: str) -> list[BatchRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(
                    WordTemplateBatch.seq,
                    WordTemplateBatch.author,
                    WordTemplateBatch.operations,
                )
                .where(WordTemplateBatch.session_id == session_id)
                .order_by(WordTemplateBatch.seq)
            )
            return [
                BatchRecord(
                    seq=r.seq,
                    author="collaborator" if r.author == "collaborator" else "model",
                    operations=json.loads(r.operations),
                )
                for r in result.all()
            ]

    async def drop_last_batch(
        self, session_id: str, *, expected_count: int | None = None
    ) -> Batch | None:
        async with self._sessionmaker() as session, session.begin():
            row = await session.scalar(
                select(WordTemplateSession)
                .where(WordTemplateSession.session_id == session_id)
                .with_for_update()
            )
            if expected_count is not None:
                count = await session.scalar(
                    select(func.count()).where(
                        WordTemplateBatch.session_id == session_id
                    )
                )
                if int(count or 0) != expected_count:
                    raise BatchConflict(session_id)
            last = (
                (
                    await session.execute(
                        select(WordTemplateBatch)
                        .where(WordTemplateBatch.session_id == session_id)
                        .order_by(WordTemplateBatch.seq.desc())
                        .limit(2)
                    )
                )
                .scalars()
                .all()
            )
            if not last:
                return None
            dropped = last[0]
            await session.execute(
                delete(WordTemplateBatch).where(
                    WordTemplateBatch.session_id == session_id,
                    WordTemplateBatch.seq == dropped.seq,
                )
            )
            await session.execute(
                delete(WordTemplateSnapshot).where(
                    WordTemplateSnapshot.session_id == session_id
                )
            )
            if len(last) == 1:
                if row is not None:
                    row.pinned_at = None
                    row.updated_at = _utcnow()
            return json.loads(dropped.operations)

    async def get_analysis(self, content_sha256: str) -> str | None:
        async with self._sessionmaker() as session:
            row = await session.get(WordTemplateAnalysis, content_sha256)
            return row.analysis if row is not None else None

    async def put_analysis(self, content_sha256: str, analysis_json: str) -> None:
        try:
            async with self._sessionmaker() as session, session.begin():
                row = await session.get(WordTemplateAnalysis, content_sha256)
                if row is None:
                    session.add(
                        WordTemplateAnalysis(
                            template_key=content_sha256,
                            analysis=analysis_json,
                            created_at=_utcnow(),
                        )
                    )
                else:
                    row.analysis = analysis_json
        except IntegrityError:
            # Another replica cached the same template's analysis first.
            return

    async def get_snapshot(self, session_id: str) -> Snapshot | None:
        async with self._sessionmaker() as session:
            row = await session.get(WordTemplateSnapshot, session_id)
            if row is None:
                return None
            return Snapshot(seq=row.seq, digest=row.digest, docx=row.docx)

    async def put_snapshot(
        self, session_id: str, seq: int, digest: str, docx: bytes
    ) -> None:
        try:
            async with self._sessionmaker() as session, session.begin():
                row = await session.get(WordTemplateSnapshot, session_id)
                if row is None:
                    session.add(
                        WordTemplateSnapshot(
                            session_id=session_id,
                            seq=seq,
                            digest=digest,
                            docx=docx,
                            updated_at=_utcnow(),
                        )
                    )
                else:
                    row.seq = seq
                    row.digest = digest
                    row.docx = docx
                    row.updated_at = _utcnow()
        except IntegrityError:
            # Another writer stored one first; either is a valid cache entry.
            return

    async def delete_image(self, session_id: str, image_id: str) -> bool:
        from fred_capability_word_template.images import batch_image_ids

        async with self._sessionmaker() as session, session.begin():
            await session.scalar(
                select(WordTemplateSession.session_id)
                .where(WordTemplateSession.session_id == session_id)
                .with_for_update()
            )
            batches = (
                await session.execute(
                    select(WordTemplateBatch.operations).where(
                        WordTemplateBatch.session_id == session_id
                    )
                )
            ).scalars()
            if image_id in batch_image_ids(json.loads(raw) for raw in batches):
                raise AssetInUse(image_id)
            deleted = await session.execute(
                delete(WordTemplateImage).where(
                    WordTemplateImage.session_id == session_id,
                    WordTemplateImage.image_id == image_id,
                )
            )
            return bool(getattr(deleted, "rowcount", 0))

    async def _image_by_sha(self, session_id: str, sha256: str) -> ImageInfo | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(*_IMAGE_INFO_COLUMNS).where(
                        WordTemplateImage.session_id == session_id,
                        WordTemplateImage.sha256 == sha256,
                    )
                )
            ).first()
            return _image_info(row) if row is not None else None

    async def put_image(
        self,
        session_id: str,
        *,
        filename: str,
        content_type: str,
        sha256: str,
        content: bytes,
        context_text: str | None = None,
    ) -> ImageInfo:
        # Parallel uploads may pick the same short id; unique keys catch the
        # race and a retry re-reads.
        for attempt in range(5):
            existing = await self._image_by_sha(session_id, sha256)
            if existing is not None:
                return existing
            ids = {i.image_id for i in await self.list_images(session_id)}
            info = ImageInfo(
                image_id=new_image_id(ids),
                filename=filename,
                content_type=content_type,
                sha256=sha256,
                size=len(content),
                context_text=context_text,
            )
            try:
                async with self._sessionmaker() as session, session.begin():
                    session.add(
                        WordTemplateImage(
                            session_id=session_id,
                            image_id=info.image_id,
                            sha256=sha256,
                            filename=filename,
                            content_type=content_type,
                            size=len(content),
                            context_text=context_text,
                            content=content,
                            created_at=_utcnow(),
                        )
                    )
                return info
            except IntegrityError:
                if attempt == 4:
                    raise
        raise AssertionError("unreachable")  # pragma: no cover

    async def list_images(self, session_id: str) -> list[ImageInfo]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(*_IMAGE_INFO_COLUMNS)
                .where(WordTemplateImage.session_id == session_id)
                .order_by(WordTemplateImage.created_at, WordTemplateImage.image_id)
            )
            return [_image_info(r) for r in result.all()]

    async def get_image(
        self, session_id: str, image_id: str
    ) -> tuple[ImageInfo, bytes] | None:
        async with self._sessionmaker() as session:
            row = await session.get(WordTemplateImage, (session_id, image_id))
            if row is None:
                return None
            return _image_info(row), row.content

    async def get_images(
        self, session_id: str, image_ids: Collection[str]
    ) -> dict[str, bytes]:
        if not image_ids:
            return {}
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(WordTemplateImage.image_id, WordTemplateImage.content).where(
                    WordTemplateImage.session_id == session_id,
                    WordTemplateImage.image_id.in_(list(image_ids)),
                )
            )
            return {r.image_id: r.content for r in result.all()}


# --- Overridable provider (services never bind at import time) ------------------

_provider: Callable[[], WordTemplateStore] | None = None


@dataclass
class _EngineCache:
    engine: AsyncEngine | None = field(default=None)
    sessionmaker: async_sessionmaker[AsyncSession] | None = field(default=None)


_engine_cache = _EngineCache()


def _default_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Build (once) the async sessionmaker from the pod's own Postgres config.

    Reads `storage.postgres` through fred-core rather than the host pod's
    configuration model, as `writable_document` does: this package owns
    tables, not a dependency on whatever pod it is installed into."""

    if _engine_cache.sessionmaker is None:
        from fred_core.common import load_postgres_config
        from fred_core.sql import create_async_engine_from_config

        engine = create_async_engine_from_config(load_postgres_config())
        _engine_cache.engine = engine
        _engine_cache.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return _engine_cache.sessionmaker


def get_word_template_store() -> WordTemplateStore:
    """Resolve the store (test-overridable provider seam)."""

    if _provider is not None:
        return _provider()
    return SqlWordTemplateStore(_default_sessionmaker())


def set_store_provider(provider: Callable[[], WordTemplateStore]) -> None:
    global _provider
    _provider = provider


def clear_store_provider() -> None:
    global _provider
    _provider = None


def summarize_batches(
    batches: Sequence[Batch],
    *,
    limit: int = 10,
    authors: Sequence[BatchAuthor] | None = None,
) -> str:
    """A short line per batch (the last ``limit``): its operations and the
    addresses they used, for the prompt's "done so far" and the undo reply.
    With ``authors`` (one per batch), each line says who made it."""

    lines: list[str] = []
    start = max(0, len(batches) - limit)
    if start:
        lines.append(f"(batches 1–{start} not shown)")
    for index, batch in enumerate(batches[start:], start=start + 1):
        who = ""
        if authors is not None and index - 1 < len(authors):
            who = " (you)" if authors[index - 1] == "model" else " (the collaborator)"
        lines.append(f"batch {index}{who}: {describe_batch(batch)}")
    return "\n".join(lines)


def _short(text: Any, limit: int = 80) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else f"{flat[:limit]}..."


def describe_operation(op: Mapping[str, Any]) -> str:
    """One operation in words, with the place and the new text (cut), for
    the prompt's list of the collaborator's edits."""
    name = str(op.get("op", "?"))
    address = op.get("address") or op.get("from") or "?"
    to = op.get("to")
    where = f"{address}–{to}" if to and to != address else str(address)
    if name == "set_text":
        return f'{where} set to "{_short(op.get("text"))}"'
    if name == "replace_text":
        return (
            f'in {where}: "{_short(op.get("find"), 40)}" replaced by '
            f'"{_short(op.get("replace"))}"'
        )
    if name == "write":
        return f'{where} rewritten: "{_short(op.get("markdown"))}"'
    if name == "insert_after":
        return f'added after {where}: "{_short(op.get("markdown"))}"'
    if name == "repeat":
        return f"{where} duplicated ×{op.get('count')}"
    if name == "remove":
        return f"{where} removed"
    if name == "move":
        side = "before" if op.get("before") else "after"
        return f"{where} moved {side} {op.get(side)}"
    return f"{name} {where}"


def describe_batch(batch: Sequence[Mapping[str, Any]]) -> str:
    bits: list[str] = []
    for op in batch:
        name = str(op.get("op", "?"))
        address = op.get("address") or op.get("from") or op.get("from_") or "?"
        to = op.get("to")
        where = f"{address}–{to}" if to and to != address else str(address)
        if name == "repeat":
            where += f" ×{op.get('count')}"
        bits.append(f"{name} {where}")
    text = ", ".join(bits)
    return text if len(text) <= 300 else f"{text[:300]}..."
