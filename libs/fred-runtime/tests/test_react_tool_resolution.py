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
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fred_core.store import VectorSearchHit
from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.react.react_tool_rendering import GENERIC_TOOL_FAILURE_MESSAGE
from fred_runtime.react.react_tool_resolution import ReActRuntimeToolResolver
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    LinkPart,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.runtime import RuntimeServices, ToolProviderPort
from langchain_core.tools import StructuredTool
from pydantic import BaseModel


class _AgentSettings:
    id: str = "agent-1"
    team_id: str | None = None
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="session-1"),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _resolver() -> ReActRuntimeToolResolver:
    return ReActRuntimeToolResolver(
        declared_tool_refs=(),
        toolset_key=None,
        services=RuntimeServices(),
        binding=_binding(),
    )


def _provider_error_artifact() -> ToolInvocationResult:
    # Synthetic bait, not a credential: this test exists to prove the classifier
    # never lets such a string reach a user-visible artifact.
    secret = (
        "sk-live-PROVIDER-SECRET /srv/private/report.docx"  # pragma: allowlist secret
    )
    return ToolInvocationResult(
        tool_ref="provider.error",
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=secret),),
        sources=(
            VectorSearchHit(
                uid="secret-source",
                title="Private diagnostic",
                content=secret,
                score=1.0,
            ),
        ),
        ui_parts=(LinkPart(href=f"https://provider.invalid/?token={secret}"),),
        is_error=True,
    )


@pytest.mark.asyncio
async def test_runtime_provider_tuple_error_is_sanitized_before_binding() -> None:
    async def _provider_error() -> tuple[str, ToolInvocationResult]:
        return ("safe provider summary", _provider_error_artifact())

    runtime_tool = StructuredTool.from_function(
        coroutine=_provider_error,
        name="provider_error",
        description="Return one provider-controlled error.",
    )
    spec = _resolver()._resolve_runtime_provider_tool(
        runtime_tool=runtime_tool,
        tool_name=runtime_tool.name,
        description=runtime_tool.description,
    )

    content, artifact = await spec.invoke({})

    assert content == f"Tool error:\n{GENERIC_TOOL_FAILURE_MESSAGE}"
    assert artifact is not None
    assert artifact.is_error is True
    assert [block.text for block in artifact.blocks] == [GENERIC_TOOL_FAILURE_MESSAGE]
    assert artifact.sources == ()
    assert artifact.ui_parts == ()


@pytest.mark.asyncio
async def test_runtime_provider_bare_error_is_sanitized_before_binding() -> None:
    async def _provider_error() -> ToolInvocationResult:
        return _provider_error_artifact()

    runtime_tool = StructuredTool.from_function(
        coroutine=_provider_error,
        name="provider_error",
        description="Return one provider-controlled error.",
    )
    spec = _resolver()._resolve_runtime_provider_tool(
        runtime_tool=runtime_tool,
        tool_name=runtime_tool.name,
        description=runtime_tool.description,
    )

    content, artifact = await spec.invoke({})

    assert content == f"Tool error:\n{GENERIC_TOOL_FAILURE_MESSAGE}"
    assert artifact is not None
    assert artifact.is_error is True
    assert [block.text for block in artifact.blocks] == [GENERIC_TOOL_FAILURE_MESSAGE]
    assert artifact.sources == ()
    assert artifact.ui_parts == ()


@pytest.mark.asyncio
async def test_runtime_provider_content_and_artifact_preserves_error_artifact() -> None:
    """Provider artifacts must survive LangChain's public invocation boundary."""

    async def _provider_error() -> tuple[str, ToolInvocationResult]:
        return ("Error: Binder Error", _provider_error_artifact())

    runtime_tool = StructuredTool.from_function(
        coroutine=_provider_error,
        name="read_query",
        description="Run one SQL query.",
        response_format="content_and_artifact",
    )
    spec = _resolver()._resolve_runtime_provider_tool(
        runtime_tool=runtime_tool,
        tool_name=runtime_tool.name,
        description=runtime_tool.description,
    )

    content, artifact = await spec.invoke({})

    assert content == f"Tool error:\n{GENERIC_TOOL_FAILURE_MESSAGE}"
    assert artifact is not None
    assert artifact.is_error is True


@pytest.mark.asyncio
async def test_context_aware_read_query_keeps_classified_engine_detail() -> None:
    """The trusted SQL detail must survive provider resolution without HTTP text."""

    async def _failing_read_query(sql: str) -> str:
        del sql
        raise RuntimeError(
            "Error calling read_query. Status code: 400. Response: "
            '{"detail":"Binder Error: Referenced column amount_typo not found"}'
        )

    base_tool = StructuredTool.from_function(
        coroutine=_failing_read_query,
        name="read_query",
        description="Run one SQL query.",
        response_format="content_and_artifact",
    )
    runtime_tool = ContextAwareTool(
        base_tool=base_tool,
        context_provider=lambda: None,
        agent_settings_provider=_AgentSettings,
    )
    spec = _resolver()._resolve_runtime_provider_tool(
        runtime_tool=runtime_tool,
        tool_name=runtime_tool.name,
        description=runtime_tool.description,
    )

    content, artifact = await spec.invoke({"sql": "SELECT amount_typo FROM d_sales"})

    assert content == (
        "Tool error:\nBinder Error: Referenced column amount_typo not found"
    )
    assert "HTTP" not in content
    assert artifact is not None
    assert artifact.is_error is True
    assert [block.text for block in artifact.blocks] == [
        "Binder Error: Referenced column amount_typo not found"
    ]


def test_ask_user_is_mounted_only_for_explicit_interactive_context() -> None:
    from fred_runtime.react.react_tool_binding import ReActToolBinder

    for enabled in (None, False):
        binding = _binding().model_copy(
            update={
                "runtime_context": RuntimeContext(
                    session_id="session-1", ask_user=enabled
                )
            }
        )
        resolver = ReActRuntimeToolResolver(
            declared_tool_refs=(),
            toolset_key=None,
            services=RuntimeServices(),
            binding=binding,
        )
        assert resolver.resolve_tools() == []

    binding = _binding().model_copy(
        update={
            "runtime_context": RuntimeContext(session_id="session-1", ask_user=True)
        }
    )
    specs = ReActRuntimeToolResolver(
        declared_tool_refs=(),
        toolset_key=None,
        services=RuntimeServices(),
        binding=binding,
    ).resolve_tools()
    assert [spec.runtime_name for spec in specs] == ["ask_user"]
    bound = ReActToolBinder(
        runtime_tools=specs, tracer=None, binding=binding
    ).build_tools()
    schema = cast(type[BaseModel], bound[0].tool.tool_call_schema)
    assert set(schema.model_fields) == {
        "question",
        "title",
        "choices",
        "allow_free_text",
    }
    assert schema.model_json_schema()["properties"]["choices"]["maxItems"] == 4


def test_ask_user_colliding_with_declared_tool_is_rejected() -> None:
    binding = _binding().model_copy(
        update={
            "runtime_context": RuntimeContext(session_id="session-1", ask_user=True)
        }
    )
    resolver = ReActRuntimeToolResolver(
        declared_tool_refs=(),
        toolset_key=None,
        services=RuntimeServices(),
        binding=binding,
        capability_tool_names=("ask_user",),
    )
    with pytest.raises(RuntimeError, match="collides"):
        resolver.resolve_tools()


@pytest.mark.parametrize(
    "payload",
    [
        {"question": " ", "allow_free_text": True, "tool_call_id": "call-1"},
        {
            "question": "Choose",
            "choices": [{"id": " yes ", "label": "Yes"}],
            "tool_call_id": "call-1",
        },
        {
            "question": "Choose",
            "choices": [{"id": "yes", "label": "Yes"}, {"id": "yes", "label": "Again"}],
            "tool_call_id": "call-1",
        },
        {
            "question": "Choose",
            "choices": [{"id": str(index), "label": str(index)} for index in range(5)],
            "tool_call_id": "call-1",
        },
    ],
)
def test_ask_user_rejects_invalid_question_forms(payload: dict[str, object]) -> None:
    from fred_runtime.runtime_support.ask_user import AskUserArgs
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AskUserArgs.model_validate(payload)


def test_ask_user_accepts_four_selected_choices_and_exposes_the_limit() -> None:
    from fred_runtime.runtime_support.ask_user import AskUserArgs

    choices = [{"id": str(index), "label": str(index)} for index in range(4)]
    args = AskUserArgs.model_validate(
        {"question": "Choose", "choices": choices, "tool_call_id": "call-1"}
    )
    assert len(args.choices) == 4


def test_ask_user_accepts_a_short_subject_title() -> None:
    from fred_runtime.runtime_support.ask_user import AskUserArgs

    args = AskUserArgs.model_validate(
        {
            "question": "How long?",
            "title": "Trip duration",
            "allow_free_text": True,
            "tool_call_id": "call-1",
        }
    )
    assert args.title == "Trip duration"


@pytest.mark.asyncio
async def test_ask_user_persists_the_subject_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_runtime.runtime_support.ask_user import ask_user

    requests: list[dict[str, object]] = []

    def answer(request: dict[str, object]) -> dict[str, str]:
        requests.append(request)
        return {"text": "A week"}

    monkeypatch.setattr("fred_runtime.runtime_support.ask_user.interrupt", answer)
    await ask_user(
        {
            "question": "How long?",
            "title": "Trip duration",
            "allow_free_text": True,
            "tool_call_id": "call-1",
        }
    )
    assert requests[0]["title"] == "Trip duration"


@pytest.mark.asyncio
@pytest.mark.parametrize("choice_count", [1, 2, 4])
async def test_ask_user_always_accepts_text_with_multiple_choices(
    monkeypatch: pytest.MonkeyPatch, choice_count: int
) -> None:
    from fred_runtime.runtime_support.ask_user import ask_user

    requests: list[dict[str, object]] = []

    def answer(request: dict[str, object]) -> dict[str, str]:
        requests.append(request)
        return {"text": "Other answer"} if choice_count >= 2 else {"choice_id": "0"}

    monkeypatch.setattr("fred_runtime.runtime_support.ask_user.interrupt", answer)
    result = await ask_user(
        {
            "question": "Choose",
            "choices": [
                {"id": str(index), "label": str(index)} for index in range(choice_count)
            ],
            "allow_free_text": False,
            "tool_call_id": "call-1",
        }
    )

    assert requests[0]["free_text"] is (choice_count >= 2)
    assert json.loads(result) == (
        {"status": "answered", "text": "Other answer"}
        if choice_count >= 2
        else {"status": "answered", "choice_id": "0"}
    )


def test_ask_user_colliding_with_provider_tool_is_rejected() -> None:
    async def provider_ask_user(question: str) -> str:
        return question

    provider_tool = StructuredTool.from_function(
        coroutine=provider_ask_user,
        name="ask_user",
        description="A provider tool with the reserved platform name.",
    )
    provider = cast(
        ToolProviderPort, SimpleNamespace(get_tools=lambda: [provider_tool])
    )
    binding = _binding().model_copy(
        update={
            "runtime_context": RuntimeContext(session_id="session-1", ask_user=True)
        }
    )
    resolver = ReActRuntimeToolResolver(
        declared_tool_refs=(),
        toolset_key=None,
        services=RuntimeServices(tool_provider=provider),
        binding=binding,
    )
    with pytest.raises(RuntimeError, match="collides"):
        resolver.resolve_tools()


@pytest.mark.parametrize(
    "label",
    [
        "Autre",
        "Other",
        "Autre (précise si tu veux)",
        "Something else",
        "autre réponse.",
    ],
)
def test_ask_user_drops_generic_other_choice(label: str) -> None:
    from fred_runtime.runtime_support.ask_user import AskUserArgs

    args = AskUserArgs.model_validate(
        {
            "question": "Mode?",
            "choices": [
                {"id": "1", "label": "Office"},
                {"id": "2", "label": "Remote"},
                {"id": "3", "label": label},
            ],
            "tool_call_id": "call-1",
        }
    )
    assert [choice.label for choice in args.choices] == ["Office", "Remote"]
    assert args.allow_free_text is True


def test_ask_user_keeps_specific_other_choice() -> None:
    from fred_runtime.runtime_support.ask_user import AskUserArgs

    args = AskUserArgs.model_validate(
        {
            "question": "Where?",
            "choices": [
                {"id": "fr", "label": "France"},
                {"id": "other", "label": "Other country"},
            ],
            "tool_call_id": "call-1",
        }
    )
    assert [choice.id for choice in args.choices] == ["fr", "other"]
    assert args.allow_free_text is False


def test_ask_user_counts_choices_after_dropping_other() -> None:
    from fred_runtime.runtime_support.ask_user import AskUserArgs

    choices = [{"id": str(index), "label": f"Option {index}"} for index in range(4)]
    args = AskUserArgs.model_validate(
        {
            "question": "Pick",
            "choices": [*choices, {"id": "x", "label": "Autre"}],
            "tool_call_id": "call-1",
        }
    )
    assert len(args.choices) == 4


@pytest.mark.asyncio
async def test_ask_user_single_choice_plus_other_allows_free_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = await _captured_request(
        monkeypatch,
        {
            "question": "Continue?",
            "choices": [{"id": "yes", "label": "Oui"}, {"id": "o", "label": "Autre"}],
            "tool_call_id": "call-1",
        },
    )
    assert [choice["id"] for choice in request["choices"]] == ["yes"]
    assert request["free_text"] is True


@pytest.mark.asyncio
async def test_ask_user_without_choices_is_a_free_text_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = await _captured_request(
        monkeypatch,
        {
            "title": "Adresse email",
            "question": "Quelle est l'adresse email du destinataire ?",
            "tool_call_id": "x",
        },
    )
    assert request["choices"] == []
    assert request["free_text"] is True


@pytest.mark.asyncio
async def test_ask_user_single_choice_keeps_free_text_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = await _captured_request(
        monkeypatch,
        {
            "question": "Confirm?",
            "choices": [{"id": "ok", "label": "OK"}],
            "tool_call_id": "call-1",
        },
    )
    assert request["free_text"] is False


async def _captured_request(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> dict[str, Any]:
    from fred_runtime.runtime_support import ask_user as ask_user_module

    captured: dict[str, Any] = {}

    def fake_interrupt(value: dict[str, Any]) -> dict[str, Any]:
        captured.update(value)
        return {"skipped": True}

    monkeypatch.setattr(ask_user_module, "interrupt", fake_interrupt)
    await ask_user_module.ask_user(payload)
    return captured
