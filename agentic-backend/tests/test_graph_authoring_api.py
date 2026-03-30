from __future__ import annotations

from typing import cast

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel

from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    GraphExecutionOutput,
    HumanChoiceOption,
    RuntimeServices,
    ToolInvocationResult,
)
from agentic_backend.core.agents.v2.graph import GraphNodeContext
from agentic_backend.core.agents.v2.graph.authoring import (
    GraphAgent,
    GraphWorkflow,
    StepResult,
    choice_step,
    finalize_step,
    intent_router_step,
    model_text_step,
    structured_model_step,
    typed_node,
)


class _TypedState(BaseModel):
    value: int


class _GraphAgentInput(BaseModel):
    message: str


class _GraphAgentState(BaseModel):
    message: str
    final_text: str | None = None


class _RouteDecision(BaseModel):
    route: str
    reason: str = ""


class _FakeContext:
    """
    Minimal graph node context stub for authoring-helper unit tests.

    Why this test double exists:
    - the new authoring helpers depend on a small subset of `GraphNodeContext`
    - keeping the stub local avoids heavyweight runtime setup for fast offline tests

    How to use it:
    - configure `runtime_payload`, `human_payload`, and `model_text`
    - pass the instance to the helper under test

    Example:
    - `context = _FakeContext(model_text="hello")`
    """

    def __init__(
        self,
        *,
        runtime_payload: object | None = None,
        human_payload: object | None = None,
        model_text: str | None = None,
        structured_payload: object | None = None,
    ) -> None:
        self._runtime_payload = runtime_payload
        self._human_payload = human_payload
        self._model_text = model_text
        self._structured_payload = structured_payload

    @property
    def binding(self) -> BoundRuntimeContext:
        return cast(BoundRuntimeContext, object())

    @property
    def services(self) -> RuntimeServices:
        return cast(RuntimeServices, object())

    @property
    def model(self) -> BaseChatModel | None:
        if self._model_text is None and self._structured_payload is None:
            return None
        return cast(BaseChatModel, object())

    def emit_status(self, status: str, detail: str | None = None) -> None:
        del status, detail

    def emit_assistant_delta(self, delta: str) -> None:
        del delta

    async def invoke_model(
        self,
        messages: list[BaseMessage],
        *,
        operation: str = "default",
    ) -> BaseMessage:
        del messages, operation
        return AIMessage(content=self._model_text or "")

    async def invoke_structured_model(
        self,
        output_model: type[BaseModel],
        messages: list[BaseMessage],
        *,
        operation: str = "default",
    ) -> BaseModel:
        del messages, operation
        payload = self._structured_payload
        if isinstance(payload, output_model):
            return payload
        if isinstance(payload, BaseModel):
            return output_model.model_validate(payload.model_dump())
        if isinstance(payload, dict):
            return output_model.model_validate(payload)
        raise RuntimeError("No structured payload configured for test context.")

    async def invoke_tool(
        self, tool_ref: str, payload: dict[str, object]
    ) -> ToolInvocationResult:
        raise NotImplementedError(f"Unexpected invoke_tool call: {tool_ref} {payload}")

    async def invoke_runtime_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> object:
        del tool_name, arguments
        return self._runtime_payload

    async def publish_text(self, **kwargs: object) -> object:
        raise NotImplementedError(f"Unexpected publish_text call: {kwargs}")

    async def publish_bytes(self, **kwargs: object) -> object:
        raise NotImplementedError(f"Unexpected publish_bytes call: {kwargs}")

    async def fetch_resource(self, **kwargs: object) -> object:
        raise NotImplementedError(f"Unexpected fetch_resource call: {kwargs}")

    async def fetch_text_resource(self, **kwargs: object) -> str:
        raise NotImplementedError(f"Unexpected fetch_text_resource call: {kwargs}")

    async def request_human_input(self, request: object) -> object:
        del request
        return self._human_payload


@pytest.mark.asyncio
async def test_typed_node_converts_step_result_to_runtime_result() -> None:
    @typed_node(_TypedState)
    async def handler(state: _TypedState, context: GraphNodeContext) -> StepResult:
        del context
        return StepResult(
            state_update={"value": state.value + 1},
            route_key="next",
        )

    result = await handler(
        _TypedState(value=2),
        cast(GraphNodeContext, _FakeContext()),
    )

    assert result.state_update == {"value": 3}
    assert result.route_key == "next"


@pytest.mark.asyncio
async def test_model_text_step_uses_fallback_without_bound_model() -> None:
    context = _FakeContext()

    content = await model_text_step(
        cast(GraphNodeContext, context),
        operation="draft_sql",
        user_prompt="Count rows",
        fallback_text="SELECT 1",
    )

    assert content == "SELECT 1"


@pytest.mark.asyncio
async def test_choice_step_returns_selected_choice_id() -> None:
    context = _FakeContext(human_payload={"choice_id": "db:analytics"})

    choice_id = await choice_step(
        cast(GraphNodeContext, context),
        stage="scope_selection",
        title="Choose database",
        question="Which database should I use?",
        choices=(
            HumanChoiceOption(id="db:analytics", label="analytics", default=True),
        ),
        metadata={"agent_family": "sql_analyst_graph"},
    )

    assert choice_id == "db:analytics"


@pytest.mark.asyncio
async def test_structured_model_step_uses_fallback_without_bound_model() -> None:
    decision = await structured_model_step(
        cast(GraphNodeContext, _FakeContext()),
        operation="route_request",
        output_model=_RouteDecision,
        system_prompt="Classify the request.",
        user_prompt="What can you do?",
        fallback_output={"route": "capabilities", "reason": "fallback"},
    )

    assert decision.route == "capabilities"


@pytest.mark.asyncio
async def test_intent_router_step_returns_route_key_and_updates() -> None:
    result = await intent_router_step(
        cast(
            GraphNodeContext,
            _FakeContext(
                structured_payload={"route": "capabilities", "reason": "meta"}
            ),
        ),
        operation="route_request",
        route_model=_RouteDecision,
        system_prompt="Classify the request.",
        user_prompt="What are your tools?",
        state_update_builder=lambda decision: {
            "final_text": decision.reason,
        },
    )

    assert result.route_key == "capabilities"
    assert result.state_update == {"final_text": "meta"}


def test_finalize_step_sets_fallback_only_when_terminal_text_is_missing() -> None:
    ready = finalize_step(
        final_text="Already complete.",
        summary_text=None,
        fallback_text="Missing summary.",
    )
    missing = finalize_step(
        final_text=None,
        summary_text=None,
        fallback_text="Missing summary.",
        done_reason="completed",
    )

    assert ready.state_update == {}
    assert missing.state_update == {
        "final_text": "Missing summary.",
        "done_reason": "completed",
    }


def test_graph_agent_derives_graph_handlers_and_default_output() -> None:
    @typed_node(_GraphAgentState)
    async def load_step(
        state: _GraphAgentState, context: GraphNodeContext
    ) -> StepResult:
        del context
        return StepResult(
            state_update={"final_text": f"Hello {state.message}"},
            route_key="finish",
        )

    class _DemoGraphAgent(GraphAgent):
        agent_id: str = "test.graph.authoring.demo"
        role: str = "Test Graph"
        description: str = "Small test graph for the declarative authoring base."
        input_schema = _GraphAgentInput
        state_schema = _GraphAgentState
        input_to_state = {"message": "message"}
        workflow = GraphWorkflow(
            entry="load",
            nodes={"load": load_step, "finalize": load_step},
            routes={"load": {"finish": "finalize"}},
        )

    definition = _DemoGraphAgent()

    graph = definition.build_graph()
    handlers = definition.node_handlers()
    initial_state = _GraphAgentState.model_validate(
        definition.build_initial_state(
            _GraphAgentInput(message="Ada"),
            cast(BoundRuntimeContext, object()),
        )
    )
    output = GraphExecutionOutput.model_validate(
        definition.build_output(_GraphAgentState(message="Ada", final_text="Hi"))
    )

    assert graph.entry_node == "load"
    assert [node.node_id for node in graph.nodes] == ["load", "finalize"]
    assert set(handlers) == {"load", "finalize"}
    assert initial_state.message == "Ada"
    assert output.content == "Hi"
