# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Temporary, user-scoped preparation ownership before an agent save."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Mapping
from uuid import uuid4

from fred_sdk.contracts.capability.preparation import PreparationSpec
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.capability_preparations.admission import StagedAsset
from control_plane_backend.capability_preparations.schemas import DraftPreparationStatus
from control_plane_backend.capability_preparations.service import (
    _assets_by_preparation,
    _status,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
)

DRAFT_LIFETIME = timedelta(hours=1)
MAX_AUTHOR_DRAFTS = 4
MAX_TEAM_DRAFTS = 64
MAX_AUTHOR_STORED_BYTES = 256 * 1024 * 1024
MAX_TEAM_STORED_BYTES = 4 * 1024 * 1024 * 1024


def draft_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= utcnow()


async def _admission_lock(session: AsyncSession, key: str) -> None:
    if session.bind and session.bind.dialect.name == "postgresql":
        await session.execute(
            text("select pg_advisory_xact_lock(hashtext(:key))"), {"key": key}
        )


async def create_draft(
    session: AsyncSession,
    *,
    team_id: str,
    author_id: str,
    target_id: str,
    group_id: str,
    generation: int,
    runtime_id: str,
    capability_id: str,
    spec: PreparationSpec,
    validated_config: Mapping[str, object],
    staged: StagedAsset,
) -> CapabilityPreparationRow:
    now = utcnow()
    await _admission_lock(session, f"draft-team:{team_id}")
    previous = (
        (
            await session.execute(
                select(CapabilityPreparationRow)
                .where(
                    CapabilityPreparationRow.owner_kind == "draft",
                    CapabilityPreparationRow.owner_id == group_id,
                )
                .order_by(CapabilityPreparationRow.draft_generation.desc())
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if previous and (
        previous[0].team_id != team_id
        or previous[0].draft_author_id != author_id
        or previous[0].draft_target_id != target_id
        or previous[0].capability_id != capability_id
        or previous[0].runtime_id != runtime_id
    ):
        raise ValueError("Draft group is not available for this target")
    if previous and (previous[0].draft_generation or 0) >= generation:
        raise ValueError("A newer template selection already exists")
    author_count = await session.scalar(
        select(func.count(CapabilityPreparationRow.id)).where(
            CapabilityPreparationRow.owner_kind == "draft",
            CapabilityPreparationRow.team_id == team_id,
            CapabilityPreparationRow.draft_author_id == author_id,
            CapabilityPreparationRow.is_current.is_(True),
            CapabilityPreparationRow.draft_expires_at > now,
            CapabilityPreparationRow.owner_id != group_id,
        )
    )
    team_count = await session.scalar(
        select(func.count(CapabilityPreparationRow.id)).where(
            CapabilityPreparationRow.owner_kind == "draft",
            CapabilityPreparationRow.team_id == team_id,
            CapabilityPreparationRow.is_current.is_(True),
            CapabilityPreparationRow.draft_expires_at > now,
            CapabilityPreparationRow.owner_id != group_id,
        )
    )
    if (author_count or 0) >= MAX_AUTHOR_DRAFTS or (team_count or 0) >= MAX_TEAM_DRAFTS:
        raise ValueError("Too many active template drafts; discard one and try again")
    draft_assets = (
        select(CapabilityPreparationAssetRow.asset_id)
        .join(
            CapabilityPreparationRow,
            CapabilityPreparationRow.id == CapabilityPreparationAssetRow.preparation_id,
        )
        .where(
            CapabilityPreparationRow.owner_kind == "draft",
            CapabilityPreparationRow.team_id == team_id,
            CapabilityPreparationRow.cleaned_at.is_(None),
        )
    )
    team_bytes = await session.scalar(
        select(func.coalesce(func.sum(CapabilityAssetRow.size), 0)).where(
            CapabilityAssetRow.owner_kind == "draft",
            CapabilityAssetRow.state == "stored",
            CapabilityAssetRow.id.in_(draft_assets),
        )
    )
    author_bytes = await session.scalar(
        select(func.coalesce(func.sum(CapabilityAssetRow.size), 0)).where(
            CapabilityAssetRow.owner_kind == "draft",
            CapabilityAssetRow.state == "stored",
            CapabilityAssetRow.id.in_(
                draft_assets.where(
                    CapabilityPreparationRow.draft_author_id == author_id
                )
            ),
        )
    )
    if (author_bytes or 0) + staged.size > MAX_AUTHOR_STORED_BYTES or (
        team_bytes or 0
    ) + staged.size > MAX_TEAM_STORED_BYTES:
        raise ValueError(
            "Temporary template storage is full; try again after old uploads expire"
        )
    config = (
        {
            key: validated_config[key]
            for key in spec.config_fields
            if key in validated_config
        }
        if spec.config_fields is not None
        else dict(validated_config)
    )
    if spec.activation_field and not config.get(spec.activation_field):
        raise ValueError("The uploaded template did not activate preparation")
    if len(json.dumps(config).encode("utf-8")) > 128 * 1024:
        raise ValueError("Preparation config exceeds 128 KiB")
    for old in previous:
        if old.is_current:
            old.is_current = False
            old.superseded_at = now
            if old.state in ("pending", "running"):
                old.state = "obsolete"
    await session.flush()
    preparation_id = str(uuid4())
    row = CapabilityPreparationRow(
        id=preparation_id,
        owner_kind="draft",
        owner_id=group_id,
        team_id=team_id,
        draft_author_id=author_id,
        draft_target_id=target_id,
        draft_generation=generation,
        draft_expires_at=now + DRAFT_LIFETIME,
        runtime_id=runtime_id,
        capability_id=capability_id,
        input_revision=str(uuid4()),
        rules_version=spec.rules_version,
        config_json=config,
        public_config_json={
            key: config[key] for key in spec.public_config_fields if key in config
        },
        gates_readiness=spec.gates_readiness,
        is_current=True,
        state="pending",
        attempts=0,
        max_attempts=spec.max_attempts,
        deadline_at=now + timedelta(seconds=spec.timeout_seconds),
        workflow_id=f"capability-preparation/{preparation_id}",
        task_queue=f"capability-preparation-{runtime_id}",
    )
    session.add(row)
    session.add(
        CapabilityAssetRow(
            id=staged.id,
            owner_kind="draft",
            owner_id=group_id,
            team_id=team_id,
            runtime_id=runtime_id,
            capability_id=capability_id,
            slot_key=staged.slot_key,
            sha256=staged.sha256,
            filename=staged.filename,
            content_type=staged.content_type,
            size=staged.size,
            object_key=staged.object_key,
            state="stored",
        )
    )
    await session.flush()
    session.add(
        CapabilityPreparationAssetRow(
            preparation_id=preparation_id, position=0, asset_id=staged.id
        )
    )
    return row


async def get_author_draft(
    session: AsyncSession,
    *,
    draft_id: str,
    team_id: str,
    author_id: str,
    lock: bool = False,
) -> CapabilityPreparationRow | None:
    query = select(CapabilityPreparationRow).where(
        CapabilityPreparationRow.id == draft_id,
        CapabilityPreparationRow.owner_kind == "draft",
        CapabilityPreparationRow.team_id == team_id,
        CapabilityPreparationRow.draft_author_id == author_id,
    )
    if lock:
        query = query.with_for_update()
    return (await session.execute(query)).scalar_one_or_none()


async def draft_status(
    session: AsyncSession, row: CapabilityPreparationRow
) -> DraftPreparationStatus:
    assert row.draft_expires_at is not None
    assets = await _assets_by_preparation(session, [row.id])
    return DraftPreparationStatus(
        draft_id=row.id,
        expires_at=row.draft_expires_at,
        preparation=_status(row, assets.get(row.id)),
        config=row.config_json,
    )


def discard_draft(row: CapabilityPreparationRow) -> None:
    row.is_current = False
    row.superseded_at = utcnow()
    if row.state in ("pending", "running"):
        row.state = "obsolete"


async def retry_draft(
    session: AsyncSession, row: CapabilityPreparationRow
) -> CapabilityPreparationRow:
    if (
        not row.is_current
        or row.state != "failed"
        or draft_expired(row.draft_expires_at)
    ):
        raise ValueError("Only a current failed draft can be retried")
    linked = (
        (
            await session.execute(
                select(CapabilityPreparationAssetRow)
                .where(CapabilityPreparationAssetRow.preparation_id == row.id)
                .order_by(CapabilityPreparationAssetRow.position)
            )
        )
        .scalars()
        .all()
    )
    row.is_current = False
    row.superseded_at = utcnow()
    await session.flush()
    preparation_id = str(uuid4())
    next_row = CapabilityPreparationRow(
        id=preparation_id,
        owner_kind="draft",
        owner_id=row.owner_id,
        team_id=row.team_id,
        draft_author_id=row.draft_author_id,
        draft_target_id=row.draft_target_id,
        draft_generation=row.draft_generation,
        draft_expires_at=row.draft_expires_at,
        runtime_id=row.runtime_id,
        capability_id=row.capability_id,
        input_revision=str(uuid4()),
        rules_version=row.rules_version,
        config_json=row.config_json,
        public_config_json=row.public_config_json,
        gates_readiness=row.gates_readiness,
        is_current=True,
        state="pending",
        attempts=0,
        max_attempts=row.max_attempts,
        deadline_at=utcnow()
        + max(timedelta(seconds=1), row.deadline_at - row.created_at),
        workflow_id=f"capability-preparation/{preparation_id}",
        task_queue=row.task_queue,
    )
    session.add(next_row)
    await session.flush()
    for position, association in enumerate(linked):
        session.add(
            CapabilityPreparationAssetRow(
                preparation_id=preparation_id,
                position=position,
                asset_id=association.asset_id,
            )
        )
    return next_row


async def adopt_draft(
    session: AsyncSession,
    *,
    draft_id: str,
    team_id: str,
    author_id: str,
    target_id: str,
    agent_id: str,
    runtime_id: str,
    capability_id: str,
    spec: PreparationSpec,
    config: Mapping[str, object],
    previous: CapabilityPreparationRow | None,
) -> None:
    row = await get_author_draft(
        session, draft_id=draft_id, team_id=team_id, author_id=author_id, lock=True
    )
    if (
        row is None
        or not row.is_current
        or draft_expired(row.draft_expires_at)
        or row.draft_target_id != target_id
        or row.runtime_id != runtime_id
        or row.capability_id != capability_id
        or row.rules_version != spec.rules_version
        or row.config_json != dict(config)
    ):
        raise ValueError(
            "The selected template draft is no longer current; select it again"
        )
    if previous is not None:
        previous.is_current = False
        previous.superseded_at = utcnow()
        if previous.state in ("pending", "running"):
            previous.state = "obsolete"
        await session.flush()
    row.owner_kind = "agent"
    row.owner_id = agent_id
    row.draft_author_id = None
    row.draft_target_id = None
    row.draft_generation = None
    row.draft_expires_at = None
    assets = (
        (
            await session.execute(
                select(CapabilityAssetRow)
                .join(
                    CapabilityPreparationAssetRow,
                    CapabilityPreparationAssetRow.asset_id == CapabilityAssetRow.id,
                )
                .where(CapabilityPreparationAssetRow.preparation_id == draft_id)
                .with_for_update(of=CapabilityAssetRow)
            )
        )
        .scalars()
        .all()
    )
    for asset in assets:
        asset.owner_kind = "agent"
        asset.owner_id = agent_id
    await session.flush()
