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

"""Persistence: six `cap_word_template_*` tables on the capability's
own metadata, without foreign keys: sessions (the pinned base), batches (the
operation log, with its author), analyses (per base sha256), snapshots (a
replay cache, never the source of truth), attachments and images (per
session). Reached through an overridable provider (`get_word_template_store`).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    delete,
    false,
    func,
    select,
    update,
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
BaseKind = Literal["template", "attachment"]
BatchAuthor = Literal["model", "collaborator"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --- Owned tables ------------------------------------------------------------


class WordTemplateBase(DeclarativeBase):
    """Isolated declarative base for the word_template capability's tables."""


class WordTemplateSession(WordTemplateBase):
    """One chat session's base choice. The base is the attached file
    ``attachment_id`` when it is set, else the library template
    ``template_key``; it is the selected one until the first edit pins it
    (``pinned_at`` set). ``user_id``/``team_id``/``agent_instance_id`` are
    write provenance, used to fetch a library template at export time."""

    __tablename__ = "cap_word_template_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_instance_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    template_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    attachment_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class WordTemplateBatch(WordTemplateBase):
    """One applied batch of operations, in order (``seq`` from 1), and who
    made it (``model`` or ``collaborator``; rows from before the column
    existed are the model's)."""

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
    """The template analysis of one base document, as JSON. The
    ``template_key`` column holds the sha256 of the base's bytes (older rows
    keyed by asset key are never read)."""

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


class WordTemplateAttachment(WordTemplateBase):
    """A Word file attached in a session's chat, kept by the capability (the
    platform keeps no attachment bytes). ``attachment_id`` is short ("doc1")
    because the model copies it into a tool call."""

    __tablename__ = "cap_word_template_attachments"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "sha256", name="uq_cap_word_template_attachments_sha256"
        ),
    )

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    attachment_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    # Its pictures were copied to `cap_word_template_images` (rows created
    # before this column existed are backfilled on first read).
    images_extracted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )


class WordTemplateImage(WordTemplateBase):
    """An image the model may place in the session's document, referenced
    as ``![caption](img:<image_id>)``: attached in the chat, or found in an
    attached Word file (``source_attachment_id``, with ``context_text``, the
    text next to it there). ``image_id`` is short ("img1") because the model
    copies it into a tool call."""

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
    source_attachment_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


# --- Records -------------------------------------------------------------------


@dataclass(frozen=True)
class BaseRef:
    """What a session's document is built on: a library template (``ref`` =
    its asset key) or an attached file (``ref`` = its short id)."""

    kind: BaseKind
    ref: str

    @property
    def identity(self) -> str:
        """Stable text identity (snapshot digests, pod caches). A template
        keeps its bare key, so snapshots from before attachments still
        match; asset keys never start with ``attachment:``."""
        return self.ref if self.kind == "template" else f"attachment:{self.ref}"


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
    attachment_id: str | None = None

    @property
    def base(self) -> BaseRef | None:
        """The selected or pinned base: the attachment when set, else the
        template, else None."""
        if self.attachment_id:
            return BaseRef("attachment", self.attachment_id)
        if self.template_key:
            return BaseRef("template", self.template_key)
        return None


@dataclass(frozen=True)
class AttachmentInfo:
    """One attached Word file, without its bytes."""

    attachment_id: str
    filename: str
    sha256: str
    size: int
    images_extracted: bool = False


@dataclass(frozen=True)
class ImageInfo:
    """One session image, without its bytes."""

    image_id: str
    filename: str
    content_type: str
    sha256: str
    size: int
    context_text: str | None = None
    source_attachment_id: str | None = None


def new_image_id(existing_ids: Collection[str]) -> str:
    """The next short, per-session image id ("img1", "img2", ...)."""
    n = len(existing_ids) + 1
    while f"img{n}" in existing_ids:
        n += 1
    return f"img{n}"


def new_attachment_id(existing_ids: Collection[str]) -> str:
    """The next short, per-session attachment id ("doc1", "doc2", ...)."""
    n = len(existing_ids) + 1
    while f"doc{n}" in existing_ids:
        n += 1
    return f"doc{n}"


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


# --- Store contract --------------------------------------------------------------


class WordTemplateStore(ABC):
    @abstractmethod
    async def get_session(
        self, session_id: str
    ) -> SessionState | None:  # pragma: no cover - interface
        """The session's template state, with its batch count, or None."""

    @abstractmethod
    async def select_base(
        self, session_id: str, base: BaseRef, writer: Writer, *, expected_count: int
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
    async def put_attachment(
        self, session_id: str, filename: str, sha256: str, content: bytes
    ) -> AttachmentInfo:  # pragma: no cover - interface
        """Store an attached Word file under the next short id, or return
        the one already stored with the same bytes in this session."""

    @abstractmethod
    async def list_attachments(
        self, session_id: str
    ) -> list[AttachmentInfo]:  # pragma: no cover - interface
        """The session's attached Word files, oldest first."""

    @abstractmethod
    async def get_attachment_content(
        self, session_id: str, attachment_id: str
    ) -> bytes | None:  # pragma: no cover - interface
        ...

    @abstractmethod
    async def mark_images_extracted(
        self, session_id: str, attachment_id: str
    ) -> None:  # pragma: no cover - interface
        """Record that the attachment's pictures were copied to the images."""

    @abstractmethod
    async def delete_attachment(
        self, session_id: str, attachment_id: str, *, keep_image_ids: Collection[str]
    ) -> bool:  # pragma: no cover - interface
        """Delete an attached Word file and the pictures taken from it, except
        ``keep_image_ids`` (already placed in the document). False when there
        was no such file."""

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
        source_attachment_id: str | None = None,
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
        attachment_id=row.attachment_id,
    )


def _set_base(row: WordTemplateSession, base: BaseRef) -> None:
    if base.kind == "attachment":
        row.attachment_id = base.ref
    else:
        row.template_key = base.ref
        row.attachment_id = None


def _stamp(row: WordTemplateSession, writer: Writer, now: datetime) -> None:
    row.user_id = writer.user_id
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
    WordTemplateImage.source_attachment_id,
)


def _image_info(row: Any) -> ImageInfo:
    return ImageInfo(
        image_id=row.image_id,
        filename=row.filename,
        content_type=row.content_type,
        sha256=row.sha256,
        size=row.size,
        context_text=row.context_text,
        source_attachment_id=row.source_attachment_id,
    )


class SqlWordTemplateStore(WordTemplateStore):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def _session_row(
        self, session: AsyncSession, session_id: str, writer: Writer, now: datetime
    ) -> WordTemplateSession:
        row = await session.get(WordTemplateSession, session_id)
        if row is None:
            row = WordTemplateSession(session_id=session_id, user_id=writer.user_id)
            session.add(row)
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

    async def select_base(
        self, session_id: str, base: BaseRef, writer: Writer, *, expected_count: int
    ) -> None:
        async with self._sessionmaker() as session, session.begin():
            count = await session.scalar(
                select(func.count()).where(WordTemplateBatch.session_id == session_id)
            )
            if int(count or 0) != expected_count:
                raise BatchConflict(session_id)
            row = await self._session_row(session, session_id, writer, _utcnow())
            _set_base(row, base)

    async def append_batch(
        self,
        session_id: str,
        base: BaseRef,
        operations: Batch,
        writer: Writer,
        *,
        expected_count: int,
        author: BatchAuthor = "model",
    ) -> int:
        try:
            async with self._sessionmaker() as session, session.begin():
                now = _utcnow()
                row = await self._session_row(session, session_id, writer, now)
                if row.pinned_at is None:
                    _set_base(row, base)
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
                row = await session.get(WordTemplateSession, session_id)
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

    async def _attachment_by_sha(
        self, session_id: str, sha256: str
    ) -> AttachmentInfo | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(
                        WordTemplateAttachment.attachment_id,
                        WordTemplateAttachment.filename,
                        WordTemplateAttachment.size,
                        WordTemplateAttachment.images_extracted,
                    ).where(
                        WordTemplateAttachment.session_id == session_id,
                        WordTemplateAttachment.sha256 == sha256,
                    )
                )
            ).first()
            if row is None:
                return None
            return AttachmentInfo(
                row.attachment_id,
                row.filename,
                sha256,
                row.size,
                bool(row.images_extracted),
            )

    async def put_attachment(
        self, session_id: str, filename: str, sha256: str, content: bytes
    ) -> AttachmentInfo:
        # Files attached at once are stored in parallel: two can pick the same
        # short id, or one file can race past the dedup read twice. The unique
        # keys catch both and a retry re-reads.
        for attempt in range(5):
            existing = await self._attachment_by_sha(session_id, sha256)
            if existing is not None:
                return existing
            ids = {a.attachment_id for a in await self.list_attachments(session_id)}
            info = AttachmentInfo(
                new_attachment_id(ids), filename, sha256, len(content)
            )
            try:
                async with self._sessionmaker() as session, session.begin():
                    session.add(
                        WordTemplateAttachment(
                            session_id=session_id,
                            attachment_id=info.attachment_id,
                            filename=filename,
                            sha256=sha256,
                            size=len(content),
                            content=content,
                            created_at=_utcnow(),
                        )
                    )
                return info
            except IntegrityError:
                if attempt == 4:
                    raise
        raise AssertionError("unreachable")  # pragma: no cover

    async def list_attachments(self, session_id: str) -> list[AttachmentInfo]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(
                    WordTemplateAttachment.attachment_id,
                    WordTemplateAttachment.filename,
                    WordTemplateAttachment.sha256,
                    WordTemplateAttachment.size,
                    WordTemplateAttachment.images_extracted,
                )
                .where(WordTemplateAttachment.session_id == session_id)
                .order_by(WordTemplateAttachment.created_at)
            )
            return [
                AttachmentInfo(
                    r.attachment_id,
                    r.filename,
                    r.sha256,
                    r.size,
                    bool(r.images_extracted),
                )
                for r in result.all()
            ]

    async def get_attachment_content(
        self, session_id: str, attachment_id: str
    ) -> bytes | None:
        async with self._sessionmaker() as session:
            row = await session.get(WordTemplateAttachment, (session_id, attachment_id))
            return row.content if row is not None else None

    async def mark_images_extracted(self, session_id: str, attachment_id: str) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(WordTemplateAttachment)
                .where(
                    WordTemplateAttachment.session_id == session_id,
                    WordTemplateAttachment.attachment_id == attachment_id,
                )
                .values(images_extracted=True)
            )

    async def delete_attachment(
        self, session_id: str, attachment_id: str, *, keep_image_ids: Collection[str]
    ) -> bool:
        async with self._sessionmaker() as session, session.begin():
            deleted = await session.execute(
                delete(WordTemplateAttachment).where(
                    WordTemplateAttachment.session_id == session_id,
                    WordTemplateAttachment.attachment_id == attachment_id,
                )
            )
            await session.execute(
                delete(WordTemplateImage).where(
                    WordTemplateImage.session_id == session_id,
                    WordTemplateImage.source_attachment_id == attachment_id,
                    WordTemplateImage.image_id.not_in(list(keep_image_ids)),
                )
            )
            return bool(getattr(deleted, "rowcount", 0))

    async def delete_image(self, session_id: str, image_id: str) -> bool:
        async with self._sessionmaker() as session, session.begin():
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
        source_attachment_id: str | None = None,
    ) -> ImageInfo:
        # Same races as `put_attachment` (parallel uploads, a backfill next
        # to an upload): the unique keys catch them, a retry re-reads.
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
                source_attachment_id=source_attachment_id,
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
                            source_attachment_id=source_attachment_id,
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
