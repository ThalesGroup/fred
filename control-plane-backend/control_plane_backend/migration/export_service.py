# Copyright Thales 2025
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

"""Builds a kea migration snapshot bundle and stores it in object storage."""

from __future__ import annotations

import io
import json
import logging
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from fred_core import create_keycloak_admin
from fred_core.security.keycloak.keycloack_admin_client import KeycloackDisabled
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.store.base_content_store import ContentStore
from fred_core.store.local_content_store import LocalContentStore
from fred_core.store.minio_content_store import MinioContentStore
from keycloak.exceptions import KeycloakError
from openfga_sdk.models.read_request_tuple_key import ReadRequestTupleKey
from sqlalchemy import text

from control_plane_backend.application_context import (
    ApplicationContext,
    get_configuration,
)
from control_plane_backend.migration.snapshot import (
    EXPORT_TABLES,
    SnapshotManifest,
    SnapshotResponse,
    sanitize_label,
)

logger = logging.getLogger(__name__)

# Where snapshots land in the control-plane content bucket.
_SNAPSHOT_PREFIX = "migration-snapshots"
# How long the returned download link stays valid.
_DOWNLOAD_TTL = timedelta(hours=6)


def _json_default(value: Any) -> Any:
    """Make non-JSON-native DB values serialisable, losslessly where possible."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (bytes, bytearray, memoryview)):
        # Banners/files travel as real objects under content/; raw bytes in a
        # row are unexpected, but never silently drop them.
        import base64

        return {"__bytes_b64__": base64.b64encode(bytes(value)).decode("ascii")}
    raise TypeError(f"Cannot serialise {type(value).__name__} for snapshot")


async def _dump_tables(engine) -> tuple[dict[str, str], dict[str, int], list[str]]:
    """Read every kept table in full.

    Returns (table -> JSONL text, table -> row count, banner storage keys).
    Tables are read with quoted identifiers because ``mcp-server`` contains a
    hyphen. Reflection is unnecessary: ``SELECT *`` plus a type-aware encoder
    captures any column added later without code changes.
    """
    jsonl_by_table: dict[str, str] = {}
    counts: dict[str, int] = {}
    banner_keys: list[str] = []

    async with engine.connect() as conn:
        for table in EXPORT_TABLES:
            # table is a hardcoded constant from EXPORT_TABLES, never user input;
            # identifiers cannot be bound as query parameters.
            query = text(f'SELECT * FROM "{table}"')  # nosec B608
            result = await conn.execute(query)
            rows = result.mappings().all()
            lines = [json.dumps(dict(row), default=_json_default) for row in rows]
            # Trailing newline per row → unambiguous JSONL; empty table → "".
            jsonl_by_table[table] = "".join(f"{line}\n" for line in lines)
            counts[table] = len(rows)
            if table == "teammetadata":
                banner_keys = [
                    row["banner_object_storage_key"]
                    for row in rows
                    if row.get("banner_object_storage_key")
                ]
            logger.info("[SNAPSHOT] dumped %d rows from %s", len(rows), table)

    return jsonl_by_table, counts, banner_keys


async def _dump_tuples() -> list[dict[str, str]]:
    """Read every OpenFGA relationship tuple, unfiltered.

    UUID-only filtering happens at import time, not here. Mirrors the pagination
    used in ``OpenFgaRebacEngine.delete_all_relations_of_reference``.
    """
    engine = ApplicationContext.get_instance().get_rebac_engine()
    if not isinstance(engine, OpenFgaRebacEngine):
        logger.warning(
            "[SNAPSHOT] ReBAC engine is %s, not OpenFGA; skipping tuple export",
            type(engine).__name__,
        )
        return []

    client = await engine.get_client()
    tuples: list[dict[str, str]] = []
    continuation_token: str | None = None
    while continuation_token != "":  # nosec: pagination cursor, not a secret
        # SDK read()/options are loosely typed (a large union); treat as Any.
        options: dict[str, Any] = {}
        if continuation_token:
            options["continuation_token"] = continuation_token
        response: Any = await client.read(ReadRequestTupleKey(), options)
        continuation_token = response.continuation_token
        for tup in response.tuples:
            tuples.append(
                {
                    "user": tup.key.user,
                    "relation": tup.key.relation,
                    "object": tup.key.object,
                }
            )

    logger.info("[SNAPSHOT] dumped %d OpenFGA tuples", len(tuples))
    return tuples


async def _dump_realm() -> dict | None:
    """Export the Keycloak realm (users + groups) via partial-export.

    Best-effort. When source and target share a realm (the co-located kea/swift
    test), the realm needs no migration, and the M2M service account may lack the
    ``manage-realm`` role partial-export requires. Either case degrades to
    ``realm_exported: false`` rather than failing the whole snapshot.
    """
    cfg = get_configuration()
    admin = create_keycloak_admin(cfg.security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.warning("[SNAPSHOT] Keycloak M2M disabled; skipping realm export")
        return None
    try:
        realm = await admin.a_export_realm(
            export_clients=True, export_groups_and_role=True
        )
    except KeycloakError as exc:
        logger.warning(
            "[SNAPSHOT] Keycloak realm export skipped (%s). The M2M service "
            "account likely lacks the 'manage-realm' role; harmless when the "
            "realm is shared between source and target.",
            exc,
        )
        return None
    logger.info("[SNAPSHOT] exported Keycloak realm")
    return realm


def _read_content_object(store: ContentStore, key: str) -> bytes | None:
    """Best-effort read of a content object's bytes for a self-contained bundle.

    ``ContentStore`` has no byte reader, so we branch on the concrete store the
    same way ``application_context`` does when constructing it.
    """
    normalized = key.lstrip("/")
    try:
        if isinstance(store, MinioContentStore):
            response = store.client.get_object(store.object_bucket, normalized)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        if isinstance(store, LocalContentStore):
            return (store.object_root / normalized).read_bytes()
    except Exception:
        logger.warning(
            "[SNAPSHOT] could not read content object %s", key, exc_info=True
        )
        return None
    logger.warning("[SNAPSHOT] unsupported content store %s", type(store).__name__)
    return None


async def build_snapshot(
    label: str | None = None,
) -> tuple[str, bytes, SnapshotManifest]:
    """Build the bundle in memory. Returns (filename, zip_bytes, manifest).

    Storage-agnostic: callers either persist it (``export_kea_snapshot``) or
    stream it straight to the client (the direct-download endpoint, used for
    cross-infrastructure migrations where object storage isn't reachable).
    """
    ctx = ApplicationContext.get_instance()
    created_at = datetime.now(timezone.utc)

    jsonl_by_table, counts, banner_keys = await _dump_tables(ctx.get_pg_async_engine())
    tuples = await _dump_tuples()
    realm = await _dump_realm()

    store = ctx.get_content_store()
    content: dict[str, bytes] = {}
    for key in banner_keys:
        data = _read_content_object(store, key)
        if data is not None:
            content[key] = data

    manifest = SnapshotManifest(
        created_at=created_at.isoformat(),
        tables=counts,
        tuple_count=len(tuples),
        realm_exported=realm is not None,
        content_keys=sorted(content.keys()),
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest.model_dump_json(indent=2))
        for table, jsonl in jsonl_by_table.items():
            archive.writestr(f"postgres/{table}.jsonl", jsonl)
        archive.writestr("openfga/tuples.json", json.dumps(tuples, indent=2))
        if realm is not None:
            archive.writestr(
                "keycloak/realm.json",
                json.dumps(realm, indent=2, default=_json_default),
            )
        for key, data in content.items():
            archive.writestr(f"content/{key.lstrip('/')}", data)

    stamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    slug = sanitize_label(label)
    filename = (
        f"kea-snapshot-{slug}-{stamp}.zip" if slug else f"kea-snapshot-{stamp}.zip"
    )
    return filename, buffer.getvalue(), manifest


async def export_kea_snapshot(label: str | None = None) -> SnapshotResponse:
    """Build a snapshot, store it in object storage, return a presigned link."""
    filename, data, manifest = await build_snapshot(label)
    store = ApplicationContext.get_instance().get_content_store()
    object_key = f"{_SNAPSHOT_PREFIX}/{filename}"
    store.put_object(object_key, io.BytesIO(data), content_type="application/zip")
    download_url = store.get_presigned_url(object_key, expires=_DOWNLOAD_TTL)

    logger.info("[SNAPSHOT] stored bundle at %s (%d bytes)", object_key, len(data))
    return SnapshotResponse(
        object_key=object_key, download_url=download_url, manifest=manifest
    )
