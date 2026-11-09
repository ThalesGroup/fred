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

"""Home launchers from shared SQL state, independent of analytics and pods."""

from __future__ import annotations

import asyncio
import logging

from fred_core import KeycloakUser, TeamPermission
from fred_core.common import personal_team_id
from fred_core.security.rebac.rebac_engine import RebacDisabledResult
from sqlalchemy.exc import SQLAlchemyError

from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import HomeAgentsResponse
from control_plane_backend.product.service import _record_to_summary

logger = logging.getLogger(__name__)


async def list_home_agents(
    user: KeycloakUser, deps: ProductServiceDependencies
) -> HomeAgentsResponse:
    """Resolve current agent-use permissions before reading five SQL launchers."""
    teams = deps.team_dependencies
    refs, defaults = await asyncio.gather(
        teams.rebac.lookup_user_resources(user, TeamPermission.CAN_USE_TEAM_AGENTS),
        teams.get_default_team_store().list_team_ids(),
    )
    personal = str(personal_team_id(user.uid))
    if isinstance(refs, RebacDisabledResult):
        team_ids = [
            str(team.id) for team in await teams.get_team_metadata_store().list_all()
        ]
    else:
        team_ids = [ref.id for ref in refs]
    team_ids = list(set(team_ids) | {personal})
    suggestions = list(set(defaults) | {personal})
    store = deps.get_agent_instance_store()
    history_unavailable = False
    try:
        records = await store.list_home_agents(user.uid, team_ids, suggestions)
    except SQLAlchemyError:
        logger.exception(
            "Home history lookup failed; falling back to agent suggestions"
        )
        records = await store.list_home_agents(
            user.uid, team_ids, suggestions, include_history=False
        )
        history_unavailable = True
    return HomeAgentsResponse(
        agents=[_record_to_summary(record) for record in records],
        history_unavailable=history_unavailable,
    )
