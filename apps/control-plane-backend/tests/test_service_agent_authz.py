# Copyright Thales 2025
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

"""Service-agent recognition in the control-plane team gate (RFC EVAL-AUTH, Sol. A)."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fred_core import AuthorizationError, KeycloakUser, Resource, TeamPermission
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata


class _FakeMetadataStore:
    """AUTHZ-05 review item 9: team existence now comes from team_metadata_store."""

    async def get_by_team_id(self, team_id: TeamId) -> TeamMetadata | None:
        return TeamMetadata(id=team_id, name="fredlab")


class _FakeRebac:
    """Records every team-permission check so tests can assert bypass vs fall-through."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[TeamPermission, ...]]] = []

    async def check_user_team_permissions_or_raise(
        self, *, user: KeycloakUser, team_id: str, permissions: list[TeamPermission]
    ) -> str | None:
        self.calls.append((user.uid, team_id, tuple(permissions)))
        return "consistency-token"


def _user(roles: list[str]) -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", roles=roles, email=None)


def _deps(rebac: _FakeRebac):
    from control_plane_backend.teams.dependencies import TeamServiceDependencies

    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=cast(Any, _FakeMetadataStore),
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, object),
        get_users_by_ids=cast(Any, lambda *_a, **_k: {}),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


@pytest.mark.asyncio
async def test_service_agent_read_bypasses_openfga() -> None:
    """service_agent + CAN_READ → authorized without any OpenFGA check."""
    from control_plane_backend.teams.service import (
        _validate_team_and_check_permission,
    )

    rebac = _FakeRebac()
    metadata, token = await _validate_team_and_check_permission(
        _user(["service_agent"]),
        TeamId("fredlab"),
        cast(Any, rebac),
        [TeamPermission.CAN_READ],
        _deps(rebac),
    )

    assert rebac.calls == []  # OpenFGA never consulted for the service identity
    assert token is None
    assert metadata.id == "fredlab"


@pytest.mark.asyncio
async def test_service_agent_write_falls_through_to_openfga() -> None:
    """service_agent + a WRITE permission is NOT bypassed → normal ReBAC check runs
    (and, holding no relation, would be denied)."""
    from control_plane_backend.teams.service import (
        _validate_team_and_check_permission,
    )

    rebac = _FakeRebac()
    await _validate_team_and_check_permission(
        _user(["service_agent"]),
        TeamId("fredlab"),
        cast(Any, rebac),
        [TeamPermission.CAN_UPDATE_AGENTS],
        _deps(rebac),
    )

    # Fell through to the real check (a real OpenFGA would deny — no relation).
    assert rebac.calls == [("u", "fredlab", (TeamPermission.CAN_UPDATE_AGENTS,))]


@pytest.mark.asyncio
async def test_normal_user_still_checked_by_openfga() -> None:
    """A regular (non-service) user is unchanged: the ReBAC check always runs."""
    from control_plane_backend.teams.service import (
        _validate_team_and_check_permission,
    )

    rebac = _FakeRebac()
    await _validate_team_and_check_permission(
        _user(["viewer"]),
        TeamId("fredlab"),
        cast(Any, rebac),
        [TeamPermission.CAN_READ],
        _deps(rebac),
    )

    assert rebac.calls == [("u", "fredlab", (TeamPermission.CAN_READ,))]


class _DenyingRebac(_FakeRebac):
    """Simulates a real OpenFGA denial: raises whenever a permission beyond
    CAN_READ is requested, exactly what happens for a caller with no team
    relation (e.g. only `public` visibility on a collaborative team)."""

    async def check_user_team_permissions_or_raise(
        self, *, user: KeycloakUser, team_id: str, permissions: list[TeamPermission]
    ) -> str | None:
        await super().check_user_team_permissions_or_raise(
            user=user, team_id=team_id, permissions=permissions
        )
        if set(permissions) - {TeamPermission.CAN_READ}:
            raise AuthorizationError(user.uid, "use_team_agents", Resource.TEAM)
        return "consistency-token"


async def _thin_get_team_by_id(
    user: KeycloakUser,
    team_id: TeamId,
    team_deps: Any,
    required_permissions: list[TeamPermission] | None = None,
) -> Any:
    """Stand-in for `teams.service.get_team_by_id` that still runs the real
    `_validate_team_and_check_permission` gate, but skips the unrelated
    membership-enrichment/permissions-listing steps of the full function
    (irrelevant to this authz decision and requiring a much heavier rebac fake)."""
    from control_plane_backend.teams.service import (
        _validate_team_and_check_permission,
    )

    metadata, _token = await _validate_team_and_check_permission(
        user,
        team_id,
        team_deps.rebac,
        required_permissions or [TeamPermission.CAN_READ],
        team_deps,
    )
    return SimpleNamespace(id=metadata.id)


@pytest.mark.asyncio
async def test_prepare_execution_service_agent_end_to_end_bypasses_openfga(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EVAL-03 end-to-end: the evaluation worker's `service_agent` identity
    reaches `POST .../prepare-execution` (`product_api.post_prepare_execution`),
    which selects CAN_READ as the required permission and is authorized via the
    existing scoped bypass in `_validate_team_and_check_permission` — no OpenFGA
    check, no stored team relation."""
    from control_plane_backend.product import api as product_api

    rebac = _FakeRebac()
    deps = cast(Any, SimpleNamespace(team_dependencies=_deps(rebac)))
    monkeypatch.setattr(
        product_api, "get_team_by_id_from_service", _thin_get_team_by_id
    )
    prepare_execution = AsyncMock(return_value=object())
    monkeypatch.setattr(product_api, "prepare_execution", prepare_execution)

    result = await product_api.post_prepare_execution(
        TeamId("fredlab"), "inst-1", deps, _user(["service_agent"])
    )

    assert rebac.calls == []  # OpenFGA never consulted for the service identity
    assert prepare_execution.await_args is not None
    assert prepare_execution.await_args.kwargs["team_id"] == "fredlab"
    assert result is not None


@pytest.mark.asyncio
async def test_prepare_execution_denies_non_service_caller_with_only_can_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-service caller who only holds CAN_READ-level access (e.g. a
    `public`-team visitor with no team relation) still requires
    CAN_USE_TEAM_AGENTS on this route and is denied — the service_agent
    relaxation does not leak to interactive users."""
    from control_plane_backend.product import api as product_api

    rebac = _DenyingRebac()
    deps = cast(Any, SimpleNamespace(team_dependencies=_deps(rebac)))
    monkeypatch.setattr(
        product_api, "get_team_by_id_from_service", _thin_get_team_by_id
    )
    monkeypatch.setattr(
        product_api, "prepare_execution", AsyncMock(return_value=object())
    )

    with pytest.raises(AuthorizationError):
        await product_api.post_prepare_execution(
            TeamId("fredlab"), "inst-1", deps, _user(["viewer"])
        )

    assert rebac.calls == [("u", "fredlab", (TeamPermission.CAN_USE_TEAM_AGENTS,))]
