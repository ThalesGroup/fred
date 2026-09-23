from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    DelegationConfig,
)
from fred_core.security.models import StandingAuthorizationError
from fred_core.tasks.agent_run import (
    AgentRunAdmissionRecord,
    AgentRunBudget,
    AgentRunScope,
    AgentRunWorkflowInputV1,
)
from fred_core.tasks.models import AgentRunTaskEvent, TaskState
from fred_runtime.background import activities as activity_module
from fred_runtime.background import runtime as runtime_module
from fred_runtime.background.activities import (
    AgentRunActivities,
    AgentRunRegistrationError,
)
from fred_runtime.background.runtime import build_background_agent_executor
from fred_runtime.common.outbound_credentials import DelegationRuntime, RunRecord


class _Tokens:
    async def get_token(self) -> str:
        return "synthetic-workload-token"


def _record() -> AgentRunAdmissionRecord:
    return AgentRunAdmissionRecord(
        person_id="person",
        team_id="team",
        runtime_id="runtime",
        agent_instance_id="instance",
        agent_id="template",
        prompt="synthetic prompt",
        scope=AgentRunScope(document_ids=("doc",), library_ids=("library",)),
        created_by="creator",
        created_at=datetime.now(timezone.utc),
        run_id="run",
        budget=AgentRunBudget(wall_clock_seconds=45, max_concurrent_children=2),
    )


class _Reporter:
    def __init__(self) -> None:
        self.events: list[AgentRunTaskEvent] = []

    async def record(self, task_id: str, event: AgentRunTaskEvent) -> None:
        self.events.append(event)


def _executor_with_iterator(monkeypatch, iterate):
    delegation = DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["runtime-workload"]),
        token_provider=cast(Any, _Tokens()),
        workload_client_id="runtime-workload",
    )

    async def authorize(request, **kwargs):
        local = delegation.records.admit(
            RunRecord(
                run_id="run",
                person_id="person",
                agent_id="instance",
                agent_instance_id="instance",
                team_id="team",
                mode="background",
                registered=True,
                run_ceiling_seconds=45,
            )
        )
        provider = delegation.provider_for(run_id=local.run_id, agent_id=local.agent_id)
        return SimpleNamespace(), SimpleNamespace(
            definition=SimpleNamespace(agent_id="template"),
            effective_agent_id="instance",
            credential_provider=provider,
            tuning=None,
            team_settings={},
            reasoning_enabled_model_ids=(),
            platform_chat_model_binding=None,
            platform_prompt=None,
            run_limits=kwargs["admission_limits"],
            run_started_at=local.started_monotonic,
        )

    monkeypatch.setattr(runtime_module, "get_delegation_runtime", lambda: delegation)
    monkeypatch.setattr(runtime_module, "_authorize_and_resolve", authorize)
    monkeypatch.setattr(runtime_module, "_iterate_runtime_event_payloads", iterate)
    return build_background_agent_executor(
        container=cast(Any, object()),
        registry={},
        capability_registry=cast(Any, object()),
    )


def _workflow_input() -> AgentRunWorkflowInputV1:
    return AgentRunWorkflowInputV1(
        task_id="task",
        workflow_id="workflow",
        record=_record(),
    )


@pytest.mark.asyncio
async def test_executor_uses_server_admission_and_durable_credentials(
    monkeypatch,
) -> None:
    delegation = DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["runtime-workload"]),
        token_provider=cast(Any, _Tokens()),
        workload_client_id="runtime-workload",
    )
    captured: dict[str, Any] = {}

    async def authorize(request, **kwargs):
        captured["request"] = request
        captured["limits"] = kwargs["admission_limits"]
        captured["authorization_access_token"] = kwargs["access_token"]
        record = delegation.records.admit(
            RunRecord(
                run_id="run",
                person_id="person",
                agent_id="instance",
                agent_instance_id="instance",
                team_id="team",
                mode="background",
                registered=True,
                run_ceiling_seconds=45,
            )
        )
        provider = delegation.provider_for(
            run_id=record.run_id, agent_id=record.agent_id
        )
        target = SimpleNamespace(
            definition=SimpleNamespace(agent_id="template"),
            effective_agent_id="instance",
            credential_provider=provider,
            tuning=None,
            team_settings={},
            reasoning_enabled_model_ids=(),
            platform_chat_model_binding=None,
            platform_prompt=None,
            run_limits=kwargs["admission_limits"],
            run_started_at=record.started_monotonic,
        )
        return SimpleNamespace(), target

    async def iterate(*args, **kwargs):
        credentials = await kwargs["credential_provider"].credentials()
        captured["credentials"] = credentials
        yield {"kind": "final", "sequence": 1}

    monkeypatch.setattr(runtime_module, "get_delegation_runtime", lambda: delegation)
    monkeypatch.setattr(runtime_module, "_authorize_and_resolve", authorize)
    monkeypatch.setattr(runtime_module, "_iterate_runtime_event_payloads", iterate)
    executor = build_background_agent_executor(
        container=cast(Any, object()),
        registry={},
        capability_registry=cast(Any, object()),
    )

    assert [event async for event in executor(_record())] == [
        {"kind": "final", "sequence": 1}
    ]
    assert captured["request"].runtime_context.selected_document_uids == ["doc"]
    assert captured["request"].runtime_context.selected_document_libraries_ids == [
        "library"
    ]
    assert captured["request"].runtime_context.access_token is None
    assert captured["request"].runtime_context.access_token_expires_at is None
    assert captured["request"].runtime_context.refresh_token is None
    assert captured["authorization_access_token"] is None
    assert captured["limits"].wall_clock_seconds == 45
    assert captured["limits"].max_concurrent_children == 2
    assert captured["credentials"].parameters[GRANT_PARAM_PERSON] == "person"
    assert captured["credentials"].parameters[GRANT_PARAM_AGENT] == "instance"


@pytest.mark.asyncio
async def test_registration_failure_never_starts_runtime(monkeypatch) -> None:
    delegation = DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["runtime-workload"]),
        token_provider=cast(Any, _Tokens()),
        workload_client_id="runtime-workload",
    )
    started = False

    async def authorize(*args, **kwargs):
        raise RuntimeError("synthetic registration failure")

    async def iterate(*args, **kwargs):
        nonlocal started
        started = True
        yield {}

    monkeypatch.setattr(runtime_module, "get_delegation_runtime", lambda: delegation)
    monkeypatch.setattr(runtime_module, "_authorize_and_resolve", authorize)
    monkeypatch.setattr(runtime_module, "_iterate_runtime_event_payloads", iterate)
    executor = build_background_agent_executor(
        container=cast(Any, object()),
        registry={},
        capability_registry=cast(Any, object()),
    )

    with pytest.raises(AgentRunRegistrationError):
        await anext(executor(_record()))
    assert started is False


@pytest.mark.asyncio
async def test_revoked_authority_during_runtime_admission_stays_authority_lost(
    monkeypatch,
) -> None:
    delegation = DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["runtime-workload"]),
        token_provider=cast(Any, _Tokens()),
        workload_client_id="runtime-workload",
    )

    async def authorize(*args, **kwargs):
        raise HTTPException(status_code=403, detail="permission_denied")

    monkeypatch.setattr(runtime_module, "get_delegation_runtime", lambda: delegation)
    monkeypatch.setattr(runtime_module, "_authorize_and_resolve", authorize)
    executor = build_background_agent_executor(
        container=cast(Any, object()),
        registry={},
        capability_registry=cast(Any, object()),
    )

    with pytest.raises(StandingAuthorizationError):
        await anext(executor(_record()))


@pytest.mark.asyncio
async def test_post_registration_binding_mismatch_finishes_admitted_run(
    monkeypatch,
) -> None:
    delegation = DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["runtime-workload"]),
        token_provider=cast(Any, _Tokens()),
        workload_client_id="runtime-workload",
    )
    finished: list[tuple[str, str | None]] = []

    async def authorize(request, **kwargs):
        local = delegation.records.admit(
            RunRecord(
                run_id="run",
                person_id="person",
                agent_id="instance",
                agent_instance_id="instance",
                registered=True,
            )
        )
        return SimpleNamespace(), SimpleNamespace(
            definition=SimpleNamespace(agent_id="different-template"),
            effective_agent_id="instance",
            credential_provider=delegation.provider_for(
                run_id="run", agent_id=local.agent_id
            ),
        )

    async def finish(provider, outcome, reason):
        finished.append((outcome, reason))
        delegation.records.discard(provider.run_id)

    monkeypatch.setattr(runtime_module, "get_delegation_runtime", lambda: delegation)
    monkeypatch.setattr(runtime_module, "_authorize_and_resolve", authorize)
    monkeypatch.setattr(runtime_module, "_finish_admitted_run", finish)
    executor = build_background_agent_executor(
        container=cast(Any, object()),
        registry={},
        capability_registry=cast(Any, object()),
    )

    with pytest.raises(AgentRunRegistrationError):
        await anext(executor(_record()))
    assert finished == [("failed", "registration_failed")]
    assert delegation.records.get("run") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_state"),
    [
        ({"kind": "final", "sequence": 1}, TaskState.succeeded),
        (
            {"kind": "execution_error", "reason": "authority_lost", "sequence": 1},
            TaskState.failed,
        ),
        ({"kind": "awaiting_human", "sequence": 1}, TaskState.failed),
    ],
)
async def test_terminal_reporting_waits_for_nested_runtime_cleanup(
    monkeypatch, payload, expected_state
) -> None:
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def iterate(*args, **kwargs):
        try:
            yield payload
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await release_cleanup.wait()

    executor = _executor_with_iterator(monkeypatch, iterate)
    reporter = _Reporter()
    monkeypatch.setattr(activity_module.activity, "heartbeat", lambda: None)
    activities = AgentRunActivities(
        rebac=cast(
            Any,
            SimpleNamespace(
                require_user_standing=lambda *args: _done(),
                check_user_team_permission_or_raise=lambda *args, **kwargs: _done(),
            ),
        ),
        executor=executor,
        reporter=cast(Any, reporter),
    )

    task = asyncio.create_task(activities.execute(_workflow_input()))
    await asyncio.wait_for(cleanup_started.wait(), 1)
    assert task.done() is False
    assert all(not event.state.is_terminal for event in reporter.events)
    release_cleanup.set()
    await asyncio.wait_for(task, 1)

    assert reporter.events[-1].state == expected_state


@pytest.mark.asyncio
async def test_cancellation_waits_for_nested_runtime_cleanup(monkeypatch) -> None:
    runtime_started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def iterate(*args, **kwargs):
        try:
            runtime_started.set()
            await asyncio.Event().wait()
            yield {"kind": "unexpected"}
        finally:
            cleanup_started.set()
            await release_cleanup.wait()

    executor = _executor_with_iterator(monkeypatch, iterate)
    reporter = _Reporter()
    monkeypatch.setattr(activity_module.activity, "heartbeat", lambda: None)
    activities = AgentRunActivities(
        rebac=cast(
            Any,
            SimpleNamespace(
                require_user_standing=lambda *args: _done(),
                check_user_team_permission_or_raise=lambda *args, **kwargs: _done(),
            ),
        ),
        executor=executor,
        reporter=cast(Any, reporter),
    )

    task = asyncio.create_task(activities.execute(_workflow_input()))
    await asyncio.wait_for(runtime_started.wait(), 1)
    task.cancel()
    await asyncio.wait_for(cleanup_started.wait(), 1)
    assert task.done() is False
    release_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)

    assert reporter.events[-1].state == TaskState.cancelled


async def _done() -> None:
    return None
