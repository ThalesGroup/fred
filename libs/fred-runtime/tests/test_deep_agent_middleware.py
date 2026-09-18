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
Tests proving DeepAgentRuntime gets the same observability guarantees as
ReActRuntime.

Deep overrides `build_executor` and never goes through
`build_react_platform_middleware_frame()`, so it used to silently skip
`TracingKpiMiddleware`/`ToolObservabilityMiddleware` — no `[LLM][CALL]` logs,
no `llm.call_latency_ms`/`agent.tool_latency_ms` KPI, no
`agent.tool.invocation.*` audit events for any Deep turn. These tests cover
both the middleware-list builder in isolation (mirrors
`test_react_middleware_frame.py::test_frame_order_is_fixed`) and the real
`build_executor` wiring (mirrors
`test_runtime_context_prompt_injection.py`'s stubbed-compile pattern).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast

import fred_runtime.deep.deep_runtime as deep_mod
import pytest
from conftest import ToolFriendlyFakeChatModel
from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.react.middleware.checkpoint_hygiene import CheckpointHygieneMiddleware
from fred_runtime.react.middleware.hitl import CapabilityHitlBinding, FredHitlMiddleware
from fred_runtime.react.middleware.rate_limit_retry import RateLimitRetryMiddleware
from fred_runtime.react.middleware.tool_observability import (
    ToolObservabilityMiddleware,
)
from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
from fred_sdk.contracts.capability import HitlSpec
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.runtime import RuntimeServices
from langchain.agents.middleware import AgentMiddleware, ToolCallLimitMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr


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


# ---------------------------------------------------------------------------
# _build_deepagent_runtime_middleware — list composition
# ---------------------------------------------------------------------------


def test_middleware_leads_with_observability_then_hitl_when_filesystem_enabled() -> (
    None
):
    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(deep_mod._FILESYSTEM_TOOL_NAMES),
    )
    assert [type(m) for m in middleware] == [
        CheckpointHygieneMiddleware,
        RateLimitRetryMiddleware,
        TracingKpiMiddleware,
        ToolObservabilityMiddleware,
        FredHitlMiddleware,
    ]


def test_middleware_keeps_hitl_before_filesystem_guards() -> None:
    """Mirrors `build_react_platform_middleware_frame`'s order exactly: the
    filesystem guards are listed AFTER `FredHitlMiddleware` on purpose, since
    `after_model` hooks run in reverse list order — a disabled filesystem call
    must still be blocked before the human gate ever sees it."""
    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(),
    )
    assert type(middleware[0]) is CheckpointHygieneMiddleware
    assert type(middleware[1]) is RateLimitRetryMiddleware
    assert type(middleware[2]) is TracingKpiMiddleware
    assert type(middleware[3]) is ToolObservabilityMiddleware
    assert type(middleware[4]) is FredHitlMiddleware
    assert all(type(m) is ToolCallLimitMiddleware for m in middleware[5:])
    # One guard per disabled filesystem tool name (ls/read_file/write_file/
    # edit_file/glob/grep/execute).
    assert len(middleware) == 5 + 7


def test_middleware_keeps_guard_for_each_unbound_filesystem_tool() -> None:
    available_tool_names = set(deep_mod._FILESYSTEM_TOOL_NAMES) - {"execute"}

    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=available_tool_names,
    )

    guards = [m for m in middleware if type(m) is ToolCallLimitMiddleware]
    assert [guard.tool_name for guard in guards] == ["execute"]
    assert deep_mod._filesystem_prompt_suffix(
        available_tool_names=available_tool_names
    ) == (
        "The following filesystem tools are disabled in this runtime: "
        "execute. Do not call them."
    )


class _MarkerMiddleware(AgentMiddleware):
    pass


def test_middleware_places_capability_middleware_before_observability() -> None:
    marker = _MarkerMiddleware()
    capability_block = CapabilityAgentBlock(
        middleware=(marker,), hitl={}, tools=(), mcp_prompt_groups=()
    )
    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(deep_mod._FILESYSTEM_TOOL_NAMES),
        capability_block=capability_block,
    )
    assert type(middleware[0]) is CheckpointHygieneMiddleware
    assert middleware[1] is marker
    assert type(middleware[2]) is RateLimitRetryMiddleware
    assert type(middleware[3]) is TracingKpiMiddleware
    assert type(middleware[4]) is ToolObservabilityMiddleware
    assert type(middleware[5]) is FredHitlMiddleware


def test_middleware_threads_capability_hitl_into_fred_hitl_middleware() -> None:
    """The merged gate must actually receive a selected capability's `HitlSpec`
    bindings — this is the piece that used to be rejected outright (see
    `test_deep_build_executor_no_longer_rejects_capability_hitl` for the
    build_executor-level proof)."""
    binding = CapabilityHitlBinding(
        spec=HitlSpec(tool="send_email", require=True),
        context=cast(Any, None),
    )
    capability_block = CapabilityAgentBlock(
        middleware=(), hitl={"send_email": binding}, tools=(), mcp_prompt_groups=()
    )
    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names={"send_email"},
        capability_block=capability_block,
    )
    hitl_middleware = next(m for m in middleware if type(m) is FredHitlMiddleware)
    assert hitl_middleware._capability_hitl == {"send_email": binding}


# ---------------------------------------------------------------------------
# build_executor — the real wiring, stubbed compile step
# ---------------------------------------------------------------------------


class _FakePolicy:
    def __init__(self, *, tool_approval_enabled: bool = False) -> None:
        self.system_prompt_template = "BASE-TEMPLATE"
        self.tool_approval = SimpleNamespace(
            enabled=tool_approval_enabled, always_require_tools=("send_email",)
        )
        self.tool_selection = SimpleNamespace(
            max_tool_calls_per_turn=None, allow_parallel_calls=False
        )


class _FakeDefinition:
    agent_id = "agent-1"
    declared_tool_refs: tuple[object, ...] = ()
    tuning_values: dict[str, str] = {}
    tool_approval_enabled = False

    def policy(self) -> _FakePolicy:
        return _FakePolicy(tool_approval_enabled=self.tool_approval_enabled)


class _FakeResolver:
    def __init__(self, **_: object) -> None:
        pass

    def resolve_tools(self) -> list[object]:
        return []


class _FakeBinder:
    def __init__(self, **_: object) -> None:
        pass

    def build_tools(self) -> list[object]:
        return []


class _PartialFilesystemBinder:
    def __init__(self, **_: object) -> None:
        pass

    def build_tools(self) -> list[object]:
        return [
            SimpleNamespace(
                runtime_name=name,
                description=f"Filesystem operation {name}",
                tool=SimpleNamespace(name=name),
                mcp_server_id=None,
            )
            for name in deep_mod._FILESYSTEM_TOOL_NAMES
            if name != "execute"
        ]


class _FakeExecutor:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


def _fake_definition() -> ReActAgentDefinition:
    return cast(ReActAgentDefinition, _FakeDefinition())


@pytest.mark.asyncio
async def test_deep_build_executor_wires_observability_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_compile(**kwargs: object) -> object:
        captured["middleware"] = list(cast(list, kwargs["middleware"]))
        return object()

    monkeypatch.setattr(deep_mod, "ReActRuntimeToolResolver", _FakeResolver)
    monkeypatch.setattr(deep_mod, "ReActToolBinder", _FakeBinder)
    monkeypatch.setattr(deep_mod, "_TransportBackedReActExecutor", _FakeExecutor)
    monkeypatch.setattr(deep_mod, "_create_compiled_deep_agent", _fake_compile)

    runtime = deep_mod.DeepAgentRuntime(
        definition=_fake_definition(), services=RuntimeServices()
    )
    runtime._model = cast(BaseChatModel, SimpleNamespace())

    await runtime.build_executor(_binding())

    # The fake tool pipeline resolves no tools, so the filesystem guard
    # clause also fires — this test only cares that observability leads.
    wired = captured["middleware"]
    assert type(wired[0]) is CheckpointHygieneMiddleware
    assert type(wired[1]) is RateLimitRetryMiddleware
    assert type(wired[2]) is TracingKpiMiddleware
    assert type(wired[3]) is ToolObservabilityMiddleware


@pytest.mark.asyncio
async def test_deep_build_executor_guards_unbound_execute_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_compile(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(deep_mod, "ReActRuntimeToolResolver", _FakeResolver)
    monkeypatch.setattr(deep_mod, "ReActToolBinder", _PartialFilesystemBinder)
    monkeypatch.setattr(deep_mod, "_TransportBackedReActExecutor", _FakeExecutor)
    monkeypatch.setattr(deep_mod, "_create_compiled_deep_agent", _fake_compile)

    runtime = deep_mod.DeepAgentRuntime(
        definition=_fake_definition(), services=RuntimeServices()
    )
    runtime._model = cast(BaseChatModel, SimpleNamespace())

    await runtime.build_executor(_binding())

    middleware = cast(list[AgentMiddleware], captured["middleware"])
    guards = [m for m in middleware if type(m) is ToolCallLimitMiddleware]
    assert [guard.tool_name for guard in guards] == ["execute"]
    assert "filesystem tools are disabled in this runtime: execute" in cast(
        str, captured["system_prompt"]
    )


@pytest.mark.asyncio
async def test_deep_build_executor_wires_capability_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A selected capability's middleware (e.g. ToolCarrierMiddleware, the
    only channel that delivers its tools) must reach the compiled deep
    agent, not be silently dropped — this was the regression the dispatch
    fix would otherwise have introduced (previously Deep only ran, by
    accident, via ReActRuntime, which does wire capability_block)."""
    captured: dict[str, Any] = {}

    def _fake_compile(**kwargs: object) -> object:
        captured["middleware"] = list(cast(list, kwargs["middleware"]))
        return object()

    monkeypatch.setattr(deep_mod, "ReActRuntimeToolResolver", _FakeResolver)
    monkeypatch.setattr(deep_mod, "ReActToolBinder", _FakeBinder)
    monkeypatch.setattr(deep_mod, "_TransportBackedReActExecutor", _FakeExecutor)
    monkeypatch.setattr(deep_mod, "_create_compiled_deep_agent", _fake_compile)

    marker = _MarkerMiddleware()
    capability_block = CapabilityAgentBlock(
        middleware=(marker,), hitl={}, tools=(), mcp_prompt_groups=()
    )
    runtime = deep_mod.DeepAgentRuntime(
        definition=_fake_definition(),
        services=RuntimeServices(),
        capability_block=capability_block,
    )
    runtime._model = cast(BaseChatModel, SimpleNamespace())

    await runtime.build_executor(_binding())

    assert marker in captured["middleware"]


@pytest.mark.asyncio
async def test_deep_build_executor_no_longer_rejects_capability_hitl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A capability with a non-empty `hitl_specs()` must not be rejected at
    build time — `build_executor` threads the binding into the wired
    FredHitlMiddleware instead (RUNTIME-EXECUTION-CONTRACT.md §8.76)."""
    binding = CapabilityHitlBinding(
        spec=HitlSpec(tool="send_email", require=True),
        context=cast(Any, None),
    )
    capability_block = CapabilityAgentBlock(
        middleware=(), hitl={"send_email": binding}, tools=(), mcp_prompt_groups=()
    )
    captured: dict[str, Any] = {}

    def _fake_compile(**kwargs: object) -> object:
        captured["middleware"] = list(cast(list, kwargs["middleware"]))
        return object()

    monkeypatch.setattr(deep_mod, "ReActRuntimeToolResolver", _FakeResolver)
    monkeypatch.setattr(deep_mod, "ReActToolBinder", _FakeBinder)
    monkeypatch.setattr(deep_mod, "_TransportBackedReActExecutor", _FakeExecutor)
    monkeypatch.setattr(deep_mod, "_create_compiled_deep_agent", _fake_compile)

    runtime = deep_mod.DeepAgentRuntime(
        definition=_fake_definition(),
        services=RuntimeServices(),
        capability_block=capability_block,
    )
    runtime._model = cast(BaseChatModel, SimpleNamespace())

    await runtime.build_executor(_binding())

    hitl_middleware = next(
        m for m in captured["middleware"] if type(m) is FredHitlMiddleware
    )
    assert hitl_middleware._capability_hitl == {"send_email": binding}


@pytest.mark.asyncio
async def test_deep_build_executor_no_longer_rejects_operator_tool_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An enabled operator `ToolApprovalPolicy` must not be rejected at build
    time — `build_executor` threads it into the same wired FredHitlMiddleware
    capability HITL already uses (RUNTIME-EXECUTION-CONTRACT.md §8.76)."""
    captured: dict[str, Any] = {}

    def _fake_compile(**kwargs: object) -> object:
        captured["middleware"] = list(cast(list, kwargs["middleware"]))
        return object()

    monkeypatch.setattr(deep_mod, "ReActRuntimeToolResolver", _FakeResolver)
    monkeypatch.setattr(deep_mod, "ReActToolBinder", _FakeBinder)
    monkeypatch.setattr(deep_mod, "_TransportBackedReActExecutor", _FakeExecutor)
    monkeypatch.setattr(deep_mod, "_create_compiled_deep_agent", _fake_compile)

    definition = _FakeDefinition()
    definition.tool_approval_enabled = True
    runtime = deep_mod.DeepAgentRuntime(
        definition=cast(ReActAgentDefinition, definition),
        services=RuntimeServices(),
    )
    runtime._model = cast(BaseChatModel, SimpleNamespace())

    await runtime.build_executor(_binding())

    hitl_middleware = next(
        m for m in captured["middleware"] if type(m) is FredHitlMiddleware
    )
    assert hitl_middleware._approval_policy.enabled is True
    assert hitl_middleware._approval_policy.always_require_tools == ("send_email",)


@pytest.mark.asyncio
async def test_compiled_deep_parent_sanitizes_payload_without_rewriting_checkpoint() -> (
    None
):
    payloads: list[dict[str, Any]] = []
    serializer = ChatOpenAI(model="mistral-small", api_key=SecretStr("offline-test"))

    class CapturePayload(AgentMiddleware):
        async def awrap_model_call(
            self,
            request: ModelRequest,
            handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
        ) -> ModelResponse:
            payloads.append(serializer._get_request_payload(request.messages))
            return await handler(request)

    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(),
        capability_block=CapabilityAgentBlock(
            middleware=(CapturePayload(),),
            tools=(),
            hitl={},
            mcp_prompt_groups=(),
        ),
    )
    messages = [
        HumanMessage(content="old question", id="human-old"),
        AIMessage(
            content="",
            id="dangling",
            tool_calls=[
                {"name": "lookup", "args": {}, "id": "unanswered"},
            ],
        ),
        HumanMessage(content="current question", id="human-current"),
        AIMessage(
            content=[
                {"type": "thinking", "thinking": [{"type": "text", "text": "list it"}]}
            ],
            name="general-purpose",
            id="named",
            tool_calls=[
                {"name": "lookup", "args": {}, "id": "answered"},
            ],
        ),
        ToolMessage(
            content="found", tool_call_id="answered", name="lookup", id="result"
        ),
    ]
    before = [message.model_dump() for message in messages]
    graph = cast(
        Any,
        deep_mod._create_compiled_deep_agent(
            model=ToolFriendlyFakeChatModel(responses=[AIMessage(content="done")]),
            tools=[],
            system_prompt="Answer briefly.",
            checkpointer=InMemorySaver(),
            middleware=middleware,
        ),
    )
    config = {"configurable": {"thread_id": "hygiene-parent"}}
    await graph.ainvoke({"messages": messages}, config)
    wire = payloads[0]["messages"]
    assistants = [message for message in wire if message["role"] == "assistant"]
    assert all("name" not in message for message in assistants)
    replayed = next(
        message
        for message in assistants
        if message["tool_calls"][0]["id"] == "answered"
    )
    assert isinstance(replayed["content"], str)
    assert "list it" in replayed["content"]
    # Deep repairs older dangling calls before model wrappers run.
    call_ids = {call["id"] for message in assistants for call in message["tool_calls"]}
    result_ids = {
        message["tool_call_id"] for message in wire if message["role"] == "tool"
    }
    assert call_ids == result_ids
    assert [message.model_dump() for message in messages] == before
    checkpoint = await graph.aget_state(config)
    persisted = {message.id: message for message in checkpoint.values["messages"]}
    for original in messages:
        assert persisted[original.id].model_dump() == original.model_dump()


@pytest.mark.asyncio
async def test_deep_hygiene_leaves_history_size_to_deep_compaction() -> None:
    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(),
    )
    # Deep's summarization middleware owns compaction: no count or size trim.
    messages: list[AnyMessage] = [
        HumanMessage(content=str(index)) for index in range(501)
    ]
    messages.append(HumanMessage(content="x" * 250_000))
    seen: list[ModelRequest] = []

    async def handler(request: ModelRequest) -> ModelResponse:
        seen.append(request)
        return ModelResponse(result=[AIMessage(content="done")])

    await middleware[0].awrap_model_call(
        ModelRequest(model=ToolFriendlyFakeChatModel(responses=[]), messages=messages),
        handler,
    )
    assert seen[0].messages == messages


@pytest.mark.asyncio
async def test_deep_hygiene_removes_dangling_calls_without_changing_input() -> None:
    middleware = deep_mod._build_deepagent_runtime_middleware(
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(),
    )
    messages = [
        HumanMessage(content="old"),
        AIMessage(
            content="", tool_calls=[{"name": "lookup", "args": {}, "id": "missing"}]
        ),
        HumanMessage(content="new"),
    ]
    before = [message.model_dump() for message in messages]

    async def handler(request: ModelRequest) -> ModelResponse:
        assert request.messages == [messages[0], messages[2]]
        return ModelResponse(result=[AIMessage(content="done")])

    await middleware[0].awrap_model_call(
        ModelRequest(model=ToolFriendlyFakeChatModel(responses=[]), messages=messages),
        handler,
    )
    assert [message.model_dump() for message in messages] == before
