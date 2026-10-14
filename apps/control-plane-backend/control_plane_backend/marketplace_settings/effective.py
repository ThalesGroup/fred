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

"""Effective agents marketplace settings: a team override, else the default."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.agent_marketplace.store import AgentMarketplaceStore
from control_plane_backend.marketplace_settings.schemas import (
    AgentsMarketplaceDefault,
    EffectiveMarketplaceSettings,
)
from control_plane_backend.marketplace_settings.store import (
    PlatformMarketplaceSettingsStore,
)
from control_plane_backend.models.marketplace_settings_models import (
    DEFAULT_AGENTS_PUBLISH_QUOTA,
    DEFAULT_AGENTS_PUBLISHING_ENABLED,
)


async def load_marketplace_default(
    get_store: Callable[[], PlatformMarketplaceSettingsStore] | None,
    *,
    session: AsyncSession | None = None,
) -> AgentsMarketplaceDefault:
    """The stored default, or the built-in one when nothing was ever saved."""
    stored = await get_store().get(session=session) if get_store is not None else None
    if stored is None:
        return AgentsMarketplaceDefault(
            agents_publishing_enabled=DEFAULT_AGENTS_PUBLISHING_ENABLED,
            agents_publish_quota=DEFAULT_AGENTS_PUBLISH_QUOTA,
        )
    return AgentsMarketplaceDefault(
        agents_publishing_enabled=stored.agents_publishing_enabled,
        agents_publish_quota=stored.agents_publish_quota,
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


def effective_marketplace_settings(
    default: AgentsMarketplaceDefault,
    metadata: TeamMetadata,
    *,
    agents_publishing_enabled: bool | None = None,
) -> EffectiveMarketplaceSettings:
    """Override else default, per setting. `agents_publishing_enabled` stands in
    for the default switch when previewing a default change."""
    default_switch = (
        default.agents_publishing_enabled
        if agents_publishing_enabled is None
        else agents_publishing_enabled
    )
    return EffectiveMarketplaceSettings(
        agents_publishing_enabled=(
            metadata.agents_publishing_enabled
            if metadata.agents_publishing_enabled is not None
            else default_switch
        ),
        agents_publish_quota=(
            metadata.agents_publish_quota
            if metadata.agents_publish_quota is not None
            else default.agents_publish_quota
        ),
    )


async def count_published_agents(
    team_ids: Iterable[TeamId],
    get_store: Callable[[], AgentMarketplaceStore] | None,
) -> dict[TeamId, int]:
    """Published agents per team, one grouped query; zero without a store."""
    ids = list(team_ids)
    if get_store is None:
        return {team_id: 0 for team_id in ids}
    return await get_store().count_published(ids)
