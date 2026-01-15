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

from fred_core.security.authorization import Action, Resource
from fred_core.security.rbac import RBACProvider
from fred_core.security.structure import KeycloakUser


class TestRBACProvider:
    """Test the RBAC authorization provider."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rbac = RBACProvider()

        # Create test users
        self.admin_user = KeycloakUser(
            uid="admin-123", username="admin", roles=["admin"], email="admin@test.com", groups=["admins"]
        )

        self.editor_user = KeycloakUser(
            uid="editor-123",
            username="editor",
            roles=["editor"],
            email="editor@test.com",
            groups=["editors"]
        )

        self.viewer_user = KeycloakUser(
            uid="viewer-123",
            username="viewer",
            roles=["viewer"],
            email="viewer@test.com",
            groups=["viewers"]
        )

        self.no_role_user = KeycloakUser(
            uid="norole-123", username="norole", roles=[], email="norole@test.com", groups=[]
        )

    def test_admin_has_all_permissions(self):
        """Test that admin users can perform all actions on all resources."""
        for action in Action:
            for resource in Resource:
                assert self.rbac.is_authorized(self.admin_user, action, resource), (
                    f"Admin should be authorized for {action.value} on {resource.value}"
                )

    def test_editor_permissions(self):
        """Test editor user permissions."""
        # Editor can create/read/update/delete tags
        assert self.rbac.is_authorized(self.editor_user, Action.CREATE, Resource.TAGS)
        assert self.rbac.is_authorized(self.editor_user, Action.READ, Resource.TAGS)
        assert self.rbac.is_authorized(self.editor_user, Action.UPDATE, Resource.TAGS)
        assert self.rbac.is_authorized(self.editor_user, Action.DELETE, Resource.TAGS)

        # todo: once defined, if there is diff between admin and editor, add tests here

    def test_viewer_permissions(self):
        """Test viewer user permissions."""
        # Viewer can only read
        for resource in [Resource.TAGS, Resource.DOCUMENTS]:
            assert self.rbac.is_authorized(self.viewer_user, Action.READ, resource), (
                f"Viewer should be able to read {resource.value}"
            )

            # Viewer cannot create, update, or delete
            assert not self.rbac.is_authorized(
                self.viewer_user, Action.CREATE, resource
            ), f"Viewer should NOT be able to create {resource.value}"
            assert not self.rbac.is_authorized(
                self.viewer_user, Action.UPDATE, resource
            ), f"Viewer should NOT be able to update {resource.value}"
            assert not self.rbac.is_authorized(
                self.viewer_user, Action.DELETE, resource
            ), f"Viewer should NOT be able to delete {resource.value}"

    def test_no_role_user_denied(self):
        """Test that users with no roles are denied access."""
        for action in Action:
            for resource in Resource:
                assert not self.rbac.is_authorized(
                    self.no_role_user, action, resource
                ), (
                    f"User with no roles should be denied {action.value} on {resource.value}"
                )

    def test_unknown_role_denied(self):
        """Test that users with unknown roles are denied access."""
        unknown_user = KeycloakUser(
            uid="unknown-123",
            username="unknown",
            roles=["unknown_role"],
            email="unknown@test.com",
            groups=[]
        )

        assert not self.rbac.is_authorized(unknown_user, Action.READ, Resource.TAGS)
        assert not self.rbac.is_authorized(unknown_user, Action.CREATE, Resource.TAGS)

    def test_multiple_roles(self):
        """Test user with multiple roles gets combined permissions."""
        multi_role_user = KeycloakUser(
            uid="multi-123",
            username="multi",
            roles=["viewer", "editor"],
            email="multi@test.com",
            groups=["viewers", "editors"]
        )

        # Should have editor permissions (highest)
        assert self.rbac.is_authorized(multi_role_user, Action.CREATE, Resource.TAGS)
        assert self.rbac.is_authorized(multi_role_user, Action.DELETE, Resource.TAGS)
        assert self.rbac.is_authorized(multi_role_user, Action.READ, Resource.TAGS)
