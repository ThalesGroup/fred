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

"""Background template analysis: the save records a pending row and returns; a job
on that replica analyses, labels and stores the result every replica reads.
A lease the job keeps alive tells an interrupted job from a slow one."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, List, Literal, Optional, Tuple

from fred_core import convert_office_bytes_to_pdf
from fred_core.common import ThreadSafeLRUCache
from fred_sdk.contracts.capability import CapabilityReadiness
from fred_sdk.contracts.capability.preparation import CapabilityObjects
from fred_sdk.contracts.runtime import CapabilityModelPort
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from fred_capability_ppt_filler.builder.analysis import (
    ANALYSIS_VERSION,
    analyze_template,
)
from fred_capability_ppt_filler.builder.labelling import label_inventory
from fred_capability_ppt_filler.builder.models import (
    AnalysisSummary,
    PatternOverride,
    TemplateInventory,
)
from fred_capability_ppt_filler.builder.preview import build_patterns_deck
from fred_capability_ppt_filler.concurrency import (
    acquire_heavy_job_slot,
    release_heavy_job_slot,
)

logger = logging.getLogger(__name__)

LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 30
# Automatic restarts after an interruption; a template that keeps killing the
# job then fails instead of looping. A save that re-runs it starts the count again.
JOB_TIMEOUT_SECONDS = 20 * 60
# Nobody waits on the job, and a large template's patterns deck exceeds the
# 60 s turn default: without a PDF there are no thumbnails and no vision labels.
PATTERNS_PDF_TIMEOUT_SECONDS = 300.0
_SLOT_POLL_SECONDS = 1.0
# Background work takes at most this many of the pod's heavy-job slots: a burst
# of preparations must not leave the turns' builds busy.
MAX_BACKGROUND_SLOTS = 2
# An outdated inventory is served from memory, re-read after this long: its
# refresh may land on another pod, or never (a failed one, no vision port).
OUTDATED_RECHECK_SECONDS = 60.0

RULES_KEY = "rules"
_AGENT_DEFAULT = "agent-default"
# Legacy row identifiers are retained only to reject them as agent identities.
PLATFORM_ID = "__platform__"
PLATFORM_NEXT_ID = "__platform_next__"
BUILTIN_ID = "__builtin__"

RowStatus = Literal["pending", "running", "succeeded", "failed", "retired"]
ViewStatus = Literal["pending", "running", "succeeded", "failed", "interrupted"]

_INTERRUPTED_DETAIL = (
    "The template analysis was interrupted. Save the agent to run it again."
)
_MISSING_DETAIL = (
    "The template analysis was not found. Save the agent again or upload the "
    "template again."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    # SQLite hands timestamps back naive; every stored value is UTC.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def labelling_key(use_vision: bool, profile_id: Optional[str]) -> str:
    """Part of the analysis key: changing the toggle or the model re-runs it."""
    if not use_vision:
        return RULES_KEY
    return f"vision:{profile_id or _AGENT_DEFAULT}"


def parse_labelling_key(key: str) -> Tuple[bool, Optional[str]]:
    """``(use_vision, profile_id)`` of a key built by :func:`labelling_key`."""
    if not key.startswith("vision:"):
        return False, None
    profile = key.removeprefix("vision:")
    return True, (None if profile == _AGENT_DEFAULT else profile)


# --- Owned table -------------------------------------------------------------------


class PptBuilderBase(DeclarativeBase):
    """Isolated declarative base for the ppt_builder capability's table."""


class AnalysisRow(PptBuilderBase):
    """The analysis of one agent instance's current template: one row per
    instance, replaced by the next save that needs a new analysis. No foreign
    keys (capability table hygiene). The files live in the pod's object store,
    each attempt under its own ``<preparation>/<job_id>/``: a key is derived from
    this row's identity, never stored or received."""

    __tablename__ = "cap_ppt_builder_analysis"
    __table_args__ = (
        CheckConstraint(
            "status <> 'succeeded' OR template_digest IS NOT NULL",
            name="cap_ppt_builder_analysis_published_check",
        ),
        CheckConstraint(
            "pending_writes >= 0",
            name="cap_ppt_builder_analysis_pending_writes_check",
        ),
    )

    agent_instance_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(128), nullable=False)
    saved_by: Mapped[str] = mapped_column(String(128), nullable=False)
    template_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    labelling_key: Mapped[str] = mapped_column(String(160), nullable=False)
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # A write from a superseded job matches no row: every update filters on it.
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    inventory_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # A succeeded row publishes the files of its job_id; these prove their bytes.
    template_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    patterns_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Object writes begun and not proven finished. Only their actual return lowers
    # it: a crash or an unknown outcome keeps erasure blocked, durably.
    pending_writes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    template_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # The platform template's pattern edits; an agent's live in its config.
    overrides_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


@dataclass(frozen=True)
class AnalysisRecord:
    """A row's facts, without its files."""

    agent_instance_id: str
    team_id: str
    template_sha256: str
    labelling_key: str
    analysis_version: int
    status: RowStatus
    job_id: str
    attempts: int
    lease_until: datetime
    error: Optional[str]
    has_thumbnails: bool
    updated_at: datetime
    inventory_json: Optional[str] = None
    template_filename: Optional[str] = None
    overrides_json: Optional[str] = None
    saved_by: Optional[str] = None

    def matches(self, sha: str, key: str) -> bool:
        # A vision run without the model port labels and stores `rules`: it
        # serves a vision config until a save, which brings the port, re-runs it.
        return self.template_sha256 == sha and self.labelling_key in (key, RULES_KEY)

    def interrupted(self, now: datetime) -> bool:
        return self.status in ("pending", "running") and self.lease_until < now

    def outdated(self) -> bool:
        return self.status == "succeeded" and self.analysis_version < ANALYSIS_VERSION

    def refreshing(self, now: datetime) -> bool:
        return self.outdated() and self.lease_until >= now

    def view_status(self, now: datetime) -> ViewStatus:
        return (
            "failed"
            if self.status == "retired"
            else ("interrupted" if self.interrupted(now) else self.status)
        )

    def inventory(self) -> Optional[TemplateInventory]:
        if self.status != "succeeded" or not self.inventory_json:
            return None
        try:
            return TemplateInventory.model_validate_json(self.inventory_json)
        except ValidationError:
            logger.warning(
                "Stored analysis of %s no longer validates", self.agent_instance_id
            )
            return None

    def overrides(self) -> List[PatternOverride]:
        return parse_overrides(self.overrides_json)


def parse_overrides(raw: Optional[str]) -> List[PatternOverride]:
    if not raw:
        return []
    try:
        return _OVERRIDES.validate_json(raw)
    except ValidationError:
        logger.warning("Stored platform pattern edits no longer validate")
        return []


def dump_overrides(overrides: List[PatternOverride]) -> Optional[str]:
    return _OVERRIDES.dump_json(overrides).decode() if overrides else None


_OVERRIDES: TypeAdapter[List[PatternOverride]] = TypeAdapter(List[PatternOverride])


# --- Files ---------------------------------------------------------------------------

_TEMPLATE_OBJECT = "template.pptx"
_PATTERNS_OBJECT = "patterns.pdf"
_objects: CapabilityObjects | None = None
# A cancelled caller leaves its write running: it stays referenced until it ends.
_uploads: set[asyncio.Task[None]] = set()


class ObjectStorageUnavailable(RuntimeError):
    """A file could not be stored: an outage Temporal retries, not a template problem."""


class PreparationWritesPending(RuntimeError):
    """An object write has no proven end: erasing now could be undone by it."""


def bind_objects(objects: CapabilityObjects) -> None:
    """The pod's object store for this capability, bound once at process startup."""
    global _objects
    _objects = objects


def _object_store() -> CapabilityObjects:
    if _objects is None:
        raise RuntimeError("ppt_builder: the pod bound no object storage.")
    return _objects


def _directory(instance_id: str) -> str:
    return instance_id.removeprefix("prep:")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _upload_ended(task: asyncio.Task[None]) -> None:
    _uploads.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.warning(
            "Object write outcome unknown; its preparation cannot be erased until resolved",
            extra={"error_code": "ppt_builder_object_write_unknown"},
        )


# --- Store ---------------------------------------------------------------------------


class AnalysisStore(ABC):
    """Persistence of the analysis rows. Every write after ``start`` names the
    job it comes from and is ignored once another job owns the row."""

    @abstractmethod
    async def get(
        self, instance_id: str, *, with_inventory: bool = True
    ) -> Optional[AnalysisRecord]:
        raise NotImplementedError

    @abstractmethod
    async def template(
        self, instance_id: str, *, sha: Optional[str] = None
    ) -> Optional[bytes]:
        """The stored template; with ``sha``, only while the row is that template's."""

    @abstractmethod
    async def patterns_pdf(self, instance_id: str) -> Optional[bytes]:
        raise NotImplementedError

    @abstractmethod
    async def heartbeat(self, instance_id: str, job_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def upload(
        self, instance_id: str, job_id: str, template: bytes, pdf: Optional[bytes]
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Store one attempt's files and return their digests; ``None`` when this
        job no longer owns the row, in which case nothing was written."""

    @abstractmethod
    async def finish(
        self,
        instance_id: str,
        job_id: str,
        inventory: TemplateInventory,
        template_digest: str,
        patterns_digest: Optional[str],
        labelling_key: Optional[str] = None,
    ) -> bool:
        """Publish the result; ``labelling_key``, when given, is the one used."""

    @abstractmethod
    async def fail(self, instance_id: str, job_id: str, error: str) -> bool:
        raise NotImplementedError


class SqlAnalysisStore(AnalysisStore):
    """Async SQLAlchemy store over ``cap_ppt_builder_analysis``."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(
        self, instance_id: str, *, with_inventory: bool = True
    ) -> Optional[AnalysisRecord]:
        row = AnalysisRow
        columns: list[Any] = [
            row.team_id,
            row.template_sha256,
            row.labelling_key,
            row.analysis_version,
            row.status,
            row.job_id,
            row.attempts,
            row.lease_until,
            row.error,
            row.patterns_digest.is_not(None),
            row.updated_at,
            row.template_filename,
            row.overrides_json,
            row.saved_by,
        ]
        if with_inventory:
            columns.append(row.inventory_json)
        async with self._sessionmaker() as session:
            found = (
                await session.execute(
                    select(*columns).where(row.agent_instance_id == instance_id)
                )
            ).first()
        if found is None:
            return None
        return AnalysisRecord(
            agent_instance_id=instance_id,
            team_id=found[0],
            template_sha256=found[1],
            labelling_key=found[2],
            analysis_version=found[3],
            status=found[4],
            job_id=found[5],
            attempts=found[6],
            lease_until=_aware(found[7]),
            error=found[8],
            has_thumbnails=bool(found[9]),
            updated_at=_aware(found[10]),
            template_filename=found[11],
            overrides_json=found[12],
            inventory_json=found[14] if with_inventory else None,
            saved_by=found[13],
        )

    async def _scalar(self, column: Any, instance_id: str, *where: Any) -> Any:
        async with self._sessionmaker() as session:
            return (
                await session.execute(
                    select(column).where(
                        AnalysisRow.agent_instance_id == instance_id, *where
                    )
                )
            ).scalar_one_or_none()

    async def _published(
        self, instance_id: str, name: str, digest: Any, *where: Any
    ) -> Optional[bytes]:
        """A file of the succeeded attempt, verified against SQL; ``None`` when
        there is none, including when retirement erases it during this read."""
        async with self._sessionmaker() as session:
            found = (
                await session.execute(
                    select(AnalysisRow.job_id, digest).where(
                        AnalysisRow.agent_instance_id == instance_id,
                        AnalysisRow.status == "succeeded",
                        *where,
                    )
                )
            ).first()
        if found is None or found[1] is None:
            return None
        try:
            content = await _object_store().read(
                f"{_directory(instance_id)}/{found[0]}/{name}"
            )
        except FileNotFoundError:
            return None
        if await asyncio.to_thread(_digest, content) != found[1]:
            raise RuntimeError(f"Stored {name} does not match its analysis")
        return content

    async def template(
        self, instance_id: str, *, sha: Optional[str] = None
    ) -> Optional[bytes]:
        where = [] if sha is None else [AnalysisRow.template_sha256 == sha]
        return await self._published(
            instance_id, _TEMPLATE_OBJECT, AnalysisRow.template_digest, *where
        )

    async def patterns_pdf(self, instance_id: str) -> Optional[bytes]:
        return await self._published(
            instance_id, _PATTERNS_OBJECT, AnalysisRow.patterns_digest
        )

    async def _update(self, instance_id: str, *where: Any, **values: Any) -> bool:
        async with self._sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    update(AnalysisRow)
                    .where(AnalysisRow.agent_instance_id == instance_id, *where)
                    .values(updated_at=_utcnow(), **values)
                )
        return bool(getattr(result, "rowcount", 0))

    async def heartbeat(self, instance_id: str, job_id: str) -> bool:
        return await self._update(
            instance_id,
            AnalysisRow.job_id == job_id,
            AnalysisRow.status.in_(("pending", "running")),
            status="running",
            lease_until=_utcnow() + timedelta(seconds=LEASE_SECONDS),
        )

    async def upload(
        self, instance_id: str, job_id: str, template: bytes, pdf: Optional[bytes]
    ) -> Optional[Tuple[str, Optional[str]]]:
        objects = _object_store()
        digests = (
            await asyncio.to_thread(_digest, template),
            None if pdf is None else await asyncio.to_thread(_digest, pdf),
        )
        try:
            await objects.check()  # An outage leaves no write of unknown outcome.
        except Exception as exc:
            raise ObjectStorageUnavailable(type(exc).__name__) from None
        # The row lock orders this with retirement: a write begun here is counted
        # before retirement reads the count, and none can begin after it.
        if not await self._update(
            instance_id,
            AnalysisRow.job_id == job_id,
            AnalysisRow.status.in_(("pending", "running")),
            pending_writes=AnalysisRow.pending_writes + 1,
        ):
            return None
        directory = f"{_directory(instance_id)}/{job_id}"

        async def write() -> None:
            await objects.write(f"{directory}/{_TEMPLATE_OBJECT}", template)
            if pdf is not None:
                await objects.write(f"{directory}/{_PATTERNS_OBJECT}", pdf)
            await self._update(
                instance_id, pending_writes=AnalysisRow.pending_writes - 1
            )

        # An SDK call cannot be recalled: only its real end may lower the count.
        task = asyncio.create_task(write())
        _uploads.add(task)
        task.add_done_callback(_upload_ended)
        try:
            await asyncio.shield(task)
        except Exception as exc:
            raise ObjectStorageUnavailable(type(exc).__name__) from None
        return digests

    async def erase_files(self, instance_id: str) -> None:
        """Erase every attempt's files of a row closed to new writes; replayable."""
        if await self._scalar(AnalysisRow.pending_writes, instance_id):
            raise PreparationWritesPending(instance_id)
        await _object_store().delete(_directory(instance_id))

    async def finish(
        self,
        instance_id: str,
        job_id: str,
        inventory: TemplateInventory,
        template_digest: str,
        patterns_digest: Optional[str],
        labelling_key: Optional[str] = None,
    ) -> bool:
        key = {} if labelling_key is None else {"labelling_key": labelling_key}
        values = dict(
            key,
            status="succeeded",
            analysis_version=ANALYSIS_VERSION,
            inventory_json=inventory.model_dump_json(),
            template_digest=template_digest,
            patterns_digest=patterns_digest,
            error=None,
        )
        return await self._update(
            instance_id,
            AnalysisRow.job_id == job_id,
            AnalysisRow.status.in_(("pending", "running")),
            AnalysisRow.lease_until > _utcnow(),
            **values,
        )

    async def fail(self, instance_id: str, job_id: str, error: str) -> bool:
        return await self._update(
            instance_id,
            AnalysisRow.job_id == job_id,
            AnalysisRow.status.in_(("pending", "running")),
            status="failed",
            lease_until=_utcnow(),
            error=error[:2000],
        )


# --- Overridable provider (the writable_document pattern) --------------------------

_provider: Callable[[], AnalysisStore] | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def default_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """One engine per pod for the capability's tables, from the pod's own config."""
    global _sessionmaker
    if _sessionmaker is None:
        from fred_core.common import load_postgres_config
        from fred_core.sql import create_async_engine_from_config

        engine = create_async_engine_from_config(load_postgres_config())
        _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return _sessionmaker


def get_analysis_store() -> AnalysisStore:
    """The analysis store: Postgres from the pod's own config, or a test override."""
    if _provider is not None:
        return _provider()
    return SqlAnalysisStore(default_sessionmaker())


def set_store_provider(provider: Callable[[], AnalysisStore]) -> None:
    global _provider
    _provider = provider


def clear_store_provider() -> None:
    global _provider
    _provider = None


# --- Pod-local memory: never a result that only this pod knows ---------------------

# A current succeeded row is immutable for its key, so caching it is
# replica-safe; an outdated one carries the monotonic time to re-read it.
_inventories: ThreadSafeLRUCache[
    Tuple[str, str, str], Tuple[TemplateInventory, Optional[float]]
] = ThreadSafeLRUCache(max_size=64)
_background_slots = 0
# Template bytes by sha are immutable too; only a few, they are large.
_templates: ThreadSafeLRUCache[str, bytes] = ThreadSafeLRUCache(max_size=4)


def cached_inventory(
    instance_id: str, sha: str, key: str
) -> Optional[TemplateInventory]:
    entry = _inventories.get((instance_id, sha, key))
    if entry is None or (entry[1] is not None and time.monotonic() >= entry[1]):
        return None
    return entry[0]


def remember_inventory(
    instance_id: str,
    sha: str,
    key: str,
    inventory: TemplateInventory,
    *,
    outdated: bool = False,
) -> None:
    recheck = time.monotonic() + OUTDATED_RECHECK_SECONDS if outdated else None
    _inventories.set((instance_id, sha, key), (inventory, recheck))


def forget_inventories(instance_id: str) -> None:
    for cache_key in _inventories.keys():
        if cache_key[0] == instance_id:
            _inventories.delete(cache_key)


def clear_caches() -> None:
    _inventories.clear()
    _templates.clear()


async def analysed_template(instance_id: str, sha: str) -> bytes:
    """The template the analysis of ``sha`` was made on, never a newer upload
    that replaced it (the row's sha and bytes are written together)."""
    content = _templates.get(sha)
    if content is None:
        content = await get_analysis_store().template(instance_id, sha=sha)
        if content is None:
            raise LookupError(f"{instance_id} no longer stores template {sha}.")
        _templates.set(sha, content)
    return content


async def ready_inventory(
    store: AnalysisStore, instance_id: str, sha: str, key: str
) -> Optional[TemplateInventory]:
    """The succeeded analysis for this exact template and labelling, or None.
    An outdated one is still served, and re-read now and then for its refresh."""
    cached = cached_inventory(instance_id, sha, key)
    if cached is not None:
        return cached
    record = await store.get(instance_id)
    if record is None or not record.matches(sha, key):
        return None
    inventory = record.inventory()
    if inventory is None:
        return None
    # A rules row serving a vision key is re-read too: another replica's save re-runs it.
    stand_in = record.labelling_key != key
    remember_inventory(
        instance_id, sha, key, inventory, outdated=record.outdated() or stand_in
    )
    return inventory


# --- Job ---------------------------------------------------------------------------


class AnalysisFailed(Exception):
    """A template problem the author can act on; its message is shown."""


async def _cpu(fn: Callable[..., Any], *args: Any) -> Any:
    # A background job waits for a heavy-job slot instead of failing fast:
    # nobody waits on it, and its lease stays alive meanwhile.
    global _background_slots
    while _background_slots >= MAX_BACKGROUND_SLOTS or not acquire_heavy_job_slot():
        await asyncio.sleep(_SLOT_POLL_SECONDS)
    _background_slots += 1
    work = asyncio.ensure_future(asyncio.to_thread(fn, *args))
    # A cancelled job's thread runs on: the slot is freed when it really ends.
    work.add_done_callback(_thread_ended)
    return await asyncio.shield(work)


def _thread_ended(work: asyncio.Future[Any]) -> None:
    global _background_slots
    _background_slots -= 1
    release_heavy_job_slot()
    if not work.cancelled():
        work.exception()  # retrieved: an abandoned thread's error is not re-logged


async def _analyse(
    template: bytes, port: Optional[CapabilityModelPort], key: str
) -> Tuple[TemplateInventory, Optional[bytes]]:
    result = await _cpu(analyze_template, template)
    if result.inventory is None:
        raise AnalysisFailed(" | ".join(e.message for e in result.errors))
    deck = await _cpu(build_patterns_deck, template, result.inventory)
    pdf = await convert_office_bytes_to_pdf(
        deck,
        suffix=".pptx",
        timeout_seconds=PATTERNS_PDF_TIMEOUT_SECONDS,
        background=True,
    )
    use_vision, profile_id = parse_labelling_key(key)
    inventory = await label_inventory(
        result.inventory,
        template,
        pdf,
        port,
        profile_id=profile_id,
        use_vision=use_vision,
    )
    return inventory, pdf


async def _analyse_and_upload(
    store: AnalysisStore,
    instance_id: str,
    job_id: str,
    template: bytes,
    port: Optional[CapabilityModelPort],
    key: str,
) -> Tuple[TemplateInventory, Optional[Tuple[str, Optional[str]]]]:
    inventory, pdf = await _analyse(template, port, key)
    return inventory, await store.upload(instance_id, job_id, template, pdf)


async def run_analysis(
    store: AnalysisStore,
    instance_id: str,
    job_id: str,
    template: bytes,
    port: Optional[CapabilityModelPort],
    key: str,
) -> None:
    """Run one analysis job to its single result write, heartbeating its lease."""
    started = time.monotonic()
    if not await store.heartbeat(instance_id, job_id):
        return  # superseded before it started
    if port is None and key != RULES_KEY:
        logger.warning(
            "Analysis of %s labels by rules: no model port for %s on this pod",
            instance_id,
            key,
        )
        key = RULES_KEY  # what the labels really are: a save with the port re-runs
    work = asyncio.ensure_future(
        _analyse_and_upload(store, instance_id, job_id, template, port, key)
    )
    try:
        while True:
            done, _ = await asyncio.wait({work}, timeout=HEARTBEAT_SECONDS)
            if done:
                break
            if time.monotonic() - started > JOB_TIMEOUT_SECONDS:
                work.cancel()
                await store.fail(
                    instance_id,
                    job_id,
                    "The template analysis took too long. Save the agent to run it again, or try a smaller template.",
                )
                return
            try:
                alive = await store.heartbeat(instance_id, job_id)
            except Exception:  # a DB blip costs one beat, the lease covers it
                logger.warning("Analysis heartbeat failed", exc_info=True)
                continue
            if not alive:
                logger.info("Analysis of %s superseded", instance_id)
                work.cancel()
                return
        inventory, digests = work.result()
    except AnalysisFailed as exc:
        await store.fail(instance_id, job_id, str(exc))
        return
    except ObjectStorageUnavailable:
        raise  # Temporal retries as a new attempt: the template is not at fault.
    except Exception:
        logger.exception("Template analysis of %s failed", instance_id)
        await store.fail(
            instance_id,
            job_id,
            "The template analysis stopped on an internal error. Save the agent to run it again; if it fails again, "
            "check the template opens in PowerPoint.",
        )
        return
    finally:
        if not work.done():
            work.cancel()
    if digests is None:
        logger.info("Analysis of %s superseded", instance_id)
        return
    if await store.finish(instance_id, job_id, inventory, *digests, key):
        forget_inventories(instance_id)
        logger.info(
            "Template analysis of %s done in %.0fs",
            instance_id,
            time.monotonic() - started,
        )


async def analysis_readiness(
    store: AnalysisStore, instance_id: str, sha: str, key: str
) -> CapabilityReadiness:
    """Consult only. Temporal owns retries independently of list/form reads."""
    record = await store.get(instance_id, with_inventory=False)
    if record is None or not record.matches(sha, key):
        return CapabilityReadiness.failed(_MISSING_DETAIL)
    if record.status == "succeeded":
        return CapabilityReadiness.ready()
    if record.status in ("failed", "retired"):
        return CapabilityReadiness.failed(
            record.error or "The template analysis failed."
        )
    return CapabilityReadiness.pending()


# --- Status view (form) ------------------------------------------------------------


class AnalysisStatusResponse(BaseModel):
    """What the agent form shows of an instance's analysis."""

    status: ViewStatus
    template_sha256: str
    labelling_key: str
    analysis_version: int
    # False when the rules changed since and no refresh is running: worth a re-run.
    current: bool
    # An outdated one being refreshed: its old inventory is shown until it ends.
    refreshing: bool = False
    error: Optional[str] = None
    updated_at: datetime
    has_thumbnails: bool = False
    summary: Optional[AnalysisSummary] = None
    inventory: Optional[TemplateInventory] = None


def status_response(record: AnalysisRecord) -> AnalysisStatusResponse:
    now = _utcnow()
    status = record.view_status(now)
    inventory = record.inventory()
    return AnalysisStatusResponse(
        status=status,
        template_sha256=record.template_sha256,
        labelling_key=record.labelling_key,
        analysis_version=record.analysis_version,
        current=not record.outdated() or record.refreshing(now),
        refreshing=record.refreshing(now),
        error=_INTERRUPTED_DETAIL if status == "interrupted" else record.error,
        updated_at=record.updated_at,
        has_thumbnails=record.has_thumbnails,
        summary=inventory.summary() if inventory else None,
        inventory=inventory,
    )
