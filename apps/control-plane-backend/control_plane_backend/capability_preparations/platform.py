# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Atomic active/candidate selection for platform-owned preparations."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from fred_sdk.contracts.capability.preparation import PreparationSpec
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.capability_preparations.admission import StagedAsset
from control_plane_backend.capability_preparations.schemas import PreparationStatus
from control_plane_backend.capability_preparations.service import (
    _assets_by_preparation,
    _status,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPlatformSelectionRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
)


async def _selection(
    session: AsyncSession,
    *,
    runtime_id: str,
    capability_id: str,
    slot_key: str,
) -> CapabilityPlatformSelectionRow:
    await session.execute(
        insert(CapabilityPlatformSelectionRow)
        .values(
            runtime_id=runtime_id,
            capability_id=capability_id,
            slot_key=slot_key,
            settings_json={},
            updated_at=utcnow(),
        )
        .on_conflict_do_nothing()
    )
    row = await session.scalar(
        select(CapabilityPlatformSelectionRow)
        .where(
            CapabilityPlatformSelectionRow.runtime_id == runtime_id,
            CapabilityPlatformSelectionRow.capability_id == capability_id,
            CapabilityPlatformSelectionRow.slot_key == slot_key,
        )
        .with_for_update()
    )
    assert row is not None
    return row


async def start_platform_candidate(
    session: AsyncSession,
    *,
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    spec: PreparationSpec,
    config: dict[str, object],
    staged: StagedAsset,
) -> CapabilityPreparationRow:
    """Keep the effective result while a new revision is prepared."""
    if staged.capability_id != capability_id or staged.slot_key != slot_key:
        raise ValueError("Candidate asset does not match the declared slot")
    serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode()) > 128 * 1024:
        raise ValueError("Preparation config exceeds 128 KiB")
    selection = await _selection(
        session,
        runtime_id=runtime_id,
        capability_id=capability_id,
        slot_key=slot_key,
    )
    if selection.candidate_preparation_id is not None:
        previous = await session.get(
            CapabilityPreparationRow,
            selection.candidate_preparation_id,
            with_for_update=True,
        )
        if previous is not None:
            previous.is_current = False
            previous.superseded_at = utcnow()
            if previous.state in ("pending", "running"):
                previous.state = "obsolete"
    preparation_id = str(uuid4())
    owner_id = f"platform:{preparation_id}"
    session.add(
        CapabilityAssetRow(
            id=staged.id,
            owner_kind="platform",
            owner_id=owner_id,
            team_id=None,
            runtime_id=runtime_id,
            capability_id=capability_id,
            slot_key=slot_key,
            sha256=staged.sha256,
            filename=staged.filename,
            content_type=staged.content_type,
            size=staged.size,
            object_key=staged.object_key,
            state="stored",
        )
    )
    row = CapabilityPreparationRow(
        id=preparation_id,
        owner_kind="platform",
        owner_id=owner_id,
        team_id=None,
        runtime_id=runtime_id,
        capability_id=capability_id,
        input_revision=str(uuid4()),
        rules_version=spec.rules_version,
        config_json=config,
        public_config_json={
            key: config[key] for key in spec.public_config_fields if key in config
        },
        gates_readiness=False,
        is_current=True,
        state="pending",
        attempts=0,
        max_attempts=spec.max_attempts,
        deadline_at=utcnow() + timedelta(seconds=spec.timeout_seconds),
        workflow_id=f"capability-preparation/{preparation_id}",
        task_queue=f"capability-preparation-{runtime_id}",
    )
    session.add(row)
    await session.flush()
    session.add(
        CapabilityPreparationAssetRow(
            preparation_id=preparation_id, position=0, asset_id=staged.id
        )
    )
    selection.candidate_preparation_id = preparation_id
    return row


async def reset_platform_selection(
    session: AsyncSession, *, runtime_id: str, capability_id: str, slot_key: str
) -> None:
    selection = await _selection(
        session,
        runtime_id=runtime_id,
        capability_id=capability_id,
        slot_key=slot_key,
    )
    for preparation_id in (
        selection.active_preparation_id,
        selection.candidate_preparation_id,
    ):
        if preparation_id is None:
            continue
        row = await session.get(
            CapabilityPreparationRow, preparation_id, with_for_update=True
        )
        if row is not None:
            row.is_current = False
            row.superseded_at = utcnow()
            if row.state in ("pending", "running"):
                row.state = "obsolete"
    selection.active_preparation_id = None
    selection.candidate_preparation_id = None
    selection.settings_json = {}


async def platform_selection_status(
    session: AsyncSession, *, runtime_id: str, capability_id: str, slot_key: str
) -> tuple[PreparationStatus | None, PreparationStatus | None, dict[str, Any]]:
    selection = await session.get(
        CapabilityPlatformSelectionRow, (runtime_id, capability_id, slot_key)
    )
    if selection is None:
        return None, None, {}
    ids = [
        preparation_id
        for preparation_id in (
            selection.active_preparation_id,
            selection.candidate_preparation_id,
        )
        if preparation_id is not None
    ]
    rows = {
        row.id: row
        for row in (
            await session.execute(
                select(CapabilityPreparationRow).where(
                    CapabilityPreparationRow.id.in_(ids)
                )
            )
        ).scalars()
    }
    assets = await _assets_by_preparation(session, ids)

    def status(preparation_id: str | None) -> PreparationStatus | None:
        row = rows.get(preparation_id) if preparation_id else None
        return _status(row, assets.get(row.id)) if row is not None else None

    return (
        status(selection.active_preparation_id),
        status(selection.candidate_preparation_id),
        selection.settings_json,
    )


async def retry_platform_candidate(
    session: AsyncSession, *, runtime_id: str, capability_id: str, slot_key: str
) -> CapabilityPreparationRow | None:
    selection = await _selection(
        session,
        runtime_id=runtime_id,
        capability_id=capability_id,
        slot_key=slot_key,
    )
    previous_id = selection.candidate_preparation_id
    if previous_id is None:
        return None
    previous = await session.get(
        CapabilityPreparationRow, previous_id, with_for_update=True
    )
    if previous is None:
        return None
    if previous.state != "failed":
        raise ValueError("Only a failed candidate can be retried")
    linked = (
        (
            await session.execute(
                select(CapabilityPreparationAssetRow)
                .where(CapabilityPreparationAssetRow.preparation_id == previous.id)
                .order_by(CapabilityPreparationAssetRow.position)
            )
        )
        .scalars()
        .all()
    )
    previous.is_current = False
    previous.superseded_at = utcnow()
    await session.flush()
    preparation_id = str(uuid4())
    now = utcnow()
    duration = max(timedelta(seconds=1), previous.deadline_at - previous.created_at)
    row = CapabilityPreparationRow(
        id=preparation_id,
        owner_kind="platform",
        owner_id=f"platform:{preparation_id}",
        team_id=None,
        runtime_id=runtime_id,
        capability_id=capability_id,
        input_revision=str(uuid4()),
        rules_version=previous.rules_version,
        config_json=previous.config_json,
        public_config_json=previous.public_config_json,
        gates_readiness=False,
        is_current=True,
        state="pending",
        attempts=0,
        max_attempts=previous.max_attempts,
        deadline_at=now + duration,
        workflow_id=f"capability-preparation/{preparation_id}",
        task_queue=previous.task_queue,
    )
    session.add(row)
    await session.flush()
    for position, association in enumerate(linked):
        session.add(
            CapabilityPreparationAssetRow(
                preparation_id=preparation_id,
                position=position,
                asset_id=association.asset_id,
            )
        )
    selection.candidate_preparation_id = preparation_id
    return row


async def refresh_platform_candidate(
    session: AsyncSession,
    *,
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    spec: PreparationSpec,
    config: dict[str, object],
) -> CapabilityPreparationRow | None:
    """Reanalyse a stored candidate or active source without removing the active result."""
    selection = await _selection(
        session, runtime_id=runtime_id, capability_id=capability_id, slot_key=slot_key
    )
    source_id = selection.candidate_preparation_id or selection.active_preparation_id
    if source_id is None:
        return None
    source = await session.get(
        CapabilityPreparationRow, source_id, with_for_update=True
    )
    if source is None:
        return None
    if source_id == selection.candidate_preparation_id and source.state in (
        "pending",
        "running",
    ):
        raise ValueError("Candidate preparation is already running")
    if len(json.dumps(config, sort_keys=True).encode()) > 128 * 1024:
        raise ValueError("Preparation config exceeds 128 KiB")
    linked = (
        (
            await session.execute(
                select(CapabilityPreparationAssetRow)
                .where(CapabilityPreparationAssetRow.preparation_id == source.id)
                .order_by(CapabilityPreparationAssetRow.position)
            )
        )
        .scalars()
        .all()
    )
    if source_id == selection.candidate_preparation_id:
        source.is_current = False
        source.superseded_at = utcnow()
    preparation_id = str(uuid4())
    row = CapabilityPreparationRow(
        id=preparation_id,
        owner_kind="platform",
        owner_id=f"platform:{preparation_id}",
        team_id=None,
        runtime_id=runtime_id,
        capability_id=capability_id,
        input_revision=str(uuid4()),
        rules_version=spec.rules_version,
        config_json=config,
        public_config_json={
            key: config[key] for key in spec.public_config_fields if key in config
        },
        gates_readiness=False,
        is_current=True,
        state="pending",
        attempts=0,
        max_attempts=spec.max_attempts,
        deadline_at=utcnow() + timedelta(seconds=spec.timeout_seconds),
        workflow_id=f"capability-preparation/{preparation_id}",
        task_queue=f"capability-preparation-{runtime_id}",
    )
    session.add(row)
    await session.flush()
    for position, association in enumerate(linked):
        session.add(
            CapabilityPreparationAssetRow(
                preparation_id=preparation_id,
                position=position,
                asset_id=association.asset_id,
            )
        )
    selection.candidate_preparation_id = preparation_id
    return row


async def set_platform_selection_settings(
    session: AsyncSession,
    *,
    runtime_id: str,
    capability_id: str,
    slot_key: str,
    settings: dict[str, Any],
) -> None:
    if len(json.dumps(settings, sort_keys=True).encode()) > 128 * 1024:
        raise ValueError("Platform settings exceed 128 KiB")
    selection = await _selection(
        session,
        runtime_id=runtime_id,
        capability_id=capability_id,
        slot_key=slot_key,
    )
    selection.settings_json = settings
