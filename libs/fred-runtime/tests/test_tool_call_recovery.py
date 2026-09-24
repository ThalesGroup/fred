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

from typing import Any, cast

import pytest
from fred_runtime.react.middleware import hitl as hitl_module
from fred_runtime.react.middleware.hitl import FredHitlMiddleware
from fred_runtime.react.middleware.tool_call_recovery import (
    ToolCallTextRecoveryMiddleware,
)
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
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool, tool


@tool
def read_query(sql: str, dataset_uids: list[str]) -> str:
    """Read fake tabular rows."""

    return "fake rows"


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


_ALL_TOOLS: list[BaseTool] = [read_query, list_tabular_documents, task, ls, write_todos]


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
        model=cast(BaseChatModel, None), messages=[], tools=[read_query]
    )
    response = ModelResponse(
        result=[
            AIMessage(
                content=_structured_call_content(
                    "read_query",
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
            "read_query",
            {"sql": "SELECT 1", "dataset_uids": ["fake-dataset"]},
        )
    ]


@pytest.mark.asyncio
async def test_longest_registered_tool_name_wins_for_suffix_overlap() -> None:
    original = AIMessage(
        content=_structured_call_content(
            "read_query", '{"sql":"SELECT 1","dataset_uids":["fake"]}'
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[query, read_query])

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert [call["name"] for call in recovered.tool_calls] == ["read_query"]


@pytest.mark.asyncio
async def test_tool_name_attached_to_an_identifier_is_not_recovered() -> None:
    original = AIMessage(
        content=_structured_call_content(
            "prefixread_query", '{"sql":"SELECT 1","dataset_uids":["fake"]}'
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original, tools=[read_query])

    assert response.result[0] is original


@pytest.mark.asyncio
async def test_illustrative_tool_call_text_is_not_recovered() -> None:
    middleware = ToolCallTextRecoveryMiddleware()
    request = ModelRequest(
        model=cast(BaseChatModel, None), messages=[], tools=[read_query]
    )
    original = AIMessage(
        content=(
            "Example:\n\n"
            'read_query{"sql": "SELECT 1", '
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
            {"type": "text", "text": "read_query"},
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
            {"type": "text", "text": "read_query"},
            {"type": "reference", "reference_ids": ["document-1"]},
            {
                "type": "text",
                "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}',
            },
        ],
        [
            {"type": "text", "text": "read_query"},
            {"type": "reference", "reference_ids": [], "title": "example"},
            {
                "type": "text",
                "text": '{"sql":"SELECT 1","dataset_uids":["fake"]}',
            },
        ],
        [
            {"type": "text", "text": "read_query"},
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
async def test_recover_valid_calls_with_prose_before_between_and_after() -> None:
    original = AIMessage(
        content=_structured_call_content(
            "read_query",
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
    assert recovered.content == (
        "I will inspect the data.\n\n\nChecking another dataset.\n\nDone."
    )
    assert [call["name"] for call in recovered.tool_calls] == ["read_query", "ls"]


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
            "read_query",
            '{"sql":"SELECT 1","dataset_uids":["fake"]}',
            preamble=preamble,
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert recovered.content == preamble.strip()
    assert [call["name"] for call in recovered.tool_calls] == ["read_query"]


@pytest.mark.asyncio
async def test_invalid_followup_stays_text_while_later_valid_call_recovers() -> None:
    original = AIMessage(
        content=_structured_call_content(
            "ls",
            '{"path":"/"} read_query{"sql":} ls{"path":"/tmp"}',
        ),
        response_metadata={"model_name": "mistral-medium-latest"},
    )

    response, _ = await _recover_message(original)

    recovered = response.result[0]
    assert isinstance(recovered, AIMessage)
    assert recovered.content == 'read_query{"sql":}'
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
            *({"type": "thinking", "thinking": "x"} for _ in range(255)),
            {"type": "text", "text": "ls"},
            {"type": "reference", "reference_ids": []},
            {"type": "text", "text": '{"path":"/"}'},
        ],
    ],
    ids=["character_cap", "call_cap", "block_cap"],
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
                    "read_query",
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
    assert recovered.content == expected_content
    assert [(call["name"], call["args"]) for call in recovered.tool_calls] == (
        expected_calls
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "model_name"),
    [
        (
            'I might call read_query{"sql": "SELECT 1", "dataset_uids": ["fake"]}',
            "mistral-medium-latest",
        ),
        (
            '`read_query{"sql": "SELECT 1", "dataset_uids": ["fake"]}`',
            "mistral-medium-latest",
        ),
        (
            'Do not execute this\n\nsend_email{"to":"person@example.invalid"}',
            "mistral-medium-latest",
        ),
        (_structured_call_content("unknown_tool", "{}"), "mistral-medium-latest"),
        (
            _structured_call_content("read_query", '{"sql": }'),
            "mistral-medium-latest",
        ),
        (
            _structured_call_content("read_query", '{"sql": "SELECT 1"'),
            "mistral-medium-latest",
        ),
        (
            _structured_call_content("read_query", '{"sql": "SELECT 1"}'),
            "mistral-medium-latest",
        ),
        ("This is an ordinary answer.", "mistral-medium-latest"),
        (
            'read_query[reference]{"sql": "SELECT 1", "dataset_uids": ["fake"]}',
            "mistral-medium-latest",
        ),
        (
            _structured_call_content(
                "read_query",
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
async def test_native_duplicate_calls_are_preserved_exactly() -> None:
    native_calls = [
        {"name": "ls", "args": {"path": "/"}, "id": "call-1"},
        {"name": "ls", "args": {"path": "/"}, "id": "call-2"},
    ]
    original = AIMessage(
        content="",
        tool_calls=native_calls,
        response_metadata={"model_name": "mistral-medium-latest"},
    )
    before = [dict(call) for call in original.tool_calls]

    response, _ = await _recover_message(original)

    assert response.result[0] is original
    assert original.tool_calls == before


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
            content=_structured_call_content(
                "send_email", '{"to": "person@example.invalid"}'
            ),
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
            content=_structured_call_content("ls", '{"path": "/"}'),
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
