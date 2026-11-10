# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""One-shot, restartable PPT preparation backfill from the legacy runtime DB."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from fred_core.common import DEFAULT_POD_SQLITE_PATH, PostgresStoreConfig
from fred_core.filesystem.gcs_filesystem import GcsFilesystem
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_core.filesystem.minio_filesystem import MinioFilesystem
from fred_core.sql import create_async_engine_from_config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from control_plane_backend.app.context import ApplicationContext
from control_plane_backend.capability_preparations.backfill import (
    LEGACY_BUILTIN_ID,
    LegacyPptAnalysis,
    count_unprepared_ppt_agents,
    import_legacy_builtin_overrides,
    import_legacy_ppt_analysis,
)
from control_plane_backend.config.loader import load_configuration

_LEGACY_QUERY = text(
    "SELECT agent_instance_id, team_id, template_sha256, labelling_key, "
    "analysis_version, status, job_id, attempts, template_pptx, inventory_json, "
    "patterns_pdf, error, template_filename, overrides_json, created_at, updated_at "
    "FROM cap_ppt_builder_analysis WHERE agent_instance_id > :cursor "
    "ORDER BY agent_instance_id LIMIT 1"
)


def _runtime_settings(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict) or not isinstance(payload.get("storage"), dict):
        raise ValueError("Runtime configuration has no storage section")
    return payload


async def _artifact_filesystem(settings: dict[str, Any]):
    store = settings["storage"].get("object_store") or {"type": "local"}
    kind = store.get("type", "local")
    if kind == "local":
        return await asyncio.to_thread(
            LocalFilesystem, root=store.get("root", "~/.fred/pod/filesystem")
        )
    if kind == "minio":
        secret = store.get("secret_key") or os.getenv("MINIO_SECRET_KEY")
        if not secret:
            raise ValueError("Runtime MinIO secret is unavailable")
        secure = store.get("secure", False)
        if not isinstance(secure, bool):
            raise ValueError("Runtime MinIO secure must be a boolean")
        return await asyncio.to_thread(
            MinioFilesystem,
            endpoint=store["endpoint"],
            access_key=store["access_key"],
            secret_key=secret,
            bucket_name=store.get("bucket_name", "fred-runtime"),
            secure=secure,
        )
    if kind == "gcs":
        return await asyncio.to_thread(
            GcsFilesystem,
            bucket_name=store["bucket_name"],
            project_id=store.get("project_id"),
        )
    raise ValueError(f"Unsupported runtime object store: {kind}")


async def _run(args: argparse.Namespace) -> Counter[str]:
    os.environ["CONFIG_FILE"] = str(args.control_plane_config)
    if args.control_plane_env:
        os.environ["ENV_FILE"] = str(args.control_plane_env)
    control_plane = (
        ApplicationContext(load_configuration()) if not args.dry_run else None
    )
    runtime = _runtime_settings(args.runtime_config)
    runtime_id = runtime.get("app", {}).get("runtime_id")
    if not isinstance(runtime_id, str) or not runtime_id:
        raise ValueError("Runtime configuration has no app.runtime_id")
    postgres = dict(
        runtime["storage"].get("postgres") or {"sqlite_path": DEFAULT_POD_SQLITE_PATH}
    )
    runtime_password = os.getenv("PPT_BACKFILL_RUNTIME_POSTGRES_PASSWORD")
    if runtime_password:
        postgres["password"] = runtime_password
    runtime_engine = create_async_engine_from_config(
        PostgresStoreConfig.model_validate(postgres)
    )
    artifact_store = await _artifact_filesystem(runtime) if not args.dry_run else None
    cp_engine = control_plane.get_pg_async_engine() if control_plane else None
    sessions = (
        async_sessionmaker(cp_engine, expire_on_commit=False) if cp_engine else None
    )
    runtime_sessions = async_sessionmaker(runtime_engine, expire_on_commit=False)
    counts: Counter[str] = Counter()
    cursor = ""
    try:
        while True:
            async with runtime_sessions() as source:
                item = (
                    (await source.execute(_LEGACY_QUERY, {"cursor": cursor}))
                    .mappings()
                    .first()
                )
            if item is None:
                break
            legacy = LegacyPptAnalysis(**dict(item))
            cursor = legacy.agent_instance_id
            counts["total"] += 1
            if args.dry_run:
                if legacy.agent_instance_id != LEGACY_BUILTIN_ID:
                    if (
                        hashlib.sha256(legacy.template_pptx).hexdigest()
                        != legacy.template_sha256
                    ):
                        raise ValueError(f"Template hash mismatch for {cursor}")
                counts[f"legacy_{legacy.status}"] += 1
                continue
            assert artifact_store is not None
            assert control_plane is not None and sessions is not None
            async with sessions() as destination:
                async with destination.begin():
                    if legacy.agent_instance_id == LEGACY_BUILTIN_ID:
                        await import_legacy_builtin_overrides(
                            destination,
                            runtime_id=runtime_id,
                            overrides_json=legacy.overrides_json,
                        )
                        outcome = "imported_builtin"
                    else:
                        outcome = await import_legacy_ppt_analysis(
                            destination,
                            legacy=legacy,
                            runtime_id=runtime_id,
                            rules_version=args.rules_version,
                            content_store=control_plane.get_content_store(),
                            artifacts=artifact_store,
                        )
            counts[outcome] += 1
        if sessions is not None:
            async with sessions() as destination:
                missing = await count_unprepared_ppt_agents(
                    destination,
                    runtime_id=runtime_id,
                    rules_version=args.rules_version,
                )
            if missing:
                raise ValueError(
                    f"Cutover blocked: {missing} PPT agents have no current preparation"
                )
        return counts
    finally:
        await runtime_engine.dispose()
        if cp_engine is not None:
            await cp_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-plane-config", required=True, type=Path)
    parser.add_argument("--control-plane-env", type=Path)
    parser.add_argument("--runtime-config", required=True, type=Path)
    parser.add_argument("--rules-version", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args)), sort_keys=True))


if __name__ == "__main__":
    main()
