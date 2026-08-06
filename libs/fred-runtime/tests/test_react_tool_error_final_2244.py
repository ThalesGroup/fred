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
Regression tests for the tool-error final-response policy (issue #2244).

Why this exists:
- the ReAct stream loop surfaces an `is_error=True` tool result verbatim as
  the final response and discards the LLM's own synthesis ("the LLM is NOT
  trusted to relay it"). That is right when the whole round of tool calls
  failed — but observed live, one 403 out of six parallel summarize calls
  (a folder tag id mistaken for a document uid) threw away five successful
  summaries and showed the user only the raw error text.
- policy under test: an error claims the final response only while no call
  of the same round has succeeded; any success — a parallel sibling or a
  later round's recovery — hands the final response back to the LLM's
  synthesis, with the error still visible to it as an ordinary tool result.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    FinalRuntimeEvent,
    ToolResultRuntimeEvent,
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


def _tool_calls_message(*call_ids: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"id": call_id, "name": "summarize_document", "args": {}}
            for call_id in call_ids
        ],
    )


def _error_result(call_id: str, text: str) -> ToolMessage:
    return ToolMessage(
        content=f"Tool error:\n{text}",
        tool_call_id=call_id,
        name="summarize_document",
        artifact=ToolInvocationResult(
            tool_ref="summarize_document",
            is_error=True,
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
        ),
    )


def _ok_result(call_id: str, text: str) -> ToolMessage:
    return ToolMessage(
        content=text,
        tool_call_id=call_id,
        name="summarize_document",
        artifact=ToolInvocationResult(
            tool_ref="summarize_document",
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
        ),
    )


def _final(collected: list[object]) -> FinalRuntimeEvent:
    finals = [e for e in collected if isinstance(e, FinalRuntimeEvent)]
    assert len(finals) == 1
    return finals[0]


@pytest.mark.asyncio
async def test_partial_round_failure_keeps_llm_synthesis_as_final() -> None:
    """The live #2244 shape: parallel batch, the error arrives BEFORE the
    successes — one failure must not discard the successful siblings'
    synthesis."""

    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1", "c2", "c3")]}}),
        (
            "updates",
            {
                "tools": {
                    "messages": [
                        _error_result("c1", "403 on folder id"),
                        _ok_result("c2", "summary two"),
                        _ok_result("c3", "summary three"),
                    ]
                }
            },
        ),
        ("updates", {"agent": {"messages": [AIMessage(content="Voici la synthèse.")]}}),
    ]

    collected = await _run_stream(events)

    assert _final(collected).content == "Voici la synthèse."
    # The failed call is still reported as failed in the trace — restoring the
    # synthesis must not repaint the error result as ok.
    errored = [
        e
        for e in collected
        if isinstance(e, ToolResultRuntimeEvent) and e.call_id == "c1"
    ]
    assert errored and errored[0].is_error is True


@pytest.mark.asyncio
async def test_partial_round_failure_error_after_success_keeps_synthesis() -> None:
    """Parallel results arrive in arbitrary order: an error landing AFTER a
    successful sibling must not claim the final response either."""

    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1", "c2")]}}),
        (
            "updates",
            {
                "tools": {
                    "messages": [
                        _ok_result("c1", "summary one"),
                        _error_result("c2", "403 on folder id"),
                    ]
                }
            },
        ),
        ("updates", {"agent": {"messages": [AIMessage(content="Voici la synthèse.")]}}),
    ]

    collected = await _run_stream(events)

    assert _final(collected).content == "Voici la synthèse."


@pytest.mark.asyncio
async def test_wholly_failed_round_still_surfaces_error_as_final() -> None:
    """The pre-#2244 guarantee stays: when every call of the round failed, the
    LLM is not trusted to relay the failure — the error text IS the final
    response (with the LLM-facing "Tool error:" prefix stripped)."""

    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1")]}}),
        ("updates", {"tools": {"messages": [_error_result("c1", "403 Forbidden")]}}),
        (
            "updates",
            {"agent": {"messages": [AIMessage(content="I could not do it, sorry!")]}},
        ),
    ]

    collected = await _run_stream(events)

    assert _final(collected).content == "403 Forbidden"


@pytest.mark.asyncio
async def test_error_then_recovery_in_later_round_restores_synthesis() -> None:
    """A failed round followed by a successful retry (the recovery path the
    §8.27 prompt suffix asks for) must end on the LLM's answer, not on the
    stale first-round error."""

    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1")]}}),
        ("updates", {"tools": {"messages": [_error_result("c1", "bad uid")]}}),
        ("updates", {"agent": {"messages": [_tool_calls_message("c2")]}}),
        ("updates", {"tools": {"messages": [_ok_result("c2", "summary")]}}),
        (
            "updates",
            {"agent": {"messages": [AIMessage(content="Here is the summary.")]}},
        ),
    ]

    collected = await _run_stream(events)

    assert _final(collected).content == "Here is the summary."


@pytest.mark.asyncio
async def test_success_then_wholly_failed_round_surfaces_error() -> None:
    """A success in an EARLIER round must not shield a later wholly-failed
    round: each round's outcome is judged on its own results."""

    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1")]}}),
        ("updates", {"tools": {"messages": [_ok_result("c1", "info")]}}),
        ("updates", {"agent": {"messages": [_tool_calls_message("c2")]}}),
        ("updates", {"tools": {"messages": [_error_result("c2", "boom")]}}),
        ("updates", {"agent": {"messages": [AIMessage(content="babble")]}}),
    ]

    collected = await _run_stream(events)

    assert _final(collected).content == "boom"
