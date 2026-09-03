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

from enum import Enum
from typing import Optional


class Action(str, Enum):
    """Actions that can be performed on resources."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    READ_GLOBAL = "read:global"

    # Document specific actions
    PROCESS = "process"


class Resource(str, Enum):
    """Resources in the system that can have permissions applied."""

    # Knowledge Flow Backend resources
    TAGS = "tag"
    DOCUMENTS = "document"
    DOCUMENTS_SOURCES = "documents_source"
    RESOURCES = "resource"
    TABLES = "table"
    TABLES_DATABASES = "tables_database"
    KPIS = "kpi"
    OPENSEARCH = "opensearch"
    LOGS = "logs"
    FILES = "files"

    # Agentic Backend resources
    FEEDBACK = "feedback"
    PROMPT_COMPLETIONS = "prompt_completions"
    METRICS = "metrics"
    AGENT = "agent"
    AGENTS = "agents"
    SESSIONS = "sessions"
    MESSAGE_ATTACHMENTS = "message_attachments"
    MCP_SERVERS = "mcp_servers"
    # Agent-capability team scoping (CAPAB-01 / #1980, RFC AGENT-CAPABILITY §8.1):
    # a platform-wide object that teams are enabled-for, not owned-by.
    CAPABILITY = "capability"

    # Authorization subject
    USER = "user"
    TEAM = "team"
    ORGANIZATION = "organization"


class AuthorizationError(PermissionError):
    """Raised when a principal is not authorized to perform an action.

    Inherits from the builtin `PermissionError` (not bare `Exception`) so that
    every call site's `except PermissionError` — the standard ReBAC-denial ->
    403 mapping — also catches this without needing its own `except
    AuthorizationError` clause. Without this, a denial raised via
    `check_permission_or_raise` (which raises `AuthorizationError`) falls
    through to a generic `except Exception` handler and surfaces as an
    unhandled 500 instead of 403 wherever only `PermissionError` is caught.
    """

    def __init__(
        self,
        user_id: str,
        action: str,
        resource: Resource,
        message: Optional[str] = None,
        *,
        actor_uid: Optional[str] = None,
        subject_type: Optional[Resource] = None,
        subject_id: Optional[str] = None,
    ):
        """Describe the actor, and optionally the checked ReBAC subject.

        ``user_id`` retains its historical string contract: it names the user
        actor when known and otherwise the checked subject. ``actor_uid`` is
        the authoritative optional actor for non-user-subject checks.
        """
        self.user_id = user_id
        self.action = action
        self.resource = resource
        self.actor_uid = actor_uid
        self.subject_type = subject_type
        self.subject_id = subject_id
        default_message = f"Not authorized to {action} {resource.value}"
        super().__init__(message or default_message)
