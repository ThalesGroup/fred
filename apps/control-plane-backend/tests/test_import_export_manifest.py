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

"""MIGR-05.13 — swift-native baseline hardening.

Covers the "Canonical contract — swift-native baseline" section of
`PLATFORM-IMPORT-RFC.md`: `SnapshotManifest` is now validated (Pydantic,
`format_version`/`users_schema_version` enforced against a supported set —
no silent default), and the bundle is honest about what it does NOT
transport (`content_keys` populated on export + surfaced as a warning on
import; `VECTORIZED`/`SQL_INDEXED` reset to `NOT_STARTED` on import so a
restored document never claims to be searchable when its embeddings/index
were never restored).
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from control_plane_backend.import_export.bundle import (
    UnsupportedBundleFormatError,
    open_bundle,
)
from control_plane_backend.import_export.exporter import run_export
from control_plane_backend.import_export.importer import MigrationReport, run_import
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.models.task_models import TASK_TABLES
from fred_core.common import TeamId
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.models import Base as CoreBase
from fred_core.scheduler import SchedulerBackend
from fred_core.sql.async_session import make_session_factory
from fred_core.tasks.models import StartMigrationRequest
from fred_core.tasks.service import TaskService
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def _minimal_bundle_bytes(manifest: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
    return buf.getvalue()


def test_open_bundle_rejects_unsupported_format_version() -> None:
    data = _minimal_bundle_bytes(
        {"format_version": 999, "users_schema_version": 1, "source_platform": "swift"}
    )
    with pytest.raises(UnsupportedBundleFormatError):
        open_bundle(data)


def test_open_bundle_rejects_missing_format_version() -> None:
    data = _minimal_bundle_bytes(
        {"users_schema_version": 1, "source_platform": "swift"}
    )
    with pytest.raises(ValidationError):
        open_bundle(data)


def test_open_bundle_rejects_missing_users_schema_version() -> None:
    """No silent default — a bundle producer that forgets this field must fail
    loudly, not be silently treated as schema v1 (the gap a Codex review found
    on PR #1993: users_schema_version used to default to 1 when absent)."""
    data = _minimal_bundle_bytes({"format_version": 1, "source_platform": "swift"})
    with pytest.raises(ValidationError):
        open_bundle(data)


def test_open_bundle_rejects_unsupported_users_schema_version() -> None:
    data = _minimal_bundle_bytes(
        {"format_version": 1, "users_schema_version": 999, "source_platform": "swift"}
    )
    with pytest.raises(UnsupportedBundleFormatError):
        open_bundle(data)


def test_open_bundle_rejects_non_swift_source_platform() -> None:
    """A matching format/schema version is not enough: this importer only ever
    reads Swift table names, so a bundle from anywhere else (or a stale kea
    bundle that happens to share these version numbers) must be rejected here
    rather than silently mis-imported."""
    data = _minimal_bundle_bytes(
        {"format_version": 1, "users_schema_version": 1, "source_platform": "kea"}
    )
    with pytest.raises(UnsupportedBundleFormatError):
        open_bundle(data)


def test_open_bundle_accepts_a_conformant_manifest() -> None:
    data = _minimal_bundle_bytes(
        {
            "format_version": 1,
            "users_schema_version": 1,
            "source_platform": "swift",
            "created_at": "2026-07-16T00:00:00Z",
            "tables": {},
            "content_keys": [],
        }
    )
    bundle = open_bundle(data)
    assert bundle.manifest.format_version == 1
    assert bundle.manifest.source_platform == "swift"
    assert bundle.manifest.users_schema_version == 1


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    # DocumentMetadataRow's table is registered on import via importer.py's own
    # import chain (imported above), so it is present on CoreBase.metadata by
    # the time create_all runs below.
    import control_plane_backend.models.agent_instance_models  # noqa: F401

    db_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(CPBase.metadata.create_all)
    return engine


async def _seed_metadata(engine: AsyncEngine, row: DocumentMetadataRow) -> None:
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        async with session.begin():
            session.add(row)


async def _import(bundle_bytes: bytes, engine: AsyncEngine) -> MigrationReport:
    task_service = TaskService.build(
        engine=engine, tables=TASK_TABLES, backend=SchedulerBackend.MEMORY
    )
    start = await task_service.start(StartMigrationRequest(), created_by="tester")
    bundle = open_bundle(bundle_bytes)
    return await run_import(
        bundle=bundle,
        import_id="imp-1",
        task_id=start.task_id,
        task_service=task_service,
        engine=engine,
    )


@pytest.mark.asyncio
async def test_export_populates_content_keys_and_import_resets_transported_stages(
    tmp_path: Path,
) -> None:
    source = await _make_engine(tmp_path, "source.sqlite3")
    dest = await _make_engine(tmp_path, "dest.sqlite3")
    try:
        await _seed_metadata(
            source,
            DocumentMetadataRow(
                document_uid="doc-1",
                source_tag="uploads",
                date_added_to_kb=datetime(2026, 1, 1, tzinfo=timezone.utc),
                tag_ids=[],
                doc={
                    "processing": {
                        "stages": {"preview": "done", "vector": "done", "sql": "done"},
                        "errors": {},
                    }
                },
            ),
        )

        snapshot = await run_export(source)
        manifest = json.loads(
            zipfile.ZipFile(io.BytesIO(snapshot)).read("manifest.json")
        )
        assert manifest["content_keys"] == ["doc-1"]

        report = await _import(snapshot, dest)

        assert report.docs_imported == 1
        assert any("1 document(s) expect content" in w for w in report.warnings)

        async with make_session_factory(dest)() as session:
            imported = (
                await session.execute(
                    select(DocumentMetadataRow).where(
                        DocumentMetadataRow.document_uid == "doc-1"
                    )
                )
            ).scalar_one()

        assert imported.doc is not None
        stages = imported.doc["processing"]["stages"]
        assert stages["vector"] == "not_started"
        assert stages["sql"] == "not_started"
        assert stages["preview"] == "done"
    finally:
        await source.dispose()
        await dest.dispose()


def _bundle_with_tables(tables: dict[str, list[dict]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format_version": 1,
                    "users_schema_version": 1,
                    "source_platform": "swift",
                    "created_at": "2026-07-16T00:00:00Z",
                    "tables": {name: len(rows) for name, rows in tables.items()},
                    "content_keys": [],
                }
            ),
        )
        for name, rows in tables.items():
            zf.writestr(
                f"postgres/{name}.jsonl", "\n".join(json.dumps(r) for r in rows)
            )
    return buf.getvalue()


def _agent_row(agent_instance_id: str, team_id: str, tuning: dict) -> dict:
    return {
        "agent_instance_id": agent_instance_id,
        "team_id": team_id,
        "template_id": "runtime-a:rico",
        "source_runtime_id": "runtime-a",
        "source_agent_id": "rico",
        "display_name": agent_instance_id,
        "tuning_json": json.dumps(tuning),
    }


async def _tunings(engine: AsyncEngine) -> dict[str, dict]:
    from control_plane_backend.models.agent_instance_models import AgentInstanceRow

    async with make_session_factory(engine)() as session:
        rows = (await session.execute(select(AgentInstanceRow))).scalars().all()
    return {row.agent_instance_id: json.loads(row.tuning_json or "{}") for row in rows}


@pytest.mark.asyncio
async def test_old_bundle_with_retired_reasoning_keys_still_imports(
    tmp_path: Path,
) -> None:
    """Agent tuning carrying the retired per-agent reasoning settings loads,
    with the settings ignored."""

    from control_plane_backend.agent_instances.store import AgentInstanceStore

    dest = await _make_engine(tmp_path, "dest.sqlite3")
    try:
        legacy = {
            "role": "r",
            "description": "d",
            "reasoning_enabled": True,
            "reasoning_default_on": True,
        }
        report = await _import(
            _bundle_with_tables({"agent_instance": [_agent_row("i1", "t", legacy)]}),
            dest,
        )

        assert report.agents_imported == 1
        record = await AgentInstanceStore(dest).get("i1")
        assert record is not None
        assert record.tuning.role == "r"
        assert "reasoning_enabled" not in record.tuning.model_dump()
    finally:
        await dest.dispose()


@pytest.mark.asyncio
async def test_old_bundle_overrides_become_recommendations_of_imported_agents(
    tmp_path: Path,
) -> None:
    """The mapping the importer runs after its phases, inside the import
    transaction. Called directly: on SQLite the task-progress writes of a
    multi-row import contend with the open import transaction."""

    from control_plane_backend.import_export.importer import (
        _map_legacy_template_overrides,
    )
    from control_plane_backend.models.agent_instance_models import AgentInstanceRow

    dest = await _make_engine(tmp_path, "dest.sqlite3")
    try:
        tuning = {"role": "r", "description": "d"}
        async with make_session_factory(dest)() as session:
            async with session.begin():
                for row in (
                    _agent_row("i1", "team-1", tuning),
                    _agent_row(
                        "i2",
                        "team-1",
                        {**tuning, "recommended_chat_profile_id": "chat.q"},
                    ),
                    _agent_row("other-team", "team-2", tuning),
                    _agent_row("pre-existing", "team-1", tuning),
                ):
                    session.add(AgentInstanceRow(**row))
                mapped = await _map_legacy_template_overrides(
                    session,
                    policies=[
                        {
                            "team_id": "team-1",
                            "agent_profile_overrides_json": json.dumps(
                                {"rico": "chat.p"}
                            ),
                        }
                    ],
                    imported_agent_ids={"i1", "i2", "other-team"},
                )

        assert mapped == 1
        tunings = await _tunings(dest)
        assert tunings["i1"]["recommended_chat_profile_id"] == "chat.p"
        assert tunings["i2"]["recommended_chat_profile_id"] == "chat.q"
        assert "recommended_chat_profile_id" not in tunings["other-team"]
        assert "recommended_chat_profile_id" not in tunings["pre-existing"]
    finally:
        await dest.dispose()


@pytest.mark.asyncio
async def test_new_bundle_round_trips_the_team_model_settings(tmp_path: Path) -> None:
    from control_plane_backend.routing_policy.store import TeamRoutingPolicyStore

    source = await _make_engine(tmp_path, "source.sqlite3")
    dest = await _make_engine(tmp_path, "dest.sqlite3")
    try:
        await TeamRoutingPolicyStore(source).upsert(
            team_id=TeamId("team-1"),
            chat_default_profile_id="chat.d",
            disabled_model_ids=["model__b"],
            reasoning_default_off_model_ids=["model__a"],
            updated_by="u1",
        )

        report = await _import(await run_export(source), dest)

        assert report.routing_policies_imported == 1
        assert report.legacy_overrides_mapped == 0
        stored = await TeamRoutingPolicyStore(dest).get(team_id=TeamId("team-1"))
        assert stored is not None
        assert stored.chat_default_profile_id == "chat.d"
        assert stored.disabled_model_ids == ("model__b",)
        assert stored.reasoning_default_off_model_ids == ("model__a",)
    finally:
        await source.dispose()
        await dest.dispose()
