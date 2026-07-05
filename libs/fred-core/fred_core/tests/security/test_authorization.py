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

"""Tests for the authorization residue after the RBAC→ReBAC migration (AUTHZ-01):
the display-only permission catalogue. Task access authorization lives in
``fred_core.tasks.authz`` (see ``tests/tasks/test_authz.py``); enforcement itself is
ReBAC and is covered by the rebac engine tests.
"""

from fred_core.security.permission_catalog import list_display_permissions
from fred_core.security.structure import KeycloakUser


def _user(roles: list[str]) -> KeycloakUser:
    return KeycloakUser(uid="u1", username="u", email="u@t.com", roles=roles)


class TestDisplayPermissions:
    """The frontend bootstrap consumes these coarse capability hints (display only)."""

    def test_admin_sees_broad_capabilities(self) -> None:
        perms = set(list_display_permissions(_user(["admin"])))
        assert "agents:read" in perms
        assert "sessions:create" in perms
        assert "mcp_servers:create" in perms

    def test_viewer_is_read_oriented(self) -> None:
        perms = set(list_display_permissions(_user(["viewer"])))
        assert "tag:read" in perms
        assert "sessions:create" in perms  # viewers can chat
        assert "feedback:create" in perms
        assert "tag:create" not in perms

    def test_no_role_has_no_capabilities(self) -> None:
        assert list_display_permissions(_user([])) == []

    def test_unknown_role_ignored(self) -> None:
        assert list_display_permissions(_user(["nope"])) == []

    def test_deduplicated_across_roles(self) -> None:
        perms = list_display_permissions(_user(["viewer", "editor"]))
        assert len(perms) == len(set(perms))
        assert "tag:create" in set(perms)  # editor capability present
