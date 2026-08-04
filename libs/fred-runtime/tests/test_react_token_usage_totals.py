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
"""
Regression test for the ReAct token-usage undercount (TRACE-01 follow-up).

Why this exists:
- a turn commonly makes several model calls: one or more tool-deciding calls,
  then the final answer. Each provider's usage_metadata is per-call, not
  cumulative, so FinalRuntimeEvent.token_usage must sum every call — a
  previous rolling "last write wins" variable silently reported only the
  last call's usage, undercounting any turn with more than one model call
  (spotted live: summing the trace's per-step token figures gave a larger
  total than the chat top-bar badge, which sums FinalRuntimeEvent.token_usage
  per exchange)
- ToolCallRuntimeEvent.token_usage (TRACE-01 per-step display) must NOT
  become a running total in the same fix — each step should keep showing
  only the usage of the model call that decided that specific step
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    FinalRuntimeEvent,
    ToolCallRuntimeEvent,
)
from langchain_core.messages import AIMessage, ToolMessage


class _FakePortable:
    agent_id = "agent-1"
    session_id = "sess-1"
    team_id = "personal"
    baggage: dict[str, object] = {}


class _FakeRuntimeContext:
    pass


class _FakeBinding:
    portable_context = _FakePortable()
    runtime_context = _FakeRuntimeContext()


class _FakeServices:
    tracer = None
    metrics = None


class _FakeCompiledAgent:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    async def astream(
        self,
        graph_input: object,
        *,
        config: object = None,
        stream_mode: object = None,
    ) -> AsyncIterator[object]:
        for event in self._events:
            yield event


async def _run_stream(events: list[object]) -> list[object]:
    executor = _TransportBackedReActExecutor(
        compiled_agent=_FakeCompiledAgent(events),  # type: ignore[arg-type]
        binding=_FakeBinding(),  # type: ignore[arg-type]
        services=_FakeServices(),  # type: ignore[arg-type]
    )
    input_model = ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content="hi"),)
    )
    collected: list[object] = []
    async for event in executor.stream(input_model, ExecutionConfig()):
        collected.append(event)
    return collected


@pytest.mark.asyncio
async def test_final_token_usage_sums_every_model_call_not_just_the_last() -> None:
    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "call-1", "name": "read_query", "args": {}}],
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
    )
    tool_result = ToolMessage(content="ok", tool_call_id="call-1", name="read_query")
    final_message = AIMessage(
        content="done",
        usage_metadata={"input_tokens": 30, "output_tokens": 10, "total_tokens": 40},
    )

    events = [
        ("updates", {"agent": {"messages": [tool_call]}}),
        ("updates", {"tools": {"messages": [tool_result]}}),
        ("updates", {"agent": {"messages": [final_message]}}),
    ]

    collected = await _run_stream(events)

    finals = [e for e in collected if isinstance(e, FinalRuntimeEvent)]
    assert len(finals) == 1
    # The bug: this used to equal just {"input_tokens": 30, ...} (the final
    # call alone), silently dropping the tool-deciding call's 120 tokens.
    assert finals[0].token_usage == {
        "input_tokens": 130,
        "output_tokens": 30,
        "total_tokens": 160,
    }


@pytest.mark.asyncio
async def test_tool_call_event_keeps_only_its_own_triggering_call_usage() -> None:
    """
    The turn-total fix must not turn the per-step (TRACE-01) figure into a
    running total: each ToolCallRuntimeEvent should show only the usage of
    the model call that decided that one step, even once a later step's
    usage has been folded into the turn total.
    """

    first_call = AIMessage(
        content="",
        tool_calls=[{"id": "call-1", "name": "read_query", "args": {}}],
        usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
    )
    first_result = ToolMessage(content="ok", tool_call_id="call-1", name="read_query")
    second_call = AIMessage(
        content="",
        tool_calls=[{"id": "call-2", "name": "read_query", "args": {}}],
        usage_metadata={"input_tokens": 5, "output_tokens": 1, "total_tokens": 6},
    )
    second_result = ToolMessage(content="ok", tool_call_id="call-2", name="read_query")
    final_message = AIMessage(content="done")

    events = [
        ("updates", {"agent": {"messages": [first_call]}}),
        ("updates", {"tools": {"messages": [first_result]}}),
        ("updates", {"agent": {"messages": [second_call]}}),
        ("updates", {"tools": {"messages": [second_result]}}),
        ("updates", {"agent": {"messages": [final_message]}}),
    ]

    collected = await _run_stream(events)

    tool_calls = [e for e in collected if isinstance(e, ToolCallRuntimeEvent)]
    assert len(tool_calls) == 2
    assert tool_calls[0].token_usage == {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
    }
    assert tool_calls[1].token_usage == {
        "input_tokens": 5,
        "output_tokens": 1,
        "total_tokens": 6,
    }
