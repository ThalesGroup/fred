# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Scoped reads and retry for durable capability preparations."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from fred_sdk.contracts.capability.preparation import PreparationAsset, PreparationWork
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.capability_preparations.schemas import (
    PreparationStatus,
    PreparationStatusPage,
    WorkerPreparationResult,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
)


def _status(row: CapabilityPreparationRow) -> PreparationStatus:
    return PreparationStatus(
        capability_id=row.capability_id,
        preparation_id=row.id,
        state=row.state,
        input_revision=row.input_revision,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        gates_readiness=row.gates_readiness,
        created_at=row.created_at,
        completed_at=row.completed_at,
        summary=row.result_summary,
        error_code=row.error_code,
        error_detail=row.error_detail,
    )


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
    return PreparationStatusPage(
        items=[_status(row) for row in rows[:limit]], has_more=len(rows) > limit
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
    return _status(row)


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
        owner_kind=row.owner_kind,
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
        config=row.config_json,
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
    row = (
        await session.execute(
            select(CapabilityPreparationRow)
            .where(CapabilityPreparationRow.id == preparation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        row is None
        or not row.is_current
        or row.state != "running"
        or row.input_revision != completion.input_revision
        or row.attempts != completion.attempt
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
            .values(is_current=False, state="obsolete", updated_at=utcnow())
        )
