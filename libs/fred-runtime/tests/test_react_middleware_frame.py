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
Tests for the ReAct platform middleware frame itself (#1972).

The behavioral equivalence of the `create_agent` migration against the legacy
4-node StateGraph is proven by the pre-migration oracle in
`test_react_loop_regressions_1972.py` (HITL payloads, sequential interrupts,
resume flow, hygiene, routing, metadata attach). This file covers what the
oracle cannot:

- the fixed frame composition order and the reserved capability-block
  insertion slot (RFC AGENT-CAPABILITY-RFC.md §5.3)
- `max_tool_calls_per_turn` enforcement via the prebuilt
  `ToolCallLimitMiddleware` (new capability — the legacy runtime raised
  NotImplementedError)
- hygiene being request-scoped: sanitize/trim/reasoning-strip must transform
  the model input WITHOUT rewriting the persisted checkpoint state
- small HITL gate variants: a bare `"cancel"` string resume, and a disabled
  approval policy gating nothing
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fred_runtime.react.middleware import (
    CheckpointHygieneMiddleware,
    DynamicPromptMiddleware,
    FredHitlMiddleware,
    ModelRoutingMiddleware,
    TracingKpiMiddleware,
    build_react_platform_middleware_frame,
)
from fred_runtime.react.react_model_adapter import (
    REACT_MODEL_OPERATION_ROUTING,
    infer_react_model_operation_from_messages,
)
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from langchain.agents.middleware import AgentMiddleware, ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer, Command
from pydantic import Field

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

EXECUTED_TOOLS: list[tuple[str, dict[str, Any]]] = []


@tool
def send_email(to: str) -> str:
    """Send an email (gated via the operator `always_require_tools` list)."""

    EXECUTED_TOOLS.append(("send_email", {"to": to}))
    return f"sent to {to}"


@tool
def get_weather(city: str) -> str:
    """Get the weather (read-only prefix → never gated)."""

    EXECUTED_TOOLS.append(("get_weather", {"city": city}))
    return f"sunny in {city}"


class ScriptedModel(BaseChatModel):
    """Deterministic scripted model recording every model input verbatim."""

    script: list[AIMessage] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-frame-1972"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        msg = self.script.pop(0) if self.script else AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _binding(language: str | None = None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(language=language),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _definition() -> ReActAgentDefinition:
    return cast(ReActAgentDefinition, SimpleNamespace(agent_id="agent-frame"))


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _build_agent(
    model: BaseChatModel,
    *,
    approval_enabled: bool = True,
    always_require_tools: tuple[str, ...] = (),
    max_tool_calls_per_turn: int | None = None,
) -> Any:
    return build_tool_loop_compiled_react_agent(
        model=model,
        tools=[send_email, get_weather],
        system_prompt="SYS-frame.",
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(
            enabled=approval_enabled, always_require_tools=always_require_tools
        ),
        checkpointer=cast(Checkpointer, InMemorySaver()),
        chat_model_factory=None,
        definition=_definition(),
        infer_operation_from_messages=infer_react_model_operation_from_messages,
        default_operation=REACT_MODEL_OPERATION_ROUTING,
        available_tool_names={"send_email", "get_weather"},
        max_tool_calls_per_turn=max_tool_calls_per_turn,
    )


def _cfg(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


@pytest.fixture(autouse=True)
def _reset_tool_log() -> None:
    EXECUTED_TOOLS.clear()


# ---------------------------------------------------------------------------
# Hygiene is request-scoped — the checkpoint is never rewritten
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hygiene_transforms_model_input_without_rewriting_state() -> None:
    """Sanitize/trim/reasoning-strip apply to the MODEL INPUT only. A hygiene
    implementation that edited graph state instead (e.g. a `before_model`
    state update) would rewrite the checkpoint and destroy history."""

    model = ScriptedModel(script=[AIMessage(content="answer")])
    agent = _build_agent(model, approval_enabled=False)

    history: list[BaseMessage] = [
        HumanMessage("q-old"),
        # Poisoned: dangling tool call from a crashed turn.
        AIMessage(
            content="",
            tool_calls=[_tool_call("get_weather", {"city": "Nice"}, "c-dead")],
        ),
        # Replayed reasoning content (list-shaped).
        AIMessage(
            content=[
                {"type": "thinking", "thinking": "hidden"},
                {"type": "text", "text": "old visible answer"},
            ]
        ),
        HumanMessage("q-new"),
    ]
    res = await agent.ainvoke({"messages": history}, _cfg("t-scoped"))

    # Model input is hygienic…
    model_input = model.calls[0]
    assert not any(getattr(m, "tool_calls", None) for m in model_input)
    replayed_ai = [m for m in model_input if isinstance(m, AIMessage)]
    assert [m.content for m in replayed_ai] == ["old visible answer"]

    # …while the persisted state still carries the original messages.
    stored = res["messages"]
    assert any(getattr(m, "tool_calls", None) for m in stored)
    stored_list_content = [
        m for m in stored if isinstance(m, AIMessage) and isinstance(m.content, list)
    ]
    assert len(stored_list_content) == 1


# ---------------------------------------------------------------------------
# HITL gate variants not covered by the oracle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hitl_cancel_accepts_plain_string_decision() -> None:
    """The legacy cancel check accepted a bare 'cancel' string resume."""

    model = ScriptedModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@x"}, "c-1")],
            ),
            AIMessage(content="okay, cancelled"),
        ]
    )
    agent = _build_agent(model, always_require_tools=("send_email",))
    cfg = _cfg("t-cancel-str")

    res = await agent.ainvoke({"messages": [HumanMessage("send an email")]}, cfg)
    assert "__interrupt__" in res
    res = await agent.ainvoke(Command(resume="cancel"), cfg)

    assert EXECUTED_TOOLS == []
    assert str(res["messages"][-1].content) == "okay, cancelled"


@pytest.mark.asyncio
async def test_hitl_disabled_policy_gates_nothing() -> None:
    model = ScriptedModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@x"}, "c-1")],
            ),
        ]
    )
    agent = _build_agent(model, approval_enabled=False)

    res = await agent.ainvoke(
        {"messages": [HumanMessage("send an email")]}, _cfg("t-disabled")
    )

    assert "__interrupt__" not in res
    assert EXECUTED_TOOLS == [("send_email", {"to": "a@x"})]


# ---------------------------------------------------------------------------
# max_tool_calls_per_turn — the previously NotImplemented free win
# ---------------------------------------------------------------------------


class _EagerToolModel(ScriptedModel):
    """Keeps requesting `get_weather` until the real tool result stops."""

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        last = messages[-1]
        if isinstance(last, ToolMessage) and "sunny" not in str(last.content):
            # The limit middleware injected a block message — wrap up.
            msg = AIMessage(content="stopped by limit")
        else:
            n = sum(1 for m in messages if isinstance(m, ToolMessage))
            msg = AIMessage(
                content="",
                tool_calls=[_tool_call("get_weather", {"city": f"city-{n}"}, f"w{n}")],
            )
        return ChatResult(generations=[ChatGeneration(message=msg)])


@pytest.mark.asyncio
async def test_max_tool_calls_per_turn_is_enforced() -> None:
    agent = _build_agent(
        _EagerToolModel(),
        approval_enabled=False,
        max_tool_calls_per_turn=1,
    )

    res = await agent.ainvoke({"messages": [HumanMessage("loop!")]}, _cfg("t-limit"))

    # Exactly one real execution; the second request was blocked by
    # ToolCallLimitMiddleware, and the run still terminated cleanly.
    assert EXECUTED_TOOLS == [("get_weather", {"city": "city-0"})]
    assert str(res["messages"][-1].content) == "stopped by limit"


# ---------------------------------------------------------------------------
# The fixed platform frame and the reserved capability slot (RFC §5.3)
# ---------------------------------------------------------------------------


class _DummyCapabilityMiddleware(AgentMiddleware):
    pass


def _frame(**overrides: Any) -> list[AgentMiddleware]:
    kwargs: dict[str, Any] = dict(
        binding=_binding(),
        definition=_definition(),
        approval_policy=ToolApprovalPolicy(enabled=True),
        chat_model_factory=None,
        infer_operation_from_messages=infer_react_model_operation_from_messages,
        default_operation=REACT_MODEL_OPERATION_ROUTING,
        available_tool_names={"send_email"},
        tracer=None,
        kpi=None,
        max_history_messages=10,
    )
    kwargs.update(overrides)
    return build_react_platform_middleware_frame(**kwargs)


def test_frame_order_is_fixed() -> None:
    frame = _frame()
    assert [type(m) for m in frame] == [
        CheckpointHygieneMiddleware,
        ModelRoutingMiddleware,
        DynamicPromptMiddleware,
        TracingKpiMiddleware,
        FredHitlMiddleware,
    ]


def test_frame_reserves_the_capability_slot() -> None:
    """The capability block (#1973) is inserted between DynamicPrompt and
    TracingKpi — capability authors never position themselves manually."""

    capability = _DummyCapabilityMiddleware()
    frame = _frame(capability_middleware=[capability])
    assert [type(m) for m in frame] == [
        CheckpointHygieneMiddleware,
        ModelRoutingMiddleware,
        DynamicPromptMiddleware,
        _DummyCapabilityMiddleware,
        TracingKpiMiddleware,
        FredHitlMiddleware,
    ]


def test_frame_appends_tool_call_limit_after_hitl() -> None:
    """ToolCallLimit is listed after FredHitl on purpose: `after_model` hooks
    run in reverse list order, so the limit blocks over-limit calls before a
    human is ever asked to approve them."""

    frame = _frame(max_tool_calls_per_turn=3)
    assert [type(m) for m in frame[-2:]] == [
        FredHitlMiddleware,
        ToolCallLimitMiddleware,
    ]
