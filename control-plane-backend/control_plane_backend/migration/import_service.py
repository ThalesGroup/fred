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

"""Restores a kea migration snapshot bundle into a (typically empty) kea.

This is the kea -> kea safety path: a faithful round-trip of the export. The
schema is identical, so there is no transformation — only type-faithful upserts
and a diff-based tuple replay. The kea -> swift transform is a separate importer
built later on the swift branch; the UUID-only tuple filter the runbook mentions
belongs there, not here (kea -> kea is a mirror).
"""

from __future__ import annotations

import io
import json
import logging
import mimetypes
import uuid
import zipfile
from datetime import date, datetime
from typing import Any

from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from openfga_sdk.client.models.tuple import ClientTuple
from openfga_sdk.client.models.write_request import ClientWriteRequest
from openfga_sdk.models.read_request_tuple_key import ReadRequestTupleKey
from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import insert as pg_insert

from control_plane_backend.application_context import ApplicationContext
from control_plane_backend.migration.snapshot import (
    BUNDLE_FORMAT_VERSION,
    EXPORT_TABLES,
    ImportReport,
)

logger = logging.getLogger(__name__)

# OpenFGA caps tuples per write request; stay well under it.
_TUPLE_WRITE_BATCH = 90
# Postgres multi-row upsert chunk.
_ROW_UPSERT_BATCH = 500


def _coerce(value: object, python_type: type | None) -> object:
    """Turn a JSON scalar back into the column's Python type where it matters.

    asyncpg needs real ``datetime``/``date``/``UUID`` objects; JSONB, arrays,
    enums, bools and strings round-trip untouched.
    """
    if value is None:
        return None
    if python_type is datetime and isinstance(value, str):
        return datetime.fromisoformat(value)
    if python_type is date and isinstance(value, str):
        return date.fromisoformat(value)
    if python_type is uuid.UUID and isinstance(value, str):
        return uuid.UUID(value)
    return value


async def _restore_postgres(
    engine, bundle: dict[str, list[dict]], report: ImportReport
) -> None:
    """Upsert every table's rows in FK-safe order using reflected schemas."""
    async with engine.begin() as conn:
        meta = MetaData()
        await conn.run_sync(meta.reflect, only=list(EXPORT_TABLES))

        for name in EXPORT_TABLES:
            rows = bundle.get(name, [])
            table = meta.tables.get(name)
            if table is None:
                report.warnings.append(f"target table missing, skipped: {name}")
                continue
            if not rows:
                report.tables[name] = 0
                continue

            # Per-column Python type, to coerce JSON scalars on the way in.
            py_types: dict[str, type | None] = {}
            for col in table.columns:
                try:
                    py_types[col.name] = col.type.python_type
                except Exception:
                    py_types[col.name] = None

            valid_cols = set(table.columns.keys())
            pk_cols = [c.name for c in table.primary_key.columns]
            coerced = [
                {
                    k: _coerce(v, py_types.get(k))
                    for k, v in row.items()
                    if k in valid_cols
                }
                for row in rows
            ]

            upserted = 0
            for start in range(0, len(coerced), _ROW_UPSERT_BATCH):
                chunk = coerced[start : start + _ROW_UPSERT_BATCH]
                stmt = pg_insert(table).values(chunk)
                update_cols = {
                    c.name: stmt.excluded[c.name]
                    for c in table.columns
                    if c.name not in pk_cols
                }
                if update_cols:
                    stmt = stmt.on_conflict_do_update(
                        index_elements=pk_cols, set_=update_cols
                    )
                else:
                    stmt = stmt.on_conflict_do_nothing(index_elements=pk_cols)
                await conn.execute(stmt)
                upserted += len(chunk)

            report.tables[name] = upserted
            logger.info("[IMPORT] upserted %d rows into %s", upserted, name)


async def _read_existing_tuples(client) -> set[tuple[str, str, str]]:
    """Read every tuple currently in the target store (for diff-based writes)."""
    existing: set[tuple[str, str, str]] = set()
    continuation_token: str | None = None
    while continuation_token != "":  # nosec: pagination cursor, not a secret
        # SDK read()/options are loosely typed (a large union); treat as Any.
        options: dict[str, Any] = {}
        if continuation_token:
            options["continuation_token"] = continuation_token
        response: Any = await client.read(ReadRequestTupleKey(), options)
        continuation_token = response.continuation_token
        for tup in response.tuples:
            existing.add((tup.key.user, tup.key.relation, tup.key.object))
    return existing


async def _restore_tuples(bundle_tuples: list[dict], report: ImportReport) -> None:
    """Write the bundle's tuples that are not already present in the store."""
    engine = ApplicationContext.get_instance().get_rebac_engine()
    if not isinstance(engine, OpenFgaRebacEngine):
        report.warnings.append("ReBAC engine is not OpenFGA; tuples skipped")
        return

    client = await engine.get_client()
    existing = await _read_existing_tuples(client)

    to_write: list[ClientTuple] = []
    for t in bundle_tuples:
        key = (t["user"], t["relation"], t["object"])
        if key in existing:
            report.tuples_skipped += 1
            continue
        to_write.append(
            ClientTuple(user=t["user"], relation=t["relation"], object=t["object"])
        )

    write_options: dict[str, Any] = {}
    for start in range(0, len(to_write), _TUPLE_WRITE_BATCH):
        chunk = to_write[start : start + _TUPLE_WRITE_BATCH]
        await client.write(ClientWriteRequest(writes=chunk), write_options)
        report.tuples_written += len(chunk)

    logger.info(
        "[IMPORT] tuples written=%d skipped=%d",
        report.tuples_written,
        report.tuples_skipped,
    )


def _restore_content(archive: zipfile.ZipFile, report: ImportReport) -> None:
    """Restore bundled content objects (e.g. team banners) to the content store."""
    store = ApplicationContext.get_instance().get_content_store()
    for info in archive.infolist():
        if info.is_dir() or not info.filename.startswith("content/"):
            continue
        key = info.filename[len("content/") :]
        if not key:
            continue
        data = archive.read(info.filename)
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        store.put_object(key, io.BytesIO(data), content_type=content_type)
        report.content_restored += 1
    if report.content_restored:
        logger.info("[IMPORT] restored %d content objects", report.content_restored)


async def import_kea_snapshot(zip_bytes: bytes) -> ImportReport:
    """Restore a kea snapshot bundle into the current kea instance."""
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = set(archive.namelist())

    manifest = json.loads(archive.read("manifest.json"))
    report = ImportReport(source_platform=manifest.get("source_platform", "unknown"))
    if manifest.get("format_version") != BUNDLE_FORMAT_VERSION:
        report.warnings.append(
            f"bundle format_version {manifest.get('format_version')} "
            f"!= expected {BUNDLE_FORMAT_VERSION}"
        )
    if report.source_platform != "kea":
        report.warnings.append(
            f"bundle source_platform is '{report.source_platform}', expected 'kea'"
        )

    # Postgres tables.
    bundle: dict[str, list[dict]] = {}
    for name in EXPORT_TABLES:
        entry = f"postgres/{name}.jsonl"
        if entry not in names:
            report.warnings.append(f"missing in bundle: {entry}")
            continue
        text = archive.read(entry).decode("utf-8")
        bundle[name] = [json.loads(line) for line in text.splitlines() if line.strip()]

    ctx = ApplicationContext.get_instance()
    await _restore_postgres(ctx.get_pg_async_engine(), bundle, report)

    # OpenFGA tuples.
    if "openfga/tuples.json" in names:
        tuples = json.loads(archive.read("openfga/tuples.json"))
        await _restore_tuples(tuples, report)
    else:
        report.warnings.append("missing in bundle: openfga/tuples.json")

    # Content (banners). Keycloak realm is intentionally not imported (shared).
    _restore_content(archive, report)

    logger.info("[IMPORT] done: %s", report.model_dump())
    return report
