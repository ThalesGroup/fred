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

"""Agents marketplace settings: built-in defaults, team overrides and back to
Default, quota validation, the platform-admin gate, and which teams a change
turns off (their published agents are removed)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from control_plane_backend.marketplace_settings.schemas import (
    SetAgentsMarketplaceDefaultRequest,
    SetTeamMarketplaceSettingsRequest,
)
from control_plane_backend.marketplace_settings.service import (
    get_marketplace_settings,
    preview_default_change,
    preview_team_change,
    set_marketplace_default,
    set_team_marketplace_settings,
)
from control_plane_backend.marketplace_settings.store import (
    PlatformMarketplaceSettingsStore,
)
from control_plane_backend.notifications.service import NotificationService
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.join_request_store import TeamJoinRequestStore
from fred_core import (
    AuthorizationError,
    KeycloakUser,
    OrganizationPermission,
    Resource,
)
from fred_core.common import TeamId
from fred_core.teams.metadata_store import (
    TEAM_DESCRIPTION_PLACEHOLDER,
    TeamMetadataStore,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine


class _FakeRebac:
    """Organization checks pass only for a platform admin."""

    def __init__(self, *, platform_admin: bool = True) -> None:
        self.platform_admin = platform_admin

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        if not (
            self.platform_admin
            and permission == OrganizationPermission.CAN_MANAGE_PLATFORM
        ):
            raise AuthorizationError(
                user.uid, str(permission), Resource.ORGANIZATION, "denied"
            )


def _admin() -> KeycloakUser:
    return KeycloakUser(uid="platform-admin", username="admin", roles=[], email=None)


@pytest_asyncio.fixture
async def team_store(control_plane_sql_engine: AsyncEngine) -> TeamMetadataStore:
    store = TeamMetadataStore(control_plane_sql_engine)
    for team_id, name in (("alpha", "Alpha"), ("beta", "Beta"), ("gamma", "Gamma")):
        await store.create(TeamId(team_id), name, TEAM_DESCRIPTION_PLACEHOLDER)
    return store


@pytest_asyncio.fixture
async def settings_store(
    control_plane_sql_engine: AsyncEngine,
) -> PlatformMarketplaceSettingsStore:
    return PlatformMarketplaceSettingsStore(control_plane_sql_engine)


def _deps(
    rebac: _FakeRebac,
    team_store: TeamMetadataStore,
    settings_store: PlatformMarketplaceSettingsStore,
) -> TeamServiceDependencies:
    unused = cast(Any, object)
    return TeamServiceDependencies(
        get_notification_service=lambda: AsyncMock(spec=NotificationService),
        get_team_join_request_store=lambda: AsyncMock(spec=TeamJoinRequestStore),
        configuration=unused,
        rebac=cast(Any, rebac),
        scheduler_backend=unused,
        get_team_metadata_store=lambda: team_store,
        get_default_team_store=unused,
        get_team_admin_charter_store=unused,
        get_prompt_store=unused,
        get_prompt_category_store=unused,
        get_content_store=unused,
        get_session_store=unused,
        get_purge_queue_store=unused,
        get_policy_catalog=unused,
        get_users_by_ids=unused,
        attach_avatar_urls=unused,
        search_users=unused,
        run_lifecycle_manager_once_in_memory=unused,
        get_marketplace_settings_store=lambda: settings_store,
    )


def _team(settings, team_id: str):
    return next(team for team in settings.teams if team.team_id == team_id)


@pytest.mark.asyncio
async def test_defaults_apply_when_nothing_was_ever_set(
    team_store: TeamMetadataStore, settings_store: PlatformMarketplaceSettingsStore
) -> None:
    settings = await get_marketplace_settings(
        user=_admin(), deps=_deps(_FakeRebac(), team_store, settings_store)
    )

    assert settings.default.agents_publishing_enabled is False
    assert settings.default.agents_publish_quota == 5
    assert settings.default.updated_at is None
    assert [team.team_name for team in settings.teams] == ["Alpha", "Beta", "Gamma"]
    for team in settings.teams:
        assert team.agents_publishing_enabled_override is None
        assert team.agents_publish_quota_override is None
        assert (team.agents_publishing_enabled, team.agents_publish_quota) == (False, 5)
        assert team.published_count == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"agents_publishing_enabled": True, "agents_publish_quota": 0},
        {"agents_publishing_enabled": True, "agents_publish_quota": None},
        {"agents_publishing_enabled": True},
    ],
)
def test_default_request_refuses_an_empty_or_too_small_quota(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SetAgentsMarketplaceDefaultRequest.model_validate(payload)


def test_team_request_refuses_a_quota_below_one() -> None:
    with pytest.raises(ValidationError):
        SetTeamMarketplaceSettingsRequest.model_validate(
            {"agents_publishing_enabled": None, "agents_publish_quota": 0}
        )


@pytest.mark.asyncio
async def test_team_override_then_back_to_default(
    team_store: TeamMetadataStore, settings_store: PlatformMarketplaceSettingsStore
) -> None:
    deps = _deps(_FakeRebac(), team_store, settings_store)

    result = await set_team_marketplace_settings(
        user=_admin(),
        team_id=TeamId("alpha"),
        request=SetTeamMarketplaceSettingsRequest(
            agents_publishing_enabled=None, agents_publish_quota=3
        ),
        deps=deps,
    )
    alpha = _team(result.settings, "alpha")
    assert (alpha.agents_publish_quota_override, alpha.agents_publish_quota) == (3, 3)

    result = await set_team_marketplace_settings(
        user=_admin(),
        team_id=TeamId("alpha"),
        request=SetTeamMarketplaceSettingsRequest(
            agents_publishing_enabled=None, agents_publish_quota=None
        ),
        deps=deps,
    )
    alpha = _team(result.settings, "alpha")
    assert (alpha.agents_publish_quota_override, alpha.agents_publish_quota) == (
        None,
        5,
    )


@pytest.mark.asyncio
async def test_a_team_created_later_follows_the_default(
    team_store: TeamMetadataStore, settings_store: PlatformMarketplaceSettingsStore
) -> None:
    deps = _deps(_FakeRebac(), team_store, settings_store)
    await set_marketplace_default(
        user=_admin(),
        request=SetAgentsMarketplaceDefaultRequest(
            agents_publishing_enabled=True, agents_publish_quota=7
        ),
        deps=deps,
    )
    await team_store.create(TeamId("delta"), "Delta", TEAM_DESCRIPTION_PLACEHOLDER)

    delta = _team(await get_marketplace_settings(user=_admin(), deps=deps), "delta")

    assert delta.agents_publishing_enabled_override is None
    assert (delta.agents_publishing_enabled, delta.agents_publish_quota) == (True, 7)


@pytest.mark.asyncio
async def test_a_team_admin_cannot_change_marketplace_settings(
    team_store: TeamMetadataStore, settings_store: PlatformMarketplaceSettingsStore
) -> None:
    deps = _deps(_FakeRebac(platform_admin=False), team_store, settings_store)
    team_admin = KeycloakUser(uid="ta", username="ta", roles=[], email=None)

    with pytest.raises(AuthorizationError):
        await set_team_marketplace_settings(
            user=team_admin,
            team_id=TeamId("alpha"),
            request=SetTeamMarketplaceSettingsRequest(
                agents_publishing_enabled=True, agents_publish_quota=None
            ),
            deps=deps,
        )
    with pytest.raises(AuthorizationError):
        await get_marketplace_settings(user=team_admin, deps=deps)

    alpha = await team_store.get_by_team_id(TeamId("alpha"))
    assert alpha is not None and alpha.agents_publishing_enabled is None


@pytest.mark.asyncio
async def test_default_switch_off_affects_teams_on_default_only(
    team_store: TeamMetadataStore, settings_store: PlatformMarketplaceSettingsStore
) -> None:
    deps = _deps(_FakeRebac(), team_store, settings_store)
    await set_marketplace_default(
        user=_admin(),
        request=SetAgentsMarketplaceDefaultRequest(
            agents_publishing_enabled=True, agents_publish_quota=5
        ),
        deps=deps,
    )
    await team_store.set_marketplace_overrides(
        TeamId("gamma"), agents_publishing_enabled=True, agents_publish_quota=None
    )

    preview = await preview_default_change(
        user=_admin(), agents_publishing_enabled=False, deps=deps
    )
    assert sorted(preview.affected_team_ids) == ["alpha", "beta"]
    assert preview.removed_published_agents == 0

    result = await set_marketplace_default(
        user=_admin(),
        request=SetAgentsMarketplaceDefaultRequest(
            agents_publishing_enabled=False, agents_publish_quota=5
        ),
        deps=deps,
    )

    assert sorted(result.impact.affected_team_ids) == ["alpha", "beta"]
    assert _team(result.settings, "gamma").agents_publishing_enabled is True


@pytest.mark.asyncio
async def test_default_switch_off_uses_overrides_at_write_time(
    team_store: TeamMetadataStore,
    settings_store: PlatformMarketplaceSettingsStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(_FakeRebac(), team_store, settings_store)
    await settings_store.set(
        agents_publishing_enabled=True, agents_publish_quota=5, updated_by="admin"
    )
    await team_store.set_marketplace_overrides(
        TeamId("gamma"), agents_publishing_enabled=True, agents_publish_quota=None
    )
    original_transaction = team_store.transaction

    @asynccontextmanager
    async def reset_override_before_write():
        await team_store.set_marketplace_overrides(
            TeamId("gamma"), agents_publishing_enabled=None, agents_publish_quota=None
        )
        async with original_transaction() as session:
            yield session

    monkeypatch.setattr(team_store, "transaction", reset_override_before_write)
    result = await set_marketplace_default(
        user=_admin(),
        request=SetAgentsMarketplaceDefaultRequest(
            agents_publishing_enabled=False, agents_publish_quota=5
        ),
        deps=deps,
    )

    assert sorted(result.impact.affected_team_ids) == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_back_to_an_off_default_turns_the_team_off(
    team_store: TeamMetadataStore, settings_store: PlatformMarketplaceSettingsStore
) -> None:
    deps = _deps(_FakeRebac(), team_store, settings_store)
    await team_store.set_marketplace_overrides(
        TeamId("alpha"), agents_publishing_enabled=True, agents_publish_quota=None
    )

    preview = await preview_team_change(
        user=_admin(),
        team_id=TeamId("alpha"),
        agents_publishing_enabled=None,
        deps=deps,
    )
    assert preview.affected_team_ids == ["alpha"]

    result = await set_team_marketplace_settings(
        user=_admin(),
        team_id=TeamId("alpha"),
        request=SetTeamMarketplaceSettingsRequest(
            agents_publishing_enabled=None, agents_publish_quota=None
        ),
        deps=deps,
    )

    assert result.impact.affected_team_ids == ["alpha"]
    assert _team(result.settings, "alpha").agents_publishing_enabled is False


@pytest.mark.asyncio
async def test_switching_on_affects_nothing(
    team_store: TeamMetadataStore, settings_store: PlatformMarketplaceSettingsStore
) -> None:
    deps = _deps(_FakeRebac(), team_store, settings_store)

    preview = await preview_team_change(
        user=_admin(),
        team_id=TeamId("alpha"),
        agents_publishing_enabled=True,
        deps=deps,
    )

    assert preview.affected_team_ids == []


@pytest.mark.asyncio
async def test_store_round_trips_the_single_row(
    settings_store: PlatformMarketplaceSettingsStore,
) -> None:
    assert await settings_store.get() is None
    await settings_store.set(
        agents_publishing_enabled=True, agents_publish_quota=2, updated_by="a"
    )
    await settings_store.set(
        agents_publishing_enabled=False, agents_publish_quota=9, updated_by="b"
    )

    stored = await settings_store.get()
    assert stored is not None
    assert (
        stored.agents_publishing_enabled,
        stored.agents_publish_quota,
        stored.updated_by,
    ) == (False, 9, "b")
