# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Stage immutable inputs and persist preparation intentions with agent saves."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping, Sequence
from uuid import uuid4

from fred_core.store.base_content_store import ContentStore
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
)


@dataclass(frozen=True)
class StagedAsset:
    id: str
    capability_id: str
    slot_key: str
    filename: str
    content_type: str
    sha256: str
    size: int
    object_key: str


async def stage_assets(
    content_store: ContentStore,
    *,
    available: Sequence[CapabilityCatalogEntry],
    selected_ids: Sequence[str],
    uploads: Mapping[str, Sequence[object]],
) -> list[StagedAsset]:
    """Store bounded originals before the SQL transaction; caller cleans on failure."""
    entries = {entry.id: entry for entry in available}
    staged: list[StagedAsset] = []
    try:
        for capability_id, files in uploads.items():
            entry = entries.get(capability_id)
            if capability_id not in selected_ids or entry is None:
                raise ValueError(
                    f"Uploaded files target an unselected capability: {capability_id}"
                )
            spec = entry.preparation
            if spec is None:
                continue
            slots = {slot.key: slot for slot in entry.assets}
            if len(files) > 32:
                raise ValueError("Too many preparation assets")
            total_size = 0
            counts: Counter[str] = Counter()
            for upload in files:
                slot_key = getattr(upload, "slot_key")
                if slot_key not in spec.asset_slots or slot_key not in slots:
                    raise ValueError(f"Undeclared preparation asset slot: {slot_key}")
                content = getattr(upload, "content")
                filename = getattr(upload, "filename")
                content_type = (
                    getattr(upload, "content_type") or "application/octet-stream"
                )
                counts[slot_key] += 1
                slot = slots[slot_key]
                if slot.max_count is not None and counts[slot_key] > slot.max_count:
                    raise ValueError(f"Too many assets for slot: {slot_key}")
                if slot.accepted_types and not any(
                    filename.lower().endswith(extension.lower())
                    for extension in slot.accepted_types
                ):
                    raise ValueError(f"Unsupported file type for slot: {slot_key}")
                total_size += len(content)
                if total_size > spec.max_input_bytes:
                    raise ValueError(
                        "Preparation assets exceed the declared size limit"
                    )
                asset_id = str(uuid4())
                key = f"capability-assets/{asset_id}"
                await asyncio.to_thread(
                    content_store.put_object,
                    key,
                    io.BytesIO(content),
                    content_type=content_type,
                )
                staged.append(
                    StagedAsset(
                        id=asset_id,
                        capability_id=capability_id,
                        slot_key=slot_key,
                        filename=filename[:255],
                        content_type=content_type[:255],
                        sha256=hashlib.sha256(content).hexdigest(),
                        size=len(content),
                        object_key=key,
                    )
                )
        return staged
    except Exception:
        await cleanup_staged_assets(content_store, staged)
        raise


async def cleanup_staged_assets(
    content_store: ContentStore, assets: Sequence[StagedAsset]
) -> None:
    for asset in assets:
        await asyncio.to_thread(content_store.delete_object, asset.object_key)


async def persist_agent_preparations(
    session: AsyncSession,
    *,
    owner_id: str,
    team_id: str,
    runtime_id: str,
    available: Sequence[CapabilityCatalogEntry],
    selected_ids: Sequence[str],
    capability_config: Mapping[str, dict[str, object]],
    staged: Sequence[StagedAsset],
) -> None:
    """Upsert current intentions in the same transaction as the agent revision."""
    current_rows = (
        (
            await session.execute(
                select(CapabilityPreparationRow)
                .where(
                    CapabilityPreparationRow.owner_kind == "agent",
                    CapabilityPreparationRow.owner_id == owner_id,
                    CapabilityPreparationRow.is_current.is_(True),
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    current = {row.capability_id: row for row in current_rows}
    declarations = {
        entry.id: entry.preparation
        for entry in available
        if entry.preparation is not None and entry.id in selected_ids
    }
    for cap_id, row in current.items():
        if cap_id not in declarations:
            row.is_current = False
            if row.state in ("pending", "running"):
                row.state = "obsolete"

    staged_by_capability: dict[str, list[StagedAsset]] = {}
    for asset in staged:
        staged_by_capability.setdefault(asset.capability_id, []).append(asset)
        session.add(
            CapabilityAssetRow(
                id=asset.id,
                owner_kind="agent",
                owner_id=owner_id,
                team_id=team_id,
                runtime_id=runtime_id,
                capability_id=asset.capability_id,
                slot_key=asset.slot_key,
                sha256=asset.sha256,
                filename=asset.filename,
                content_type=asset.content_type,
                size=asset.size,
                object_key=asset.object_key,
                state="stored",
            )
        )
    if staged:
        await session.flush()

    for cap_id, spec in declarations.items():
        assert spec is not None
        previous = current.get(cap_id)
        new_assets = staged_by_capability.get(cap_id, [])
        assets: list[tuple[str, str, str]] = []
        if previous is not None:
            linked = (
                await session.execute(
                    select(CapabilityPreparationAssetRow, CapabilityAssetRow)
                    .join(
                        CapabilityAssetRow,
                        CapabilityPreparationAssetRow.asset_id == CapabilityAssetRow.id,
                    )
                    .where(CapabilityPreparationAssetRow.preparation_id == previous.id)
                    .order_by(CapabilityPreparationAssetRow.position)
                )
            ).all()
            assets = [(asset.id, asset.slot_key, asset.sha256) for _, asset in linked]
        previous_assets = list(assets)
        if new_assets:
            replaced_slots = {asset.slot_key for asset in new_assets}
            assets = [asset for asset in assets if asset[1] not in replaced_slots]
            assets.extend(
                (asset.id, asset.slot_key, asset.sha256) for asset in new_assets
            )
        config = dict(capability_config.get(cap_id, {}).get("config") or {})
        serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > 128 * 1024:
            raise ValueError("Preparation config exceeds 128 KiB")
        if (
            previous is not None
            and previous.rules_version == spec.rules_version
            and previous.config_json == config
            and previous_assets == assets
        ):
            continue
        if previous is not None:
            previous.is_current = False
            if previous.state in ("pending", "running"):
                previous.state = "obsolete"
            await session.flush()
        preparation_id = str(uuid4())
        revision = str(uuid4())
        session.add(
            CapabilityPreparationRow(
                id=preparation_id,
                owner_kind="agent",
                owner_id=owner_id,
                team_id=team_id,
                runtime_id=runtime_id,
                capability_id=cap_id,
                input_revision=revision,
                rules_version=spec.rules_version,
                config_json=config,
                gates_readiness=spec.gates_readiness,
                is_current=True,
                state="pending",
                attempts=0,
                max_attempts=spec.max_attempts,
                deadline_at=utcnow() + timedelta(seconds=spec.timeout_seconds),
                workflow_id=f"capability-preparation/{preparation_id}",
                task_queue=f"capability-preparation-{runtime_id}",
            )
        )
        await session.flush()
        for position, (asset_id, _, _) in enumerate(assets):
            session.add(
                CapabilityPreparationAssetRow(
                    preparation_id=preparation_id,
                    position=position,
                    asset_id=asset_id,
                )
            )
