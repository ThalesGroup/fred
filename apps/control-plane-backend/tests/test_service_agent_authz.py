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

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from fred_core import KeycloakUser, TeamPermission
from fred_core.common import TeamId


class _FakeAdmin:
    async def a_get_group(self, team_id: str) -> dict[str, Any]:
        return {"id": team_id, "name": "fredlab"}


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
    return KeycloakUser(uid="u", username="u", roles=roles, email=None, groups=[])


def _deps(rebac: _FakeRebac):
    from control_plane_backend.teams.dependencies import TeamServiceDependencies

    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        create_keycloak_admin_client=cast(Any, _FakeAdmin),
        get_team_metadata_store=cast(Any, lambda: object()),
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, lambda: object()),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, lambda: object()),
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
    admin, group, token = await _validate_team_and_check_permission(
        _user(["service_agent"]),
        TeamId("fredlab"),
        cast(Any, rebac),
        [TeamPermission.CAN_READ],
        _deps(rebac),
    )

    assert rebac.calls == []  # OpenFGA never consulted for the service identity
    assert token is None
    assert group["id"] == "fredlab"


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
