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

"""Per-child token accounting: `agent.subagent_turn_completed`.

A child turn emits no `agent.turn_completed` of its own, so this metric is the
only place its spend is measurable. These tests pin what a Grafana panel and the
KPI store depend on: one event per child, the parent's identity as dims, the
child's depth, and — because the writer is an abstract port — a sink that fails
never turning a finished child into a failed tool call.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fred_capability_subagent.capability import (
    SUBAGENT_TURN_COMPLETED_METRIC,
    SubAgentCapability,
    SubAgentConfig,
)
from fred_core.kpi import NoOpKPIWriter
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import AgentInvocationRequest, AgentInvocationResult
from fred_sdk.contracts.runtime import AgentInvokerPort, RuntimeServices
from langchain_core.tools import StructuredTool

AGENT_ID = "v2.sample.assistant"
CHILD_TOKENS = {"input_tokens": 1200, "output_tokens": 300, "cache_read_tokens": 900}


class _RecordingKPIWriter(NoOpKPIWriter):
    """Records the `emit` keyword arguments instead of writing them anywhere."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class _RaisingKPIWriter(NoOpKPIWriter):
    def emit(self, **kwargs: Any) -> None:
        raise ConnectionError("the KPI sink is down")


class _StubInvoker(AgentInvokerPort):
    def __init__(self, result: AgentInvocationResult) -> None:
        self._result = result

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResult:
        return self._result


def _run_subagent(
    *, result: AgentInvocationResult, kpi_writer: Any, depth: int = 0
) -> Callable[..., Awaitable[tuple[str, Any]]]:
    """Build the tool for one turn and hand back its coroutine."""

    ctx = CapabilityContext(
        identity=CapabilityIdentity(
            user_id="alice",
            session_id="session-1",
            team_id="fredlab",
            agent_instance_id="instance-1",
            agent_id=AGENT_ID,
            exchange_id="exchange-1",
        ),
        config=SubAgentConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(
            agent_invoker=_StubInvoker(result), kpi_writer=kpi_writer
        ),
        invocation_depth=depth,
    )
    tool = SubAgentCapability().tools(ctx)[0]
    assert isinstance(tool, StructuredTool)
    assert tool.coroutine is not None
    return tool.coroutine


@pytest.mark.asyncio
async def test_one_event_per_child_carries_the_parents_identity_and_the_childs_tokens():
    kpi = _RecordingKPIWriter()
    run = _run_subagent(
        result=AgentInvocationResult(
            agent_id=AGENT_ID, content="42 documents match.", token_usage=CHILD_TOKENS
        ),
        kpi_writer=kpi,
    )

    await run(prompt="Count the matching documents.")

    assert len(kpi.events) == 1
    event = kpi.events[0]
    assert event["name"] == SUBAGENT_TURN_COMPLETED_METRIC
    assert event["type"] == "timer"
    assert event["unit"] == "ms"
    assert event["value"] >= 0
    assert event["quantities"] == CHILD_TOKENS
    assert event["actor"].user_id == "alice"
    # The PARENT's identity: what ties a child's spend back to the turn that
    # launched it. The child's own depth is the one value that is not.
    assert event["dims"] == {
        "session_id": "session-1",
        "team_id": "fredlab",
        "agent_instance_id": "instance-1",
        "exchange_id": "exchange-1",
        "template_agent_id": AGENT_ID,
        "invocation_depth": "1",
        "finish_reason": "stop",
    }


@pytest.mark.asyncio
async def test_depth_dim_is_the_childs_not_the_parents():
    kpi = _RecordingKPIWriter()
    run = _run_subagent(
        result=AgentInvocationResult(agent_id=AGENT_ID, content="done"),
        kpi_writer=kpi,
        depth=2,
    )

    await run(prompt="Do the thing.")

    assert kpi.events[0]["dims"]["invocation_depth"] == "3"


@pytest.mark.asyncio
async def test_a_failed_child_is_still_measured():
    # A child that burned tokens and then failed is exactly the runaway this
    # metric exists to show, so it is emitted with finish_reason="error".
    kpi = _RecordingKPIWriter()
    run = _run_subagent(
        result=AgentInvocationResult(
            agent_id=AGENT_ID,
            content="model provider timed out",
            is_error=True,
            token_usage=CHILD_TOKENS,
        ),
        kpi_writer=kpi,
    )

    _, artifact = await run(prompt="Do the thing.")

    assert artifact.is_error is True
    assert len(kpi.events) == 1
    assert kpi.events[0]["dims"]["finish_reason"] == "error"
    assert kpi.events[0]["quantities"] == CHILD_TOKENS


@pytest.mark.asyncio
async def test_an_over_cap_answer_is_still_measured():
    # The cap rejects the ANSWER; the child ran and its spend is real.
    kpi = _RecordingKPIWriter()
    run = _run_subagent(
        result=AgentInvocationResult(
            agent_id=AGENT_ID, content="x" * 40_001, token_usage=CHILD_TOKENS
        ),
        kpi_writer=kpi,
    )

    _, artifact = await run(prompt="Summarize everything.")

    assert artifact.is_error is True
    assert len(kpi.events) == 1


@pytest.mark.asyncio
async def test_a_child_reporting_no_tokens_emits_no_counters():
    kpi = _RecordingKPIWriter()
    run = _run_subagent(
        result=AgentInvocationResult(agent_id=AGENT_ID, content="done"), kpi_writer=kpi
    )

    await run(prompt="Do the thing.")

    # None rather than zeros: a counter that never moved is not a counter at 0.
    assert kpi.events[0]["quantities"] is None


@pytest.mark.asyncio
async def test_a_raising_kpi_writer_never_fails_the_tool_result():
    run = _run_subagent(
        result=AgentInvocationResult(
            agent_id=AGENT_ID, content="42 documents match.", token_usage=CHILD_TOKENS
        ),
        kpi_writer=_RaisingKPIWriter(),
    )

    content, artifact = await run(prompt="Count the matching documents.")

    assert content == "42 documents match."
    assert artifact.is_error is False


@pytest.mark.asyncio
async def test_no_kpi_writer_is_not_an_error():
    run = _run_subagent(
        result=AgentInvocationResult(agent_id=AGENT_ID, content="done"), kpi_writer=None
    )

    content, artifact = await run(prompt="Do the thing.")

    assert content == "done"
    assert artifact.is_error is False
