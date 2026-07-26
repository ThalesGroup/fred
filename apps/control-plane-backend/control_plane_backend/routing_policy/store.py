# Copyright Thales 2026
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

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime

from fred_core.common import TeamId
from fred_core.sql import make_session_factory, use_session
from fred_sdk.contracts.context import TeamOperationRouteRule
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.routing_policy_models import TeamRoutingPolicyRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredTeamRoutingPolicy:
    """One team's stored routing policy row (TEAM-ROUTING-POLICY-RFC.md §3)."""

    team_id: TeamId
    version: int
    chat_default_profile_id: str | None
    operation_rules: tuple[TeamOperationRouteRule, ...]
    updated_by: str | None
    updated_at: datetime | None


def _row_to_record(row: TeamRoutingPolicyRow) -> StoredTeamRoutingPolicy:
    raw_rules = json.loads(row.operation_rules_json or "[]")
    return StoredTeamRoutingPolicy(
        team_id=TeamId(row.team_id),
        version=row.version,
        chat_default_profile_id=row.chat_default_profile_id,
        operation_rules=tuple(
            TeamOperationRouteRule.model_validate(r) for r in raw_rules
        ),
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


class TeamRoutingPolicyStore:
    """Pure CRUD over ``team_routing_policy`` (TEAM-05, #2118).

    Same select-then-write upsert shape as ``TeamCapabilitySettingsStore`` —
    portable across the local SQLite dev DB and Postgres, no dialect-specific
    ``ON CONFLICT``. This store never checks authorization or capability
    enablement — that's the service layer's job (``service.py``), same
    separation ``team_capability_settings`` draws between its store and
    ``enablement.py``.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def upsert(
        self,
        *,
        team_id: TeamId,
        chat_default_profile_id: str | None,
        operation_rules: list[TeamOperationRouteRule],
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredTeamRoutingPolicy:
        rules_payload = json.dumps([r.model_dump(mode="json") for r in operation_rules])
        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(TeamRoutingPolicyRow).where(
                        TeamRoutingPolicyRow.team_id == str(team_id)
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                version = 1
                s.add(
                    TeamRoutingPolicyRow(
                        team_id=str(team_id),
                        version=version,
                        chat_default_profile_id=chat_default_profile_id,
                        operation_rules_json=rules_payload,
                        updated_by=updated_by,
                    )
                )
            else:
                version = existing.version + 1
                existing.version = version
                existing.chat_default_profile_id = chat_default_profile_id
                existing.operation_rules_json = rules_payload
                existing.updated_by = updated_by
        return StoredTeamRoutingPolicy(
            team_id=team_id,
            version=version,
            chat_default_profile_id=chat_default_profile_id,
            operation_rules=tuple(operation_rules),
            updated_by=updated_by,
            updated_at=None,
        )

    async def get(
        self,
        *,
        team_id: TeamId,
        session: AsyncSession | None = None,
    ) -> StoredTeamRoutingPolicy | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(TeamRoutingPolicyRow).where(
                        TeamRoutingPolicyRow.team_id == str(team_id)
                    )
                )
            ).scalar_one_or_none()
        return _row_to_record(row) if row is not None else None
