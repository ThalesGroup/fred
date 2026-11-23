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

"""No prompt/response/tool-argument content in the generic app-log store
(issue #2009).

`TracingKpiMiddleware._log_model_call`/`_log_model_response` feed the shared
app logger — which flows into the generic, durable log store explorable via
OpenSearch Dashboards (see docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §7:
"Content ... Nowhere in any observability or audit stream"). Lock in that
only lengths/names/counts are logged, never message/argument/answer text.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from fred_core.security.delegation import DelegationConfig
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    set_delegation_runtime,
)
from fred_runtime.react.middleware import tracing_kpi as tracing_kpi_module
from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

SECRET_QUESTION = (
    "what is my confidential account balance of $1,000,000"  # pragma: allowlist secret
)
SECRET_ANSWER = "your confidential account balance is one million dollars"  # pragma: allowlist secret
SECRET_ARG_VALUE = "sk-super-secret-tool-argument-value"  # pragma: allowlist secret
TOOL_NAME_CANARY = "customer-resource-lookup-canary"
ARG_KEY_CANARY = "account_identifier_canary"


@pytest.fixture(autouse=True)
def _delegated_logging_context():
    set_delegation_runtime(
        DelegationRuntime(config=DelegationConfig(act_for_people=True))
    )
    try:
        yield
    finally:
        set_delegation_runtime(None)


def test_log_model_call_never_logs_message_content(caplog) -> None:
    request = ModelRequest(
        model=cast(BaseChatModel, None),
        messages=[HumanMessage(content=SECRET_QUESTION)],
        system_prompt="be helpful",
        state={"messages": [HumanMessage(content=SECRET_QUESTION)]},
    )

    with caplog.at_level(logging.INFO, logger=tracing_kpi_module.__name__):
        TracingKpiMiddleware._log_model_call(request)

    assert caplog.records, "sanity: a log line was emitted"
    for record in caplog.records:
        assert SECRET_QUESTION not in record.getMessage()


def test_log_model_response_never_logs_tool_args_or_answer_text(caplog) -> None:
    tool_response = ModelResponse(
        result=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": TOOL_NAME_CANARY,
                        "args": {ARG_KEY_CANARY: SECRET_ARG_VALUE},
                        "id": "1",
                    }
                ],
            )
        ]
    )
    answer_response = ModelResponse(result=[AIMessage(content=SECRET_ANSWER)])

    with caplog.at_level(logging.INFO, logger=tracing_kpi_module.__name__):
        TracingKpiMiddleware._log_model_response(tool_response)
        TracingKpiMiddleware._log_model_response(answer_response)

    assert caplog.records, "sanity: log lines were emitted"
    for record in caplog.records:
        emitted = repr({**record.__dict__, "message": record.getMessage()})
        assert SECRET_ARG_VALUE not in emitted
        assert SECRET_ANSWER not in emitted
        assert TOOL_NAME_CANARY not in emitted
        assert ARG_KEY_CANARY not in emitted


def test_flag_off_preserves_legacy_tool_name_and_argument_key_logging(caplog) -> None:
    set_delegation_runtime(None)
    response = ModelResponse(
        result=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": TOOL_NAME_CANARY,
                        "args": {ARG_KEY_CANARY: SECRET_ARG_VALUE},
                        "id": "1",
                    }
                ],
            )
        ]
    )

    with caplog.at_level(logging.INFO, logger=tracing_kpi_module.__name__):
        TracingKpiMiddleware._log_model_response(response)

    emitted = " ".join(record.getMessage() for record in caplog.records)
    assert TOOL_NAME_CANARY in emitted
    assert ARG_KEY_CANARY in emitted
    assert SECRET_ARG_VALUE not in emitted


def test_the_captured_prompt_carries_the_tools_the_model_was_given() -> None:
    """
    End-to-end through the middleware, not just the serializer.

    `serialize_model_request` falls back to a bare message list when `tools` is
    empty, so a rename upstream (`ModelRequest.system_prompt` is already a
    back-compat property) would silently revert the capture to messages-only
    with every serializer test still green. This drives the real hook against a
    real `ModelRequest` so that regression fails here (#2412 measurement needs
    the tools payload to actually reach the trace).
    """

    from fred_sdk.contracts.runtime import SpanPort, TracerPort
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel

    class _Args(BaseModel):
        sql: str

    class _PortableContext:
        agent_name = "fred-auto"
        agent_id = "fred-auto"

    class _Binding:
        portable_context = _PortableContext()

    captured: dict[str, Any] = {}

    class _Span(SpanPort):
        def set_attribute(self, key: str, value: Any) -> None:
            captured.setdefault("attrs", {})[key] = value

        def set_io(self, *, input: Any = None, output: Any = None) -> None:
            if input is not None:
                captured["input"] = input

        def end(self) -> None:
            pass

    class _Tracer(TracerPort):
        @property
        def captures_content(self) -> bool:
            return True

        def start_span(
            self,
            name: str,
            *,
            context: object | None = None,
            attributes: Any = None,
            parent: Any = None,
            **kwargs: object,
        ) -> Any:
            return _Span()

    request = ModelRequest(
        model=_RecordingModel(),
        messages=[HumanMessage(content="combien de voitures ?")],
        system_prompt="be helpful",
        tools=[
            StructuredTool.from_function(
                func=lambda **kwargs: None,
                name="read_query",
                description="Execute one read-only SQL query",
                args_schema=_Args,
            )
        ],
        state={"messages": []},
    )

    middleware = TracingKpiMiddleware(
        tracer=cast(Any, _Tracer()), kpi=None, binding=cast(Any, _Binding())
    )

    async def _handler(req: ModelRequest) -> ModelResponse:
        messages = list(req.messages)
        if req.system_message is not None:
            messages.insert(0, req.system_message)
        return ModelResponse(
            result=[await req.model.bind_tools(req.tools).ainvoke(messages)]
        )

    asyncio.run(middleware.awrap_model_call(request, _handler))

    payload = captured.get("input")
    assert isinstance(payload, dict), "tools present: payload must carry both fields"
    assert [tool["name"] for tool in payload["tools"]] == ["read_query"]
    assert "sql" in str(payload["tools"][0]["parameters"])

    # Character sizes ride as attributes, never as usage details: Langfuse
    # renders every usage key under one TOKENS unit and aggregates the ones it
    # does not know, so a character count shown there reads as extra tokens.
    attrs = cast(dict[str, int], captured.get("attrs", {}))
    assert attrs["chars_system"] == len("be helpful")
    assert attrs["chars_messages"] == len("combien de voitures ?")
    assert attrs["chars_tools"] > 0


class _RecordingModel(BaseChatModel):
    calls: list[tuple[list[BaseMessage], list[dict[str, Any]]]] = Field(
        default_factory=list
    )

    @property
    def _llm_type(self) -> str:
        return "final-input-test"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        return self.bind(tools=[convert_to_openai_tool(tool) for tool in tools])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append((messages, kwargs.get("tools", [])))
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="done"))]
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("captures_content", [True, False])
async def test_compiled_trace_captures_final_model_input(
    captures_content: bool,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from fred_runtime.runtime_support.trace_payloads import serialize_model_request

    model = _RecordingModel()
    early_tool = StructuredTool.from_function(
        lambda query: "unused", name="early_tool", description="Initial tool"
    )
    final_tool = StructuredTool.from_function(
        lambda query: "unused", name="final_tool", description="Final tool disclosure"
    )

    class _LaterMiddleware(AgentMiddleware):
        async def awrap_model_call(
            self,
            request: ModelRequest,
            handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
        ) -> ModelResponse:
            return await handler(
                request.override(
                    system_message=SystemMessage(content="final skill catalogue"),
                    messages=[*request.messages, HumanMessage(content="later message")],
                    tools=[final_tool],
                )
            )

    spans: list[Mock] = []

    def start_span(**kwargs: Any) -> Mock:
        span = Mock()
        spans.append(span)
        return span

    tracer = SimpleNamespace(captures_content=captures_content, start_span=start_span)
    binding = SimpleNamespace(
        portable_context=SimpleNamespace(agent_id="test", agent_name="test")
    )
    telemetry = TracingKpiMiddleware(
        tracer=cast(Any, tracer), kpi=None, binding=cast(Any, binding)
    )
    serialize = Mock(wraps=serialize_model_request)
    monkeypatch.setattr(tracing_kpi_module, "serialize_model_request", serialize)
    agent = create_agent(
        model,
        tools=[early_tool, final_tool],
        system_prompt="initial",
        middleware=[telemetry, _LaterMiddleware()],
    )
    caplog.set_level(logging.INFO, logger=tracing_kpi_module.__name__)

    await asyncio.gather(
        *(
            agent.ainvoke({"messages": [HumanMessage(content=question)]})
            for question in (SECRET_QUESTION, "second concurrent question")
        )
    )

    assert len(model.calls) == len(spans) == 2
    assert model.callbacks is None
    expected = [
        serialize_model_request(messages, tools=tools)
        for messages, tools in model.calls
    ]
    captured = [
        call.kwargs["input"]
        for span in spans
        for call in span.set_io.call_args_list
        if "input" in call.kwargs
    ]
    if captures_content:
        assert sorted(captured, key=str) == sorted(expected, key=str)
        assert serialize.call_count == 2
        for span in spans:
            assert (
                sum("input" in call.kwargs for call in span.set_io.call_args_list) == 1
            )
            attrs = {
                call.args[0]: call.args[1] for call in span.set_attribute.call_args_list
            }
            assert attrs["chars_system"] == len("final skill catalogue")
    else:
        assert captured == []
        serialize.assert_not_called()
        assert SECRET_QUESTION not in repr([span.mock_calls for span in spans])
    assert SECRET_QUESTION not in repr([vars(record) for record in caplog.records])
    assert all(span.end.call_count == 1 for span in spans)
