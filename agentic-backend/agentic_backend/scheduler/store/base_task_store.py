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

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from agentic_backend.scheduler.task_structures import (
    AgentContextRefsV1,
    AgentTaskRecordV1,
    AgentTaskStatus,
)

# -------------------------
# Base interface
# -------------------------


class BaseAgentTaskStore(ABC):
    """
    Persistence interface for agent task registry.

    Responsibilities:
    - Create and store (task_id -> workflow handle) with ownership (user_id).
    - Provide ownership-checked reads.
    - Support listing by user with filters.
    - Support status/snapshot updates (from API polling or workflow status-update activity).
    """

    @abstractmethod
    async def create(
        self,
        *,
        task_id: str,
        user_id: str,
        target_agent: str,
        request_text: str,
        workflow_id: str,
        run_id: Optional[str] = None,
        context: Optional[AgentContextRefsV1] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AgentTaskRecordV1:
        """
        Create or upsert a task record.

        Requirements:
        - Must be idempotent on task_id (upsert semantics).
        - Must persist ownership user_id and workflow handle.
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self, task_id: str) -> AgentTaskRecordV1:
        """Return task by id or raise AgentTaskNotFoundError."""
        raise NotImplementedError

    @abstractmethod
    async def get_for_user(self, *, task_id: str, user_id: str) -> AgentTaskRecordV1:
        """Return task if owned by user, else raise AgentTaskForbiddenError/NotFound."""
        raise NotImplementedError

    @abstractmethod
    async def list_for_user(
        self,
        *,
        user_id: str,
        limit: int = 20,
        statuses: Optional[Sequence[AgentTaskStatus]] = None,
        target_agent: Optional[str] = None,
    ) -> List[AgentTaskRecordV1]:
        """List tasks for user ordered by creation time (newest first)."""
        raise NotImplementedError

    @abstractmethod
    async def update_handle(
        self,
        *,
        task_id: str,
        workflow_id: str,
        run_id: Optional[str],
    ) -> None:
        """Update workflow handle fields for an existing task."""
        raise NotImplementedError

    @abstractmethod
    async def update_status(
        self,
        *,
        task_id: str,
        status: AgentTaskStatus,
        last_message: Optional[str] = None,
        percent_complete: Optional[float] = None,
        blocked: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[str]] = None,
        error_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Updates the cached status and progress.
        Note: percent_complete and last_message are promoted to top-level
        for easier UI consumption.
        """
        raise NotImplementedError


# -------------------------
# Optional helper: status transitions
# -------------------------

_ALLOWED_STATUS_TRANSITIONS: Dict[AgentTaskStatus, set[AgentTaskStatus]] = {
    AgentTaskStatus.QUEUED: {AgentTaskStatus.RUNNING, AgentTaskStatus.CANCELED},
    AgentTaskStatus.RUNNING: {
        AgentTaskStatus.BLOCKED,
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.FAILED,
        AgentTaskStatus.CANCELED,
    },
    AgentTaskStatus.BLOCKED: {
        AgentTaskStatus.RUNNING,  # resume
        AgentTaskStatus.CANCELED,
        AgentTaskStatus.FAILED,
    },
    AgentTaskStatus.COMPLETED: set(),
    AgentTaskStatus.FAILED: set(),
    AgentTaskStatus.CANCELED: set(),
}


def is_valid_status_transition(current: AgentTaskStatus, nxt: AgentTaskStatus) -> bool:
    # Always allow transitioning to the same state (idempotency)
    if current == nxt:
        return True
    return nxt in _ALLOWED_STATUS_TRANSITIONS.get(current, set())
