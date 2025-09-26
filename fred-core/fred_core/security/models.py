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

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from fred_core.security.structure import KeycloakUser


class Action(Enum):
    """Actions that can be performed on resources."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"

    # Document specific actions
    PROCESS = "process"


class Resource(Enum):
    """Resources in the system that can have permissions applied."""

    # Knowledge Flow Backend resources
    TAGS = "tags"
    DOCUMENTS = "documents"
    DOCUMENTS_SOURCES = "documents_sources"
    RESOURCES = "resources"
    TABLES = "tables"
    TABLES_DATABASES = "tables_databases"
    KPIS = "kpis"
    OPENSEARCH = "opensearch"
    LOGS = "logs"

    # Agentic Backend resources
    FEEDBACK = "feedback"
    PROMPT_COMPLETIONS = "prompt_completions"
    METRICS = "metrics"
    AGENTS = "agents"
    SESSIONS = "sessions"
    MESSAGE_ATTACHMENTS = "message_attachments"


class AuthorizationError(Exception):
    """Raised when a user is not authorized to perform an action."""

    def __init__(
        self,
        user_id: str,
        action: Action,
        resource: Resource,
        message: Optional[str] = None,
    ):
        self.user_id = user_id
        self.action = action
        self.resource = resource
        default_message = f"Not authorized to {action.value} {resource.value}"
        super().__init__(message or default_message)


class AuthorizationProvider(ABC):
    """Abstract base class for authorization providers."""

    @abstractmethod
    def is_authorized(
        self,
        user: KeycloakUser,
        action: Action,
        resource: Resource,
    ) -> bool:
        """Check if user is authorized to perform action on resource."""
        pass
