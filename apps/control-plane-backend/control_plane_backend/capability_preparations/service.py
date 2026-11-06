# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Scoped reads and retry for durable capability preparations."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from fred_core.store.base_content_store import ContentStore
from fred_sdk.contracts.capability.preparation import PreparationAsset, PreparationWork
from pydantic import JsonValue
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.capability_preparations.schemas import (
    CleanupLease,
    PreparationStatus,
    PreparationStatusPage,
    WorkerPreparationResult,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPlatformSelectionRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
)


def _status(
    row: CapabilityPreparationRow, assets: list[PreparationAsset] | None = None
) -> PreparationStatus:
    return PreparationStatus(
        capability_id=row.capability_id,
        preparation_id=row.id,
        state=cast(Literal["pending", "running", "succeeded", "failed"], row.state),
        input_revision=row.input_revision,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        gates_readiness=row.gates_readiness,
        created_at=row.created_at,
        completed_at=row.completed_at,
        summary=row.result_summary,
        error_code=row.error_code,
        error_detail=row.error_detail,
        result_reference=row.result_reference,
        assets=assets or [],
        public_config=row.public_config_json,
    )


async def _assets_by_preparation(
    session: AsyncSession, preparation_ids: list[str]
) -> dict[str, list[PreparationAsset]]:
    if not preparation_ids:
        return {}
    linked = (
        await session.execute(
            select(CapabilityPreparationAssetRow.preparation_id, CapabilityAssetRow)
            .join(
                CapabilityAssetRow,
                CapabilityPreparationAssetRow.asset_id == CapabilityAssetRow.id,
            )
            .where(CapabilityPreparationAssetRow.preparation_id.in_(preparation_ids))
            .order_by(
                CapabilityPreparationAssetRow.preparation_id,
                CapabilityPreparationAssetRow.position,
            )
        )
    ).all()
    result: dict[str, list[PreparationAsset]] = {}
    for preparation_id, asset in linked:
        result.setdefault(preparation_id, []).append(
            PreparationAsset(
                asset_id=UUID(asset.id),
                slot_key=asset.slot_key,
                filename=asset.filename,
                sha256=asset.sha256,
                size=asset.size,
            )
        )
    return result


async def list_agent_preparations(
    session: AsyncSession,
    *,
    agent_instance_id: str,
    team_id: str,
    limit: int,
    offset: int,
) -> PreparationStatusPage:
    rows = (
        (
            await session.execute(
                select(CapabilityPreparationRow)
                .where(
                    CapabilityPreparationRow.owner_kind == "agent",
                    CapabilityPreparationRow.owner_id == agent_instance_id,
                    CapabilityPreparationRow.team_id == team_id,
                    CapabilityPreparationRow.is_current.is_(True),
                )
                .order_by(CapabilityPreparationRow.capability_id)
                .limit(limit + 1)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    visible = rows[:limit]
    assets = await _assets_by_preparation(session, [row.id for row in visible])
    return PreparationStatusPage(
        items=[_status(row, assets.get(row.id)) for row in visible],
        has_more=len(rows) > limit,
    )


async def retry_agent_preparation(
    session: AsyncSession,
    *,
    agent_instance_id: str,
    team_id: str,
    capability_id: str,
) -> PreparationStatus | None:
    previous = (
        await session.execute(
            select(CapabilityPreparationRow)
            .where(
                CapabilityPreparationRow.owner_kind == "agent",
                CapabilityPreparationRow.owner_id == agent_instance_id,
                CapabilityPreparationRow.team_id == team_id,
                CapabilityPreparationRow.capability_id == capability_id,
                CapabilityPreparationRow.is_current.is_(True),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if previous is None:
        return None
    if previous.state != "failed":
        raise ValueError("Only a failed preparation can be retried")
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
    now = utcnow()
    preparation_id = str(uuid4())
    duration = max(timedelta(seconds=1), previous.deadline_at - previous.created_at)
    row = CapabilityPreparationRow(
        id=preparation_id,
        owner_kind="agent",
        owner_id=agent_instance_id,
        team_id=team_id,
        runtime_id=previous.runtime_id,
        capability_id=capability_id,
        input_revision=str(uuid4()),
        rules_version=previous.rules_version,
        config_json=previous.config_json,
        public_config_json=previous.public_config_json,
        gates_readiness=previous.gates_readiness,
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
    assets = await _assets_by_preparation(session, [row.id])
    return _status(row, assets.get(row.id))


async def get_worker_work(
    session: AsyncSession, preparation_id: str
) -> PreparationWork | None:
    row = await session.get(CapabilityPreparationRow, preparation_id)
    if row is None or not row.is_current or row.state != "running":
        return None
    linked = (
        (
            await session.execute(
                select(CapabilityAssetRow)
                .join(
                    CapabilityPreparationAssetRow,
                    CapabilityPreparationAssetRow.asset_id == CapabilityAssetRow.id,
                )
                .where(CapabilityPreparationAssetRow.preparation_id == preparation_id)
                .order_by(CapabilityPreparationAssetRow.position)
            )
        )
        .scalars()
        .all()
    )
    return PreparationWork(
        preparation_id=UUID(row.id),
        owner_kind=cast(Literal["agent", "platform"], row.owner_kind),
        owner_id=row.owner_id,
        runtime_id=row.runtime_id,
        capability_id=row.capability_id,
        input_revision=row.input_revision,
        rules_version=row.rules_version,
        attempt=row.attempts,
        max_attempts=row.max_attempts,
        assets=tuple(
            PreparationAsset(
                asset_id=UUID(asset.id),
                slot_key=asset.slot_key,
                filename=asset.filename,
                sha256=asset.sha256,
                size=asset.size,
            )
            for asset in linked
        ),
        config=cast(dict[str, JsonValue], row.config_json),
    )


async def current_agent_results(
    session: AsyncSession,
    *,
    agent_instance_id: str,
    team_id: str,
) -> dict[str, str]:
    """Return only published references from the current agent revisions."""
    rows = (
        await session.execute(
            select(
                CapabilityPreparationRow.capability_id,
                CapabilityPreparationRow.result_reference,
            ).where(
                CapabilityPreparationRow.owner_kind == "agent",
                CapabilityPreparationRow.owner_id == agent_instance_id,
                CapabilityPreparationRow.team_id == team_id,
                CapabilityPreparationRow.is_current.is_(True),
                CapabilityPreparationRow.state == "succeeded",
                CapabilityPreparationRow.result_reference.is_not(None),
            )
        )
    ).all()
    return {capability_id: reference for capability_id, reference in rows if reference}


async def current_platform_results(
    session: AsyncSession, *, runtime_id: str
) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    selections = (
        (
            await session.execute(
                select(CapabilityPlatformSelectionRow).where(
                    CapabilityPlatformSelectionRow.runtime_id == runtime_id
                )
            )
        )
        .scalars()
        .all()
    )
    active_ids = [
        selection.active_preparation_id
        for selection in selections
        if selection.active_preparation_id is not None
    ]
    active_rows = {
        row.id: row
        for row in (
            await session.execute(
                select(CapabilityPreparationRow).where(
                    CapabilityPreparationRow.id.in_(active_ids),
                    CapabilityPreparationRow.is_current.is_(True),
                    CapabilityPreparationRow.state == "succeeded",
                )
            )
        ).scalars()
    }
    results = {}
    settings = {}
    for selection in selections:
        key = f"{selection.capability_id}:platform:{selection.slot_key}"
        row = (
            active_rows.get(selection.active_preparation_id)
            if selection.active_preparation_id is not None
            else None
        )
        if row is not None and row.result_reference:
            results[key] = row.result_reference
        if selection.settings_json:
            settings[key] = selection.settings_json
    return results, settings


async def get_work_asset(
    session: AsyncSession, *, preparation_id: str, asset_id: str
) -> CapabilityAssetRow | None:
    row = await session.get(CapabilityPreparationRow, preparation_id)
    if row is None or not row.is_current or row.state != "running":
        return None
    return (
        await session.execute(
            select(CapabilityAssetRow)
            .join(
                CapabilityPreparationAssetRow,
                CapabilityPreparationAssetRow.asset_id == CapabilityAssetRow.id,
            )
            .where(
                CapabilityPreparationAssetRow.preparation_id == preparation_id,
                CapabilityAssetRow.id == asset_id,
                CapabilityAssetRow.state == "stored",
            )
        )
    ).scalar_one_or_none()


async def begin_worker_attempt(
    session: AsyncSession, *, preparation_id: str, attempt: int
) -> PreparationWork | None:
    row = (
        await session.execute(
            select(CapabilityPreparationRow)
            .where(CapabilityPreparationRow.id == preparation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or not row.is_current or row.state != "running":
        return None
    if attempt < row.attempts:
        return None
    if attempt > row.max_attempts or utcnow() >= row.deadline_at:
        row.state = "failed"
        row.error_code = "preparation_attempts_exhausted"
        row.completed_at = utcnow()
        return None
    row.attempts = attempt
    await session.flush()
    return await get_worker_work(session, preparation_id)


async def publish_worker_result(
    session: AsyncSession,
    *,
    preparation_id: str,
    completion: WorkerPreparationResult,
) -> bool:
    candidate = await session.get(CapabilityPreparationRow, preparation_id)
    selection = None
    if candidate is not None and candidate.owner_kind == "platform":
        selection = (
            await session.execute(
                select(CapabilityPlatformSelectionRow)
                .where(
                    CapabilityPlatformSelectionRow.candidate_preparation_id
                    == preparation_id
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
    row = (
        await session.execute(
            select(CapabilityPreparationRow)
            .where(CapabilityPreparationRow.id == preparation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if (
        row is None
        or not row.is_current
        or row.state != "running"
        or row.input_revision != completion.input_revision
        or row.attempts != completion.attempt
        or (row.owner_kind == "platform" and selection is None)
    ):
        return False
    if completion.state == "succeeded":
        assert completion.result is not None
        expected_prefix = f"capability-results/{preparation_id}/{completion.attempt}/"
        if not completion.result.reference.startswith(expected_prefix):
            raise ValueError("Result reference is outside the preparation attempt")
        row.result_reference = completion.result.reference
        row.result_summary = completion.result.summary
    else:
        row.error_code = completion.error_code
        row.error_detail = completion.error_detail
    row.state = completion.state
    row.completed_at = utcnow()
    if selection is not None and completion.state == "succeeded":
        if selection.active_preparation_id is not None:
            old_assets = await _assets_by_preparation(
                session, [selection.active_preparation_id, row.id]
            )
            old_hashes = [
                asset.sha256
                for asset in old_assets.get(selection.active_preparation_id, [])
            ]
            new_hashes = [asset.sha256 for asset in old_assets.get(row.id, [])]
            if old_hashes != new_hashes:
                selection.settings_json = {}
            previous = await session.get(
                CapabilityPreparationRow,
                selection.active_preparation_id,
                with_for_update=True,
            )
            if previous is not None:
                previous.is_current = False
                previous.superseded_at = utcnow()
        selection.active_preparation_id = row.id
        selection.candidate_preparation_id = None
    return True


async def retire_agent_preparations(
    session: AsyncSession, *, team_id: str, agent_instance_ids: list[str]
) -> None:
    """Fence every in-flight result in the agent deletion transaction."""
    if not agent_instance_ids:
        return
    for start in range(0, len(agent_instance_ids), 500):
        await session.execute(
            update(CapabilityPreparationRow)
            .where(
                CapabilityPreparationRow.owner_kind == "agent",
                CapabilityPreparationRow.team_id == team_id,
                CapabilityPreparationRow.owner_id.in_(
                    agent_instance_ids[start : start + 500]
                ),
                CapabilityPreparationRow.is_current.is_(True),
            )
            .values(
                is_current=False,
                state="obsolete",
                superseded_at=utcnow(),
                updated_at=utcnow(),
            )
        )


async def claim_cleanup(
    session: AsyncSession, *, runtime_id: str, limit: int = 8
) -> list[CleanupLease]:
    """Lease old revisions after turns and worker attempts have aged out."""
    now = utcnow()
    rows = (
        (
            await session.execute(
                select(CapabilityPreparationRow)
                .where(
                    CapabilityPreparationRow.runtime_id == runtime_id,
                    CapabilityPreparationRow.is_current.is_(False),
                    CapabilityPreparationRow.state.in_(
                        ("obsolete", "succeeded", "failed")
                    ),
                    CapabilityPreparationRow.cleaned_at.is_(None),
                    CapabilityPreparationRow.superseded_at <= now - timedelta(hours=24),
                    or_(
                        CapabilityPreparationRow.dispatch_until.is_(None),
                        CapabilityPreparationRow.dispatch_until <= now,
                    ),
                )
                .order_by(
                    CapabilityPreparationRow.superseded_at, CapabilityPreparationRow.id
                )
                .limit(min(limit, 20))
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    leases = []
    for row in rows:
        claim_id = uuid4()
        row.dispatch_owner = str(claim_id)
        row.dispatch_until = now + timedelta(minutes=5)
        leases.append(CleanupLease(preparation_id=UUID(row.id), claim_id=claim_id))
    return leases


async def finish_cleanup(
    session: AsyncSession,
    *,
    preparation_id: str,
    claim_id: str,
    content_store: ContentStore,
) -> bool:
    row = (
        await session.execute(
            select(CapabilityPreparationRow)
            .where(CapabilityPreparationRow.id == preparation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        row is None
        or row.is_current
        or row.cleaned_at is not None
        or row.dispatch_owner != claim_id
        or row.dispatch_until is None
        or row.dispatch_until <= utcnow()
    ):
        return False
    row.cleaned_at = utcnow()
    row.dispatch_owner = None
    row.dispatch_until = None
    await session.flush()
    assets = (
        (
            await session.execute(
                select(CapabilityAssetRow)
                .join(
                    CapabilityPreparationAssetRow,
                    CapabilityPreparationAssetRow.asset_id == CapabilityAssetRow.id,
                )
                .where(CapabilityPreparationAssetRow.preparation_id == preparation_id)
                .with_for_update(of=CapabilityAssetRow)
            )
        )
        .scalars()
        .all()
    )
    for asset in assets:
        if asset.state != "stored":
            continue
        still_used = await session.scalar(
            select(CapabilityPreparationRow.id)
            .join(
                CapabilityPreparationAssetRow,
                CapabilityPreparationAssetRow.preparation_id
                == CapabilityPreparationRow.id,
            )
            .where(
                CapabilityPreparationAssetRow.asset_id == asset.id,
                or_(
                    CapabilityPreparationRow.is_current.is_(True),
                    CapabilityPreparationRow.cleaned_at.is_(None),
                ),
            )
            .limit(1)
        )
        if still_used is None:
            await asyncio.to_thread(content_store.delete_object, asset.object_key)
            asset.state = "retired"
            asset.retired_at = utcnow()
    return True
