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

"""Mistral reasoning stays in the replayed history; other models are unchanged."""

from __future__ import annotations

import json
import re
from typing import Any, cast
from unittest.mock import Mock

import httpx
import pytest
from fred_runtime.react.middleware import CheckpointHygieneMiddleware
from fred_runtime.react.middleware.tool_call_recovery import (
    ToolCallTextRecoveryMiddleware,
)
from fred_runtime.support.reasoning_replay import (
    MistralReasoningReplayChatOpenAI,
    replays_native_reasoning,
    with_mistral_reasoning_replay,
)
from fred_runtime.support.thinking import (
    RECALLED_REASONING_PREFIX,
    keep_native_reasoning,
)
from fred_runtime.support.tool_loop import total_char_len
from fred_sdk.contracts.context import BoundRuntimeContext
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

_CALL = {"name": "read_document", "args": {"uid": "doc-1"}, "id": "call-1"}


def _chat(model: str) -> ChatOpenAI:
    return ChatOpenAI(model=model, api_key=cast(Any, "test-key"))


def _streamed_reasoning(*deltas: str) -> list[str | dict[Any, Any]]:
    """One `thinking` block per streamed delta, as `AIMessageChunk.__add__` keeps them."""
    return [
        {"type": "thinking", "thinking": [{"type": "text", "text": delta}]}
        for delta in deltas
    ]


def _history() -> list[BaseMessage]:
    return [
        HumanMessage("first question"),
        AIMessage(content=[*_streamed_reasoning("old ", "plan"), "old answer"]),
        HumanMessage("second question"),
        AIMessage(
            content=[
                *_streamed_reasoning("read ", "the doc"),
                {"type": "reference", "reference_ids": []},
            ],
            tool_calls=[_CALL],
        ),
        ToolMessage("doc text", tool_call_id="call-1"),
    ]


def _thinking(text: str) -> dict[str, object]:
    return {"type": "thinking", "thinking": [{"type": "text", "text": text}]}


@pytest.mark.asyncio
@pytest.mark.parametrize("native_duplicate", [False, True])
@pytest.mark.parametrize("preamble", ["", "I will read the document.\n\n"])
async def test_recovered_call_keeps_reasoning_in_the_next_request(
    native_duplicate: bool, preamble: str
) -> None:
    @tool
    def read_document(uid: str) -> str:
        """Read a fake document."""
        return "document text"

    original = AIMessage(
        content=[
            *_streamed_reasoning("read ", "the doc"),
            {"type": "text", "text": f"{preamble}read_document"},
            {"type": "reference", "reference_ids": []},
            {"type": "text", "text": '{"uid":"doc-1"} } runaway text'},
        ],
        tool_calls=[_CALL] if native_duplicate else [],
        response_metadata={"model_name": "mistral-medium-latest"},
    )
    model = cast(
        BaseChatModel, with_mistral_reasoning_replay(_chat("mistral-medium-latest"))
    )

    async def respond(_: ModelRequest) -> ModelResponse:
        return ModelResponse(result=[original])

    recovered = (
        await ToolCallTextRecoveryMiddleware().awrap_model_call(
            ModelRequest(model=model, messages=[], tools=[read_document]), respond
        )
    ).result[0]
    assert isinstance(recovered, AIMessage)
    assert len(recovered.tool_calls) == 1
    call_id = recovered.tool_calls[0]["id"]
    assert call_id is not None
    if native_duplicate:
        assert call_id == "call-1"
    history: list[AnyMessage] = [
        HumanMessage("Read the document"),
        recovered,
        ToolMessage("document text", tool_call_id=call_id),
    ]
    payloads: list[dict[str, Any]] = []

    async def capture(request: ModelRequest) -> ModelResponse:
        payloads.append(
            cast(ChatOpenAI, request.model)._get_request_payload(request.messages)
        )
        return ModelResponse(result=[AIMessage("done")])

    await CheckpointHygieneMiddleware(
        max_history_messages=None,
        binding=cast(BoundRuntimeContext, Mock()),
        kpi=None,
    ).awrap_model_call(ModelRequest(model=model, messages=history), capture)

    wire = payloads[0]["messages"]
    expected_content = [_thinking("read the doc")]
    if preamble:
        expected_content.append({"type": "text", "text": preamble.strip()})
    assert wire[1]["content"] == expected_content
    assert wire[1]["tool_calls"][0]["id"] == wire[2]["tool_call_id"] == call_id
    assert original.content[0] == _thinking("read ")


def test_only_plain_mistral_chat_openai_replays_reasoning() -> None:
    mistral = with_mistral_reasoning_replay(_chat("mistral-medium-latest"))
    other = with_mistral_reasoning_replay(_chat("gpt-4o-mini"))
    azure = AzureChatOpenAI(
        model="mistral-medium-latest",
        api_key=cast(Any, "test-key"),
        azure_endpoint="https://example.invalid",
        api_version="2024-10-21",
    )

    assert isinstance(mistral, MistralReasoningReplayChatOpenAI)
    assert replays_native_reasoning(mistral)
    assert type(other) is ChatOpenAI and not replays_native_reasoning(other)
    assert with_mistral_reasoning_replay(azure) is azure
    assert not replays_native_reasoning(azure)


def test_keep_native_reasoning_shapes_every_turn_as_one_chunk() -> None:
    kept = keep_native_reasoning(_history())

    assert kept[1].content == [
        _thinking("old plan"),
        {"type": "text", "text": "old answer"},
    ]
    assert kept[3].content == [_thinking("read the doc")]
    assert cast(AIMessage, kept[3]).tool_calls[0]["id"] == "call-1"
    # Idempotent: the model client reshapes the same content again.
    assert keep_native_reasoning(kept) == kept
    # The size budget counts the replayed reasoning.
    assert total_char_len(kept) >= len("old planread the doc")


def test_mistral_payload_carries_reasoning_chunks() -> None:
    model = with_mistral_reasoning_replay(_chat("mistral-medium-latest"))
    assert isinstance(model, ChatOpenAI)

    payload = model._get_request_payload(keep_native_reasoning(_history()))

    wire = payload["messages"]
    assert wire[1]["content"] == [
        _thinking("old plan"),
        {"type": "text", "text": "old answer"},
    ]
    assert wire[3]["content"] == [_thinking("read the doc")]
    assert wire[3]["tool_calls"][0]["id"] == "call-1"
    assert wire[4] == {"role": "tool", "content": "doc text", "tool_call_id": "call-1"}


def test_other_payloads_still_drop_reasoning_blocks() -> None:
    payload = _chat("gpt-4o-mini")._get_request_payload(_history())

    assert "thinking" not in str(payload["messages"])


@pytest.mark.asyncio
async def test_mistral_replays_a_rejected_dotted_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @tool
    async def knowledge_search(query: str) -> str:
        """Search the available documents."""
        raise AssertionError("An unknown call must not execute the underscored tool.")

    @tool
    async def get_status() -> str:
        """Return the current status."""
        return "ready"

    call = AIMessage(
        content="",
        tool_calls=[
            {"name": "knowledge.search", "args": {"query": "q"}, "id": "call-1"},
            {"name": "get_status", "args": {}, "id": "call-2"},
        ],
    )
    builder = StateGraph(MessagesState)
    builder.add_node("tools", ToolNode([knowledge_search, get_status]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    tool_batch = await builder.compile().ainvoke({"messages": [call]})
    rejected, success = tool_batch["messages"][1:]
    assert isinstance(rejected, ToolMessage) and isinstance(success, ToolMessage)
    assert rejected.status == "error"
    assert success.content == "ready"
    history = [
        HumanMessage("Search for q"),
        call,
        rejected,
        success,
        HumanMessage("Retry"),
    ]
    sent: list[list[dict[str, Any]]] = []

    def mock_provider(request: httpx.Request) -> httpx.Response:
        messages = json.loads(request.content)["messages"]
        sent.append(messages)
        if any(
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", call["function"]["name"])
            for message in messages
            for call in message.get("tool_calls", [])
        ):
            return httpx.Response(400, json={"message": "Bad Request", "detail": ""})
        return httpx.Response(
            200,
            json={
                "id": "response",
                "model": "mistral",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "I can retry."},
                    }
                ],
            },
        )

    monkeypatch.setattr("openai._base_client.get_platform", lambda: "Linux")
    with httpx.Client(transport=httpx.MockTransport(mock_provider)) as http:
        model = with_mistral_reasoning_replay(
            ChatOpenAI(model="mistral", api_key=cast(Any, "test-key"), http_client=http)
        )
        assert isinstance(model, ChatOpenAI)
        response = model.bind_tools([knowledge_search, get_status]).invoke(history)

    assert response.content == "I can retry."
    calls = sent[0][1]["tool_calls"]
    replayed_name = calls[0]["function"]["name"]
    assert replayed_name not in {"knowledge.search", "knowledge_search"}
    assert calls[0]["id"] == sent[0][2]["tool_call_id"] == "call-1"
    assert sent[0][2]["content"].startswith(
        f"Error: {replayed_name} is not a valid tool"
    )
    assert calls[1]["id"] == sent[0][3]["tool_call_id"] == "call-2"
    assert calls[1]["function"]["name"] == "get_status"
    assert sent[0][3]["content"] == "ready"
    assert call.tool_calls[0]["name"] == "knowledge.search"
    assert isinstance(rejected.content, str)
    assert rejected.content.startswith("Error: knowledge.search is not a valid tool")
    other_payload = _chat("gpt-4o-mini")._get_request_payload(history)
    other_call = other_payload["messages"][1]["tool_calls"][0]
    assert other_call["function"]["name"] == "knowledge.search"


def test_mistral_replay_scopes_reused_call_ids_and_keeps_legacy_messages() -> None:
    call_id = "call-1"
    raw_call = {
        "type": "function",
        "id": call_id,
        "function": {"name": "docs.search", "arguments": "{}"},
    }
    legacy_call = AIMessage(content="").model_copy(
        update={"additional_kwargs": {"tool_calls": [raw_call]}}
    )
    history = [
        HumanMessage("Find a document"),
        legacy_call,
        ToolMessage(
            "Error: docs.search is not a valid tool, try one of [get_status].",
            tool_call_id=call_id,
        ),
        HumanMessage("Find a meeting"),
        AIMessage(
            content="",
            tool_calls=[{"name": "calendar.search", "id": call_id, "args": {}}],
        ),
        ToolMessage(
            "Error: calendar.search is not a valid tool, try one of [get_status].",
            tool_call_id=call_id,
        ),
    ]
    model = with_mistral_reasoning_replay(_chat("mistral"))
    assert isinstance(model, ChatOpenAI)

    wire = model._get_request_payload(history)["messages"]

    for index, expected in [(1, "docs_search"), (4, "calendar_search")]:
        assert wire[index]["tool_calls"][0]["function"]["name"] == expected
        assert wire[index + 1]["content"] == (
            f"Error: {expected} is not a valid tool, try one of [get_status]."
        )
    assert raw_call["function"] == {"name": "docs.search", "arguments": "{}"}
    other_wire = _chat("gpt-4o-mini")._get_request_payload(history)["messages"]
    assert other_wire[1]["tool_calls"][0]["function"]["name"] == "docs.search"


async def _model_input(model: object) -> list[BaseMessage]:
    middleware = CheckpointHygieneMiddleware(
        max_history_messages=None,
        binding=cast(BoundRuntimeContext, Mock()),
        kpi=None,
    )
    seen: list[BaseMessage] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.extend(request.messages)
        return ModelResponse(result=[AIMessage(content="done")])

    request = ModelRequest(
        model=cast(BaseChatModel, model), messages=cast(list[AnyMessage], _history())
    )
    await middleware.awrap_model_call(request, handler)
    return seen


@pytest.mark.asyncio
async def test_hygiene_keeps_mistral_reasoning_in_every_turn() -> None:
    seen = await _model_input(
        with_mistral_reasoning_replay(_chat("mistral-small-latest"))
    )

    assert seen[1].content[0] == _thinking("old plan")  # closed turn
    assert seen[3].content == [_thinking("read the doc")]  # open turn
    assert RECALLED_REASONING_PREFIX not in str(seen)


@pytest.mark.asyncio
async def test_hygiene_keeps_text_rehoming_for_other_models() -> None:
    seen = await _model_input(_chat("gpt-4o-mini"))

    assert seen[1].content == "old answer"
    assert seen[3].content == f"{RECALLED_REASONING_PREFIX}read the doc"
