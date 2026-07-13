"""Kea→Swift import service (MIGR-05).

Reads a KBundle and writes the migrated data into the swift control-plane DB.
Emits MigrationTaskEvent progress events so the frontend SSE stream stays live.

All three write phases (agents, tags, metadata) share a single SQLAlchemy
transaction opened against the same AsyncEngine.  Any failure rolls back
everything atomically — no partial state is left behind.

Scope (current snapshot):
- Agents   → agent_instance rows (MAPPED only; IGNORED silently skipped; GAP warned)
- Tags     → tag rows (preserving tag_id, owner_id, doc JSON)
- Metadata → metadata rows (preserving document_uid and doc JSON;
             content/vectors already in S3+OpenSearch via MIGR-06)
- Team metadata → team_metadata rows (branding + per-team retention, CTRLP-12;
             swift-native snapshots only, idempotent skip-if-present)
- MCP servers      → SKIP (re-seeded by deployment on swift)
- Resources/prompts → SKIP (0 rows in current exports)

Pre-conditions handled outside this module (MIGR-04 / MIGR-06):
- Keycloak users already present with the same UUIDs
- OpenFGA tuples already restored (Option A — ops bulk-copy)
- MinIO binaries and embeddings already mirrored
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypeVar

from fred_core.common import TeamId
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.sql.async_session import make_session_factory
from fred_core.tasks.models import MigrationDetail, MigrationTaskEvent, TaskState
from fred_core.tasks.service import TaskService
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.import_export.agent_map import (
    AgentMapOutcome,
    classify_agent,
)
from control_plane_backend.import_export.bundle import KBundle
from control_plane_backend.models.agent_instance_models import AgentInstanceRow

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class MigrationReport:
    import_id: str
    source_platform: str
    agents_imported: int = 0
    agents_skipped: int = 0
    agents_gap: int = 0
    tags_imported: int = 0
    tags_skipped: int = 0
    docs_imported: int = 0
    docs_skipped: int = 0
    teams_imported: int = 0
    teams_skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_dt(value: Any) -> datetime | None:
    """Accept an ISO-8601 string, a datetime, or None — return a datetime/None.

    Swift-native snapshots serialize timestamps as ISO strings; kea snapshots may
    already carry datetimes or None. This normalises both for ORM TIMESTAMP columns.
    """
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _build_agent_team_index(tuples: list[dict[str, Any]]) -> dict[str, str]:
    """Return agent_id → team_id from OpenFGA owner tuples.

    user:UID  owner agent:AID  →  personal-{UID}
    team:TID  owner agent:AID  →  {TID}
    """
    index: dict[str, str] = {}
    for t in tuples:
        obj: str = t.get("object", "")
        user: str = t.get("user", "")
        if t.get("relation") != "owner" or not obj.startswith("agent:"):
            continue
        agent_id = obj.removeprefix("agent:")
        if user.startswith("team:"):
            index[agent_id] = user.removeprefix("team:")
        elif user.startswith("user:"):
            index[agent_id] = f"personal-{user.removeprefix('user:')}"
    return index


_STEP_LABELS: dict[str, str] = {
    "classify": "Classifying agents",
    "agents": "Importing agents",
    "tags": "Importing tags",
    "metadata": "Importing documents",
    "team_metadata": "Importing team settings",
}


async def _emit(
    task_service: TaskService,
    task_id: str,
    state: TaskState,
    step_id: str,
    processed: int,
    total: int,
    failed: int,
    step_override: str | None = None,
) -> None:
    label = step_override or _STEP_LABELS.get(step_id, step_id)
    step_str = f"{label} ({processed}/{total})" if total > 0 else label
    progress = processed / total if total > 0 else None
    await task_service.record(
        MigrationTaskEvent(
            task_id=task_id,
            state=state,
            seq=0,
            timestamp=_utcnow(),
            step=step_str,
            progress=progress,
            detail=MigrationDetail(
                step_id=step_id,
                processed=processed,
                total=total,
                failed=failed,
            ),
        )
    )


async def _run_phase(
    *,
    task_service: TaskService,
    task_id: str,
    step_id: str,
    items: list[T],
    import_fn: Callable[[T, AsyncSession], Awaitable[bool]],
    session: AsyncSession,
) -> tuple[int, int]:
    """Generic import loop — emits SSE progress, returns (imported, skipped).

    import_fn(item, session) must return True if the item was written,
    False if it was skipped (already present or intentionally excluded).
    Any exception propagates and the caller's transaction rolls back.
    """
    total = len(items)
    await _emit(task_service, task_id, TaskState.running, step_id, 0, total, 0)
    imported = skipped = 0
    for item in items:
        written = await import_fn(item, session)
        if written:
            imported += 1
        else:
            skipped += 1
        await _emit(
            task_service,
            task_id,
            TaskState.running,
            step_id,
            imported + skipped,
            total,
            0,
        )
    return imported, skipped


async def run_import(
    *,
    bundle: KBundle,
    import_id: str,
    task_id: str,
    task_service: TaskService,
    engine: AsyncEngine,
    agent_instance_store: AgentInstanceStore,
) -> MigrationReport:
    source_platform = bundle.manifest.source_platform
    report = MigrationReport(
        import_id=import_id,
        source_platform=source_platform,
    )
    is_swift_native = source_platform == "swift"

    # Swift-native snapshots carry full agent_instance rows and team_id directly,
    # so they bypass the kea classification / agent_map translation entirely.
    raw_native_agents: list[dict[str, Any]] = (
        list(bundle.iter_table("agent_instance")) if is_swift_native else []
    )

    tuples = bundle.openfga_tuples()
    agent_team_index = _build_agent_team_index(tuples)

    # ── Phase 1: classify agents (no DB writes) — kea snapshots only ──────────
    raw_agents = [] if is_swift_native else list(bundle.iter_table("agent"))
    await _emit(
        task_service, task_id, TaskState.running, "classify", 0, len(raw_agents), 0
    )

    to_create_agents: list[AgentInstanceRecord] = []

    for row in raw_agents:
        agent_id: str = row["id"]
        payload: dict[str, Any] = row.get("payload_json") or {}
        result = classify_agent(payload)

        if result.outcome == AgentMapOutcome.IGNORED:
            report.agents_skipped += 1
            continue

        if result.outcome == AgentMapOutcome.GAP:
            kea_ref = result.kea_template or "<unknown>"
            report.agents_gap += 1
            report.warnings.append(
                f"agent {agent_id}: no swift template for '{kea_ref}' (GAP — "
                "add to KEA_TO_SWIFT_TEMPLATE in agent_map.py before cutover)"
            )
            continue

        team_id_str = agent_team_index.get(agent_id)
        if team_id_str is None:
            report.warnings.append(
                f"agent {agent_id}: no OpenFGA owner tuple found — skipped"
            )
            report.agents_skipped += 1
            continue

        template_id = result.swift_template_id or ""
        runtime_part, _, agent_part = template_id.partition(":")
        display_name: str = row.get("name") or payload.get("name") or agent_id
        tuning = ManagedAgentTuning(role=display_name, description=display_name)

        to_create_agents.append(
            AgentInstanceRecord(
                agent_instance_id=agent_id,
                team_id=TeamId(team_id_str),
                template_id=template_id,
                source_runtime_id=runtime_part,
                source_agent_id=agent_part,
                display_name=display_name,
                description=None,
                enabled=bool(payload.get("enabled", True)),
                created_by=None,
                tuning=tuning,
            )
        )

    raw_tags = list(bundle.iter_table("tag"))
    raw_metadata = list(bundle.iter_table("metadata"))
    # team_metadata carries per-team branding + retention (CTRLP-12); swift-native
    # snapshots only — kea snapshots omit the table and iter_table yields nothing.
    raw_team_metadata = list(bundle.iter_table("team_metadata"))

    # ── Phases 2–4: all writes in a single atomic transaction ─────────────────
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        async with session.begin():
            # --- agents (kea: mapped records / swift: native rows) ---
            async def _import_agent(
                record: AgentInstanceRecord, s: AsyncSession
            ) -> bool:
                if (
                    await agent_instance_store.get(record.agent_instance_id, session=s)
                    is not None
                ):
                    return False
                await agent_instance_store.create(record, session=s)
                return True

            async def _import_agent_native(
                row: dict[str, Any], s: AsyncSession
            ) -> bool:
                aid = row["agent_instance_id"]
                if await s.get(AgentInstanceRow, aid) is not None:
                    return False
                s.add(
                    AgentInstanceRow(
                        agent_instance_id=aid,
                        team_id=row["team_id"],
                        template_id=row["template_id"],
                        source_runtime_id=row["source_runtime_id"],
                        source_agent_id=row["source_agent_id"],
                        display_name=row["display_name"],
                        description=row.get("description"),
                        enabled=bool(row.get("enabled", True)),
                        created_by=row.get("created_by"),
                        tuning_json=row.get("tuning_json"),
                        prompt_refs_json=row.get("prompt_refs_json"),
                        created_at=_coerce_dt(row.get("created_at")),
                        updated_at=_coerce_dt(row.get("updated_at")),
                    )
                )
                return True

            if is_swift_native:
                ai, as_ = await _run_phase(
                    task_service=task_service,
                    task_id=task_id,
                    step_id="agents",
                    items=raw_native_agents,
                    import_fn=_import_agent_native,
                    session=session,
                )
            else:
                ai, as_ = await _run_phase(
                    task_service=task_service,
                    task_id=task_id,
                    step_id="agents",
                    items=to_create_agents,
                    import_fn=_import_agent,
                    session=session,
                )
            report.agents_imported += ai
            report.agents_skipped += as_

            # --- tags ---
            async def _import_tag(row: dict[str, Any], s: AsyncSession) -> bool:
                tag_id = row["tag_id"]
                if await s.get(TagRow, tag_id) is not None:
                    return False
                s.add(
                    TagRow(
                        tag_id=tag_id,
                        created_at=_coerce_dt(row.get("created_at")),
                        updated_at=_coerce_dt(row.get("updated_at")),
                        owner_id=row.get("owner_id"),
                        name=row.get("name"),
                        path=row.get("path"),
                        description=row.get("description"),
                        type=row.get("type"),
                        doc=row.get("doc"),
                    )
                )
                return True

            report.tags_imported, report.tags_skipped = await _run_phase(
                task_service=task_service,
                task_id=task_id,
                step_id="tags",
                items=raw_tags,
                import_fn=_import_tag,
                session=session,
            )

            # --- document metadata ---
            async def _import_metadata(row: dict[str, Any], s: AsyncSession) -> bool:
                uid = row["document_uid"]
                if await s.get(DocumentMetadataRow, uid) is not None:
                    return False
                s.add(
                    DocumentMetadataRow(
                        document_uid=uid,
                        source_tag=row.get("source_tag"),
                        date_added_to_kb=_coerce_dt(row.get("date_added_to_kb")),
                        tag_ids=row.get("tag_ids") or [],
                        doc=row.get("doc"),
                    )
                )
                return True

            report.docs_imported, report.docs_skipped = await _run_phase(
                task_service=task_service,
                task_id=task_id,
                step_id="metadata",
                items=raw_metadata,
                import_fn=_import_metadata,
                session=session,
            )

            # --- team metadata (branding + retention) ---
            async def _import_team_metadata(
                row: dict[str, Any], s: AsyncSession
            ) -> bool:
                team_id = row["id"]
                # Idempotent, consistent with other phases: skip if the team row
                # already exists so re-importing never clobbers live settings.
                if await s.get(TeamMetadataRow, team_id) is not None:
                    return False
                s.add(
                    TeamMetadataRow(
                        id=team_id,
                        # AUTHZ-05 review item 9: `name` was added after this
                        # bundle format existed. Fall back to the id so an
                        # older export (pre-item-9) still imports cleanly
                        # instead of violating the NOT NULL constraint.
                        name=row.get("name") or team_id,
                        description=row.get("description"),
                        is_private=bool(row.get("is_private", True)),
                        banner_object_storage_key=row.get("banner_object_storage_key"),
                        max_resources_storage_size=row.get(
                            "max_resources_storage_size"
                        ),
                        current_resources_storage_size=row.get(
                            "current_resources_storage_size"
                        )
                        or 0,
                        team_delete_grace=row.get("team_delete_grace"),
                        max_idle=row.get("max_idle"),
                        retention_updated_by=row.get("retention_updated_by"),
                        created_at=_coerce_dt(row.get("created_at")),
                        updated_at=_coerce_dt(row.get("updated_at")),
                    )
                )
                return True

            report.teams_imported, report.teams_skipped = await _run_phase(
                task_service=task_service,
                task_id=task_id,
                step_id="team_metadata",
                items=raw_team_metadata,
                import_fn=_import_team_metadata,
                session=session,
            )

    # ── Non-DB warnings ───────────────────────────────────────────────────────
    if report.warnings:
        logger.warning(
            "[import-export] import %s completed with %d warning(s):\n%s",
            import_id,
            len(report.warnings),
            "\n".join(f"  • {w}" for w in report.warnings),
        )

    summary = (
        ", ".join(
            filter(
                None,
                [
                    f"{report.agents_imported} agents imported"
                    if report.agents_imported
                    else None,
                    f"{report.agents_skipped} agents skipped"
                    if report.agents_skipped
                    else None,
                    f"{report.agents_gap} gaps" if report.agents_gap else None,
                    f"{report.tags_imported} tags" if report.tags_imported else None,
                    f"{report.docs_imported} docs" if report.docs_imported else None,
                    f"{report.teams_imported} teams" if report.teams_imported else None,
                ],
            )
        )
        or "nothing imported"
    )

    await _emit(
        task_service,
        task_id,
        TaskState.running,
        "metadata",
        report.docs_imported,
        report.docs_imported,
        0,
        step_override=summary,
    )

    bundle.close()
    return report
