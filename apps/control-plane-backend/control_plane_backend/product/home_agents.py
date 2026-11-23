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

"""Home launchers from shared SQL state; only the question field limit reads a pod."""

from __future__ import annotations

import asyncio
import logging

from fred_core import KeycloakUser, TeamPermission
from fred_core.common import personal_team_id
from fred_core.security.rebac.rebac_engine import RebacDisabledResult
from sqlalchemy.exc import SQLAlchemyError

from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.platform_ui_settings.service import (
    home_layout_or_classic,
    is_featurable,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import (
    FeaturedHomeAgent,
    HomeAgentsResponse,
    HomeShowcaseResponse,
)
from control_plane_backend.product.service import (
    _record_to_summary,
    _runtime_execution_metadata_for_source,
)

logger = logging.getLogger(__name__)


async def _usable_team_ids(
    user: KeycloakUser, deps: ProductServiceDependencies
) -> list[str]:
    """Teams whose agents the user may chat with, from current permissions."""
    teams = deps.team_dependencies
    refs = await teams.rebac.lookup_user_resources(
        user, TeamPermission.CAN_USE_TEAM_AGENTS
    )
    if isinstance(refs, RebacDisabledResult):
        return [
            str(team.id) for team in await teams.get_team_metadata_store().list_all()
        ]
    return [ref.id for ref in refs]


async def list_home_agents(
    user: KeycloakUser, deps: ProductServiceDependencies, *, limit: int = 5
) -> HomeAgentsResponse:
    """Resolve current agent-use permissions before reading bounded SQL launchers."""
    teams = deps.team_dependencies
    usable, defaults = await asyncio.gather(
        _usable_team_ids(user, deps),
        teams.get_default_team_store().list_team_ids(),
    )
    personal = str(personal_team_id(user.uid))
    team_ids = list(set(usable) | {personal})
    suggestions = list(set(defaults) | {personal})
    store = deps.get_agent_instance_store()
    history_unavailable = False
    try:
        records = await store.list_home_agents(
            user.uid, team_ids, suggestions, limit=limit
        )
    except SQLAlchemyError:
        logger.exception(
            "Home history lookup failed; falling back to agent suggestions"
        )
        records = await store.list_home_agents(
            user.uid, team_ids, suggestions, include_history=False, limit=limit
        )
        history_unavailable = True
    return HomeAgentsResponse(
        agents=[_record_to_summary(record) for record in records],
        history_unavailable=history_unavailable,
    )


# The home must not wait on a slow pod: past this, no counter (the chat still enforces it).
ASK_LIMIT_TIMEOUT_SECONDS = 2.0


async def _chat_input_limit(
    record: AgentInstanceRecord, deps: ProductServiceDependencies
) -> int | None:
    """`app.max_chat_input_chars` of the agent's pod, read like a chat preparation."""
    source = next(
        (
            item
            for item in deps.configuration.platform.runtime_catalog_sources
            if item.enabled and item.runtime_id == record.source_runtime_id
        ),
        None,
    )
    if source is None:
        return None
    try:
        _, limit = await asyncio.wait_for(
            _runtime_execution_metadata_for_source(source.base_url),
            ASK_LIMIT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.debug("Chat input limit of %s timed out", source.runtime_id)
        return None
    return limit


async def get_home_showcase(
    user: KeycloakUser, deps: ProductServiceDependencies
) -> HomeShowcaseResponse:
    """Home mode plus the admin-chosen featured and question agents this user can chat with."""
    stored = await deps.get_platform_ui_settings_store().get_home()
    layout = home_layout_or_classic(stored.layout)
    ask_id = stored.ask_agent_instance_id
    # Only the advanced home shows these agents: skip the lookups otherwise.
    if layout == "classic" or (not stored.featured and ask_id is None):
        return HomeShowcaseResponse(layout=layout)
    ids = [entry.agent_instance_id for entry in stored.featured]
    usable, defaults, records = await asyncio.gather(
        _usable_team_ids(user, deps),
        deps.team_dependencies.get_default_team_store().list_team_ids(),
        deps.get_agent_instance_store().get_many(
            ids + ([ask_id] if ask_id is not None else [])
        ),
    )
    visible = set(defaults) & set(usable)
    ask_record = records.get(ask_id) if ask_id is not None else None
    if ask_record is not None and not is_featurable(ask_record, visible):
        ask_record = None
    return HomeShowcaseResponse(
        layout=layout,
        featured=[
            FeaturedHomeAgent(
                agent=_record_to_summary(record),
                badge=entry.badge,
                highlights=entry.highlights,
            )
            for entry in stored.featured
            if (record := records.get(entry.agent_instance_id)) is not None
            and is_featurable(record, visible)
        ],
        ask_agent=_record_to_summary(ask_record) if ask_record is not None else None,
        ask_max_chat_input_chars=(
            await _chat_input_limit(ask_record, deps)
            if ask_record is not None
            else None
        ),
    )
