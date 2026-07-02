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

"""Display-only role → capability catalogue for the frontend permission summary.

This is **NOT** an authorization mechanism. Enforcement is performed exclusively by
ReBAC (OpenFGA) at every endpoint. This catalogue only tells the UI which coarse
capabilities a user's Keycloak role implies, so the frontend can gate menus/buttons
(`/frontend/bootstrap` permission summary). It must never be used to allow/deny an
operation server-side.
"""

from typing import Set

from fred_core.security.models import Action, Resource
from fred_core.security.structure import KeycloakUser

ALL = set(Action)
CRUD = {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE}
READ_ONLY = {Action.READ}
CRU = {Action.CREATE, Action.READ, Action.UPDATE}

# Coarse capability hints per Keycloak role, used for UI display only.
ROLE_CAPABILITIES: dict[str, dict[Resource, Set[Action]]] = {
    "admin": {**{resource: ALL for resource in Resource}},
    "editor": {
        Resource.TAGS: CRUD,
        Resource.DOCUMENTS: CRU,
        Resource.RESOURCES: CRUD,
        Resource.DOCUMENTS_SOURCES: READ_ONLY,
        Resource.TABLES: CRUD,
        Resource.TABLES_DATABASES: CRUD,
        Resource.KPIS: READ_ONLY,
        Resource.OPENSEARCH: READ_ONLY,
        Resource.FEEDBACK: {Action.CREATE},
        Resource.PROMPT_COMPLETIONS: {Action.CREATE},
        Resource.METRICS: {Action.READ},
        Resource.AGENTS: READ_ONLY,
        Resource.SESSIONS: CRUD,
        Resource.MCP_SERVERS: CRU,
        Resource.MESSAGE_ATTACHMENTS: {Action.CREATE, Action.READ},
        Resource.USER: READ_ONLY,
        Resource.FILES: CRUD,
    },
    "viewer": {
        **{resource: READ_ONLY for resource in Resource},
        Resource.FEEDBACK: {Action.CREATE},
        Resource.SESSIONS: CRUD,
        Resource.MESSAGE_ATTACHMENTS: CRUD,
        Resource.PROMPT_COMPLETIONS: {Action.CREATE},
        Resource.FILES: CRUD,
    },
    "service_agent": {
        Resource.TAGS: READ_ONLY,
        Resource.DOCUMENTS: READ_ONLY,
        Resource.TABLES_DATABASES: READ_ONLY,
        Resource.TABLES: READ_ONLY,
        Resource.OPENSEARCH: READ_ONLY,
        Resource.METRICS: READ_ONLY,
    },
}


def list_display_permissions(user: KeycloakUser) -> list[str]:
    """Return the flat ``resource:action`` capability hints for a user's roles.

    Display-only — see module docstring. Order is preserved and de-duplicated.
    """
    allowed: list[str] = []
    for role in user.roles:
        resource_permissions = ROLE_CAPABILITIES.get(role)
        if resource_permissions is None:
            continue
        for resource, actions in resource_permissions.items():
            for action in actions:
                key = f"{resource.value}:{action.value}"
                if key not in allowed:
                    allowed.append(key)
    return allowed
