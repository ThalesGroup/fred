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

from fred_core.security.models import (
    Action,
    AuthorizationError,
    AuthorizationProvider,
    Resource,
)
from fred_core.security.rbac import RBACProvider
from fred_core.security.structure import KeycloakUser

authz_providers: list[AuthorizationProvider] = [RBACProvider()]

# Fake user to use when a function requires a user but we don't have one yet
# but should have one when authorization is added to the service.
# This is a temporary workaround and should be replaced with a real user.
TODO_PASS_REAL_USER = KeycloakUser(
    uid="internal-admin-todo",
    username="internal admin - todo",
    email="internal-admin-todo@localhost",
    roles=["admin"],
)

# Internal admin user to use for system operations that must always succeed
# and should not be subject to authorization checks.
NO_AUTHZ_CHECK_USER = KeycloakUser(
    uid="internal-admin",
    username="internal admin",
    email="internal-admin@localhost",
    roles=["admin"],
)


def is_authorized(
    user: KeycloakUser,
    action: Action,
    resource: Resource,
) -> bool:
    """Check if user is authorized to perform action on resource using RBAC."""

    for provider in authz_providers:
        if not provider.is_authorized(user, action, resource):
            return False

    return True


def authorize_or_raise(
    user: KeycloakUser,
    action: Action,
    resource: Resource,
) -> None:
    """Authorize user to perform action on resource, raising AuthorizationError if denied."""
    if not is_authorized(user, action, resource):
        raise AuthorizationError(user.uid, action.value, resource)
