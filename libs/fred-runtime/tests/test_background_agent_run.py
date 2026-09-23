from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from typing import Any, cast

import httpx
import pytest
from fred_core.security.models import AuthorizationError, Resource
from fred_core.tasks.agent_run import (
    AgentRunAdmissionRecord,
    AgentRunBudget,
    AgentRunWorkflowInputV1,
    ScheduledAgentRunInputV1,
    ScheduledAgentRunOccurrence,
    ScheduledAgentRunOccurrenceRequest,
)
from fred_core.tasks.models import AgentRunDetail, AgentRunTaskEvent, TaskState
from fred_runtime.background import activities as activity_module
from fred_runtime.background import workflow as workflow_module
from fred_runtime.background.activities import AgentRunActivities
from fred_runtime.background.reporter import (
    AgentRunReportUnavailableError,
    HttpAgentRunReporter,
)
from fred_runtime.background.workflow import AgentRunWorkflow, ScheduledAgentRunWorkflow
from temporalio import workflow
from temporalio.exceptions import ApplicationError


def _input() -> AgentRunWorkflowInputV1:
    return AgentRunWorkflowInputV1(
        task_id="synthetic-task",
        workflow_id="synthetic-workflow",
        record=AgentRunAdmissionRecord(
            person_id="synthetic-person",
            team_id="synthetic-team",
            runtime_id="synthetic-runtime",
            agent_instance_id="synthetic-instance",
            agent_id="synthetic-agent",
            prompt="synthetic prompt",
            created_by="synthetic-person",
            created_at=datetime.now(timezone.utc),
            run_id="synthetic-run",
            budget=AgentRunBudget(wall_clock_seconds=30, max_concurrent_children=1),
        ),
    )


def _scheduled_occurrence() -> ScheduledAgentRunOccurrence:
    return ScheduledAgentRunOccurrence(
        task_id="synthetic-task",
        workflow_id="synthetic-child-workflow",
        record=_input().record,
    )


def _scheduled_input() -> ScheduledAgentRunInputV1:
    return ScheduledAgentRunInputV1(
        schedule_id="synthetic-schedule",
        runtime_id="synthetic-runtime",
    )


class _Reporter:
    def __init__(self) -> None:
        self.events: list[AgentRunTaskEvent] = []

    async def record(self, task_id: str, event: AgentRunTaskEvent) -> None:
        self.events.append(event)

    async def create_occurrence(
        self, schedule_id: str, request: ScheduledAgentRunOccurrenceRequest
    ) -> Any:
        raise AssertionError("occurrence creation is not expected")


class _Rebac:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.standing_checks = 0

    async def require_user_standing(self, user_id: str) -> None:
        self.standing_checks += 1
        if not self.allow:
            raise AuthorizationError(
                user_id, "standing", Resource.ORGANIZATION, "denied"
            )

    async def check_user_team_permission_or_raise(
        self, *args: Any, **kwargs: Any
    ) -> None:
        if not self.allow:
            raise AssertionError("permission must not be checked after standing denial")


@pytest.mark.asyncio
async def test_activity_denial_is_terminal_and_never_calls_executor() -> None:
    reporter = _Reporter()
    called = False

    async def execute(record: AgentRunAdmissionRecord):
        nonlocal called
        called = True
        if False:
            yield {}

    activities = AgentRunActivities(
        rebac=cast(Any, _Rebac(allow=False)), executor=execute, reporter=reporter
    )
    await activities.execute(_input())
    assert called is False
    assert [
        (event.state, event.detail.reason) for event in reporter.events if event.detail
    ] == [(TaskState.failed, "authority_lost")]


@pytest.mark.asyncio
async def test_http_reporter_uses_workload_auth_and_bounded_event_body() -> None:
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers["authorization"]
        seen["body"] = request.content.decode()
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:

        async def token() -> str:
            return "synthetic-workload-token"

        reporter = HttpAgentRunReporter(
            base_url="https://control.invalid", client=client, workload_token=token
        )
        await reporter.record(
            "synthetic-task",
            AgentRunTaskEvent(
                task_id="synthetic-task",
                state=TaskState.failed,
                seq=0,
                timestamp=datetime.now(timezone.utc),
                detail=AgentRunDetail(reason="execution_failed"),
                error="Background agent run failed",
            ),
        )
    assert seen["path"] == "/internal/agent-run-tasks/synthetic-task/events"
    assert seen["authorization"] == "Bearer synthetic-workload-token"
    assert "synthetic prompt" not in seen["body"]
    assert set(json.loads(seen["body"])) == {"state", "seq", "reason"}


@pytest.mark.asyncio
async def test_http_reporter_sanitizes_failures_and_does_not_retry_purged_task() -> (
    None
):
    calls = 0

    async def not_found(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, text="SYNTHETIC-RESPONSE-CANARY")

    async with httpx.AsyncClient(transport=httpx.MockTransport(not_found)) as client:

        async def token() -> str:
            return "synthetic-token"

        reporter = HttpAgentRunReporter(
            base_url="https://control.invalid", client=client, workload_token=token
        )
        await reporter.record(
            "SYNTHETIC-TASK-ID-CANARY",
            AgentRunTaskEvent(
                task_id="SYNTHETIC-TASK-ID-CANARY",
                state=TaskState.failed,
                seq=1,
                timestamp=datetime.now(timezone.utc),
                detail=AgentRunDetail(reason="authority_lost"),
            ),
        )
    assert calls == 1


@pytest.mark.asyncio
async def test_http_reporter_does_not_expose_url_or_response_on_rejection() -> None:
    async def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="SYNTHETIC-RESPONSE-CANARY")

    async with httpx.AsyncClient(transport=httpx.MockTransport(rejected)) as client:

        async def token() -> str:
            return "synthetic-token"

        reporter = HttpAgentRunReporter(
            base_url="https://control.invalid", client=client, workload_token=token
        )
        with pytest.raises(AgentRunReportUnavailableError) as exc:
            await reporter.record(
                "SYNTHETIC-TASK-ID-CANARY",
                AgentRunTaskEvent(
                    task_id="SYNTHETIC-TASK-ID-CANARY",
                    state=TaskState.running,
                    seq=1,
                    timestamp=datetime.now(timezone.utc),
                ),
            )
    message = str(exc.value)
    assert "SYNTHETIC-TASK-ID-CANARY" not in message
    assert "SYNTHETIC-RESPONSE-CANARY" not in message


@pytest.mark.asyncio
async def test_deleted_schedule_occurrence_is_non_retryable() -> None:
    async def not_found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="SYNTHETIC-RESPONSE-CANARY")

    async with httpx.AsyncClient(transport=httpx.MockTransport(not_found)) as client:

        async def token() -> str:
            return "synthetic-token"

        reporter = HttpAgentRunReporter(
            base_url="https://control.invalid", client=client, workload_token=token
        )
        with pytest.raises(ApplicationError) as exc:
            await reporter.create_occurrence(
                "SYNTHETIC-SCHEDULE-ID-CANARY",
                ScheduledAgentRunOccurrenceRequest(
                    workflow_id="parent-workflow", run_id="run"
                ),
            )
    assert exc.value.non_retryable is True
    assert "SYNTHETIC-SCHEDULE-ID-CANARY" not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, "authority_lost"),
        (403, "authority_lost"),
        (409, "schedule_occurrence_conflict"),
    ],
)
async def test_terminal_schedule_occurrence_rejections_are_non_retryable(
    status_code: int, error_type: str
) -> None:
    calls = 0

    async def rejected(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, text="SYNTHETIC-RESPONSE-CANARY")

    async with httpx.AsyncClient(transport=httpx.MockTransport(rejected)) as client:

        async def token() -> str:
            return "synthetic-token"

        reporter = HttpAgentRunReporter(
            base_url="https://control.invalid", client=client, workload_token=token
        )
        with pytest.raises(ApplicationError) as exc:
            await reporter.create_occurrence(
                "SYNTHETIC-SCHEDULE-ID-CANARY",
                ScheduledAgentRunOccurrenceRequest(
                    workflow_id="parent-workflow", run_id="run"
                ),
            )

    assert calls == 1
    assert exc.value.non_retryable is True
    assert exc.value.type == error_type
    assert "SYNTHETIC-SCHEDULE-ID-CANARY" not in str(exc.value)
    assert "SYNTHETIC-RESPONSE-CANARY" not in str(exc.value)


@pytest.mark.asyncio
async def test_activity_cancellation_waits_for_executor_cleanup(monkeypatch) -> None:
    reporter = _Reporter()
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def execute(record: AgentRunAdmissionRecord):
        try:
            started.set()
            await asyncio.Event().wait()
            if False:
                yield {}
        finally:
            cleaned.set()

    monkeypatch.setattr(activity_module.activity, "heartbeat", lambda: None)
    activities = AgentRunActivities(rebac=_Rebac(), executor=execute, reporter=reporter)  # type: ignore[arg-type]
    task = asyncio.create_task(activities.execute(_input()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
    assert reporter.events[-1].state == TaskState.cancelled


def test_agent_run_workflow_disables_execution_retries() -> None:
    assert "RetryPolicy(maximum_attempts=1)" in inspect.getsource(AgentRunWorkflow.run)


@pytest.mark.asyncio
async def test_scheduled_parent_cancel_before_child_start_prevents_execution(
    monkeypatch,
) -> None:
    child_command = asyncio.Event()
    child_started = False
    captured: dict[str, Any] = {}

    async def execute_activity(*args: Any, **kwargs: Any):
        return _scheduled_occurrence()

    async def execute_child(*args: Any, **kwargs: Any):
        nonlocal child_started
        captured.update(kwargs)
        child_command.set()
        await asyncio.Event().wait()
        child_started = True

    monkeypatch.setattr(workflow_module.workflow, "execute_activity", execute_activity)
    monkeypatch.setattr(
        workflow_module.workflow, "execute_child_workflow", execute_child
    )
    monkeypatch.setattr(
        workflow_module.workflow,
        "info",
        lambda: type("Info", (), {"workflow_id": "synthetic-parent-workflow"})(),
    )
    monkeypatch.setattr(
        workflow_module.workflow, "uuid4", lambda: "synthetic-occurrence-run"
    )

    task = asyncio.create_task(ScheduledAgentRunWorkflow().run(_scheduled_input()))
    await asyncio.wait_for(child_command.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert child_started is False
    assert (
        captured["cancellation_type"]
        == workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED
    )
    assert captured["parent_close_policy"] == workflow.ParentClosePolicy.REQUEST_CANCEL


@pytest.mark.asyncio
async def test_scheduled_parent_cancel_waits_for_running_child_cleanup(
    monkeypatch,
) -> None:
    child_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def execute_activity(*args: Any, **kwargs: Any):
        return _scheduled_occurrence()

    async def execute_child(*args: Any, **kwargs: Any):
        child_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await release_cleanup.wait()

    monkeypatch.setattr(workflow_module.workflow, "execute_activity", execute_activity)
    monkeypatch.setattr(
        workflow_module.workflow, "execute_child_workflow", execute_child
    )
    monkeypatch.setattr(
        workflow_module.workflow,
        "info",
        lambda: type("Info", (), {"workflow_id": "synthetic-parent-workflow"})(),
    )
    monkeypatch.setattr(
        workflow_module.workflow, "uuid4", lambda: "synthetic-occurrence-run"
    )

    task = asyncio.create_task(ScheduledAgentRunWorkflow().run(_scheduled_input()))
    await asyncio.wait_for(child_started.wait(), 1)
    task.cancel()
    await asyncio.wait_for(cleanup_started.wait(), 1)
    assert task.done() is False
    release_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)


@pytest.mark.asyncio
async def test_each_occurrence_rechecks_standing(monkeypatch) -> None:
    reporter = _Reporter()
    rebac = _Rebac()

    async def execute(record: AgentRunAdmissionRecord):
        if False:
            yield {}

    monkeypatch.setattr(activity_module.activity, "heartbeat", lambda: None)
    activities = AgentRunActivities(rebac=rebac, executor=execute, reporter=reporter)  # type: ignore[arg-type]
    await activities.execute(_input())
    await activities.execute(_input())
    assert rebac.standing_checks == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_state", "expected_reason"),
    [
        (
            {"kind": "execution_error", "reason": "authority_lost"},
            TaskState.failed,
            "authority_lost",
        ),
        (
            {"kind": "execution_error", "reason": "child_limit_reached"},
            TaskState.failed,
            "child_limit_reached",
        ),
        ({"kind": "awaiting_human"}, TaskState.failed, "execution_failed"),
        ({"kind": "progress"}, TaskState.failed, "execution_failed"),
    ],
)
async def test_activity_does_not_report_false_success(
    monkeypatch, payload, expected_state, expected_reason
) -> None:
    reporter = _Reporter()

    async def execute(record: AgentRunAdmissionRecord):
        yield payload

    monkeypatch.setattr(activity_module.activity, "heartbeat", lambda: None)
    activities = AgentRunActivities(rebac=_Rebac(), executor=execute, reporter=reporter)  # type: ignore[arg-type]
    await activities.execute(_input())
    assert [event.seq for event in reporter.events] == [1, 2]
    assert reporter.events[-1].state == expected_state
    assert reporter.events[-1].detail is not None
    assert reporter.events[-1].detail.reason == expected_reason
