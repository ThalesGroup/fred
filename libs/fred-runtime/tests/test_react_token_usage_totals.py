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
- tool rows carry no token figure at all (#2403): a tool call costs nothing by
  itself, and the deciding call's whole prompt on a tool row read as if a free
  call had consumed 17k tokens
- `context_tokens` is the size of the context the turn leaves behind, which the
  chat UI diffs against the previous turn to show what a message really added
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
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }


@pytest.mark.asyncio
async def test_final_token_usage_carries_cache_detail_through_the_pipeline() -> None:
    """
    CACHE-01: `input_token_details.cache_read`/`cache_creation` (LangChain's
    standardized cache breakdown, since `langchain-core` 0.3.9) must survive
    normalize_token_usage -> sum_token_usage -> FinalRuntimeEvent, the same
    path the base input/output/total fields already take.
    """

    tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "call-1", "name": "read_query", "args": {}}],
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_token_details": {"cache_read": 80, "cache_creation": 0},
        },
    )
    tool_result = ToolMessage(content="ok", tool_call_id="call-1", name="read_query")
    final_message = AIMessage(
        content="done",
        usage_metadata={
            "input_tokens": 30,
            "output_tokens": 10,
            "total_tokens": 40,
            "input_token_details": {"cache_read": 0, "cache_creation": 25},
        },
    )

    events = [
        ("updates", {"agent": {"messages": [tool_call]}}),
        ("updates", {"tools": {"messages": [tool_result]}}),
        ("updates", {"agent": {"messages": [final_message]}}),
    ]

    collected = await _run_stream(events)

    finals = [e for e in collected if isinstance(e, FinalRuntimeEvent)]
    assert len(finals) == 1
    assert finals[0].token_usage == {
        "input_tokens": 130,
        "output_tokens": 30,
        "total_tokens": 160,
        "cache_read_tokens": 80,
        "cache_creation_tokens": 25,
    }


def _tool_call(call_id: str, input_tokens: int, output_tokens: int = 1) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"id": call_id, "name": "read_query", "args": {}}],
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


@pytest.mark.asyncio
async def test_tool_call_event_no_longer_carries_the_deciding_calls_prompt() -> None:
    """
    The misleading field is gone from the contract, not merely unused: a tool
    row must have no way to render the deciding call's whole prompt again.
    """

    events = [
        ("updates", {"agent": {"messages": [_tool_call("call-1", 17550)]}}),
        (
            "updates",
            {"tools": {"messages": [ToolMessage(content="ok", tool_call_id="call-1")]}},
        ),
        ("updates", {"agent": {"messages": [AIMessage(content="done")]}}),
    ]

    (tool_call,) = [
        e for e in await _run_stream(events) if isinstance(e, ToolCallRuntimeEvent)
    ]
    assert not hasattr(tool_call, "token_usage")


@pytest.mark.asyncio
async def test_context_tokens_is_the_last_calls_input_even_after_trimming() -> None:
    """
    History trimming (`CheckpointHygieneMiddleware`) can shrink the context
    between two calls. `context_tokens` must still report what the LAST call
    actually sent, so the UI diffs against reality rather than a high-water
    mark it can never reach again.
    """

    events = [
        ("updates", {"agent": {"messages": [_tool_call("call-1", 90_000)]}}),
        (
            "updates",
            {"tools": {"messages": [ToolMessage(content="ok", tool_call_id="call-1")]}},
        ),
        (
            "updates",
            {
                "agent": {
                    "messages": [
                        AIMessage(
                            content="done",
                            usage_metadata={
                                "input_tokens": 40_000,
                                "output_tokens": 10,
                                "total_tokens": 40_010,
                            },
                        )
                    ]
                }
            },
        ),
    ]

    (final,) = [
        e for e in await _run_stream(events) if isinstance(e, FinalRuntimeEvent)
    ]

    assert final.context_tokens == 40_000


@pytest.mark.asyncio
async def test_a_turn_cut_short_by_a_tool_error_still_reports_its_context() -> None:
    """
    When a whole round of tool calls fails, the error is surfaced directly as
    the final response and the LLM is never called again. The turn still
    reports the context of the one call it did make.
    """

    events = [
        ("updates", {"agent": {"messages": [_tool_call("call-1", 500)]}}),
        (
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content="Tool error:\nboom",
                            tool_call_id="call-1",
                            name="t",
                            artifact={"tool_ref": "t", "is_error": True},
                        )
                    ]
                }
            },
        ),
    ]

    (final,) = [
        e for e in await _run_stream(events) if isinstance(e, FinalRuntimeEvent)
    ]

    assert final.context_tokens == 500
