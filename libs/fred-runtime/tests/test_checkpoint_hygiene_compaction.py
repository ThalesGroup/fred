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

"""Model-request tests for ReAct history compaction."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fred_runtime.react.middleware.checkpoint_hygiene import (
    CheckpointHygieneMiddleware,
)
from fred_runtime.support.tool_loop import (
    ChatTurnTooLargeError,
    ChatTurnTooManyMessagesError,
)
from fred_sdk.contracts.context import BoundRuntimeContext
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def _middleware(
    *, max_messages: int = 500, max_chars: int = 200_000
) -> CheckpointHygieneMiddleware:
    return CheckpointHygieneMiddleware(
        max_history_messages=max_messages,
        max_history_chars=max_chars,
        binding=cast(BoundRuntimeContext, object()),
        kpi=None,
    )


def _request(messages: list[Any]) -> ModelRequest:
    return ModelRequest(
        model=cast(BaseChatModel, object()),
        messages=messages,
        state={"messages": messages},
    )


@pytest.mark.asyncio
async def test_large_tool_result_keeps_task_plan_and_followup() -> None:
    huge_result = "x" * 210_000
    messages = [
        SystemMessage(content="Leader context"),
        HumanMessage(content="Create an Excel workbook from my CSV"),
        AIMessage(
            content="",
            tool_calls=[{"name": "read_query", "args": {}, "id": "read"}],
        ),
        ToolMessage(content=huge_result, tool_call_id="read"),
        AIMessage(content="I will now create the workbook"),
        HumanMessage(content="continue"),
    ]
    request = _request(messages)
    seen: list[list[Any]] = []

    async def handler(current: ModelRequest) -> ModelResponse:
        seen.append(current.messages)
        return ModelResponse(result=[])

    await _middleware().awrap_model_call(request, handler)

    assert [message.content for message in seen[0]] == [
        "Leader context",
        "Create an Excel workbook from my CSV",
        "I will now create the workbook",
        "continue",
    ]
    assert request.messages == messages
    assert request.state == {"messages": messages}
    assert messages[3].content == huge_result


@pytest.mark.asyncio
async def test_serialized_state_keeps_full_history_for_next_turn() -> None:
    messages = [
        HumanMessage(content="Create an Excel workbook from my CSV"),
        AIMessage(content="", tool_calls=[{"name": "read", "args": {}, "id": "read"}]),
        ToolMessage(content="x" * 210_000, tool_call_id="read"),
        AIMessage(content="I will continue the workbook"),
        HumanMessage(content="continue"),
    ]
    request = _request(messages)
    seen: list[list[Any]] = []

    async def handler(current: ModelRequest) -> ModelResponse:
        seen.append(current.messages)
        return ModelResponse(result=[AIMessage(content="I am continuing")])

    response = await _middleware().awrap_model_call(request, handler)
    serializer = JsonPlusSerializer()
    checkpoint = serializer.dumps_typed([*request.state["messages"], *response.result])
    restored = serializer.loads_typed(checkpoint)
    assert restored[2].content == messages[2].content

    followup = _request([*restored, HumanMessage(content="keep going")])
    await _middleware().awrap_model_call(followup, handler)
    assert [message.content for message in seen[1]] == [
        "Create an Excel workbook from my CSV",
        "I will continue the workbook",
        "continue",
        "I am continuing",
        "keep going",
    ]


@pytest.mark.asyncio
async def test_active_tool_pair_is_preserved_during_compaction() -> None:
    messages = [
        HumanMessage(content="original task"),
        AIMessage(content="", tool_calls=[{"name": "read", "args": {}, "id": "old"}]),
        ToolMessage(content="x" * 1000, tool_call_id="old"),
        AIMessage(content="next step"),
        HumanMessage(content="continue"),
        AIMessage(
            content="", tool_calls=[{"name": "write", "args": {}, "id": "current"}]
        ),
        ToolMessage(content="ready", tool_call_id="current"),
    ]
    seen: list[list[Any]] = []

    async def handler(current: ModelRequest) -> ModelResponse:
        seen.append(current.messages)
        return ModelResponse(result=[])

    await _middleware(max_chars=100).awrap_model_call(_request(messages), handler)
    assert seen[0][:2] == [messages[0], messages[3]]
    assert seen[0][2:] == messages[4:]


@pytest.mark.asyncio
async def test_earlier_active_tool_rounds_can_make_room_for_latest_round() -> None:
    messages: list[Any] = [
        HumanMessage(content="Put my CSV files in an Excel workbook")
    ]
    for call_id in ("first", "second", "latest"):
        messages.extend(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "read_query", "args": {}, "id": call_id}],
                ),
                ToolMessage(content=call_id * 15_000, tool_call_id=call_id),
            ]
        )
    seen: list[list[Any]] = []

    async def handler(current: ModelRequest) -> ModelResponse:
        seen.append(current.messages)
        return ModelResponse(result=[])

    request = _request(messages)
    await _middleware(max_chars=100_000).awrap_model_call(request, handler)

    assert seen[0] == [messages[0], *messages[-2:]]
    assert request.messages == messages


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("messages", "max_messages", "max_chars", "error_type"),
    [
        ([HumanMessage(content="x" * 101)], 500, 100, ChatTurnTooLargeError),
        (
            [
                HumanMessage(content="x" * 101),
                AIMessage(content="plan"),
                HumanMessage(content="continue"),
            ],
            500,
            100,
            ChatTurnTooLargeError,
        ),
        (
            [
                HumanMessage(content="current"),
                AIMessage(content="one"),
                AIMessage(content="two"),
            ],
            2,
            200_000,
            ChatTurnTooManyMessagesError,
        ),
    ],
)
async def test_oversized_active_context_never_reaches_model(
    messages: list[Any], max_messages: int, max_chars: int, error_type: type[Exception]
) -> None:
    called = False

    async def handler(current: ModelRequest) -> ModelResponse:
        nonlocal called
        called = True
        return ModelResponse(result=[])

    with pytest.raises(error_type):
        await _middleware(
            max_messages=max_messages, max_chars=max_chars
        ).awrap_model_call(_request(messages), handler)
    assert not called
