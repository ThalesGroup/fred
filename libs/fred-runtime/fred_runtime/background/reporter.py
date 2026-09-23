from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx
from fred_core.tasks.agent_run import (
    ScheduledAgentRunOccurrence,
    ScheduledAgentRunOccurrenceRequest,
)
from fred_core.tasks.models import AgentRunTaskEvent
from temporalio.exceptions import ApplicationError


class AgentRunReporter(Protocol):
    async def record(self, task_id: str, event: AgentRunTaskEvent) -> None: ...

    async def create_occurrence(
        self, schedule_id: str, request: ScheduledAgentRunOccurrenceRequest
    ) -> ScheduledAgentRunOccurrence: ...


class AgentRunReportUnavailableError(RuntimeError):
    """A bounded reporting failure that carries no URL or response body."""


class HttpAgentRunReporter:
    """Narrow workload-authenticated control-plane client."""

    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient,
        workload_token: Callable[[], Awaitable[str]],
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._workload_token = workload_token

    async def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._workload_token()}"}

    async def record(self, task_id: str, event: AgentRunTaskEvent) -> None:
        try:
            response = await self._client.post(
                f"{self._base_url}/internal/agent-run-tasks/{task_id}/events",
                headers=await self._headers(),
                json={
                    "state": event.state.value,
                    "seq": event.seq,
                    "reason": event.detail.reason if event.detail is not None else None,
                },
            )
        except Exception:
            raise AgentRunReportUnavailableError("task_event_unavailable") from None
        # Account deletion purges the task/admission pair. Reporting must not
        # recreate it or turn the already-terminal local result into a retry.
        if response.status_code == 404:
            return
        if response.is_error:
            raise AgentRunReportUnavailableError("task_event_rejected") from None

    async def create_occurrence(
        self, schedule_id: str, request: ScheduledAgentRunOccurrenceRequest
    ) -> ScheduledAgentRunOccurrence:
        try:
            response = await self._client.post(
                f"{self._base_url}/internal/agent-run-schedules/{schedule_id}/occurrences",
                headers=await self._headers(),
                json=request.model_dump(mode="json"),
            )
        except Exception:
            raise AgentRunReportUnavailableError(
                "schedule_occurrence_unavailable"
            ) from None
        if response.status_code == 404:
            raise ApplicationError(
                "schedule_not_found", type="schedule_not_found", non_retryable=True
            ) from None
        if response.status_code in (401, 403):
            raise ApplicationError(
                "schedule_authority_lost", type="authority_lost", non_retryable=True
            ) from None
        if response.status_code == 409:
            raise ApplicationError(
                "schedule_occurrence_conflict",
                type="schedule_occurrence_conflict",
                non_retryable=True,
            ) from None
        if response.is_error:
            raise AgentRunReportUnavailableError(
                "schedule_occurrence_rejected"
            ) from None
        try:
            return ScheduledAgentRunOccurrence.model_validate(response.json())
        except Exception:
            raise AgentRunReportUnavailableError(
                "schedule_occurrence_invalid"
            ) from None
