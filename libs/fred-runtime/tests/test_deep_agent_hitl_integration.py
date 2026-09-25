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

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import fred_runtime.deep.deep_runtime as deep_mod
import pytest
from conftest import RecordingSpan, RecordingTracer, ToolFriendlyFakeChatModel
from deepagents.backends import StateBackend
from deepagents.backends.protocol import BackendProtocol
from deepagents.middleware import subagents as deep_subagents
from deepagents.middleware.filesystem import FilesystemMiddleware
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.react.middleware.hitl import CapabilityHitlBinding
from fred_runtime.react.react_runtime import _TransportBackedReActExecutor
from fred_runtime.react.react_tracing import active_agent_span
from fred_sdk.contracts.capability import HitlSpec, ToolCarrierMiddleware
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
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer, Command
from pydantic import Field, SecretStr


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
        subagent_middleware=deep_mod._build_deepagent_runtime_middleware(
            tracer=None,
            kpi=None,
            binding=_binding(),
            approval_policy=approval_policy or ToolApprovalPolicy(),
            available_tool_names=available_tool_names,
            capability_block=capability_block,
            child=True,
        ),
        backend=StateBackend(),
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


class _NativeModel(ToolFriendlyFakeChatModel):
    """Route scripted replies by task input so concurrent children are deterministic."""

    scripts: dict[str, list[AIMessage]]
    requests: list[list[BaseMessage]] = Field(default_factory=list)
    bound_names: list[set[str]] = Field(default_factory=list)
    fail_after_tool: bool = False
    failed: bool = False
    pause_model: asyncio.Event | None = None

    def bind_tools(self, tools: Any, **kwargs: Any) -> _NativeModel:
        self.bound_names.append({tool.name for tool in tools})
        return self

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.requests.append(list(messages))
        key = next(
            str(message.content)
            for message in messages
            if isinstance(message, HumanMessage)
        )
        if self.pause_model is not None and key != "parent":
            self.pause_model.set()
            await asyncio.Future()
        if (
            self.fail_after_tool
            and key != "parent"
            and any(isinstance(m, ToolMessage) for m in messages)
            and not self.failed
        ):
            self.failed = True
            raise _NativeRateLimited()
        index = sum(isinstance(message, AIMessage) for message in messages)
        return ChatResult(
            generations=[ChatGeneration(message=self.scripts[key][index])]
        )


class _NativeRateLimited(Exception):
    status_code = 429
    headers = {"Retry-After": "0"}


def _delegation(*children: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            _tool_call(
                "task",
                {"description": child, "subagent_type": "general-purpose"},
                f"task-{child}",
            )
            for child in children
        ],
    )


def _native_agent(
    model: _NativeModel,
    *,
    tools: list[Any],
    backend: BackendProtocol | None = None,
    capability_hitl: dict[str, CapabilityHitlBinding] | None = None,
    approval_policy: ToolApprovalPolicy | None = None,
    tracer: RecordingTracer | None = None,
    available_tool_names: set[str] | None = None,
) -> Any:
    carrier = ToolCarrierMiddleware(tools, capability_id="scoped-test")
    block = CapabilityAgentBlock(
        middleware=(carrier,),
        tools=tuple(tools),
        hitl=capability_hitl or {},
        mcp_prompt_groups=(),
    )

    def frame(*, child: bool = False) -> list[AgentMiddleware]:
        return deep_mod._build_deepagent_runtime_middleware(
            tracer=tracer,
            kpi=None,
            binding=_binding(),
            approval_policy=approval_policy or ToolApprovalPolicy(),
            available_tool_names=(
                available_tool_names
                if available_tool_names is not None
                else {tool.name for tool in tools}
            ),
            capability_block=block,
            child=child,
        )

    return deep_mod._create_compiled_deep_agent(
        model=model,
        tools=[],
        system_prompt="INSTANCE INSTRUCTIONS: use only the selected scope.",
        checkpointer=InMemorySaver(),
        middleware=frame(),
        subagent_middleware=frame(child=True),
        backend=backend if backend is not None else StateBackend(),
    )


@pytest.mark.asyncio
async def test_native_children_and_parent_share_live_conversation_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SharedNamespace:
        content: str | None = None

        async def exists(self, path: str) -> bool:
            del path
            return self.content is not None

        async def write_text(self, path: str, content: str) -> None:
            del path
            self.content = content

        async def read_text(self, path: str) -> str:
            del path
            assert self.content is not None
            return self.content

    child_backends: list[BackendProtocol] = []
    original_create_sub_agent = deep_subagents.create_sub_agent

    def capture_child_backend(*args: Any, **kwargs: Any) -> Any:
        spec = args[0]
        child_backends.extend(
            middleware.backend
            for middleware in spec["middleware"]
            if isinstance(middleware, FilesystemMiddleware)
            and isinstance(middleware.backend, BackendProtocol)
        )
        return original_create_sub_agent(*args, **kwargs)

    monkeypatch.setattr(deep_subagents, "create_sub_agent", capture_child_backend)
    model = _NativeModel(
        responses=[],
        scripts={"parent": [AIMessage(content="done")]},
    )
    namespace = SharedNamespace()
    backend = deep_mod.CompositeBackend(
        default=deep_mod.ConversationNamespaceBackend(
            cast(Any, SimpleNamespace(namespace=lambda *_args, **_kwargs: namespace)),
            namespace_id="scratchpad",
            max_bytes=100,
            max_files=10,
        ),
        routes={},
        artifacts_root="/.deep",
    )
    agent = _native_agent(model, tools=[], backend=backend)

    assert agent is not None
    assert child_backends
    assert all(child_backend is backend for child_backend in child_backends)
    child_write = await child_backends[0].awrite("/shared.md", "shared live")
    parent_read = await backend.aread("/shared.md")
    sibling_read = await child_backends[0].aread("/shared.md")

    assert child_write.error is None
    assert parent_read.file_data == {
        "content": "shared live",
        "encoding": "utf-8",
    }
    assert sibling_read.file_data == parent_read.file_data


@pytest.mark.asyncio
async def test_native_children_parent_and_fresh_graph_share_scratchpad(
    tmp_path: Any,
) -> None:
    safe_filesystem_tools = {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "glob",
        "grep",
    }
    storage = LocalFilesystem(str(tmp_path))
    backend = deep_mod._build_conversation_backend(
        ConversationFilesystemService(storage, "conversation-a")
    )
    model = _NativeModel(
        responses=[],
        scripts={
            "parent": [
                _delegation("writer"),
                _delegation("reader"),
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "read_file",
                            {"file_path": "/shared.md"},
                            "parent-read",
                        )
                    ],
                ),
                AIMessage(content="parent done"),
            ],
            "writer": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "write_file",
                            {
                                "file_path": "/shared.md",
                                "content": "shared live",
                            },
                            "child-write",
                        )
                    ],
                ),
                AIMessage(content="writer done"),
            ],
            "reader": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "read_file",
                            {"file_path": "/shared.md"},
                            "sibling-read",
                        )
                    ],
                ),
                AIMessage(content="reader done"),
            ],
        },
    )
    agent = _native_agent(
        model,
        tools=[],
        backend=backend,
        available_tool_names=safe_filesystem_tools,
    )

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="parent")]},
        {"configurable": {"thread_id": "shared-scratchpad-first"}},
    )

    tool_results = {
        message.tool_call_id: message
        for request in model.requests
        for message in request
        if isinstance(message, ToolMessage)
    }
    assert result["messages"][-1].content == "parent done"
    assert tool_results["child-write"].status == "success"
    assert "shared live" in str(tool_results["sibling-read"].content)
    assert "shared live" in str(tool_results["parent-read"].content)

    fresh_model = _NativeModel(
        responses=[],
        scripts={
            "fresh parent": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "read_file",
                            {"file_path": "/shared.md"},
                            "fresh-read",
                        )
                    ],
                ),
                AIMessage(content="fresh done"),
            ]
        },
    )
    fresh_backend = deep_mod._build_conversation_backend(
        ConversationFilesystemService(storage, "conversation-a")
    )
    fresh_agent = _native_agent(
        fresh_model,
        tools=[],
        backend=fresh_backend,
        available_tool_names=safe_filesystem_tools,
    )
    fresh_result = await fresh_agent.ainvoke(
        {"messages": [HumanMessage(content="fresh parent")]},
        {"configurable": {"thread_id": "shared-scratchpad-fresh"}},
    )
    fresh_read = next(
        message
        for request in fresh_model.requests
        for message in request
        if isinstance(message, ToolMessage) and message.tool_call_id == "fresh-read"
    )

    assert fresh_result["messages"][-1].content == "fresh done"
    assert fresh_read.status == "success"
    assert "shared live" in str(fresh_read.content)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "gate", ["operator", "required", "conditional", "raising", "false"]
)
async def test_native_child_approval_never_waits_or_bypasses(gate: str) -> None:
    executions: list[str] = []

    @tool
    def sensitive(value: str) -> str:
        """Perform a scoped action."""
        executions.append(value)
        return value

    @tool
    def harmless() -> str:
        """Read public information."""
        executions.append("harmless")
        return "safe"

    def condition(_request: Any) -> bool:
        if gate == "raising":
            raise ValueError("invalid policy input")
        return gate == "conditional"

    binding = CapabilityHitlBinding(
        spec=HitlSpec(tool="sensitive", require=gate == "required", when=condition),
        context=cast(Any, None),
    )
    model = _NativeModel(
        responses=[],
        scripts={
            "parent": [_delegation("child"), AIMessage(content="parent done")],
            "child": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call("sensitive", {"value": "secret"}, "sensitive-call"),
                        _tool_call("harmless", {}, "safe-call"),
                    ],
                ),
                AIMessage(content="child done"),
            ],
        },
    )
    agent = _native_agent(
        model,
        tools=[sensitive, harmless],
        capability_hitl={"sensitive": binding},
        approval_policy=ToolApprovalPolicy(
            enabled=gate == "operator", always_require_tools=("sensitive",)
        ),
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="parent")]},
        {"configurable": {"thread_id": gate}},
    )
    assert "__interrupt__" not in result
    assert result["messages"][-1].content == "parent done"
    assert sorted(executions) == (
        ["harmless", "secret"] if gate == "false" else ["harmless"]
    )
    child_requests = [
        messages
        for messages in model.requests
        if any(isinstance(m, HumanMessage) and m.content == "child" for m in messages)
    ]
    assert "INSTANCE INSTRUCTIONS" in str(child_requests[0][0].content)
    assert "There is no user" in str(child_requests[0][0].content)
    results = [
        m
        for m in child_requests[-1]
        if isinstance(m, ToolMessage) and m.tool_call_id == "sensitive-call"
    ]
    assert len(results) == 1
    assert results[0].status == ("success" if gate == "false" else "error")
    if gate in {"operator", "required"}:
        assert "sensitive" not in model.bound_names[1]
    assert "harmless" in model.bound_names[1]
    assert "task" not in model.bound_names[1]


@pytest.mark.asyncio
async def test_native_child_cannot_execute_disabled_filesystem_tools() -> None:
    model = _NativeModel(
        responses=[],
        scripts={
            "parent": [_delegation("child"), AIMessage(content="parent done")],
            "child": [
                AIMessage(
                    content="",
                    tool_calls=[
                        _tool_call(
                            "write_file",
                            {"file_path": "/blocked.txt", "content": "blocked"},
                            "blocked",
                        )
                    ],
                ),
                AIMessage(content="refused"),
            ],
        },
    )
    agent = _native_agent(model, tools=[])
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="parent")]},
        {"configurable": {"thread_id": "blocked"}},
    )
    assert not result.get("files")
    child_results = [
        m
        for messages in model.requests
        for m in messages
        if isinstance(m, ToolMessage) and m.tool_call_id == "blocked"
    ]
    assert child_results and all(
        "limit" in str(m.content).lower() for m in child_results
    )


@pytest.mark.asyncio
async def test_native_child_retry_hygiene_does_not_replay_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executions = 0

    @tool
    def increment() -> str:
        """Perform one side effect."""
        nonlocal executions
        executions += 1
        return "incremented"

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(
        "fred_runtime.react.middleware.rate_limit_retry.asyncio.sleep", no_sleep
    )
    model = _NativeModel(
        responses=[],
        fail_after_tool=True,
        scripts={
            "parent": [_delegation("child"), AIMessage(content="done")],
            "child": [
                AIMessage(
                    content="",
                    name="named-child",
                    tool_calls=[_tool_call("increment", {}, "once")],
                ),
                AIMessage(content="child done"),
            ],
        },
    )
    tracer = RecordingTracer(capture=True)
    agent = _native_agent(model, tools=[increment], tracer=tracer)
    await agent.ainvoke(
        {"messages": [HumanMessage(content="parent")]},
        {"configurable": {"thread_id": "retry"}},
    )
    assert executions == 1
    assert model.failed
    assert len(model.requests) == 5
    serializer = ChatOpenAI(model="unused", api_key=SecretStr("unused"))
    replay_requests = [
        messages
        for messages in model.requests
        if any(
            isinstance(m, ToolMessage) and m.tool_call_id == "once" for m in messages
        )
    ]
    assert len(replay_requests) == 2
    for messages in replay_requests:
        payload = serializer._get_request_payload(messages)
        assert all(
            "name" not in message
            for message in payload["messages"]
            if message["role"] == "assistant"
        )
    assert all(span.ended for _, _, span in tracer.spans)
    assert (
        sum(span.attributes.get("status") == "error" for _, _, span in tracer.spans)
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_native_parallel_children_keep_trace_context_and_close_spans(
    cancel: bool,
) -> None:
    both_started = asyncio.Event()
    release = asyncio.Event()
    observed: dict[str, object] = {}

    @tool
    async def rendezvous(label: str) -> str:
        """Wait until both child tasks overlap."""
        observed[label] = active_agent_span.get()
        if len(observed) == 2:
            both_started.set()
        await release.wait()
        assert active_agent_span.get() is observed[label]
        return label

    model = _NativeModel(
        responses=[],
        scripts={
            "parent": [_delegation("left", "right"), AIMessage(content="done")],
            **{
                label: [
                    AIMessage(
                        content="",
                        tool_calls=[
                            _tool_call("rendezvous", {"label": label}, f"call-{label}")
                        ],
                    ),
                    AIMessage(content=label),
                ]
                for label in ("left", "right")
            },
        },
    )
    tracer = RecordingTracer(capture=True)
    root = RecordingSpan()
    token = active_agent_span.set(root)
    try:
        agent = _native_agent(model, tools=[rendezvous], tracer=tracer)
        run = asyncio.create_task(
            agent.ainvoke(
                {"messages": [HumanMessage(content="parent")]},
                {"configurable": {"thread_id": f"parallel-{cancel}"}},
            )
        )
        await asyncio.wait_for(both_started.wait(), timeout=10)
        assert active_agent_span.get() is root
        assert observed["left"] is not observed["right"]
        if cancel:
            run.cancel()
            with pytest.raises(asyncio.CancelledError):
                await run
        else:
            release.set()
            await run
        task_spans = [
            span for _, attrs, span in tracer.spans if attrs.get("tool_name") == "task"
        ]
        assert len(task_spans) == 2
        for label in ("left", "right"):
            tool_span = observed[label]
            index = next(
                i for i, (_, _, span) in enumerate(tracer.spans) if span is tool_span
            )
            assert tracer.parents[index] in task_spans
            parent = tracer.parents[index]
            assert parent is not None
            assert any(
                label in str(item.get("input"))
                for item in cast(RecordingSpan, parent).io
            )
        assert all(span.ended for _, _, span in tracer.spans)
        assert active_agent_span.get() is root
        if cancel:
            assert all(
                cast(RecordingSpan, span).attributes["status"] == "cancelled"
                for span in observed.values()
            )
            assert all(span.attributes["status"] == "cancelled" for span in task_spans)
    finally:
        active_agent_span.reset(token)


@pytest.mark.asyncio
async def test_native_child_model_cancellation_propagates_and_closes_spans() -> None:
    started = asyncio.Event()
    model = _NativeModel(
        responses=[],
        pause_model=started,
        scripts={
            "parent": [_delegation("child")],
            "child": [],
        },
    )
    tracer = RecordingTracer()
    root = RecordingSpan()
    token = active_agent_span.set(root)
    try:
        agent = _native_agent(model, tools=[], tracer=tracer)
        run = asyncio.create_task(
            agent.ainvoke(
                {"messages": [HumanMessage(content="parent")]},
                {"configurable": {"thread_id": "model-cancel"}},
            )
        )
        try:
            await asyncio.wait_for(started.wait(), timeout=10)
            run.cancel()
            with pytest.raises(asyncio.CancelledError):
                await run
        finally:
            if not run.done():
                run.cancel()
                await asyncio.gather(run, return_exceptions=True)
        assert active_agent_span.get() is root
        assert len(tracer.spans) == 3  # Parent model, task tool, child model.
        assert all(span.ended for _, _, span in tracer.spans)
        task_span = next(
            span for _, attrs, span in tracer.spans if attrs.get("tool_name") == "task"
        )
        assert task_span.attributes["status"] == "cancelled"
        assert tracer.parents[-1] is task_span
    finally:
        active_agent_span.reset(token)
