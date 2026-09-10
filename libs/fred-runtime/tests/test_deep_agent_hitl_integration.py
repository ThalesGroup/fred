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
Real `deepagents`/LangGraph integration proof that capability-declared and
operator-configured approval both gate a Deep agent turn
(RUNTIME-EXECUTION-CONTRACT.md §8.76; OpenSpec `agent-human-approval`).

`test_deep_agent_middleware.py` proves the middleware LIST composition with
fakes; it never drives a real compiled agent, so it cannot prove a gated call
actually pauses (a real `interrupt()`), that an ungated one does not, or that
the pause reaches Fred's own transport layer. This file drives both approval
sources through a real `deepagents.create_deep_agent` compiled graph and a
real `InMemorySaver`, mirroring `test_react_loop_regressions_1972.py`'s
pattern for ReAct; the transport-level tests additionally drive the real
`_TransportBackedReActExecutor` Deep uses in production. It also proves the
`deepagents` built-in-filesystem-tool-name overlap composes cleanly with a
gated tool of the same name (design.md D3).
"""

from __future__ import annotations

from typing import Any, cast

import fred_runtime.deep.deep_runtime as deep_mod
import pytest
from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.react.middleware.hitl import CapabilityHitlBinding
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_sdk.contracts.capability import HitlSpec
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ToolApprovalPolicy
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    RuntimeServices,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer, Command
from pydantic import Field


@tool
def send_email(to: str) -> str:
    """Send an email (capability-gated in these tests)."""

    return f"sent to {to}"


class _RecordingModel(BaseChatModel):
    """Deterministic scripted model — same shape as the ReAct HITL fixtures."""

    script: list[AIMessage] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "recording-deep-hitl"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_RecordingModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        msg = self.script.pop(0) if self.script else AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(),
        portable_context=PortableContext(
            request_id="request-deep-hitl",
            correlation_id="correlation-deep-hitl",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _compile_deep_agent(
    model: BaseChatModel,
    *,
    tools: list[Any],
    capability_hitl: dict[str, CapabilityHitlBinding] | None = None,
    available_tool_names: set[str],
    approval_policy: ToolApprovalPolicy | None = None,
) -> Any:
    """Build a real compiled deep agent through the exact same helpers
    `DeepAgentRuntime.build_executor` uses, without faking the tool
    resolver/binder layer (those are covered by `test_deep_agent_middleware.py`)."""

    capability_block = CapabilityAgentBlock(
        middleware=(), hitl=capability_hitl or {}, tools=(), mcp_prompt_groups=()
    )
    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=approval_policy or ToolApprovalPolicy(),
        available_tool_names=available_tool_names,
        capability_block=capability_block,
    )
    return deep_mod._create_compiled_deep_agent(
        model=model,
        tools=tools,
        system_prompt="You send emails when asked.",
        checkpointer=cast(Checkpointer, InMemorySaver()),
        middleware=middleware,
    )


async def _drive(agent: Any, payload: object, thread: str) -> list[dict[str, Any]]:
    """Stream one run and return only the `updates`-mode events, exactly like
    `_TransportBackedReActExecutor.stream`."""

    config = {"configurable": {"thread_id": thread}}
    updates: list[dict[str, Any]] = []
    async for mode, update in agent.astream(
        payload, config=config, stream_mode=["messages", "updates"]
    ):
        if mode == "updates" and isinstance(update, dict):
            updates.append(update)
    return updates


def _has_interrupt(updates: list[dict[str, Any]]) -> bool:
    return any("__interrupt__" in update for update in updates)


@pytest.mark.asyncio
async def test_deep_hitl_when_false_proceeds_without_pausing() -> None:
    """A capability binding with `require=False` and a `when` predicate that
    evaluates false on this turn (`document_extract`/`document_summarize`'s
    default shape, gated on operator-configurable `require_confirmation`)
    must run straight through with no interrupt at all."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@example.com"}, "c-1")],
            ),
            AIMessage(content="sent"),
        ]
    )
    capability_hitl = {
        "send_email": CapabilityHitlBinding(
            spec=HitlSpec(tool="send_email", require=False, when=lambda _req: False),
            context=cast(Any, None),
        )
    }
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        capability_hitl=capability_hitl,
        available_tool_names={"send_email"},
    )

    updates = await _drive(
        agent, {"messages": [HumanMessage("email a@example.com")]}, "t-no-pause"
    )

    assert not _has_interrupt(updates)


@pytest.mark.asyncio
async def test_deep_hitl_when_true_pauses_and_resumes_on_proceed() -> None:
    """A capability binding whose `when` predicate evaluates true must
    actually pause the turn with a real LangGraph interrupt — not merely
    avoid crashing — and a `proceed` resume must then execute the tool
    exactly once, matching ReActRuntime's existing HITL behavior."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@example.com"}, "c-1")],
            ),
            AIMessage(content="sent"),
        ]
    )
    capability_hitl = {
        "send_email": CapabilityHitlBinding(
            spec=HitlSpec(tool="send_email", require=False, when=lambda _req: True),
            context=cast(Any, None),
        )
    }
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        capability_hitl=capability_hitl,
        available_tool_names={"send_email"},
    )

    updates = await _drive(
        agent, {"messages": [HumanMessage("email a@example.com")]}, "t-pause-proceed"
    )
    assert _has_interrupt(updates)

    resumed = await _drive(
        agent, Command(resume={"choice_id": "proceed"}), "t-pause-proceed"
    )
    assert not _has_interrupt(resumed)
    tool_messages = [
        message
        for update in resumed
        for value in update.values()
        if isinstance(value, dict)
        for message in value.get("messages") or []
        if getattr(message, "type", None) == "tool"
    ]
    assert any(
        getattr(message, "content", "") == "sent to a@example.com"
        for message in tool_messages
    )


@pytest.mark.asyncio
async def test_deep_hitl_when_true_cancel_skips_the_tool() -> None:
    """A `cancel` resume must skip the gated call entirely and let the model
    replan, same as ReActRuntime's batch-cancel semantics."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@example.com"}, "c-1")],
            ),
            AIMessage(content="cancelled, not sending"),
        ]
    )
    capability_hitl = {
        "send_email": CapabilityHitlBinding(
            spec=HitlSpec(tool="send_email", require=True),
            context=cast(Any, None),
        )
    }
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        capability_hitl=capability_hitl,
        available_tool_names={"send_email"},
    )

    updates = await _drive(
        agent, {"messages": [HumanMessage("email a@example.com")]}, "t-pause-cancel"
    )
    assert _has_interrupt(updates)

    resumed = await _drive(
        agent, Command(resume={"choice_id": "cancel"}), "t-pause-cancel"
    )
    assert not _has_interrupt(resumed)
    tool_messages = [
        message
        for update in resumed
        for value in update.values()
        if isinstance(value, dict)
        for message in value.get("messages") or []
        if getattr(message, "type", None) == "tool"
    ]
    assert not tool_messages  # the gated call never executed


@pytest.mark.asyncio
async def test_deep_hitl_filesystem_tool_name_overlap_does_not_collide() -> None:
    """`deepagents.create_deep_agent` always injects its own built-in
    filesystem tools (`ls`/`read_file`/`write_file`/...) regardless of the
    `tools=` list passed in, and `FredHitlMiddleware.rewrite_filesystem_tool_arguments`
    treats those same names specially. No shipped capability gates a
    filesystem tool by name today, but if one did, gating must still compose
    cleanly with the rewrite step instead of colliding — one combined
    interrupt, no double gate, no crash."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    _tool_call("read_file", {"file_path": "/workspace/notes.md"}, "c-1")
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    capability_hitl = {
        "read_file": CapabilityHitlBinding(
            spec=HitlSpec(tool="read_file", require=True),
            context=cast(Any, None),
        )
    }
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        capability_hitl=capability_hitl,
        # Includes "read_file" to match what build_executor actually computes
        # when Fred's own filesystem MCP tool is bound under that name (the
        # per-name enabled filesystem case) — this is what makes
        # `rewrite_filesystem_tool_arguments` actually engage instead of
        # no-opping merely because the gate itself thinks no filesystem tool
        # is available.
        available_tool_names={"send_email", "read_file"},
    )

    updates = await _drive(
        agent, {"messages": [HumanMessage("read my notes")]}, "t-fs-overlap"
    )
    # Exactly one interrupt for the batch — no second, native gate fired
    # alongside FredHitlMiddleware's.
    interrupt_updates = [u for u in updates if "__interrupt__" in u]
    assert len(interrupt_updates) == 1
    assert len(interrupt_updates[0]["__interrupt__"]) == 1

    resumed = await _drive(
        agent, Command(resume={"choice_id": "proceed"}), "t-fs-overlap"
    )
    assert not _has_interrupt(resumed)


@pytest.mark.asyncio
async def test_deep_hitl_operator_policy_gates_named_tool_and_resumes_on_proceed() -> (
    None
):
    """Operator-configured `always_require_tools` gates a Deep tool call the
    same way a capability `HitlSpec` does, through the same real compiled
    graph — the build-time rejection this used to hit is gone."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@example.com"}, "c-1")],
            ),
            AIMessage(content="sent"),
        ]
    )
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        available_tool_names={"send_email"},
        approval_policy=ToolApprovalPolicy(
            enabled=True, always_require_tools=("send_email",)
        ),
    )

    updates = await _drive(
        agent, {"messages": [HumanMessage("email a@example.com")]}, "t-operator-proceed"
    )
    assert _has_interrupt(updates)

    resumed = await _drive(
        agent, Command(resume={"choice_id": "proceed"}), "t-operator-proceed"
    )
    assert not _has_interrupt(resumed)
    tool_messages = [
        message
        for update in resumed
        for value in update.values()
        if isinstance(value, dict)
        for message in value.get("messages") or []
        if getattr(message, "type", None) == "tool"
    ]
    assert any(
        getattr(message, "content", "") == "sent to a@example.com"
        for message in tool_messages
    )


@pytest.mark.asyncio
async def test_deep_hitl_operator_policy_cancel_skips_the_tool() -> None:
    """An operator-gated Deep tool call must skip on cancel, same as a
    capability-gated one."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@example.com"}, "c-1")],
            ),
            AIMessage(content="cancelled, not sending"),
        ]
    )
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        available_tool_names={"send_email"},
        approval_policy=ToolApprovalPolicy(
            enabled=True, always_require_tools=("send_email",)
        ),
    )

    updates = await _drive(
        agent, {"messages": [HumanMessage("email a@example.com")]}, "t-operator-cancel"
    )
    assert _has_interrupt(updates)

    resumed = await _drive(
        agent, Command(resume={"choice_id": "cancel"}), "t-operator-cancel"
    )
    assert not _has_interrupt(resumed)
    tool_messages = [
        message
        for update in resumed
        for value in update.values()
        if isinstance(value, dict)
        for message in value.get("messages") or []
        if getattr(message, "type", None) == "tool"
    ]
    assert not tool_messages  # the gated call never executed


@pytest.mark.asyncio
async def test_deep_hitl_tool_outside_operator_list_skips_gate() -> None:
    """A tool with no capability binding and not in the operator's exact list
    runs without pausing — mirrors ReAct's
    `test_hitl_tool_outside_operator_list_skips_gate`."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@example.com"}, "c-1")],
            ),
            AIMessage(content="sent"),
        ]
    )
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        available_tool_names={"send_email"},
        approval_policy=ToolApprovalPolicy(
            enabled=True, always_require_tools=("other_tool",)
        ),
    )

    updates = await _drive(
        agent,
        {"messages": [HumanMessage("email a@example.com")]},
        "t-operator-unlisted",
    )
    assert not _has_interrupt(updates)


async def _stream_events(
    executor: _TransportBackedReActExecutor,
    input_model: ReActInput,
    config: ExecutionConfig,
) -> list[Any]:
    return [event async for event in executor.stream(input_model, config)]


@pytest.mark.asyncio
async def test_deep_hitl_transport_level_pause_is_observable_and_resumes_on_proceed() -> (
    None
):
    """Transport-level proof: the pause must reach the real
    `_TransportBackedReActExecutor` as an `AwaitingHumanRuntimeEvent`, and
    resume via `ExecutionConfig.resume_payload`/`interrupt_id` — LangGraph's
    targeted `Command(resume={interrupt_id: payload})` form, not the bare
    `Command(resume=payload)` the compiled-graph tests above use directly."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@example.com"}, "c-1")],
            ),
            AIMessage(content="sent"),
        ]
    )
    capability_hitl = {
        "send_email": CapabilityHitlBinding(
            spec=HitlSpec(tool="send_email", require=True),
            context=cast(Any, None),
        )
    }
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        capability_hitl=capability_hitl,
        available_tool_names={"send_email"},
    )
    executor = _TransportBackedReActExecutor(
        compiled_agent=agent,
        binding=_binding(),
        services=RuntimeServices(),
        runtime_class_name="DeepAgentRuntime",
    )
    input_model = ReActInput(
        messages=(
            ReActMessage(role=ReActMessageRole.USER, content="email a@example.com"),
        )
    )

    events = await _stream_events(
        executor, input_model, ExecutionConfig(session_id="t-transport-proceed")
    )
    awaiting = [e for e in events if isinstance(e, AwaitingHumanRuntimeEvent)]
    assert len(awaiting) == 1
    request = awaiting[0].request
    assert request.interrupt_id

    resumed_events = await _stream_events(
        executor,
        input_model,
        ExecutionConfig(
            session_id="t-transport-proceed",
            interrupt_id=request.interrupt_id,
            resume_payload={"choice_id": "proceed"},
        ),
    )
    assert not any(isinstance(e, AwaitingHumanRuntimeEvent) for e in resumed_events)
    tool_results = [
        e
        for e in resumed_events
        if type(e).__name__ == "ToolResultRuntimeEvent"
        and getattr(e, "content", None) == "sent to a@example.com"
    ]
    assert len(tool_results) == 1


@pytest.mark.asyncio
async def test_deep_hitl_transport_level_cancel_executes_the_tool_zero_times() -> None:
    """Same transport-level proof as above, for the cancel outcome: resuming
    with a cancel decision through `_TransportBackedReActExecutor` must not
    execute the gated tool."""

    model = _RecordingModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("send_email", {"to": "a@example.com"}, "c-1")],
            ),
            AIMessage(content="cancelled, not sending"),
        ]
    )
    capability_hitl = {
        "send_email": CapabilityHitlBinding(
            spec=HitlSpec(tool="send_email", require=True),
            context=cast(Any, None),
        )
    }
    agent = _compile_deep_agent(
        model,
        tools=[send_email],
        capability_hitl=capability_hitl,
        available_tool_names={"send_email"},
    )
    executor = _TransportBackedReActExecutor(
        compiled_agent=agent,
        binding=_binding(),
        services=RuntimeServices(),
        runtime_class_name="DeepAgentRuntime",
    )
    input_model = ReActInput(
        messages=(
            ReActMessage(role=ReActMessageRole.USER, content="email a@example.com"),
        )
    )

    events = await _stream_events(
        executor, input_model, ExecutionConfig(session_id="t-transport-cancel")
    )
    awaiting = [e for e in events if isinstance(e, AwaitingHumanRuntimeEvent)]
    assert len(awaiting) == 1
    request = awaiting[0].request
    assert request.interrupt_id

    resumed_events = await _stream_events(
        executor,
        input_model,
        ExecutionConfig(
            session_id="t-transport-cancel",
            interrupt_id=request.interrupt_id,
            resume_payload={"choice_id": "cancel"},
        ),
    )
    assert not any(isinstance(e, AwaitingHumanRuntimeEvent) for e in resumed_events)
    tool_results = [
        e for e in resumed_events if type(e).__name__ == "ToolResultRuntimeEvent"
    ]
    assert len(tool_results) == 0
