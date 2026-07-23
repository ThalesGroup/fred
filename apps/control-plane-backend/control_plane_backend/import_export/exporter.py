"""Swift-native snapshot exporter (MIGR-05).

Produces a .zip snapshot of this swift instance's business configuration, in a
format symmetric with the importer (``bundle.py`` / ``importer.py``). The zip is
re-importable through the importer's swift-native branch, enabling the
export → reset → import test cycle.

Zip layout (``source_platform="swift"``)::

    manifest.json
    postgres/agent_instance.jsonl   swift agent_instance rows (all columns)
    postgres/tag.jsonl              swift tag rows
    postgres/metadata.jsonl         swift document metadata rows
    postgres/team_metadata.jsonl    swift team_metadata rows (branding + retention)

Not included (handled by ops / preserved across reset):
- OpenFGA tuples — reset() deletes only Postgres rows, so team ownership
  survives; cross-environment tuple restore is ops Option A (MIGR-04).
- Object-store binaries and vector embeddings — mirrored separately (MIGR-06).
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone

from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.sql.async_session import make_session_factory
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.agent_instance_models import AgentInstanceRow

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1
# This export never writes users.json, but manifest.json's users_schema_version
# is required on every bundle regardless (bundle.py::SnapshotManifest) — declare
# it so a re-import of this exact export never fails on a missing field.
USERS_SCHEMA_VERSION = 1
SOURCE_PLATFORM = "swift"


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _agent_to_dict(row: AgentInstanceRow) -> dict:
    return {
        "agent_instance_id": row.agent_instance_id,
        "team_id": row.team_id,
        "template_id": row.template_id,
        "source_runtime_id": row.source_runtime_id,
        "source_agent_id": row.source_agent_id,
        "display_name": row.display_name,
        "description": row.description,
        "enabled": row.enabled,
        "created_by": row.created_by,
        "tuning_json": row.tuning_json,
        "prompt_refs_json": row.prompt_refs_json,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


def _tag_to_dict(row: TagRow) -> dict:
    return {
        "tag_id": row.tag_id,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
        "owner_id": row.owner_id,
        "name": row.name,
        "path": row.path,
        "description": row.description,
        "type": row.type,
        "doc": row.doc,
    }


def _metadata_to_dict(row: DocumentMetadataRow) -> dict:
    return {
        "document_uid": row.document_uid,
        "source_tag": row.source_tag,
        "date_added_to_kb": _dt(row.date_added_to_kb),
        "tag_ids": list(row.tag_ids) if row.tag_ids else [],
        "doc": row.doc,
    }


def _team_metadata_to_dict(row: TeamMetadataRow) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "joining_mode": row.joining_mode,
        "banner_object_storage_key": row.banner_object_storage_key,
        "max_resources_storage_size": row.max_resources_storage_size,
        "current_resources_storage_size": row.current_resources_storage_size,
        # CTRLP-12 (RFC §3.D): per-team retention travels with branding in the
        # same team_metadata row so team settings survive a platform migration.
        "team_delete_grace": row.team_delete_grace,
        "max_idle": row.max_idle,
        "retention_updated_by": row.retention_updated_by,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


def _jsonl(rows: list[dict]) -> bytes:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode("utf-8")


async def run_export(engine: AsyncEngine) -> bytes:
    """Read the three business tables and return a swift-native snapshot zip."""
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        agents = [
            _agent_to_dict(r)
            for r in (await session.execute(select(AgentInstanceRow))).scalars().all()
        ]
        tags = [
            _tag_to_dict(r)
            for r in (await session.execute(select(TagRow))).scalars().all()
        ]
        metadata = [
            _metadata_to_dict(r)
            for r in (await session.execute(select(DocumentMetadataRow)))
            .scalars()
            .all()
        ]
        team_metadata = [
            _team_metadata_to_dict(r)
            for r in (await session.execute(select(TeamMetadataRow))).scalars().all()
        ]

    manifest = {
        "format_version": FORMAT_VERSION,
        "users_schema_version": USERS_SCHEMA_VERSION,
        "source_platform": SOURCE_PLATFORM,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": {
            "agent_instance": len(agents),
            "tag": len(tags),
            "metadata": len(metadata),
            "team_metadata": len(team_metadata),
        },
        "tuple_count": 0,
        "realm_exported": False,
        # Every exported document's binary is expected to already be mirrored
        # into the target's object store (MIGR-06) — this import never
        # transports content, only declares what it assumes is there.
        "content_keys": [m["document_uid"] for m in metadata],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("postgres/agent_instance.jsonl", _jsonl(agents))
        zf.writestr("postgres/tag.jsonl", _jsonl(tags))
        zf.writestr("postgres/metadata.jsonl", _jsonl(metadata))
        zf.writestr("postgres/team_metadata.jsonl", _jsonl(team_metadata))

    logger.info(
        "[import-export] export: %d agents, %d tags, %d docs, %d teams",
        len(agents),
        len(tags),
        len(metadata),
        len(team_metadata),
    )
    return buffer.getvalue()
