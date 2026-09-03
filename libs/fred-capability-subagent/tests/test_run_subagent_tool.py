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

"""Chat-time `run_subagent` tests.

The tool is built from a typed `CapabilityContext` and reaches the platform
only through `RuntimeServices.agent_invoker`, so the whole path runs offline
against a stub invoker.
"""

from __future__ import annotations

import asyncio

import pytest
from fred_capability_subagent.capability import (
    DEFAULT_MAX_DEPTH,
    MAX_MAX_DEPTH,
    MAX_SUBAGENT_CONTENT_CHARS,
    MIN_MAX_DEPTH,
    SubAgentCapability,
    SubAgentConfig,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import AgentInvocationRequest, AgentInvocationResult
from fred_sdk.contracts.runtime import AgentInvokerPort, RuntimeServices
from langchain_core.messages import AIMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

AGENT_ID = "v2.sample.assistant"


class _StubInvoker(AgentInvokerPort):
    """Records the request it was handed and replays a canned result."""

    def __init__(self, result: AgentInvocationResult) -> None:
        self._result = result
        self.requests: list[AgentInvocationRequest] = []

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResult:
        self.requests.append(request)
        return self._result


def _context(
    *,
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_DEPTH,
    invoker: AgentInvokerPort | None = None,
) -> CapabilityContext[SubAgentConfig, EmptyModel]:
    return CapabilityContext(
        identity=CapabilityIdentity(
            user_id="alice",
            session_id="session-1",
            team_id="fredlab",
            agent_id=AGENT_ID,
        ),
        config=SubAgentConfig(max_depth=max_depth),
        turn_options=EmptyModel(),
        services=RuntimeServices(agent_invoker=invoker),
        invocation_depth=depth,
    )


def _tools(**kwargs):
    return SubAgentCapability().tools(_context(**kwargs))


def test_tool_is_offered_below_max_depth():
    for depth in range(DEFAULT_MAX_DEPTH):
        tools = _tools(depth=depth)
        assert [t.name for t in tools] == ["run_subagent"]


def test_tool_is_absent_at_max_depth():
    assert _tools(depth=DEFAULT_MAX_DEPTH) == ()
    # And stays absent past it, whatever a deeper stack would report.
    assert _tools(depth=DEFAULT_MAX_DEPTH + 4) == ()


def test_max_depth_is_clamped_both_ways():
    # Above the ceiling: a config that asks for more gets the ceiling.
    assert _tools(depth=MAX_MAX_DEPTH - 1, max_depth=99) != ()
    assert _tools(depth=MAX_MAX_DEPTH, max_depth=99) == ()
    # Below the floor: zero or negative cannot switch the tool off at depth 0
    # in a way the floor does not allow.
    assert _tools(depth=MIN_MAX_DEPTH - 1, max_depth=0) != ()
    assert _tools(depth=MIN_MAX_DEPTH, max_depth=0) == ()


def test_description_carries_no_per_turn_value():
    # Tool schemas sit at the front of the prompt: a description that changed
    # between turns would invalidate the KV cache for the whole conversation.
    first = _tools(depth=1)[0].description
    second = _tools(depth=1)[0].description
    assert first == second
    # It does vary by execution context, which is the point of building it.
    assert first != _tools(depth=2)[0].description


def test_missing_agent_id_fails_loud():
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="alice"),
        config=SubAgentConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    with pytest.raises(RuntimeError, match="agent_id"):
        SubAgentCapability().tools(ctx)


@pytest.mark.asyncio
async def test_child_answer_is_returned_with_the_framing_sent():
    invoker = _StubInvoker(
        AgentInvocationResult(agent_id=AGENT_ID, content="42 documents match.")
    )
    tool = _tools(invoker=invoker)[0]

    content, artifact = await tool.coroutine(prompt="Count the matching documents.")

    assert content == "42 documents match."
    assert artifact.is_error is False
    request = invoker.requests[0]
    assert request.agent_id == AGENT_ID
    assert request.message.endswith("Count the matching documents.")
    assert "sub-agent" in request.message
    assert request.context.session_id == "session-1"


@pytest.mark.asyncio
async def test_failing_child_becomes_a_tool_error_carrying_the_message():
    invoker = _StubInvoker(
        AgentInvocationResult(
            agent_id=AGENT_ID, content="model provider timed out", is_error=True
        )
    )
    tool = _tools(invoker=invoker)[0]

    content, artifact = await tool.coroutine(prompt="Do the thing.")

    assert artifact.is_error is True
    assert "model provider timed out" in content


@pytest.mark.asyncio
async def test_over_cap_answer_asks_for_a_shorter_one_instead_of_truncating():
    long_answer = "x" * (MAX_SUBAGENT_CONTENT_CHARS + 1)
    invoker = _StubInvoker(
        AgentInvocationResult(agent_id=AGENT_ID, content=long_answer)
    )
    tool = _tools(invoker=invoker)[0]

    content, artifact = await tool.coroutine(prompt="Summarize everything.")

    assert artifact.is_error is True
    assert "shorter answer" in content
    # Never a silent truncation: the caller gets no fragment of the answer.
    assert long_answer[:100] not in content


@pytest.mark.asyncio
async def test_missing_invoker_port_fails_loud():
    tool = _tools()[0]
    with pytest.raises(RuntimeError, match="agent_invoker"):
        await tool.coroutine(prompt="Do the thing.")


@pytest.mark.asyncio
async def test_calls_in_one_assistant_message_run_concurrently():
    """Two `run_subagent` calls in one AIMessage overlap in flight.

    Driven through LangGraph's real `ToolNode`, which is what runs a turn's
    tool calls — the barrier only releases if both children are in flight, so
    a sequential implementation deadlocks instead of quietly passing.
    """

    barrier = asyncio.Barrier(2)

    class _BarrierInvoker(AgentInvokerPort):
        async def invoke(
            self, request: AgentInvocationRequest
        ) -> AgentInvocationResult:
            await barrier.wait()
            return AgentInvocationResult(agent_id=AGENT_ID, content="done")

    tool = _tools(invoker=_BarrierInvoker())[0]
    message = AIMessage(
        content="",
        tool_calls=[
            {"id": "call-1", "name": "run_subagent", "args": {"prompt": "first"}},
            {"id": "call-2", "name": "run_subagent", "args": {"prompt": "second"}},
        ],
    )

    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode([tool]))
    graph.add_edge(START, "tools")

    result = await asyncio.wait_for(
        graph.compile().ainvoke({"messages": [message]}), timeout=5
    )

    assert [m.content for m in result["messages"][1:]] == ["done", "done"]
