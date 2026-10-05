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

"""Background template analysis (design.md D4). The save records a pending row
in ``cap_ppt_builder_analysis`` and returns; a job on that replica analyses,
labels and stores the result, which every replica reads. A lease the job keeps
alive tells an interrupted job from a slow one."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional, Tuple

from fred_core import convert_office_bytes_to_pdf
from fred_core.common import ThreadSafeLRUCache
from fred_sdk.contracts.capability import CapabilityReadiness
from fred_sdk.contracts.runtime import CapabilityModelPort
from pydantic import BaseModel, ValidationError
from sqlalchemy import (
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from fred_capability_ppt_filler.builder.analysis import (
    ANALYSIS_VERSION,
    analyze_template,
)
from fred_capability_ppt_filler.builder.labelling import label_inventory
from fred_capability_ppt_filler.builder.models import (
    AnalysisSummary,
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
# job then fails instead of looping. A manual re-run starts the count again.
MAX_ATTEMPTS = 3
JOB_TIMEOUT_SECONDS = 20 * 60
# Nobody waits on the job, and a large template's patterns deck exceeds the
# 60 s turn default: without a PDF there are no thumbnails and no vision labels.
PATTERNS_PDF_TIMEOUT_SECONDS = 300.0
_SLOT_POLL_SECONDS = 1.0

RULES_KEY = "rules"
_AGENT_DEFAULT = "agent-default"

RowStatus = Literal["pending", "running", "succeeded", "failed"]
ViewStatus = Literal["pending", "running", "succeeded", "failed", "interrupted"]

_INTERRUPTED_DETAIL = (
    "The template analysis was interrupted. Re-run it from the agent settings."
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
    keys (capability table hygiene)."""

    __tablename__ = "cap_ppt_builder_analysis"

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
    # Kept so a re-run needs no user token to refetch the template.
    template_pptx: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    inventory_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patterns_pdf: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


@dataclass(frozen=True)
class AnalysisRecord:
    """A row without its binaries."""

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

    def matches(self, sha: str, key: str) -> bool:
        return self.template_sha256 == sha and self.labelling_key == key

    def interrupted(self, now: datetime) -> bool:
        return self.status in ("pending", "running") and self.lease_until < now

    def view_status(self, now: datetime) -> ViewStatus:
        return "interrupted" if self.interrupted(now) else self.status

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


# --- Store ---------------------------------------------------------------------------


class AnalysisStore(ABC):
    """Persistence of the analysis rows. Every write after ``start`` names the
    job it comes from and is ignored once another job owns the row."""

    @abstractmethod
    async def get(
        self, instance_id: str, *, with_inventory: bool = True
    ) -> Optional[AnalysisRecord]: ...

    @abstractmethod
    async def template(self, instance_id: str) -> Optional[bytes]: ...

    @abstractmethod
    async def patterns_pdf(self, instance_id: str) -> Optional[bytes]: ...

    @abstractmethod
    async def start(
        self,
        *,
        instance_id: str,
        team_id: str,
        saved_by: Optional[str],
        template_sha256: str,
        labelling_key: str,
        template: Optional[bytes],
    ) -> str:
        """Make the row a fresh pending analysis and return its job id.
        ``template=None`` keeps the stored bytes (a re-run)."""

    @abstractmethod
    async def claim_interrupted(self, instance_id: str) -> Optional[str]:
        """Take over an interrupted analysis with attempts left; one replica wins."""

    @abstractmethod
    async def heartbeat(self, instance_id: str, job_id: str) -> bool: ...

    @abstractmethod
    async def finish(
        self,
        instance_id: str,
        job_id: str,
        inventory: TemplateInventory,
        patterns_pdf: Optional[bytes],
    ) -> bool: ...

    @abstractmethod
    async def fail(self, instance_id: str, job_id: str, error: str) -> bool: ...


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
            row.patterns_pdf.is_not(None),
            row.updated_at,
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
            inventory_json=found[11] if with_inventory else None,
        )

    async def _scalar(self, column: Any, instance_id: str) -> Any:
        async with self._sessionmaker() as session:
            return (
                await session.execute(
                    select(column).where(AnalysisRow.agent_instance_id == instance_id)
                )
            ).scalar_one_or_none()

    async def template(self, instance_id: str) -> Optional[bytes]:
        return await self._scalar(AnalysisRow.template_pptx, instance_id)

    async def patterns_pdf(self, instance_id: str) -> Optional[bytes]:
        return await self._scalar(AnalysisRow.patterns_pdf, instance_id)

    async def _update(self, instance_id: str, *where: Any, **values: Any) -> bool:
        async with self._sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    update(AnalysisRow)
                    .where(AnalysisRow.agent_instance_id == instance_id, *where)
                    .values(updated_at=_utcnow(), **values)
                )
        return bool(getattr(result, "rowcount", 0))

    async def start(
        self,
        *,
        instance_id: str,
        team_id: str,
        saved_by: Optional[str],
        template_sha256: str,
        labelling_key: str,
        template: Optional[bytes],
    ) -> str:
        job_id = str(uuid.uuid4())
        now = _utcnow()
        values: dict[str, Any] = {
            "team_id": team_id,
            "template_sha256": template_sha256,
            "labelling_key": labelling_key,
            "analysis_version": ANALYSIS_VERSION,
            "status": "pending",
            "job_id": job_id,
            "attempts": 1,
            "lease_until": now + timedelta(seconds=LEASE_SECONDS),
            "inventory_json": None,
            "patterns_pdf": None,
            "error": None,
        }
        if saved_by:
            values["saved_by"] = saved_by
        if template is not None:
            values["template_pptx"] = template
        if await self._update(instance_id, **values):
            return job_id
        if template is None:
            raise LookupError(f"No stored template for {instance_id}.")
        try:
            async with self._sessionmaker() as session:
                async with session.begin():
                    session.add(
                        AnalysisRow(
                            **{"saved_by": "unknown", **values},
                            agent_instance_id=instance_id,
                            created_at=now,
                            updated_at=now,
                        )
                    )
        except IntegrityError:  # a concurrent save inserted it first
            await self._update(instance_id, **values)
        return job_id

    async def claim_interrupted(self, instance_id: str) -> Optional[str]:
        job_id = str(uuid.uuid4())
        now = _utcnow()
        claimed = await self._update(
            instance_id,
            AnalysisRow.status.in_(("pending", "running")),
            AnalysisRow.lease_until < now,
            AnalysisRow.attempts < MAX_ATTEMPTS,
            job_id=job_id,
            status="pending",
            attempts=AnalysisRow.attempts + 1,
            lease_until=now + timedelta(seconds=LEASE_SECONDS),
        )
        return job_id if claimed else None

    async def heartbeat(self, instance_id: str, job_id: str) -> bool:
        return await self._update(
            instance_id,
            AnalysisRow.job_id == job_id,
            AnalysisRow.status.in_(("pending", "running")),
            status="running",
            lease_until=_utcnow() + timedelta(seconds=LEASE_SECONDS),
        )

    async def finish(
        self,
        instance_id: str,
        job_id: str,
        inventory: TemplateInventory,
        patterns_pdf: Optional[bytes],
    ) -> bool:
        return await self._update(
            instance_id,
            AnalysisRow.job_id == job_id,
            status="succeeded",
            inventory_json=inventory.model_dump_json(),
            patterns_pdf=patterns_pdf,
            error=None,
        )

    async def fail(self, instance_id: str, job_id: str, error: str) -> bool:
        return await self._update(
            instance_id,
            AnalysisRow.job_id == job_id,
            status="failed",
            error=error[:2000],
        )


# --- Overridable provider (the writable_document pattern) --------------------------

_provider: Callable[[], AnalysisStore] | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_analysis_store() -> AnalysisStore:
    """The analysis store: Postgres from the pod's own config, or a test override."""
    global _sessionmaker
    if _provider is not None:
        return _provider()
    if _sessionmaker is None:
        from fred_core.common import load_postgres_config
        from fred_core.sql import create_async_engine_from_config

        engine = create_async_engine_from_config(load_postgres_config())
        _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return SqlAnalysisStore(_sessionmaker)


def set_store_provider(provider: Callable[[], AnalysisStore]) -> None:
    global _provider
    _provider = provider


def clear_store_provider() -> None:
    global _provider
    _provider = None


# --- Pod-local memory: never a result that only this pod knows ---------------------

# A succeeded row is immutable for its key, so caching it is replica-safe.
_inventories: ThreadSafeLRUCache[Tuple[str, str, str], TemplateInventory] = (
    ThreadSafeLRUCache(max_size=64)
)
# The last save's model port per instance, so a re-run started on this pod can
# label with vision; elsewhere a re-run labels by rules (marked heuristic).
_ports: ThreadSafeLRUCache[str, CapabilityModelPort] = ThreadSafeLRUCache(max_size=256)
_running: set[asyncio.Task[None]] = set()


def remember_port(instance_id: str, port: Optional[CapabilityModelPort]) -> None:
    if port is not None:
        _ports.set(instance_id, port)


def cached_inventory(
    instance_id: str, sha: str, key: str
) -> Optional[TemplateInventory]:
    return _inventories.get((instance_id, sha, key))


def remember_inventory(
    instance_id: str, sha: str, key: str, inventory: TemplateInventory
) -> None:
    _inventories.set((instance_id, sha, key), inventory)


def clear_caches() -> None:
    _inventories.clear()
    _ports.clear()


async def ready_inventory(
    store: AnalysisStore, instance_id: str, sha: str, key: str
) -> Optional[TemplateInventory]:
    """The succeeded analysis for this exact template and labelling, or None."""
    cache_key = (instance_id, sha, key)
    cached = _inventories.get(cache_key)
    if cached is not None:
        return cached
    record = await store.get(instance_id)
    if record is None or not record.matches(sha, key):
        return None
    inventory = record.inventory()
    if inventory is not None:
        _inventories.set(cache_key, inventory)
    return inventory


# --- Job ---------------------------------------------------------------------------


class AnalysisFailed(Exception):
    """A template problem the author can act on; its message is shown."""


async def _cpu(fn: Callable[..., Any], *args: Any) -> Any:
    # A background job waits for a heavy-job slot instead of failing fast:
    # nobody waits on it, and its lease stays alive meanwhile.
    while not acquire_heavy_job_slot():
        await asyncio.sleep(_SLOT_POLL_SECONDS)
    try:
        return await asyncio.to_thread(fn, *args)
    finally:
        release_heavy_job_slot()


async def _analyse(
    template: bytes, port: Optional[CapabilityModelPort], key: str
) -> Tuple[TemplateInventory, Optional[bytes]]:
    result = await _cpu(analyze_template, template)
    if result.inventory is None:
        raise AnalysisFailed(" | ".join(e.message for e in result.errors))
    deck = await _cpu(build_patterns_deck, template, result.inventory)
    pdf = await convert_office_bytes_to_pdf(
        deck, suffix=".pptx", timeout_seconds=PATTERNS_PDF_TIMEOUT_SECONDS
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
    work = asyncio.ensure_future(_analyse(template, port, key))
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
                    "The template analysis took too long. Re-run it, or try a smaller template.",
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
        inventory, pdf = work.result()
    except AnalysisFailed as exc:
        await store.fail(instance_id, job_id, str(exc))
        return
    except Exception:
        logger.exception("Template analysis of %s failed", instance_id)
        await store.fail(
            instance_id,
            job_id,
            "The template analysis stopped on an internal error. Re-run it; if it fails again, "
            "check the template opens in PowerPoint.",
        )
        return
    finally:
        if not work.done():
            work.cancel()
    if await store.finish(instance_id, job_id, inventory, pdf):
        logger.info(
            "Template analysis of %s done in %.0fs",
            instance_id,
            time.monotonic() - started,
        )


def _spawn(coro: Coroutine[Any, Any, None]) -> None:
    # The loop keeps only weak references to tasks: hold each until it ends.
    task = asyncio.get_running_loop().create_task(coro)
    _running.add(task)
    task.add_done_callback(_running.discard)


def spawn_analysis(
    store: AnalysisStore,
    instance_id: str,
    job_id: str,
    template: bytes,
    key: str,
) -> None:
    _spawn(
        run_analysis(store, instance_id, job_id, template, _ports.get(instance_id), key)
    )


async def restart_from_stored(
    store: AnalysisStore,
    record: AnalysisRecord,
    *,
    labelling_key: Optional[str] = None,
) -> None:
    """Re-run the analysis from the template already in the row."""
    template = await store.template(record.agent_instance_id)
    if template is None:
        raise LookupError(f"No stored template for {record.agent_instance_id}.")
    key = labelling_key or record.labelling_key
    job_id = await store.start(
        instance_id=record.agent_instance_id,
        team_id=record.team_id,
        saved_by=None,
        template_sha256=record.template_sha256,
        labelling_key=key,
        template=None,
    )
    spawn_analysis(store, record.agent_instance_id, job_id, template, key)


async def recover_interrupted(store: AnalysisStore, instance_id: str) -> bool:
    """Restart an interrupted analysis if this replica wins the claim."""
    job_id = await store.claim_interrupted(instance_id)
    if job_id is None:
        return False
    template = await store.template(instance_id)
    record = await store.get(instance_id, with_inventory=False)
    if template is None or record is None:
        return False
    logger.info("Restarting interrupted analysis of %s", instance_id)
    spawn_analysis(store, instance_id, job_id, template, record.labelling_key)
    return True


async def analysis_readiness(
    store: AnalysisStore, instance_id: str, sha: str, key: str
) -> CapabilityReadiness:
    """Readiness of the analysis for this template and labelling; restarts an
    interrupted one (bounded by ``MAX_ATTEMPTS``)."""
    record = await store.get(instance_id, with_inventory=False)
    if record is None or not record.matches(sha, key):
        return CapabilityReadiness.failed(_MISSING_DETAIL)
    if record.status == "succeeded":
        return CapabilityReadiness.ready()
    if record.status == "failed":
        return CapabilityReadiness.failed(
            record.error or "The template analysis failed."
        )
    if record.interrupted(_utcnow()):
        if await recover_interrupted(store, instance_id):
            return CapabilityReadiness.pending()
        again = await store.get(instance_id, with_inventory=False)
        if again is None or again.interrupted(_utcnow()):
            return CapabilityReadiness.failed(_INTERRUPTED_DETAIL)
    return CapabilityReadiness.pending()


# --- Status view (form) ------------------------------------------------------------


class AnalysisStatusResponse(BaseModel):
    """What the agent form shows of an instance's analysis."""

    status: ViewStatus
    template_sha256: str
    labelling_key: str
    analysis_version: int
    # False when the rules changed since: the next save re-runs it.
    current: bool
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
        current=record.analysis_version >= ANALYSIS_VERSION,
        error=_INTERRUPTED_DETAIL if status == "interrupted" else record.error,
        updated_at=record.updated_at,
        has_thumbnails=record.has_thumbnails,
        summary=inventory.summary() if inventory else None,
        inventory=inventory,
    )
