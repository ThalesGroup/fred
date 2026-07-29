"""CTRLP-12 (M1): team_metadata survives a platform export → import round-trip.

Team branding and per-team retention live on the same ``team_metadata`` row
(RFC §3.D). This test seeds a team with branding + retention + storage fields in
a source store, exports a swift-native snapshot, imports it into a *fresh* store,
and asserts every column round-trips. It also asserts the import is idempotent:
re-importing over an existing team skips it rather than clobbering live settings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pytest
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.import_export.bundle import open_bundle
from control_plane_backend.import_export.exporter import run_export
from control_plane_backend.import_export.importer import MigrationReport, run_import
from control_plane_backend.models.base import Base as CPBase
from fred_core.models import Base as CoreBase
from fred_core.scheduler import SchedulerBackend
from fred_core.tasks.models import StartMigrationRequest
from fred_core.tasks.service import TaskService
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class _FakeRebac:
    """Minimal `RebacEngine` stand-in — only what the import's #2065
    organization-relation reconciliation phase needs."""

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.ensured_team_ids: list[str] = []

    async def ensure_team_organization_relations(self, team_ids: Iterable[str]) -> None:
        self.ensured_team_ids.extend(team_ids)


def _as_utc(value: datetime) -> datetime:
    """Attach UTC tz to a naive datetime (SQLite drops tzinfo on read)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    """One file-backed SQLite async engine carrying the full control-plane schema."""
    # Import the ORM modules so every table is registered on the two metadatas
    # before create_all runs.
    import control_plane_backend.models.agent_instance_models  # noqa: F401
    import fred_core.tasks.orm_models  # noqa: F401

    db_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(CPBase.metadata.create_all)
    return engine


async def _seed_team(engine: AsyncEngine, row: TeamMetadataRow) -> None:
    from fred_core.sql.async_session import make_session_factory

    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        async with session.begin():
            session.add(row)


async def _import(
    bundle_bytes: bytes, engine: AsyncEngine, *, rebac: Any | None = None
) -> MigrationReport:
    task_service = TaskService.build(engine=engine, backend=SchedulerBackend.MEMORY)
    start = await task_service.start(StartMigrationRequest(), created_by="tester")
    bundle = open_bundle(bundle_bytes)
    return await run_import(
        bundle=bundle,
        import_id="imp-1",
        task_id=start.task_id,
        task_service=task_service,
        engine=engine,
        agent_instance_store=AgentInstanceStore(engine),
        rebac=rebac,
    )


@pytest.mark.asyncio
async def test_team_metadata_round_trips_through_export_import(tmp_path: Path) -> None:
    """description, joining_mode, banner, storage sizes, retention + audit all survive."""
    created = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    updated = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    source = await _make_engine(tmp_path, "source.sqlite3")
    dest = await _make_engine(tmp_path, "dest.sqlite3")
    try:
        await _seed_team(
            source,
            TeamMetadataRow(
                id="team-alpha",
                name="Alpha",
                description="Alpha team space",
                joining_mode="open",
                banner_object_storage_key="teams/team-alpha/banner.png",
                max_resources_storage_size=5_000_000,
                current_resources_storage_size=1_234,
                team_delete_grace="P30D",
                max_idle="P90D",
                retention_updated_by="kc-sub-owner-123",
                created_at=created,
                updated_at=updated,
            ),
        )

        snapshot = await run_export(source)
        report = await _import(snapshot, dest)

        assert report.teams_imported == 1
        assert report.teams_skipped == 0

        from fred_core.sql.async_session import make_session_factory

        async with make_session_factory(dest)() as session:
            imported = (
                await session.execute(
                    select(TeamMetadataRow).where(TeamMetadataRow.id == "team-alpha")
                )
            ).scalar_one()

        assert imported.name == "Alpha"
        assert imported.description == "Alpha team space"
        assert imported.joining_mode == "open"
        assert imported.banner_object_storage_key == "teams/team-alpha/banner.png"
        assert imported.max_resources_storage_size == 5_000_000
        assert imported.current_resources_storage_size == 1_234
        assert imported.team_delete_grace == "P30D"
        assert imported.max_idle == "P90D"
        assert imported.retention_updated_by == "kc-sub-owner-123"
        # SQLite returns naive datetimes; normalise before comparing to the aware
        # originals. The wall-clock value is what must round-trip.
        assert _as_utc(imported.created_at) == created
        assert _as_utc(imported.updated_at) == updated
    finally:
        await source.dispose()
        await dest.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_value", ["request_only", "closed"])
async def test_team_metadata_import_normalizes_legacy_joining_mode(
    tmp_path: Path, legacy_value: str
) -> None:
    """A bundle exported before the 2026-07-26 `JoiningMode` narrowing may still
    carry `request_only`/`closed` literally — importing it must not write a
    value the current 2-state enum rejects on the next read."""
    source = await _make_engine(tmp_path, f"legacy-src-{legacy_value}.sqlite3")
    dest = await _make_engine(tmp_path, f"legacy-dst-{legacy_value}.sqlite3")
    try:
        await _seed_team(
            source,
            TeamMetadataRow(
                id="team-legacy",
                name="Legacy",
                joining_mode=legacy_value,
            ),
        )

        snapshot = await run_export(source)
        report = await _import(snapshot, dest)

        assert report.teams_imported == 1

        from fred_core.sql.async_session import make_session_factory

        async with make_session_factory(dest)() as session:
            imported = (
                await session.execute(
                    select(TeamMetadataRow).where(TeamMetadataRow.id == "team-legacy")
                )
            ).scalar_one()

        assert imported.joining_mode == "invite_only"
    finally:
        await source.dispose()
        await dest.dispose()


@pytest.mark.asyncio
async def test_team_metadata_import_is_idempotent_and_skips_existing(
    tmp_path: Path,
) -> None:
    """Re-importing over an existing team skips it — live settings are preserved."""
    source = await _make_engine(tmp_path, "src2.sqlite3")
    dest = await _make_engine(tmp_path, "dst2.sqlite3")
    try:
        await _seed_team(
            source,
            TeamMetadataRow(
                id="team-beta",
                name="Beta",
                description="Exported description",
                joining_mode="invite_only",
                team_delete_grace="P7D",
            ),
        )
        # dest already holds team-beta with different, live settings.
        await _seed_team(
            dest,
            TeamMetadataRow(
                id="team-beta",
                name="Beta",
                description="Live description",
                joining_mode="open",
                team_delete_grace="P365D",
            ),
        )

        snapshot = await run_export(source)
        report = await _import(snapshot, dest)

        assert report.teams_imported == 0
        assert report.teams_skipped == 1

        from fred_core.sql.async_session import make_session_factory

        async with make_session_factory(dest)() as session:
            row = (
                await session.execute(
                    select(TeamMetadataRow).where(TeamMetadataRow.id == "team-beta")
                )
            ).scalar_one()

        # Unchanged — the existing row won, no clobber.
        assert row.description == "Live description"
        assert row.joining_mode == "open"
        assert row.team_delete_grace == "P365D"
    finally:
        await source.dispose()
        await dest.dispose()


@pytest.mark.asyncio
async def test_team_metadata_import_guarantees_organization_relation(
    tmp_path: Path,
) -> None:
    """#2065: a swift-native import never restores raw OpenFGA tuples (only
    kea bundles do — MIGR-05.04) and `_import_team_metadata` writes
    `TeamMetadataRow`s directly, bypassing `teams.service.create_team`
    (which now writes the organization structural edge itself) entirely.
    The import's own cold-path reconciliation must establish it instead of
    silently leaving a newly-registered team without the invariant."""
    source = await _make_engine(tmp_path, "org-src.sqlite3")
    dest = await _make_engine(tmp_path, "org-dst.sqlite3")
    try:
        await _seed_team(source, TeamMetadataRow(id="team-gamma", name="Gamma"))
        snapshot = await run_export(source)
        rebac = _FakeRebac()

        report = await _import(snapshot, dest, rebac=rebac)

        assert report.teams_imported == 1
        assert rebac.ensured_team_ids == ["team-gamma"]
    finally:
        await source.dispose()
        await dest.dispose()


@pytest.mark.asyncio
async def test_team_metadata_import_warns_when_rebac_unavailable(
    tmp_path: Path,
) -> None:
    """#2065: with no ReBAC engine available (the default `rebac=None` used
    by every other test in this module), the import must not silently skip
    the organization structural relation — it must warn explicitly that the
    invariant was not established and a ReBAC-enabled re-run is required."""
    source = await _make_engine(tmp_path, "warn-src.sqlite3")
    dest = await _make_engine(tmp_path, "warn-dst.sqlite3")
    try:
        await _seed_team(source, TeamMetadataRow(id="team-delta", name="Delta"))
        snapshot = await run_export(source)

        report = await _import(snapshot, dest)

        assert report.teams_imported == 1
        assert any(
            "organization structural relation" in w and "ReBAC" in w
            for w in report.warnings
        )
    finally:
        await source.dispose()
        await dest.dispose()
