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
Unit tests for the streaming protocol contract between:

1. _legacy_events_from_runtime_event (session_agent.py)
   Tests the conversion from v2 typed RuntimeEvent objects to the legacy
   LangGraph-shaped tuples/dicts consumed by the StreamTranscoder.

2. _apply_openai_stream_usage_default (factory.py)
   Tests that OpenAI-compatible model construction always enables:
   - streaming=True  → causes LangChain to use SSE and fire on_llm_new_token
   - stream_usage=True → includes token counts in the streaming response
   and that explicit opt-outs in agent config are respected.

These tests lock the streaming contract so that the agentic-pod branch
migration to HTTP SSE and new libs does not silently regress it.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.tool import ToolMessage

from agentic_backend.core.agents.v2.runtime_support.session_agent import (
    _legacy_events_from_runtime_event,
    _requested_stream_modes,
)
from agentic_backend.core.agents.v2.contracts.runtime import (
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    FinalRuntimeEvent,
    HumanChoiceOption,
    HumanInputRequest,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
)
from fred_core.model.factory import _apply_openai_stream_usage_default

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_MODES = frozenset({"messages", "updates"})
_MESSAGES_ONLY = frozenset({"messages"})
_UPDATES_ONLY = frozenset({"updates"})


def _delta_event(delta: str) -> AssistantDeltaRuntimeEvent:
    return AssistantDeltaRuntimeEvent(sequence=0, delta=delta)


def _tool_call_event(
    tool_name: str = "search",
    call_id: str = "c1",
    args: dict | None = None,
) -> ToolCallRuntimeEvent:
    return ToolCallRuntimeEvent(
        sequence=1,
        tool_name=tool_name,
        call_id=call_id,
        arguments=args or {},
    )


def _tool_result_event(
    tool_name: str = "search",
    call_id: str = "c1",
    content: str = "result",
    is_error: bool = False,
) -> ToolResultRuntimeEvent:
    return ToolResultRuntimeEvent(
        sequence=2,
        tool_name=tool_name,
        call_id=call_id,
        content=content,
        is_error=is_error,
        sources=(),
        ui_parts=(),
    )


def _final_event(
    content: str = "The answer.",
    model_name: str | None = "gpt-test",
    token_usage: dict | None = None,
) -> FinalRuntimeEvent:
    return FinalRuntimeEvent(
        sequence=3,
        content=content,
        sources=(),
        ui_parts=(),
        model_name=model_name,
        token_usage=token_usage,
        finish_reason="stop",
    )


def _awaiting_human_event() -> AwaitingHumanRuntimeEvent:
    return AwaitingHumanRuntimeEvent(
        sequence=4,
        request=HumanInputRequest(
            stage="tool_approval",
            title="Confirm",
            question="Run this tool?",
            choices=(
                HumanChoiceOption(id="proceed", label="Yes", default=True),
                HumanChoiceOption(id="cancel", label="No"),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# 1. AssistantDeltaRuntimeEvent → "messages" legacy event
# ---------------------------------------------------------------------------


def test_assistant_delta_produces_messages_mode_event() -> None:
    """
    AssistantDeltaRuntimeEvent must become a ("messages", (AIMessageChunk, metadata))
    tuple so the StreamTranscoder can process it as a streaming token chunk.
    """
    legacy = _legacy_events_from_runtime_event(
        _delta_event("Hello "), requested_modes=_ALL_MODES
    )

    assert len(legacy) == 1
    event = legacy[0]
    assert isinstance(event, tuple)
    mode, payload = event
    assert mode == "messages"
    assert isinstance(payload, tuple) and len(payload) == 2
    chunk, meta = payload
    assert isinstance(chunk, AIMessageChunk)
    assert chunk.content == "Hello "
    assert isinstance(meta, dict)
    assert "langgraph_node" in meta


def test_assistant_delta_filtered_when_messages_mode_not_requested() -> None:
    """Delta events must be suppressed when only 'updates' mode is requested."""
    legacy = _legacy_events_from_runtime_event(
        _delta_event("Hello"), requested_modes=_UPDATES_ONLY
    )
    assert legacy == []


def test_assistant_delta_included_when_messages_mode_requested() -> None:
    """Delta events must pass through when 'messages' is in requested modes."""
    legacy = _legacy_events_from_runtime_event(
        _delta_event("Hi"), requested_modes=_MESSAGES_ONLY
    )
    assert len(legacy) == 1


def test_assistant_delta_node_is_agent() -> None:
    """The langgraph_node metadata for delta events must be 'agent' (not 'tools')."""
    legacy = _legacy_events_from_runtime_event(
        _delta_event("x"), requested_modes=_ALL_MODES
    )
    _, (_, meta) = legacy[0]
    assert meta.get("langgraph_node") == "agent"


# ---------------------------------------------------------------------------
# 2. ToolCallRuntimeEvent → "updates" legacy event
# ---------------------------------------------------------------------------


def test_tool_call_produces_updates_mode_event() -> None:
    """
    ToolCallRuntimeEvent must become an 'updates' dict with an AIMessage
    carrying tool_calls — this is what the transcoder reads to emit a
    tool_call ChatMessage.
    """
    legacy = _legacy_events_from_runtime_event(
        _tool_call_event("lookup", "c42", {"q": "test"}),
        requested_modes=_ALL_MODES,
    )

    assert len(legacy) == 1
    event = legacy[0]
    assert isinstance(event, dict)
    # The dict must contain an agent node key
    assert len(event) == 1
    node_key = next(iter(event))
    payload = event[node_key]
    assert "messages" in payload
    msgs = payload["messages"]
    assert len(msgs) == 1
    msg = msgs[0]
    assert isinstance(msg, AIMessage)
    assert msg.tool_calls
    tc = msg.tool_calls[0]
    assert tc.get("id") == "c42"
    assert tc.get("name") == "lookup"
    assert tc.get("args") == {"q": "test"}


def test_tool_call_filtered_when_updates_not_requested() -> None:
    """Tool call events are updates-mode and must be suppressed when only messages requested."""
    legacy = _legacy_events_from_runtime_event(
        _tool_call_event(), requested_modes=_MESSAGES_ONLY
    )
    assert legacy == []


# ---------------------------------------------------------------------------
# 3. ToolResultRuntimeEvent → "updates" legacy event
# ---------------------------------------------------------------------------


def test_tool_result_produces_updates_mode_event() -> None:
    """
    ToolResultRuntimeEvent must become an 'updates' dict with a ToolMessage —
    the transcoder reads this to emit a tool_result ChatMessage and set
    tool_activity_seen=True.
    """
    legacy = _legacy_events_from_runtime_event(
        _tool_result_event("search", "c1", "The capital is Paris"),
        requested_modes=_ALL_MODES,
    )

    assert len(legacy) == 1
    event = legacy[0]
    assert isinstance(event, dict)
    node_key = next(iter(event))
    payload = event[node_key]
    msgs = payload.get("messages", [])
    assert len(msgs) == 1
    msg = msgs[0]
    assert isinstance(msg, ToolMessage)
    assert msg.content == "The capital is Paris"
    assert msg.tool_call_id == "c1"
    assert msg.name == "search"


def test_tool_result_filtered_when_updates_not_requested() -> None:
    legacy = _legacy_events_from_runtime_event(
        _tool_result_event(), requested_modes=_MESSAGES_ONLY
    )
    assert legacy == []


# ---------------------------------------------------------------------------
# 4. FinalRuntimeEvent → "updates" legacy event
# ---------------------------------------------------------------------------


def test_final_event_produces_updates_mode_event() -> None:
    """
    FinalRuntimeEvent must become an 'updates' dict with a final AIMessage —
    the transcoder uses this to build the pending_assistant_final ChatMessage.
    """
    legacy = _legacy_events_from_runtime_event(
        _final_event("Done!", model_name="gpt-4o"),
        requested_modes=_ALL_MODES,
    )

    assert len(legacy) == 1
    event = legacy[0]
    assert isinstance(event, dict)
    node_key = next(iter(event))
    payload = event[node_key]
    msgs = payload.get("messages", [])
    assert len(msgs) == 1
    msg = msgs[0]
    assert isinstance(msg, AIMessage)
    assert msg.content == "Done!"
    # model_name must appear in response_metadata so the transcoder can pick it up
    assert msg.response_metadata.get("model_name") == "gpt-4o"


def test_final_event_carries_token_usage_in_response_metadata() -> None:
    usage = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    legacy = _legacy_events_from_runtime_event(
        _final_event("Answer.", token_usage=usage),
        requested_modes=_ALL_MODES,
    )
    event = legacy[0]
    node_key = next(iter(event))
    msg = event[node_key]["messages"][0]
    assert isinstance(msg, AIMessage)
    # token_usage must be in response_metadata for the transcoder
    assert msg.response_metadata.get("token_usage") == usage


def test_final_event_filtered_when_updates_not_requested() -> None:
    legacy = _legacy_events_from_runtime_event(
        _final_event(), requested_modes=_MESSAGES_ONLY
    )
    assert legacy == []


# ---------------------------------------------------------------------------
# 5. AwaitingHumanRuntimeEvent → "__interrupt__" updates event
# ---------------------------------------------------------------------------


def test_awaiting_human_produces_interrupt_event() -> None:
    """
    AwaitingHumanRuntimeEvent must become an 'updates' dict with key
    '__interrupt__' so the transcoder can detect and handle HITL payloads.
    """
    legacy = _legacy_events_from_runtime_event(
        _awaiting_human_event(), requested_modes=_ALL_MODES
    )

    assert len(legacy) == 1
    event = legacy[0]
    assert isinstance(event, dict)
    assert "__interrupt__" in event


def test_awaiting_human_filtered_when_updates_not_requested() -> None:
    legacy = _legacy_events_from_runtime_event(
        _awaiting_human_event(), requested_modes=_MESSAGES_ONLY
    )
    assert legacy == []


# ---------------------------------------------------------------------------
# 6. _requested_stream_modes helper
# ---------------------------------------------------------------------------


def test_requested_modes_from_list() -> None:
    modes = _requested_stream_modes(["messages", "updates"])
    assert "messages" in modes
    assert "updates" in modes


def test_requested_modes_from_string() -> None:
    modes = _requested_stream_modes("updates")
    assert modes == frozenset({"updates"})


def test_requested_modes_default_to_updates() -> None:
    """Unrecognised input falls back to updates-only."""
    modes = _requested_stream_modes(None)
    assert modes == frozenset({"updates"})


# ---------------------------------------------------------------------------
# 7. _apply_openai_stream_usage_default (factory.py)
# ---------------------------------------------------------------------------


def test_streaming_true_is_set_by_default() -> None:
    """
    The factory must inject streaming=True for OpenAI models when the caller
    has not provided an explicit value. This enables SSE token-by-token
    streaming in LangChain and fires on_llm_new_token callbacks that
    LangGraph's stream_mode='messages' relies on.
    """
    settings: dict = {}
    _apply_openai_stream_usage_default(settings)
    assert settings["streaming"] is True


def test_stream_usage_true_is_set_by_default() -> None:
    """
    stream_usage=True must be injected to include token counts in the SSE
    response. Without this, usage metadata is absent on the final message.
    """
    settings: dict = {}
    _apply_openai_stream_usage_default(settings)
    assert settings["stream_usage"] is True


def test_explicit_streaming_false_is_preserved() -> None:
    """
    An operator can opt out of streaming by setting streaming: false in the
    agent YAML (e.g. for gateways that don't support SSE). This must be
    respected — setdefault must not override an explicit False.
    """
    settings = {"streaming": False}
    _apply_openai_stream_usage_default(settings)
    assert settings["streaming"] is False


def test_explicit_stream_usage_false_is_preserved() -> None:
    """
    stream_usage: false opt-out must be preserved, e.g. when a provider
    does not support the usage-in-stream OpenAI extension.
    """
    settings = {"stream_usage": False}
    _apply_openai_stream_usage_default(settings)
    assert settings["stream_usage"] is False


def test_existing_streaming_true_not_overwritten() -> None:
    """setdefault must be idempotent when streaming is already True."""
    settings = {"streaming": True}
    _apply_openai_stream_usage_default(settings)
    assert settings["streaming"] is True


def test_other_settings_are_not_modified() -> None:
    """The function must leave unrelated model settings intact."""
    settings = {"temperature": 0.5, "max_retries": 3}
    _apply_openai_stream_usage_default(settings)
    assert settings["temperature"] == 0.5
    assert settings["max_retries"] == 3


def test_both_streaming_defaults_applied_together() -> None:
    """Both streaming and stream_usage defaults must be applied in one call."""
    settings: dict = {}
    _apply_openai_stream_usage_default(settings)
    assert "streaming" in settings
    assert "stream_usage" in settings
    assert settings["streaming"] is True
    assert settings["stream_usage"] is True
