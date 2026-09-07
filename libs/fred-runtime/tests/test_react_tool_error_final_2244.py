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
from fred_runtime.react.react_runtime import (
    _GENERIC_TOOL_FAILURE_MESSAGE,
    _TransportBackedReActExecutor,
    _user_facing_tool_error_text,
)
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


def _raw_status_error_result(call_id: str, text: str) -> ToolMessage:
    """The shape a raised, uncaught tool exception takes today: LangGraph's
    own default `ToolNode` template, not Fred's `"Tool error:\\n"`
    convention — e.g. a built-in Workspace or MCP tool failure."""
    return ToolMessage(
        content=f"Error: {text}\n Please fix your mistakes.",
        tool_call_id=call_id,
        name="summarize_document",
        status="error",
    )


def _contradictory_result(call_id: str, text: str) -> ToolMessage:
    """`status="error"` with a present artifact whose `is_error` is `False` —
    the case a fallback-ternary classification would misclassify as success
    by never consulting `status`."""
    return ToolMessage(
        content=text,
        tool_call_id=call_id,
        name="summarize_document",
        status="error",
        artifact=ToolInvocationResult(
            tool_ref="summarize_document",
            is_error=False,
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
        ),
    )


def _content_divergent_error_result(
    call_id: str, safe_text: str, sensitive_content: str
) -> ToolMessage:
    """A typed `is_error=True` artifact with safe blocks, paired with a
    `content` field independently set to a different, sensitive string —
    the divergence `_resolve_runtime_provider_tool` can produce."""
    return ToolMessage(
        content=sensitive_content,
        tool_call_id=call_id,
        name="summarize_document",
        status="error",
        artifact=ToolInvocationResult(
            tool_ref="summarize_document",
            is_error=True,
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=safe_text),),
        ),
    )


def _blocks_empty_error_result(call_id: str, real_message: str) -> ToolMessage:
    """The shape a runtime-provider tool without populated `blocks` returns
    today (ppt_filler, html_artifact, writable_document): the real message
    lives only in `content`, and the `is_error=True` artifact has no blocks."""
    return ToolMessage(
        content=real_message,
        tool_call_id=call_id,
        name="ppt_filler",
        status="error",
        artifact=ToolInvocationResult(tool_ref="ppt_filler", is_error=True),
    )


def test_typed_error_artifact_is_rendered_via_render_tool_result() -> None:
    """Trusted case: text comes from `render_tool_result(artifact)`, with only
    Fred's own presentation prefix removed — never from `message.content`."""
    artifact = ToolInvocationResult(
        tool_ref="summarize_document",
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text="boom"),),
    )
    assert _user_facing_tool_error_text(artifact) == "boom"


def test_untyped_failure_without_artifact_is_the_generic_message() -> None:
    assert _user_facing_tool_error_text(None) == _GENERIC_TOOL_FAILURE_MESSAGE


def test_untyped_failure_with_non_erroring_artifact_is_the_generic_message() -> None:
    artifact = ToolInvocationResult(
        tool_ref="summarize_document",
        is_error=False,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text="boom"),),
    )
    assert _user_facing_tool_error_text(artifact) == _GENERIC_TOOL_FAILURE_MESSAGE


def test_typed_error_artifact_with_no_blocks_falls_back_to_generic_message() -> None:
    """An `is_error=True` artifact with no `blocks` renders to an empty
    string via `render_tool_result` — must fall back to the generic
    message, not surface that empty string."""
    artifact = ToolInvocationResult(tool_ref="ppt_filler", is_error=True)
    assert _user_facing_tool_error_text(artifact) == _GENERIC_TOOL_FAILURE_MESSAGE


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


@pytest.mark.asyncio
async def test_raw_status_error_with_no_artifact_still_surfaces_as_final() -> None:
    """The untyped shape (`status="error"`, `artifact=None`) still engages
    whole-round suppression, but its raw content must never reach either
    user-facing event — both collapse to the bounded generic message."""

    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1")]}}),
        (
            "updates",
            {"tools": {"messages": [_raw_status_error_result("c1", "boom")]}},
        ),
        (
            "updates",
            {
                "agent": {
                    "messages": [AIMessage(content="I published it successfully!")]
                }
            },
        ),
    ]

    collected = await _run_stream(events)

    assert _final(collected).content == _GENERIC_TOOL_FAILURE_MESSAGE
    errored = [
        e
        for e in collected
        if isinstance(e, ToolResultRuntimeEvent) and e.call_id == "c1"
    ]
    assert errored and errored[0].is_error is True
    assert errored[0].content == _GENERIC_TOOL_FAILURE_MESSAGE


@pytest.mark.asyncio
async def test_status_error_with_non_erroring_artifact_still_classified_as_error() -> (
    None
):
    """`status="error"` with a present artifact whose `is_error` is `False`
    must still classify as an error (true OR, not a fallback ternary), and
    both user-facing events must show the generic message, not raw content."""

    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1")]}}),
        (
            "updates",
            {"tools": {"messages": [_contradictory_result("c1", "boom")]}},
        ),
        (
            "updates",
            {
                "agent": {
                    "messages": [AIMessage(content="I published it successfully!")]
                }
            },
        ),
    ]

    collected = await _run_stream(events)

    assert _final(collected).content == _GENERIC_TOOL_FAILURE_MESSAGE
    errored = [
        e
        for e in collected
        if isinstance(e, ToolResultRuntimeEvent) and e.call_id == "c1"
    ]
    assert errored and errored[0].is_error is True
    assert errored[0].content == _GENERIC_TOOL_FAILURE_MESSAGE


@pytest.mark.asyncio
async def test_partial_round_raw_status_error_keeps_synthesis() -> None:
    """Partial-success semantics hold for the untyped shape too: a raw
    `status="error"` call alongside a successful typed sibling must not
    discard the LLM's synthesis."""

    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1", "c2")]}}),
        (
            "updates",
            {
                "tools": {
                    "messages": [
                        _raw_status_error_result("c1", "boom"),
                        _ok_result("c2", "summary two"),
                    ]
                }
            },
        ),
        ("updates", {"agent": {"messages": [AIMessage(content="Voici la synthèse.")]}}),
    ]

    collected = await _run_stream(events)

    assert _final(collected).content == "Voici la synthèse."
    errored = [
        e
        for e in collected
        if isinstance(e, ToolResultRuntimeEvent) and e.call_id == "c1"
    ]
    assert errored and errored[0].is_error is True
    assert errored[0].content == _GENERIC_TOOL_FAILURE_MESSAGE


@pytest.mark.asyncio
async def test_untyped_status_error_never_leaks_secret_or_langgraph_instruction() -> (
    None
):
    """A distinctive secret/token/path embedded in an untyped, untrusted
    failure's raw content must never reach either user-facing event — only
    the bounded generic message may."""

    secret_repr = "ValueError('sk-live-SECRET-TOKEN at /etc/shadow')"
    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1")]}}),
        (
            "updates",
            {"tools": {"messages": [_raw_status_error_result("c1", secret_repr)]}},
        ),
        ("updates", {"agent": {"messages": [AIMessage(content="Done, no issues!")]}}),
    ]

    collected = await _run_stream(events)

    final = _final(collected)
    errored = [
        e
        for e in collected
        if isinstance(e, ToolResultRuntimeEvent) and e.call_id == "c1"
    ]
    assert errored and errored[0].is_error is True
    for leaked in (
        "sk-live-SECRET-TOKEN",
        "/etc/shadow",
        "ValueError",
        "Please fix your mistakes",
    ):
        assert leaked not in final.content
        assert leaked not in errored[0].content
    assert final.content == _GENERIC_TOOL_FAILURE_MESSAGE
    assert errored[0].content == _GENERIC_TOOL_FAILURE_MESSAGE


@pytest.mark.asyncio
async def test_typed_error_ignores_divergent_message_content() -> None:
    """A typed `is_error=True` artifact with safe rendered blocks must be
    shown even when `message.content` independently carries a different,
    sensitive string — the shape `_resolve_runtime_provider_tool` can produce."""

    sensitive = "sk-live-SECRET-TOKEN /etc/shadow"
    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1")]}}),
        (
            "updates",
            {
                "tools": {
                    "messages": [
                        _content_divergent_error_result(
                            "c1", "safe Fred error text", sensitive
                        )
                    ]
                }
            },
        ),
        ("updates", {"agent": {"messages": [AIMessage(content="I handled it fine!")]}}),
    ]

    collected = await _run_stream(events)

    final = _final(collected)
    errored = [
        e
        for e in collected
        if isinstance(e, ToolResultRuntimeEvent) and e.call_id == "c1"
    ]
    assert errored and errored[0].is_error is True
    assert final.content == "safe Fred error text"
    assert errored[0].content == "safe Fred error text"
    assert sensitive not in final.content
    assert sensitive not in errored[0].content


@pytest.mark.asyncio
async def test_typed_error_with_empty_blocks_shows_generic_message_not_empty() -> None:
    """An is_error=True artifact with no blocks must not surface an empty
    string, and must not fall back to the real `message.content` either —
    it degrades to the bounded generic message."""

    real_message = "Could not fetch the PPT template 'X' after 3s [TimeoutError]."
    events = [
        ("updates", {"agent": {"messages": [_tool_calls_message("c1")]}}),
        (
            "updates",
            {"tools": {"messages": [_blocks_empty_error_result("c1", real_message)]}},
        ),
        ("updates", {"agent": {"messages": [AIMessage(content="Done!")]}}),
    ]

    collected = await _run_stream(events)

    final = _final(collected)
    errored = [
        e
        for e in collected
        if isinstance(e, ToolResultRuntimeEvent) and e.call_id == "c1"
    ]
    assert errored and errored[0].is_error is True
    assert final.content == _GENERIC_TOOL_FAILURE_MESSAGE
    assert errored[0].content == _GENERIC_TOOL_FAILURE_MESSAGE
    assert final.content != ""
    assert errored[0].content != real_message
