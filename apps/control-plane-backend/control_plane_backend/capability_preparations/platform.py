# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Atomic active/candidate selection for platform-owned preparations."""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

from fred_sdk.contracts.capability.preparation import PreparationSpec
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.capability_preparations.admission import StagedAsset
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
    CapabilityPlatformSelectionRow,
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
