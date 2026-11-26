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
from typing import Any, cast
from unittest.mock import Mock

import httpx
import pytest
from fred_runtime.react.middleware import CheckpointHygieneMiddleware
from fred_runtime.react.middleware.tool_call_recovery import (
    ToolCallTextRecoveryMiddleware,
)
from fred_runtime.react.react_stream_adapter import decode_stream_chunk
from fred_runtime.support.reasoning_replay import (
    MistralReasoningReplayChatOpenAI,
    replays_native_reasoning,
    with_mistral_reasoning_replay,
    with_openai_reasoning,
)
from fred_runtime.support.thinking import (
    FLAT_REASONING_METADATA_KEY,
    RECALLED_REASONING_PREFIX,
    keep_native_reasoning,
    store_flat_reasoning,
    thread_reasoning_within_open_turn,
)
from fred_runtime.support.tool_loop import total_char_len
from fred_sdk.contracts.context import BoundRuntimeContext
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    message_chunk_to_message,
)
from langchain_core.messages.ai import add_ai_message_chunks
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from openai.types.chat import ChatCompletion

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


@pytest.mark.parametrize("replay", [False, True])
def test_vllm_reasoning_survives_the_openai_stream(replay: bool) -> None:
    deltas = [
        {"role": "assistant", "reasoning": "first "},
        {"reasoning": "again ", "reasoning_content": "duplicate"},
        {"content": "See "},
        {"reasoning_content": "then ", "content": "the "},
        {"content": "answer"},
        {
            "reasoning": "tool",
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_document", "arguments": "{}"},
                }
            ],
        },
    ]
    frames = [
        {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "mistral",
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        for delta in deltas
    ]
    sse = "".join(f"data: {json.dumps(frame)}\n\n" for frame in frames)
    sse += "data: [DONE]\n\n"

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, text=sse, headers={"content-type": "text/event-stream"}
            )
        )
    ) as http_client:
        model = ChatOpenAI(
            model="mistral",
            api_key=cast(Any, "test-key"),
            base_url="https://example.invalid/v1",
            http_client=http_client,
            http_socket_options=(),
            max_retries=0,
            timeout=2,
            stream_chunk_timeout=2,
        )
        if replay:
            model = with_mistral_reasoning_replay(model)
        model = with_openai_reasoning(model)
        chunks = [
            generation.message
            for generation in cast(ChatOpenAI, model)._stream([HumanMessage("Read it")])
        ]

    decoded = [decode_stream_chunk(chunk) for chunk in chunks]
    assert (
        "".join(fragment for item in decoded for fragment in item.thought_fragments)
        == "first again then tool"
    )
    assert "".join(item.text or "" for item in decoded) == "See the answer"
    assert all(isinstance(chunk, AIMessageChunk) for chunk in chunks)
    ai_chunks = cast(list[AIMessageChunk], chunks)
    combined = add_ai_message_chunks(ai_chunks[0], *ai_chunks[1:])
    assert combined.tool_calls[0]["id"] == "call-1"
    assert combined.content == "See the answer"
    saved = message_chunk_to_message(combined)
    assert isinstance(saved, AIMessage)
    store_flat_reasoning(saved)
    assert saved.content == [
        _thinking("first again then tool"),
        {"type": "text", "text": "See the answer"},
    ]
    assert "reasoning" not in saved.additional_kwargs
    # A gateway can use any model alias. Flat reasoning stays display-only
    # unless native replay was explicitly enabled on the selected profile.
    history = [HumanMessage("Read it"), saved]
    assert thread_reasoning_within_open_turn(history)[1].content == "See the answer"
    assert replays_native_reasoning(model) is replay
    if replay:
        wire = model._get_request_payload(history)["messages"]
        assert wire[1]["content"][0] == _thinking("first again then tool")


def test_vllm_reasoning_survives_a_nonstreamed_completion() -> None:
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "mistral",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "reasoning": "A plan",
                        "content": "The answer",
                    },
                }
            ],
        }
    )
    model = with_openai_reasoning(_chat("mistral"))
    message = model._create_chat_result(completion).generations[0].message

    assert message.content == [
        _thinking("A plan"),
        {"type": "text", "text": "The answer"},
    ]


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
    model = with_mistral_reasoning_replay(_chat("mistral-medium-latest"))

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


def test_only_opted_in_chat_openai_replays_reasoning() -> None:
    mistral = with_mistral_reasoning_replay(_chat("custom-alias"))
    other = with_openai_reasoning(_chat("mistral-medium-latest"))
    azure = AzureChatOpenAI(
        model="mistral-medium-latest",
        api_key=cast(Any, "test-key"),
        azure_endpoint="https://example.invalid",
        api_version="2024-10-21",
    )

    assert isinstance(mistral, MistralReasoningReplayChatOpenAI)
    assert replays_native_reasoning(mistral)
    assert not replays_native_reasoning(other)
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


@pytest.mark.asyncio
async def test_mistral_replay_defaults_off_for_existing_checkpoints() -> None:
    model = with_openai_reasoning(_chat("mistral"))
    seen = await _model_input(model)
    assert isinstance(model, ChatOpenAI)
    assert not replays_native_reasoning(model)
    wire = model._get_request_payload(seen)["messages"]
    assert wire[1]["content"] == "old answer"
    assert wire[3]["content"] is None
    assert wire[3]["tool_calls"][0]["id"] == wire[4]["tool_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_checkpoint_hygiene_stores_completed_flat_reasoning() -> None:
    middleware = CheckpointHygieneMiddleware(
        max_history_messages=None,
        binding=cast(BoundRuntimeContext, Mock()),
        kpi=None,
    )
    message = AIMessage(
        content="",
        tool_calls=[_CALL],
        additional_kwargs={"reasoning": "Read the doc"},
        response_metadata={FLAT_REASONING_METADATA_KEY: True},
    )

    async def handler(_: ModelRequest) -> ModelResponse:
        return ModelResponse(result=[message])

    response = await middleware.awrap_model_call(
        ModelRequest(
            model=_chat("mistral"), messages=[HumanMessage("What does it say?")]
        ),
        handler,
    )

    assert response.result[0].content == [_thinking("Read the doc")]
    assert message.tool_calls[0]["id"] == "call-1"
    assert "reasoning" not in message.additional_kwargs
