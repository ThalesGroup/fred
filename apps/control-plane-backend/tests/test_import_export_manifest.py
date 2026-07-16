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
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.import_export.bundle import (
    UnsupportedBundleFormatError,
    open_bundle,
)
from control_plane_backend.import_export.exporter import run_export
from control_plane_backend.import_export.importer import MigrationReport, run_import
from control_plane_backend.models.base import Base as CPBase
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


def test_open_bundle_accepts_a_conformant_manifest() -> None:
    data = _minimal_bundle_bytes(
        {
            "format_version": 1,
            "users_schema_version": 1,
            "source_platform": "swift",
            "created_at": "2026-07-16T00:00:00Z",
            "tables": {},
            "tuple_count": 0,
            "realm_exported": False,
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
    import fred_core.tasks.orm_models  # noqa: F401

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
