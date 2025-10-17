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

import logging
from typing import Set

from fred_core.security.models import (
    Action,
    AuthorizationProvider,
    Resource,
)
from fred_core.security.structure import KeycloakUser

logger = logging.getLogger(__name__)

ALL = set(Action)
CRUD = {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE}
READ_ONLY = {Action.READ}
CRU = {Action.CREATE, Action.READ, Action.UPDATE}


class RBACProvider(AuthorizationProvider):
    """Role-Based Access Control authorization provider."""

    def __init__(self):
        # Define role permissions
        self.role_permissions: dict[str, dict[Resource, Set[Action]]] = {
            "admin": {
                # Admin can do everything
                **{resource: ALL for resource in Resource}
            },
            "editor": {
                # Knowledge Flow
                Resource.TAGS: CRUD,
                Resource.DOCUMENTS: CRU,  # Can't process and delete Document (Action.PROCESS and Action.DELETE)
                Resource.RESOURCES: CRUD,
                Resource.DOCUMENTS_SOURCES: READ_ONLY,  # Can't rescan sources (Action.UPDATE)
                Resource.TABLES: CRUD,
                Resource.TABLES_DATABASES: CRUD,
                Resource.KPIS: READ_ONLY,
                Resource.OPENSEARCH: READ_ONLY,
                # Agentic
                Resource.FEEDBACK: {
                    Action.CREATE
                },  # Can't delete or read feedback (as it would allow to read others feedbacks for now)
                Resource.PROMPT_COMPLETIONS: {Action.CREATE},
                Resource.METRICS: {Action.READ},
                Resource.AGENTS: READ_ONLY,  # Can't create/update/delete agents
                Resource.SESSIONS: CRUD,
                Resource.MESSAGE_ATTACHMENTS: {Action.CREATE},
                Resource.USER: READ_ONLY,
                Resource.GROUP: READ_ONLY,
            },
            "viewer": {
                # Viewer can only read
                **{resource: READ_ONLY for resource in Resource},
                # Except for:
                Resource.FEEDBACK: {Action.CREATE},
                # Viewer can chat:
                Resource.SESSIONS: CRUD,
                Resource.MESSAGE_ATTACHMENTS: {Action.CREATE},
                Resource.PROMPT_COMPLETIONS: {Action.CREATE},
            },
            "service_agent": {
                Resource.TAGS: READ_ONLY,
                Resource.DOCUMENTS: READ_ONLY,
                Resource.TABLES_DATABASES: READ_ONLY,
                Resource.TABLES: READ_ONLY,
            },
        }

    def is_authorized(
        self,
        user: KeycloakUser,
        action: Action,
        resource: Resource,
    ) -> bool:
        """Check if user is authorized to perform action on resource."""

        # Check if user has any roles that allow this action on this resource
        for role in user.roles:
            if self._role_has_permission(role, action, resource):
                return True

        logger.warning(
            "Authorization denied: user=%s roles=%s action=%s resource=%s",
            user.uid,
            user.roles,
            action.value,
            resource.value,
        )
        return False

    def _role_has_permission(
        self, role: str, action: Action, resource: Resource
    ) -> bool:
        """Check if a specific role has permission for action on resource."""
        if role not in self.role_permissions:
            return False

        resource_permissions = self.role_permissions[role].get(resource, set())
        return action in resource_permissions

    def list_permissions_for_user(self, user: KeycloakUser) -> list[str]:
        """
        Return a flat list of 'resource:action' strings the user is allowed to perform.
        """
        allowed: list[str] = []
        for role in user.roles:
            if role not in self.role_permissions:
                continue
            for resource, actions in self.role_permissions[role].items():
                for action in actions:
                    key = f"{resource.value}:{action.value}"
                    if key not in allowed:
                        allowed.append(key)
        return allowed
