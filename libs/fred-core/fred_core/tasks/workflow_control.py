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

"""Thin control surface over the Temporal workflow that backs a task.

Each app owns and *submits* its own workflows (ingestion, lifecycle, …); fred-core
only needs to **observe** (for reconciliation) and **cancel** them by id. This module
deliberately has no `submit` — task execution is not a fred-core concern.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fred_core.scheduler import TemporalClientProvider

logger = logging.getLogger(__name__)


class ExecutionStatus(StrEnum):
    """Backend-agnostic status of the workflow that backs a task.

    Returned by ``WorkflowControl.get_status``. ``None`` (not a member) means the
    status could not be determined (transient / unreachable) — the caller must never
    treat that as a failure.
    """

    running = "running"
    completed = "completed"
    failed = "failed"
    timed_out = "timed_out"
    canceled = "canceled"
    terminated = "terminated"

    @property
    def is_terminal_failure(self) -> bool:
        """Terminal executor states that mean the task did *not* succeed and was
        *not* user-cancelled. ``canceled`` is deliberately excluded — a user-requested
        cancellation is reconciled to ``TaskState.cancelled``, not ``failed`` (see
        ``TaskService._reconciled_terminal``), so cancellations never inflate failure
        counts or error history.
        """
        return self in (
            ExecutionStatus.failed,
            ExecutionStatus.timed_out,
            ExecutionStatus.terminated,
        )

    @property
    def is_cancellation(self) -> bool:
        """The execution ended because cancellation was requested (user/admin)."""
        return self == ExecutionStatus.canceled


# Temporal WorkflowExecutionStatus.name → ExecutionStatus. CONTINUED_AS_NEW is
# treated as still-running (non-terminal).
_TEMPORAL_STATUS_BY_NAME: dict[str, ExecutionStatus] = {
    "RUNNING": ExecutionStatus.running,
    "CONTINUED_AS_NEW": ExecutionStatus.running,
    "COMPLETED": ExecutionStatus.completed,
    "FAILED": ExecutionStatus.failed,
    "TIMED_OUT": ExecutionStatus.timed_out,
    "CANCELED": ExecutionStatus.canceled,
    "TERMINATED": ExecutionStatus.terminated,
}


class WorkflowControl(Protocol):
    """Observe/cancel the execution backing a task, by workflow id."""

    async def get_status(self, workflow_id: str) -> ExecutionStatus | None:
        """Return the workflow's status, or ``None`` if it cannot be determined."""
        ...

    async def cancel(self, workflow_id: str) -> None:
        """Request cooperative cancellation of the workflow."""
        ...


class NoopWorkflowControl:
    """Memory mode: there is no external workflow to query or cancel.

    ``get_status`` returns ``None`` (so reconciliation leaves the task untouched) and
    ``cancel`` is a no-op.
    """

    async def get_status(self, workflow_id: str) -> ExecutionStatus | None:
        return None

    async def cancel(self, workflow_id: str) -> None:
        return None


class TemporalWorkflowControl:
    """Query/cancel Temporal workflows by id via the shared client.

    Usage:
    ```python
    control = TemporalWorkflowControl(client_provider)
    status = await control.get_status("wf-123")   # describe()
    await control.cancel("wf-123")
    ```
    ``get_status`` swallows any error (Temporal unreachable, workflow not found) and
    returns ``None``, so a transient outage never reads as a failure.
    """

    def __init__(self, client_provider: TemporalClientProvider) -> None:
        self._client_provider = client_provider

    async def get_status(self, workflow_id: str) -> ExecutionStatus | None:
        try:
            client = await self._client_provider.get_client()
            handle = client.get_workflow_handle(workflow_id)
            description = await handle.describe()
        except Exception:
            logger.warning(
                "[TemporalWorkflowControl] could not describe workflow_id=%s",
                workflow_id,
                exc_info=True,
            )
            return None
        status = getattr(description, "status", None)
        name = getattr(status, "name", None)
        return _TEMPORAL_STATUS_BY_NAME.get(name) if name else None

    async def cancel(self, workflow_id: str) -> None:
        client = await self._client_provider.get_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.cancel()
