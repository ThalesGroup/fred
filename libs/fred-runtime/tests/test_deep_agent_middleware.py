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

from types import SimpleNamespace
from typing import Any, cast

import fred_runtime.deep.deep_runtime as deep_mod
import pytest
from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.react.middleware.hitl import CapabilityHitlBinding, FredHitlMiddleware
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
from langchain_core.language_models.chat_models import BaseChatModel


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
        filesystem_tools_enabled=True,
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(),
    )
    assert [type(m) for m in middleware] == [
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
        filesystem_tools_enabled=False,
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(),
    )
    assert type(middleware[0]) is TracingKpiMiddleware
    assert type(middleware[1]) is ToolObservabilityMiddleware
    assert type(middleware[2]) is FredHitlMiddleware
    assert all(type(m) is ToolCallLimitMiddleware for m in middleware[3:])
    # One guard per disabled filesystem tool name (ls/read_file/write_file/
    # edit_file/glob/grep/execute).
    assert len(middleware) == 3 + 7


class _MarkerMiddleware(AgentMiddleware):
    pass


def test_middleware_places_capability_middleware_before_observability() -> None:
    marker = _MarkerMiddleware()
    capability_block = CapabilityAgentBlock(
        middleware=(marker,), hitl={}, tools=(), mcp_prompt_groups=()
    )
    middleware = deep_mod._build_deepagent_runtime_middleware(
        filesystem_tools_enabled=True,
        tracer=None,
        kpi=None,
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(),
        available_tool_names=set(),
        capability_block=capability_block,
    )
    assert middleware[0] is marker
    assert type(middleware[1]) is TracingKpiMiddleware
    assert type(middleware[2]) is ToolObservabilityMiddleware
    assert type(middleware[3]) is FredHitlMiddleware


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
        filesystem_tools_enabled=True,
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
    assert type(wired[0]) is TracingKpiMiddleware
    assert type(wired[1]) is ToolObservabilityMiddleware


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
