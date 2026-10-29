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

from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import Mock

import pytest
from fred_core.kpi import BaseKPIWriter
from fred_runtime.react.middleware import hitl as hitl_module
from fred_runtime.react.middleware.hitl import FredHitlMiddleware
from fred_runtime.react.middleware.tool_call_recovery import (
    MAX_TOOL_CALL_RECOVERY_NAME_CHARS,
    ToolCallTextRecoveryMiddleware,
)
from fred_runtime.runtime_support.ask_user import AskUserArgs
from fred_runtime.support.thinking import content_to_text
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ToolApprovalPolicy
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool, tool


@tool
def query_tabular_documents(sql: str, dataset_uids: list[str]) -> str:
    """Read fake tabular rows."""

    return "fake rows"


@tool
def search_documents(question: str, top_k: int) -> str:
    """Search fake documents."""

    return "fake hits"


@tool
def query(sql: str, dataset_uids: list[str]) -> str:
    """Read fake rows through a shorter tool name."""

    return "fake rows"


@tool
def list_tabular_documents() -> str:
    """List fake tabular documents."""

    return "fake document"


@tool
def task(description: str, subagent_type: str) -> str:
    """Run a fake delegated task."""

    return "fake task"


@tool
def ls(path: str) -> str:
    """List a fake directory."""

    return "fake-file.md"


@tool
def write_todos(todos: list[dict[str, str]]) -> str:
    """Write fake todo items."""

    return "fake todos"


@tool
def send_email(to: str) -> str:
    """Send a fake email."""

    return f"sent to {to}"


_ALL_TOOLS: list[BaseTool] = [
    query_tabular_documents,
    search_documents,
    list_tabular_documents,
    task,
    ls,
    write_todos,
]


def _structured_call_content(
    name: str,
    arguments_and_followups: str,
    *,
    preamble: str = "",
) -> list[str | dict[Any, Any]]:
    return [
        {"type": "text", "text": f"{preamble}{name}"},
        {"type": "reference", "reference_ids": []},
        {"type": "text", "text": arguments_and_followups},
    ]


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


async def _recover_message(
    message: AIMessage, *, tools: list[BaseTool] | None = None
) -> tuple[ModelResponse, AIMessage]:
    middleware = ToolCallTextRecoveryMiddleware()
    request = ModelRequest(
        model=cast(BaseChatModel, None),
        messages=[],
        tools=cast(list[BaseTool | dict[str, Any]], tools or _ALL_TOOLS),
    )
    response = ModelResponse(result=[message])

    async def handler(_: ModelRequest) -> ModelResponse:
        return response

    return await middleware.awrap_model_call(request, handler), message


@pytest.mark.asyncio
async def test_completed_mistral_tool_call_text_becomes_a_native_call() -> None:
    middleware = ToolCallTextRecoveryMiddleware()
    request = ModelRequest(
        model=cast(BaseChatModel, None), messages=[], tools=[query_tabular_documents]
    )
    response = ModelResponse(
        result=[
            AIMessage(
                content=_structured_call_content(
                    "query_tabular_documents",
                    '{"sql": "SELECT 1", "dataset_uids": ["fake-dataset"]}',
                ),
                response_metadata={"model_name": "mistral-medium-latest"},
            )
        ]
    )

    async def handler(_: ModelRequest) -> ModelResponse:
        return response

    recovered = await middleware.awrap_model_call(request, handler)

    message = recovered.result[0]
    assert isinstance(message, AIMessage)
    assert message.content == ""
    assert [(call["name"], call["args"]) for call in message.tool_calls] == [
        (
            "query_tabular_documents",
            {"sql": "SELECT 1", "dataset_uids": ["fake-dataset"]},
        )
    ]


def _question_tool() -> BaseTool:
    async def invoke(**payload: Any) -> str:
        return ""

    return StructuredTool.from_function(
        coroutine=invoke,
        name="ask_user",
        description="Ask the user a question.",
        args_schema=AskUserArgs,
    )


@pytest.mark.asyncio
async def test_marked_questions_with_literal_line_breaks_recover_all_calls() -> None:
    content: list[str | dict[str, object]] = [
        {"type": "text", "text": "ask_user"},
        {"type": "reference", "reference_ids": []},
        {
            "type": "text",
            "text": (
                '{"question":"\nWhich island?","choices":[{"id":"one","label":"One"}],'
                '"allow_free_text":true} ask_user'
                '{"question":"Which hotel?","allow_free_text":true} ask_user'
            ),
        },
        {"type": "reference", "reference_ids": []},
        {
            "type": "text",
            "text": (
                '{"question":"\r\nHow long?","allow_free_text":true} ask_user'
                '{"question":"What budget?","allow_free_text":true}'
            ),
        },
    ]
    original = AIMessage(
        content=content,
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[_question_tool()])

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert recovered.content == ""
    assert [call["args"]["question"] for call in recovered.tool_calls] == [
        "\nWhich island?",
        "Which hotel?",
        "\r\nHow long?",
        "What budget?",
    ]
    assert len({call["id"] for call in recovered.tool_calls}) == 4
    assert all("tool_call_id" not in call["args"] for call in recovered.tool_calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        '{"question":"Which\t island?","allow_free_text":true}',
        '{"question":"Which island?","allow_free_text":true,"unexpected":1}',
        '{"question":"Which island?","allow_free_text":true,"tool_call_id":"spoof"}',
        (
            '{"question":"Which island?","choices":['
            '{"id":"same","label":"First"},{"id":"same","label":"Second"}]}'
        ),
    ],
)
async def test_marked_question_rejects_other_invalid_arguments(arguments: str) -> None:
    original = AIMessage(
        content=_structured_call_content("ask_user", arguments),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[_question_tool()])

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
async def test_recovery_counts_only_reconstructed_calls_by_model() -> None:
    kpi = Mock(spec=BaseKPIWriter)
    middleware = ToolCallTextRecoveryMiddleware(kpi=kpi)
    configured_model = Mock(spec=BaseChatModel)
    configured_model.model_name = "mistral-medium-configured"
    request = ModelRequest(
        model=cast(BaseChatModel, configured_model),
        messages=[],
        tools=[ls, list_tabular_documents],
    )
    response = ModelResponse(
        result=[
            AIMessage(
                content=_structured_call_content(
                    "ls", '{"path":"/"} list_tabular_documents{}'
                ),
                response_metadata={"model_name": "mistral-medium-latest"},
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "ls", "args": {"path": "/"}, "id": "native"}],
                response_metadata={"model_name": "mistral-medium-latest"},
            ),
        ]
    )

    async def handler(_: ModelRequest) -> ModelResponse:
        return response

    await middleware.awrap_model_call(request, handler)

    kpi.count.assert_called_once()
    args, kwargs = kpi.count.call_args
    assert args == ("agent.tool_call_text_recovered_total", 2)
    assert kwargs["dims"] == {"model_name": "mistral-medium-configured"}


@pytest.mark.asyncio
async def test_longest_registered_tool_name_wins_for_suffix_overlap() -> None:
    original = AIMessage(
        content=_structured_call_content(
            "query_tabular_documents", '{"sql":"SELECT 1","dataset_uids":["fake"]}'
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(
        original, tools=[query, query_tabular_documents]
    )

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert [call["name"] for call in recovered.tool_calls] == [
        "query_tabular_documents"
    ]


@pytest.mark.asyncio
async def test_tool_name_attached_to_an_identifier_is_not_recovered() -> None:
    original = AIMessage(
        content=_structured_call_content(
            "prefixquery_tabular_documents",
            '{"sql":"SELECT 1","dataset_uids":["fake"]}',
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[query_tabular_documents])

    assert response.result[0] is original


@pytest.mark.asyncio
async def test_illustrative_tool_call_text_is_not_recovered() -> None:
    middleware = ToolCallTextRecoveryMiddleware()
    request = ModelRequest(
        model=cast(BaseChatModel, None), messages=[], tools=[query_tabular_documents]
    )
    original = AIMessage(
        content=(
            "Example:\n\n"
            'query_tabular_documents{"sql": "SELECT 1", '
            '"dataset_uids": ["fake-dataset"]}'
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    async def handler(_: ModelRequest) -> ModelResponse:
        return ModelResponse(result=[original])

    response = await middleware.awrap_model_call(request, handler)

    assert response.result == [original]
    assert original.tool_calls == []


@pytest.mark.asyncio
async def test_duplicate_json_keys_are_not_recovered() -> None:
    original = AIMessage(
        content=[
            {"type": "text", "text": "query_tabular_documents"},
            {"type": "reference", "reference_ids": []},
            {
                "type": "text",
                "text": (
                    '{"sql": "SELECT 1", "sql": "SELECT 2", '
                    '"dataset_uids": ["fake-dataset"]}'
                ),
            },
        ],
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
async def test_unknown_argument_is_not_recovered() -> None:
    original = AIMessage(
        content=_structured_call_content("ls", '{"path":"/","unexpected":"value"}'),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[ls])

    assert response.result[0] is original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        [
            {"type": "text", "text": "query_tabular_documents"},
            {"type": "reference", "reference_ids": ["document-1"]},
            {
                "type": "text",
                "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}',
            },
        ],
        [
            {"type": "text", "text": "query_tabular_documents"},
            {"type": "reference", "reference_ids": [], "title": "example"},
            {
                "type": "text",
                "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}',
            },
        ],
        [
            {"type": "text", "text": "query_tabular_documents"},
            {"type": "reference", "reference_ids": []},
            {"type": "reference", "reference_ids": []},
            {
                "type": "text",
                "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}',
            },
        ],
    ],
    ids=[
        "ordinary_citation",
        "reference_extra_field",
        "multiple_references",
    ],
)
async def test_only_exact_empty_reference_sentinel_is_recovered(
    content: str | list[str | dict[Any, Any]],
) -> None:
    original = AIMessage(
        content=content,
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
async def test_recover_valid_calls_keeps_only_the_prose_before_the_first_call() -> None:
    original = AIMessage(
        content=_structured_call_content(
            "query_tabular_documents",
            '{"sql":"SELECT 1","dataset_uids":["fake"]}'
            "\nChecking another dataset.\n"
            'ls{"path":"/"}'
            "\nDone.",
            preamble="I will inspect the data.\n\n",
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert recovered.content == "I will inspect the data."
    assert [call["name"] for call in recovered.tool_calls] == [
        "query_tabular_documents",
        "ls",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preamble",
    ["Example only:\n\n", "Do not execute the following instruction.\n\n"],
)
async def test_exact_typed_call_recovers_despite_instructional_preamble(
    preamble: str,
) -> None:
    original = AIMessage(
        content=_structured_call_content(
            "query_tabular_documents",
            '{"sql":"SELECT 1","dataset_uids":["fake"]}',
            preamble=preamble,
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert recovered.content == preamble.strip()
    assert [call["name"] for call in recovered.tool_calls] == [
        "query_tabular_documents"
    ]


@pytest.mark.asyncio
async def test_invalid_followup_is_dropped_while_later_valid_call_recovers() -> None:
    original = AIMessage(
        content=_structured_call_content(
            "ls",
            '{"path":"/"} query_tabular_documents{"sql":} ls{"path":"/tmp"}',
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert recovered.content == ""
    assert [call["args"] for call in recovered.tool_calls] == [
        {"path": "/"},
        {"path": "/tmp"},
    ]


@pytest.mark.asyncio
async def test_deeply_nested_json_remains_assistant_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = ("[" * 2_000) + "0" + ("]" * 2_000)

    def recursion_overflow(*_: object, **__: object) -> object:
        raise RecursionError("nested JSON overflow")

    monkeypatch.setattr(
        "fred_runtime.react.middleware.tool_call_recovery._JSON_DECODER.raw_decode",
        recursion_overflow,
    )
    original = AIMessage(
        content=_structured_call_content("ls", f'{{"path":{nested}}}'),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[ls])

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        _structured_call_content("ls", '{"path":"' + ("x" * 16_385) + '"}'),
        _structured_call_content(
            "ls",
            '{"path":"/"}' + ('ls{"path":"/"}' * 16),
        ),
        [
            {"type": "text", "text": "ls"},
            {"type": "reference", "reference_ids": []},
            {"type": "text", "text": '{"path":"'},
            "x" * 16_385,
            '"}',
        ],
    ],
    ids=["character_cap", "call_cap", "mixed_character_cap"],
)
async def test_recovery_caps_reject_before_creating_calls(
    content: str | list[str | dict[Any, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_uuid() -> None:
        pytest.fail("rejected representations must not allocate call ids")

    monkeypatch.setattr(
        "fred_runtime.react.middleware.tool_call_recovery.uuid.uuid4",
        unexpected_uuid,
    )
    original = AIMessage(
        content=content,
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[ls])

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected_content", "expected_calls"),
    [
        (
            [
                {"type": "thinking", "thinking": "<redacted>"},
                {"type": "text", "text": "read"},
                {"type": "text", "text": "_query"},
                {"type": "reference", "reference_ids": []},
                {
                    "type": "text",
                    "text": (
                        '{"sql": "SELECT * FROM fake_table LIMIT 5", '
                        '"dataset_uids": ["fake-dataset"]} '
                        "list_tabular_documents{}"
                    ),
                },
            ],
            "",
            [
                (
                    "query_tabular_documents",
                    {
                        "sql": "SELECT * FROM fake_table LIMIT 5",
                        "dataset_uids": ["fake-dataset"],
                    },
                ),
                ("list_tabular_documents", {}),
            ],
        ),
        (
            [
                {"type": "thinking", "thinking": "<redacted>"},
                {
                    "type": "text",
                    "text": "Plan de découpage en cinq lots.\n\ntask",
                },
                {"type": "reference", "reference_ids": []},
                {
                    "type": "text",
                    "text": (
                        '{"description": "fake rows 1-100", '
                        '"subagent_type": "general-purpose"}'
                        'task{"description": "fake rows 101-200", '
                        '"subagent_type": "general-purpose"}'
                    ),
                },
            ],
            "Plan de découpage en cinq lots.",
            [
                (
                    "task",
                    {
                        "description": "fake rows 1-100",
                        "subagent_type": "general-purpose",
                    },
                ),
                (
                    "task",
                    {
                        "description": "fake rows 101-200",
                        "subagent_type": "general-purpose",
                    },
                ),
            ],
        ),
        (
            [
                {"type": "thinking", "thinking": "<redacted>"},
                {"type": "text", "text": "ls"},
                {"type": "reference", "reference_ids": []},
                {
                    "type": "text",
                    "text": (
                        '{"path": "/"}'
                        'write_todos{"todos": ['
                        '{"content": "lot 1", "status": "completed"}, '
                        '{"content": "lot 5", "status": "in_progress"}]}'
                    ),
                },
            ],
            "",
            [
                ("ls", {"path": "/"}),
                (
                    "write_todos",
                    {
                        "todos": [
                            {"content": "lot 1", "status": "completed"},
                            {"content": "lot 5", "status": "in_progress"},
                        ]
                    },
                ),
            ],
        ),
    ],
    ids=["query_then_catalog", "two_delegated_tasks", "list_then_update_todos"],
)
async def test_reconstructed_incidents_recover_every_complete_call_once(
    content: str | list[str | dict[Any, Any]],
    expected_content: str,
    expected_calls: list[tuple[str, dict[str, object]]],
) -> None:
    response, _ = await _recover_message(
        AIMessage(
            content=content,
            response_metadata={"model_name": "mistral-medium-latest"},
        )
    )

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == expected_content
    assert [(call["name"], call["args"]) for call in recovered.tool_calls] == (
        expected_calls
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected_calls"),
    [
        (
            [
                {"type": "thinking", "thinking": "<redacted>"},
                {"type": "text", "text": "read"},
                "_query",
                {"type": "reference", "reference_ids": []},
                {"type": "text", "text": '{"sql": "'},
                'SELECT COUNT(*) FROM fake_fleet", "dataset_uids": ["fake-dataset"]} '
                + 'query_tabular_documents{"sql": "SELECT COUNT(*) FROM fake_vehicles", '
                + '"dataset_uids": ["fake-dataset"]}',
            ],
            [
                (
                    "query_tabular_documents",
                    {
                        "sql": "SELECT COUNT(*) FROM fake_fleet",
                        "dataset_uids": ["fake-dataset"],
                    },
                ),
                (
                    "query_tabular_documents",
                    {
                        "sql": "SELECT COUNT(*) FROM fake_vehicles",
                        "dataset_uids": ["fake-dataset"],
                    },
                ),
            ],
        ),
        (
            [
                {"type": "thinking", "thinking": "<redacted>"},
                {"type": "text", "text": "search"},
                "_documents_using_vectorization",
                {"type": "reference", "reference_ids": []},
                {"type": "text", "text": '{"question": "'},
                'fleet size", "top_k": 5} '
                + 'search_documents{"question": "rental fleet", "top_k": 5}',
            ],
            [
                (
                    "search_documents",
                    {"question": "fleet size", "top_k": 5},
                ),
                (
                    "search_documents",
                    {"question": "rental fleet", "top_k": 5},
                ),
            ],
        ),
    ],
    ids=["mixed_tabular_query", "mixed_vector_search"],
)
async def test_mixed_checkpoint_fragments_recover_two_calls(
    content: list[str | dict[str, Any]],
    expected_calls: list[tuple[str, dict[str, object]]],
) -> None:
    response, _ = await _recover_message(
        AIMessage(
            content=content, response_metadata={"model_name": "mistral-medium-latest"}
        )
    )

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == ""
    assert [
        (call["name"], call["args"]) for call in recovered.tool_calls
    ] == expected_calls


@tool
def build_presentation(
    file_name: str | None = None,
    slides: list[dict[str, Any]] | None = None,
    changes: list[dict[str, Any]] | None = None,
) -> str:
    """Build or revise a fake deck."""

    return "fake deck"


def _streamed_content(deltas: list[str | dict[str, Any]]) -> list[str | dict[Any, Any]]:
    """Aggregate one-block deltas the way a streamed model call does."""

    message = AIMessageChunk(content="")
    for delta in deltas:
        message += AIMessageChunk(content=[delta])
    assert isinstance(message.content, list)
    return message.content


@pytest.mark.asyncio
async def test_streamed_call_with_one_block_per_delta_is_recovered() -> None:
    # Reasoning streams one block per delta: a long turn ends with far more
    # blocks than calls, and the recovery must still see the call.
    first_args = (
        '{"changes": [{"op": "replace", "slide": 2, '
        '"slides": [{"kind": "agenda", "title": "Fake agenda"}]}]}'
    )
    second_call = (
        'build_presentation{"file_name": "fake_deck", '
        '"slides": [{"kind": "cover", "title": "Fake deck"}]}'
    )
    tail = f"{first_args}}} {second_call}"
    content = _streamed_content(
        [
            *(
                {"type": "thinking", "thinking": [{"type": "text", "text": "x"}]}
                for _ in range(400)
            ),
            {"type": "text", "text": "build_"},
            {"type": "text", "text": "presentation"},
            {"type": "reference", "reference_ids": []},
            *(
                {"type": "text", "text": tail[i : i + 4]}
                for i in range(0, len(tail), 4)
            ),
        ]
    )
    assert len(content) > 400

    response, _ = await _recover_message(
        AIMessage(
            content=content, response_metadata={"model_name": "mistral-medium-latest"}
        ),
        tools=[build_presentation],
    )

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    # The over-closing brace after the first call is not shown as content.
    assert content_to_text(recovered.content) == ""
    assert [(call["name"], call["args"]) for call in recovered.tool_calls] == [
        ("build_presentation", json.loads(first_args)),
        (
            "build_presentation",
            {
                "file_name": "fake_deck",
                "slides": [{"kind": "cover", "title": "Fake deck"}],
            },
        ),
    ]


@pytest.mark.asyncio
async def test_streamed_call_with_empty_blocks_between_deltas_is_recovered() -> None:
    args = '{"file_name": "fake_deck", "slides": [{"kind": "cover", "title": "Fake"}]}'
    content = _streamed_content(
        [
            {"type": "text", "text": "build_"},
            {},
            {"type": "text", "text": "presentation"},
            {"type": "signature"},
            {"type": "reference", "reference_ids": []},
            {},
            *(
                {"type": "text", "text": args[i : i + 8]}
                for i in range(0, len(args), 8)
            ),
            {},
        ]
    )

    response, _ = await _recover_message(
        AIMessage(
            content=content, response_metadata={"model_name": "mistral-medium-latest"}
        ),
        tools=[build_presentation],
    )

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert recovered.content == ""
    assert [(call["name"], call["args"]) for call in recovered.tool_calls] == [
        ("build_presentation", json.loads(args))
    ]


@pytest.mark.asyncio
async def test_plain_answer_with_literal_braces_stays_text() -> None:
    content = _streamed_content(
        [
            {"type": "text", "text": "Pass an empty object to reset the deck:\n"},
            {},
            {"type": "text", "text": "```python\nbuild_presentation({})\n```"},
        ]
    )
    original = AIMessage(
        content=content, response_metadata={"model_name": "mistral-medium-latest"}
    )

    response, _ = await _recover_message(original, tools=[build_presentation])

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
async def test_repeated_exact_markers_recover_four_valid_calls() -> None:
    args = [
        {"sql": f"SELECT {index}", "dataset_uids": ["fake-dataset"]}
        for index in range(1, 5)
    ]
    content: list[str | dict[str, Any]] = [
        {"type": "thinking", "thinking": "<redacted>"},
        {"type": "text", "text": "read"},
        "_query",
        {"type": "reference", "reference_ids": []},
        {"type": "text", "text": json.dumps(args[0])},
        f" query_tabular_documents{json.dumps(args[1])} query_tabular_documents",
        {"type": "reference", "reference_ids": []},
        {"type": "text", "text": json.dumps(args[2])},
        f" query_tabular_documents{json.dumps(args[3])}",
    ]

    response, _ = await _recover_message(
        AIMessage(
            content=content, response_metadata={"model_name": "mistral-medium-latest"}
        ),
        tools=[query_tabular_documents],
    )

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == ""
    assert [(call["name"], call["args"]) for call in recovered.tool_calls] == [
        ("query_tabular_documents", item) for item in args
    ]


@pytest.mark.asyncio
async def test_repeated_markers_obey_total_call_cap() -> None:
    content: list[str | dict[str, object]] = [
        {"type": "text", "text": "query_tabular_documents"}
    ]
    for index in range(17):
        content.extend(
            [
                {"type": "reference", "reference_ids": []},
                {
                    "type": "text",
                    "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}'
                    + (" query_tabular_documents" if index < 16 else ""),
                },
            ]
        )
    original = AIMessage(
        content=content,
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[query_tabular_documents])

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("between", "later_marker", "later_args"),
    [
        (
            "",
            {"type": "reference", "reference_ids": []},
            '{"sql":"SELECT 2","dataset_uids":["fake"]}',
        ),
        (
            " unknown_tool",
            {"type": "reference", "reference_ids": []},
            '{"sql":"SELECT 2","dataset_uids":["fake"]}',
        ),
        (
            " query_tabular_documents",
            {"type": "reference", "reference_ids": ["citation"]},
            '{"sql":"SELECT 2","dataset_uids":["fake"]}',
        ),
        (
            " query_tabular_documents",
            {"type": "reference", "reference_ids": []},
            '{"sql":,"dataset_uids":["fake"]}',
        ),
    ],
    ids=["adjacent", "unknown_tool", "modified_reference", "invalid_later_json"],
)
async def test_invalid_later_marker_rejects_all_calls(
    between: str, later_marker: dict[str, object], later_args: str
) -> None:
    original = AIMessage(
        content=[
            {"type": "text", "text": "query_tabular_documents"},
            {"type": "reference", "reference_ids": []},
            {
                "type": "text",
                "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}' + between,
            },
            later_marker,
            later_args,
        ],
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[query_tabular_documents])

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "model_name"),
    [
        (
            [
                {"type": "text", "text": "read"},
                "_query",
                {"type": "reference", "reference_ids": [], "title": "example"},
                {"type": "text", "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}'},
            ],
            "mistral-medium-latest",
        ),
        (
            [
                {"type": "text", "text": "read"},
                "_query",
                {"type": "reference", "reference_ids": []},
                {"type": "text", "text": '{"sql":'},
                ',"dataset_uids":["fake"]}',
            ],
            "mistral-medium-latest",
        ),
        (
            [
                {"type": "text", "text": "read"},
                "_query",
                {"type": "reference", "reference_ids": []},
                {"type": "text", "text": '{"sql":"SELECT 1",'},
                '"dataset_uids":["fake"],"unexpected":1}',
            ],
            "mistral-medium-latest",
        ),
        (
            [
                {"type": "text", "text": "Example: read"},
                '_query{"sql":"SELECT 1","dataset_uids":["fake"]}',
            ],
            "mistral-medium-latest",
        ),
        (
            [
                {"type": "text", "text": "read"},
                "_query",
                {"type": "reference", "reference_ids": []},
                {"type": "text", "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}'},
            ],
            "gpt-5",
        ),
    ],
    ids=[
        "modified_reference",
        "malformed_json",
        "schema_invalid",
        "ordinary_text",
        "other_provider",
    ],
)
async def test_invalid_mixed_fragments_do_not_recover(
    content: list[str | dict[str, Any]], model_name: str
) -> None:
    original = AIMessage(content=content, response_metadata={"model_name": model_name})

    response, _ = await _recover_message(original, tools=[query_tabular_documents])

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "model_name"),
    [
        (
            'I might call query_tabular_documents{"sql": "SELECT 1", "dataset_uids": ["fake"]}',
            "mistral-medium-latest",
        ),
        (
            '`query_tabular_documents{"sql": "SELECT 1", "dataset_uids": ["fake"]}`',
            "mistral-medium-latest",
        ),
        (
            'Do not execute this\n\nsend_email{"to":"person@example.invalid"}',
            "mistral-medium-latest",
        ),
        (_structured_call_content("unknown_tool", "{}"), "mistral-medium-latest"),
        (
            _structured_call_content("query_tabular_documents", '{"sql": }'),
            "mistral-medium-latest",
        ),
        (
            _structured_call_content("query_tabular_documents", '{"sql": "SELECT 1"'),
            "mistral-medium-latest",
        ),
        (
            _structured_call_content("query_tabular_documents", '{"sql": "SELECT 1"}'),
            "mistral-medium-latest",
        ),
        ("This is an ordinary answer.", "mistral-medium-latest"),
        (
            'query_tabular_documents[reference]{"sql": "SELECT 1", "dataset_uids": ["fake"]}',
            "mistral-medium-latest",
        ),
        (
            _structured_call_content(
                "query_tabular_documents",
                '{"sql": "SELECT 1", "dataset_uids": ["fake"]}',
            ),
            "gpt-5",
        ),
    ],
    ids=[
        "ambiguous_prose",
        "quoted_example",
        "instructional_prose",
        "unknown_tool",
        "malformed_json",
        "partial_json",
        "schema_invalid",
        "ordinary_text",
        "exporter_placeholder",
        "other_provider",
    ],
)
async def test_ambiguous_or_invalid_content_remains_assistant_text(
    content: str | list[str | dict[Any, Any]], model_name: str
) -> None:
    original = AIMessage(
        content=content,
        response_metadata={"model_name": model_name},
    )

    response, _ = await _recover_message(original)

    assert response.result[0] is original
    assert original.tool_calls == []


@pytest.mark.asyncio
async def test_native_duplicate_calls_are_preserved_after_the_text_call() -> None:
    native_calls = [
        {"name": "ls", "args": {"path": "/"}, "id": "call-1"},
        {"name": "ls", "args": {"path": "/"}, "id": "call-2"},
    ]
    original = AIMessage(
        content=[
            {"type": "text", "text": "read"},
            "_query",
            {"type": "reference", "reference_ids": []},
            {"type": "text", "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}'},
        ],
        tool_calls=native_calls,
        response_metadata={"model_name": "mistral-medium-latest"},
    )
    before = [dict(call) for call in original.tool_calls]

    response, _ = await _recover_message(original)

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert recovered.content == ""
    assert [call["name"] for call in recovered.tool_calls] == [
        "query_tabular_documents",
        "ls",
        "ls",
    ]
    assert recovered.tool_calls[1:] == before


@tool
def read_document(
    document_uid: str, offset: int = 0, max_chars: int | None = None
) -> str:
    """Read a fake document."""

    return "fake text"


_REFERENCE: dict[str, Any] = {"type": "reference", "reference_ids": []}


def _leaked_content(
    name_head: str, name_tail: str, *texts: str | dict[str, Any]
) -> list[str | dict[str, Any]]:
    """The leaked shape: thinking deltas, a split name, the reference, then text."""

    split = [
        piece
        for text in texts
        for piece in (
            [text]
            if isinstance(text, dict)
            else [{"type": "text", "text": text[:12]}, text[12:]]
        )
    ]
    return [
        "",
        *({"type": "thinking", "thinking": "<redacted>"} for _ in range(3)),
        {"type": "text", "text": name_head},
        name_tail,
        _REFERENCE,
        *split,
    ]


_DECK_CHANGES = {
    "file_name": "fake_deck",
    "changes": [{"op": "replace", "slide": 2, "slides": [{"title": "Fake"}]}],
}
_DECK_SLIDES = {"file_name": "fake_deck", "slides": [{"title": "Fake cover"}]}


@pytest.mark.asyncio
async def test_duplicate_text_and_native_call_keeps_one_call_and_clears_content() -> (
    None
):
    native = {"name": "build_presentation", "args": _DECK_CHANGES, "id": "call-1"}
    original = AIMessage(
        content=_leaked_content(
            "build",
            "_presentation",
            json.dumps(_DECK_CHANGES) + ']"}] } } } ######\n---------- ----------',
        ),
        tool_calls=[native],
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[build_presentation])

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == ""
    assert recovered.tool_calls == [{**native, "type": "tool_call"}]


@pytest.mark.asyncio
async def test_distinct_text_and_native_calls_are_both_kept_text_first() -> None:
    original = AIMessage(
        content=_leaked_content(
            "build", "_presentation", json.dumps(_DECK_CHANGES) + " } }"
        ),
        tool_calls=[
            {"name": "build_presentation", "args": _DECK_SLIDES, "id": "call-1"}
        ],
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[build_presentation])

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == ""
    assert [(call["args"], call["id"]) for call in recovered.tool_calls] == [
        (_DECK_CHANGES, recovered.tool_calls[0]["id"]),
        (_DECK_SLIDES, "call-1"),
    ]
    assert (recovered.tool_calls[0]["id"] or "").startswith("recovered-")


@pytest.mark.asyncio
async def test_sentence_ending_in_dot_then_tool_name_anchors_next_call() -> None:
    def read(offset: int) -> str:
        return json.dumps(
            {"document_uid": "fake-doc", "offset": offset, "max_chars": 5000}
        )

    looping = "\n\n\n+++++ internal tasks + history. I will read the next part."
    original = AIMessage(
        content=_leaked_content(
            "read",
            "_document",
            read(5000) + looping + "read_document",
            _REFERENCE,
            read(10000) + looping + "read_document",
            _REFERENCE,
            read(15000) + looping,
        ),
        tool_calls=[
            {
                "name": "I'll read the final section now. >>> read_document",
                "args": json.loads(read(20000)),
                "id": "call-1",
            }
        ],
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[read_document])

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == ""
    assert [
        (call["name"], call["args"]["offset"]) for call in recovered.tool_calls
    ] == [
        ("read_document", 5000),
        ("read_document", 10000),
        ("read_document", 15000),
        ("read_document", 20000),
    ]


@pytest.mark.asyncio
async def test_two_calls_back_to_back_after_one_reference() -> None:
    changes = {"changes": _DECK_CHANGES["changes"]}
    original = AIMessage(
        content=_leaked_content(
            "build",
            "_presentation",
            json.dumps(changes) + "build_presentation" + json.dumps(_DECK_SLIDES),
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[build_presentation])

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == ""
    assert [call["args"] for call in recovered.tool_calls] == [changes, _DECK_SLIDES]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runaway",
    [
        "\n\n\n+++++ .gitignore\n\n\n+++++ .gitignore.orig.orig",
        "} {} {} {} {}",
        " I will read the document. I will read the document. I will read it.",
        ' } }\n```json\n{"file_name": "fake_deck_v2',
    ],
    ids=["diff_headers", "empty_objects", "looping_prose", "half_second_call"],
)
async def test_runaway_text_after_recovered_call_is_dropped(runaway: str) -> None:
    original = AIMessage(
        content=_leaked_content(
            "Let me read it.\n\nread",
            "_document",
            '{"document_uid": "fake-doc"}' + runaway,
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[read_document])

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == "Let me read it."
    assert [call["args"] for call in recovered.tool_calls] == [
        {"document_uid": "fake-doc"}
    ]


@pytest.mark.asyncio
async def test_registered_dotted_name_wins_over_its_suffix_at_the_anchor() -> None:
    dotted = StructuredTool.from_function(
        func=lambda document_uid: "fake text",
        name="ns.read_document",
        description="Read a fake namespaced document.",
    )
    original = AIMessage(
        content=_leaked_content(
            "Reading.ns.read", "_document", '{"document_uid": "fake-doc"}'
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[read_document, dotted])

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert content_to_text(recovered.content) == "Reading."
    assert [call["name"] for call in recovered.tool_calls] == ["ns.read_document"]


@pytest.mark.asyncio
async def test_invalid_text_call_next_to_a_native_call_leaves_the_message() -> None:
    original = AIMessage(
        content=_leaked_content(
            "read", "_document", '{"document_uid": "fake-doc", "page": 2}'
        ),
        tool_calls=[
            {"name": "read_document", "args": {"document_uid": "x"}, "id": "c-1"}
        ],
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[read_document])

    assert response.result[0] is original


@pytest.mark.asyncio
async def test_native_call_with_looped_name_keeps_its_trailing_registered_tool() -> (
    None
):
    looped = '{"path": "/"}' + " repeat the plan" * 400 + " >>> ls"
    original = AIMessage(
        content="",
        tool_calls=[{"name": looped, "args": {"path": "/"}, "id": "call-1"}],
        response_metadata={"model_name": "gpt-4o"},
    )

    response, _ = await _recover_message(original)

    message = response.result[0]
    assert isinstance(message, AIMessage)
    assert [(c["name"], c["args"], c["id"]) for c in message.tool_calls] == [
        ("ls", {"path": "/"}, "call-1")
    ]
    assert original.tool_calls[0]["name"] == looped


@pytest.mark.asyncio
async def test_unknown_native_call_name_is_only_clipped_for_the_tool_error() -> None:
    original = AIMessage(
        content="",
        tool_calls=[
            {"name": "x" * 6000, "args": {}, "id": "call-1"},
            {"name": "not_a_tool", "args": {}, "id": "call-2"},
            {"name": "ls", "args": {"path": "/"}, "id": "call-3"},
        ],
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    message = response.result[0]
    assert isinstance(message, AIMessage)
    assert [c["name"] for c in message.tool_calls] == [
        "x" * MAX_TOOL_CALL_RECOVERY_NAME_CHARS,
        "not_a_tool",
        "ls",
    ]


@pytest.mark.asyncio
async def test_registered_native_call_names_leave_the_message_untouched() -> None:
    original = AIMessage(
        content="",
        tool_calls=[{"name": "ls", "args": {"path": "/"}, "id": "call-1"}],
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    assert response.result[0] is original


@pytest.mark.asyncio
async def test_recovery_is_exactly_once_for_the_completed_message() -> None:
    first, _ = await _recover_message(
        AIMessage(
            content=_structured_call_content("ls", '{"path": "/"}'),
            response_metadata={"model_name": "mistral-medium-latest"},
        )
    )
    recovered = first.result[0]
    assert isinstance(recovered, AIMessage)
    call_ids = [call["id"] for call in recovered.tool_calls]

    second, _ = await _recover_message(recovered)

    assert second.result[0] is recovered
    assert [call["id"] for call in recovered.tool_calls] == call_ids
    assert len(recovered.tool_calls) == 1


@pytest.mark.asyncio
async def test_disabled_recovery_preserves_the_no_execution_baseline() -> None:
    middleware = ToolCallTextRecoveryMiddleware(enabled=False)
    original = AIMessage(
        content=_structured_call_content("ls", '{"path": "/"}'),
        response_metadata={"model_name": "mistral-medium-latest"},
    )
    response = ModelResponse(result=[original])

    async def handler(_: ModelRequest) -> ModelResponse:
        return response

    result = await middleware.awrap_model_call(
        ModelRequest(model=cast(BaseChatModel, None), messages=[], tools=[ls]),
        handler,
    )

    assert result is response
    assert result.result == [original]
    assert original.tool_calls == []


@pytest.mark.asyncio
async def test_recovered_call_reaches_the_existing_hitl_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response, _ = await _recover_message(
        AIMessage(
            content=[
                {"type": "text", "text": "send"},
                "_email",
                {"type": "reference", "reference_ids": []},
                {"type": "text", "text": '{"to":"'},
                'person@example.invalid"}',
            ],
            response_metadata={"model_name": "mistral-medium-latest"},
        ),
        tools=[send_email],
    )
    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    captured: list[dict[str, object]] = []

    def approve(payload: object) -> dict[str, str]:
        assert isinstance(payload, dict)
        captured.append(payload)
        return {"choice_id": "proceed"}

    monkeypatch.setattr(hitl_module, "interrupt", approve)
    gate = FredHitlMiddleware(
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(
            enabled=True,
            always_require_tools=("send_email",),
        ),
        available_tool_names={"send_email"},
    )

    update = await gate.aafter_model({"messages": [recovered]}, None)  # type: ignore[arg-type]

    assert update is None
    assert len(captured) == 1
    assert captured[0]["pending_calls"] == [
        {
            "tool_call_id": recovered.tool_calls[0]["id"],
            "tool_name": "send_email",
            "args_preview": '{"to": "person@example.invalid"}',
        }
    ]


@pytest.mark.asyncio
async def test_recovered_call_reaches_the_existing_run_budget() -> None:
    response, _ = await _recover_message(
        AIMessage(
            content=[
                {"type": "text", "text": "l"},
                "s",
                {"type": "reference", "reference_ids": []},
                {"type": "text", "text": '{"path":"'},
                '/"}',
            ],
            response_metadata={"model_name": "mistral-medium-latest"},
        )
    )
    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    limiter = ToolCallLimitMiddleware(run_limit=1, exit_behavior="continue")

    update = await limiter.aafter_model(
        {
            "messages": [recovered],
            "run_tool_call_count": {"__all__": 1},
        },
        None,  # type: ignore[arg-type]
    )

    assert update is not None
    blocked = update["messages"]
    assert len(blocked) == 1
    assert isinstance(blocked[0], ToolMessage)
    assert blocked[0].status == "error"
    assert blocked[0].tool_call_id == recovered.tool_calls[0]["id"]
