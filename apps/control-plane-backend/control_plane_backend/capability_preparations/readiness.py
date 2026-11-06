# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Read the current durable gates for agent availability."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.agent_instances.suspension import ReadinessVerdict
from control_plane_backend.models.capability_preparation_models import (
    CapabilityPreparationRow,
)


def _verdict(rows: Sequence[CapabilityPreparationRow]) -> ReadinessVerdict:
    blocked = sorted(
        (row for row in rows if row.state != "succeeded"),
        key=lambda row: row.capability_id,
    )
    if not blocked:
        return ReadinessVerdict(ready=True)
    failed = next((row for row in blocked if row.state == "failed"), None)
    detail = None
    if failed is not None:
        detail = failed.error_detail or (
            f"Preparation failed for capability '{failed.capability_id}'."
        )
    return ReadinessVerdict(
        ready=False,
        capability_ids=tuple(row.capability_id for row in blocked),
        detail=detail,
    )


async def agent_preparation_readiness(
    session: AsyncSession,
    *,
    team_id: str,
    agent_instance_ids: Sequence[str],
) -> dict[str, ReadinessVerdict]:
    """Batch current gating rows so one listing never performs an N+1 read."""
    result: dict[str, ReadinessVerdict] = {}
    for start in range(0, len(agent_instance_ids), 500):
        ids = agent_instance_ids[start : start + 500]
        rows = (
            (
                await session.execute(
                    select(CapabilityPreparationRow).where(
                        CapabilityPreparationRow.owner_kind == "agent",
                        CapabilityPreparationRow.team_id == team_id,
                        CapabilityPreparationRow.owner_id.in_(ids),
                        CapabilityPreparationRow.is_current.is_(True),
                        CapabilityPreparationRow.gates_readiness.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        by_agent: dict[str, list[CapabilityPreparationRow]] = defaultdict(list)
        for row in rows:
            by_agent[row.owner_id].append(row)
        result.update(
            {owner_id: _verdict(items) for owner_id, items in by_agent.items()}
        )
    return result
