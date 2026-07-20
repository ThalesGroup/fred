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
from fred_runtime.deep.deep_runtime import (
    _build_deepagent_runtime_middleware,
)
from fred_runtime.react.middleware.tool_observability import (
    ToolObservabilityMiddleware,
)
from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as ProcessRuntimeContext
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import ReActAgentDefinition
from fred_sdk.contracts.runtime import RuntimeServices
from langchain.agents.middleware import ToolCallLimitMiddleware
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


def test_middleware_leads_with_observability_when_filesystem_enabled() -> None:
    middleware = _build_deepagent_runtime_middleware(
        filesystem_tools_enabled=True,
        tracer=None,
        kpi=None,
        binding=_binding(),
    )
    assert [type(m) for m in middleware] == [
        TracingKpiMiddleware,
        ToolObservabilityMiddleware,
    ]


def test_middleware_keeps_observability_first_then_filesystem_guards() -> None:
    middleware = _build_deepagent_runtime_middleware(
        filesystem_tools_enabled=False,
        tracer=None,
        kpi=None,
        binding=_binding(),
    )
    assert type(middleware[0]) is TracingKpiMiddleware
    assert type(middleware[1]) is ToolObservabilityMiddleware
    assert all(type(m) is ToolCallLimitMiddleware for m in middleware[2:])
    # One guard per disabled filesystem tool name (ls/read_file/write_file/
    # edit_file/glob/grep/execute).
    assert len(middleware) == 2 + 7


# ---------------------------------------------------------------------------
# build_executor — the real wiring, stubbed compile step
# ---------------------------------------------------------------------------


class _FakePolicy:
    def __init__(self) -> None:
        self.system_prompt_template = "BASE-TEMPLATE"
        self.guardrails: list[object] = []
        self.tool_approval = SimpleNamespace(enabled=False)
        self.tool_selection = SimpleNamespace(
            max_tool_calls_per_turn=None, allow_parallel_calls=False
        )


class _FakeDefinition:
    agent_id = "agent-1"
    declared_tool_refs: tuple[object, ...] = ()
    tuning_values: dict[str, str] = {}

    def policy(self) -> _FakePolicy:
        return _FakePolicy()


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

    # build_executor reads the KPI writer off the process-wide runtime
    # context (mirrors `test_kf_workspace_client.py`'s `_make_client`
    # helper) — a NoOpKPIWriter is enough, no real config needed.
    set_runtime_context(
        ProcessRuntimeContext(RuntimeConfig(knowledge_flow_url="http://test"))
    )
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
