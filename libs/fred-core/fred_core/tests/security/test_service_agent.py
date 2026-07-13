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

"""Tests for the service-agent recognition helper (RFC EVAL-AUTH, Solution A)."""

from fred_core.security.rebac.rebac_engine import (
    SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS,
    TeamPermission,
)
from fred_core.security.structure import (
    SERVICE_AGENT_ROLE,
    KeycloakUser,
    is_service_agent,
)


def _user(roles: list[str]) -> KeycloakUser:
    return KeycloakUser(uid="u-1", username="u", roles=roles, email="u@t.com")


def test_service_agent_detected() -> None:
    assert is_service_agent(_user([SERVICE_AGENT_ROLE])) is True


def test_service_agent_detected_among_other_roles() -> None:
    assert is_service_agent(_user(["viewer", SERVICE_AGENT_ROLE])) is True


def test_non_service_roles_are_not_service_agent() -> None:
    assert is_service_agent(_user(["admin"])) is False
    assert is_service_agent(_user(["editor", "viewer"])) is False
    assert is_service_agent(_user([])) is False


def test_allowed_team_permissions_are_read_only() -> None:
    # The worker may only satisfy CAN_READ — never a write/admin permission.
    assert SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS == frozenset(
        {TeamPermission.CAN_READ}
    )
    assert (
        TeamPermission.CAN_UPDATE_AGENTS not in SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS
    )
    assert (
        TeamPermission.CAN_READ_CONVERSATIONS
        not in SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS
    )
