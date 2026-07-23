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
Capability agent assembly + HITL gating through the platform frame (#1973).

Builds on the frame tests (`test_react_middleware_frame.py` — fakes are
imported, not duplicated) and covers what the registry tests cannot:

- the capability block is deterministic: sorted by capability id regardless
  of selection order, authored order preserved within one capability's stack
- the demo capability's tool is callable in chat when enabled in code (the
  same `build_tool_loop_compiled_react_agent` seam the executor uses)
- capability `HitlSpec`s gate through the ONE `FredHitlMiddleware`: `require`,
  `when` (typed context visible), raising `when` ⇒ interrupt (fail-closed), a
  non-gating spec staying non-gating (#1978 retired the legacy name-prefix
  heuristics — a capability tool is gated only by its own spec or the
  operator's exact list), operator exact-list override, and gating
  independent of the operator `enabled` toggle
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fred_runtime.capabilities import (
    CapabilityAssemblyError,
    CapabilityRegistry,
    build_capability_agent_block,
    build_capability_context,
)
from fred_runtime.capabilities.demo import DemoEchoCapability, DemoEchoConfig
from fred_runtime.react.react_model_adapter import (
    REACT_MODEL_OPERATION_ROUTING,
    infer_react_model_operation_from_messages,
)
from fred_runtime.react.react_tool_loop import build_tool_loop_compiled_react_agent
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityIdentity,
    CapabilityManifest,
    EmptyModel,
    HitlGateRequest,
    HitlSpec,
)
from fred_sdk.contracts.models import ToolApprovalPolicy
from fred_sdk.contracts.runtime import RuntimeServices
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer, Command
from pydantic import BaseModel
from test_react_middleware_frame import (
    ScriptedModel,
    _binding,
    _cfg,
    _definition,
    _tool_call,
)

# ---------------------------------------------------------------------------
# Test capabilities
# ---------------------------------------------------------------------------

GADGET_RUNS: list[dict[str, Any]] = []


class _GadgetConfig(BaseModel):
    workspace_root: str = "/workspace"


class _GadgetCapability(AgentCapability[_GadgetConfig, _GadgetConfig, EmptyModel]):
    """HITL tracer: one gated tool whose gate reads the typed config."""

    manifest = CapabilityManifest(
        id="demo_gadget",
        version="1.0.0",
        name="cap.demo_gadget.name",
        description="cap.demo_gadget.description",
        icon="Build",
    )
    ConfigModel = _GadgetConfig

    def __init__(
        self,
        *,
        require: bool = False,
        when: Any = None,
        question: str | None = None,
    ) -> None:
        self._spec = HitlSpec(
            tool="demo_gadget", require=require, when=when, question=question
        )

    def hitl_specs(self) -> list[HitlSpec]:
        return [self._spec]

    def tools(self, ctx: CapabilityContext[_GadgetConfig, EmptyModel]) -> list[Any]:
        del ctx

        @tool
        def demo_gadget(path: str) -> str:
            """Operate the demo gadget on a path."""

            GADGET_RUNS.append({"path": path})
            return f"gadget ran on {path}"

        return [demo_gadget]


class _NamedMiddleware(AgentMiddleware):
    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label

    @property
    def name(self) -> str:
        return f"named-{self.label}"


class _StackConfig(BaseModel):
    pass


def _stack_capability(cap_id: str) -> AgentCapability[Any, Any, Any]:
    class _Cap(AgentCapability[_StackConfig, _StackConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id=cap_id,
            version="1.0.0",
            name=f"cap.{cap_id}.name",
            description=f"cap.{cap_id}.description",
            icon="Layers",
        )
        ConfigModel = _StackConfig

        def middleware(
            self, ctx: CapabilityContext[_StackConfig, EmptyModel]
        ) -> list[AgentMiddleware]:
            return [
                _NamedMiddleware(f"{cap_id}-first"),
                _NamedMiddleware(f"{cap_id}-second"),
            ]

    return _Cap()


def _identity() -> CapabilityIdentity:
    return CapabilityIdentity(user_id="user-1", session_id="session-1")


def _contexts(
    registry: CapabilityRegistry,
    configs: dict[str, dict[str, Any]],
) -> dict[str, CapabilityContext[Any, Any]]:
    return {
        cap_id: build_capability_context(
            registry.capability(cap_id),
            identity=_identity(),
            services=RuntimeServices(),
            config=config,
        )
        for cap_id, config in configs.items()
    }


def _build_capability_agent(
    model: BaseChatModel,
    registry: CapabilityRegistry,
    configs: dict[str, dict[str, Any]],
    *,
    approval_enabled: bool = True,
    always_require_tools: list[str] | None = None,
) -> Any:
    block = build_capability_agent_block(registry, _contexts(registry, configs))
    return build_tool_loop_compiled_react_agent(
        model=model,
        tools=[],
        system_prompt="SYS-cap.",
        binding=_binding(),
        approval_policy=ToolApprovalPolicy(
            enabled=approval_enabled,
            always_require_tools=tuple(always_require_tools or ()),
        ),
        checkpointer=cast(Checkpointer, InMemorySaver()),
        chat_model_factory=None,
        definition=_definition(),
        infer_operation_from_messages=infer_react_model_operation_from_messages,
        default_operation=REACT_MODEL_OPERATION_ROUTING,
        available_tool_names={"demo_echo", "demo_gadget"},
        capability_middleware=block.middleware,
        capability_hitl=block.hitl,
    )


@pytest.fixture(autouse=True)
def _reset_gadget_log() -> None:
    GADGET_RUNS.clear()


# ---------------------------------------------------------------------------
# Deterministic capability block (RFC §5.3)
# ---------------------------------------------------------------------------


def test_capability_block_is_sorted_by_id_with_authored_order_within() -> None:
    registry = CapabilityRegistry()
    registry.register(_stack_capability("zeta_cap"))
    registry.register(_stack_capability("alpha_cap"))

    # Selection order deliberately reversed — a UI reorder must not matter.
    contexts = _contexts(registry, {"zeta_cap": {}, "alpha_cap": {}})
    block = build_capability_agent_block(registry, contexts)

    labels = [mw.label for mw in block.middleware]  # type: ignore[attr-defined]
    assert labels == [
        "alpha_cap-first",
        "alpha_cap-second",
        "zeta_cap-first",
        "zeta_cap-second",
    ]


# ---------------------------------------------------------------------------
# block.tools — capability.tools(ctx) is the one source for HITL binding and
# for Graph agents (bridge, Phase 4); collisions across capabilities never
# silently shadow (#1973 doctrine: a broken capability suspends, it never
# silently degrades)
# ---------------------------------------------------------------------------


def _tool_capability(cap_id: str, tool_name: str) -> AgentCapability[Any, Any, Any]:
    class _Cap(AgentCapability[_StackConfig, _StackConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id=cap_id,
            version="1.0.0",
            name=f"cap.{cap_id}.name",
            description=f"cap.{cap_id}.description",
            icon="Extension",
        )
        ConfigModel = _StackConfig

        def tools(self, ctx: CapabilityContext[_StackConfig, EmptyModel]) -> list[Any]:
            del ctx

            @tool(tool_name)
            def _probe(x: str) -> str:
                """A probe tool."""
                return x

            return [_probe]

    return _Cap()


def test_block_tools_collects_capability_tools_deduped_by_name() -> None:
    registry = CapabilityRegistry()
    registry.register(_tool_capability("cap_a", "tool_a"))
    registry.register(_tool_capability("cap_b", "tool_b"))

    contexts = _contexts(registry, {"cap_a": {}, "cap_b": {}})
    block = build_capability_agent_block(registry, contexts)

    assert {t.name for t in block.tools} == {"tool_a", "tool_b"}


def test_hitl_binding_tool_comes_from_block_tools() -> None:
    registry = _gadget_registry(require=True)
    contexts = _contexts(registry, {"demo_gadget": {}})
    block = build_capability_agent_block(registry, contexts)

    assert {t.name for t in block.tools} == {"demo_gadget"}
    binding = block.hitl["demo_gadget"]
    assert binding.tool is not None
    assert binding.tool is next(t for t in block.tools if t.name == "demo_gadget")


def test_default_middleware_tools_are_the_same_objects_as_block_tools() -> None:
    """
    CAPAB-02: for a capability relying on the default `middleware()` (i.e. it
    implements only `tools()`), the ReAct middleware's `.tools` and
    `block.tools`/HITL binding must be the SAME tool instances, not two
    independently-built closures. `tools(ctx)` is called exactly once per
    capability per assembly.
    """
    calls: list[int] = []

    class _CountingCapability(AgentCapability[_StackConfig, _StackConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id="counting_cap",
            version="1.0.0",
            name="cap.counting_cap.name",
            description="cap.counting_cap.description",
            icon="Extension",
        )
        ConfigModel = _StackConfig

        def tools(self, ctx: CapabilityContext[_StackConfig, EmptyModel]) -> list[Any]:
            del ctx
            calls.append(1)

            @tool
            def counting_probe(x: str) -> str:
                """A probe tool."""
                return x

            return [counting_probe]

    registry = CapabilityRegistry()
    registry.register(_CountingCapability())
    contexts = _contexts(registry, {"counting_cap": {}})
    block = build_capability_agent_block(registry, contexts)

    assert len(calls) == 1
    (middleware,) = block.middleware
    assert list(middleware.tools) == list(block.tools)  # type: ignore[attr-defined]
    assert middleware.tools[0] is block.tools[0]  # type: ignore[attr-defined]


def test_tools_and_overridden_middleware_compose_not_either_or() -> None:
    """
    CAPAB-02 regression: a capability implementing BOTH `tools()` (plain
    tools) AND overriding `middleware()` (a genuine ReAct-only hook) must get
    BOTH contributions in `block.middleware` — an earlier version of the
    assembly loop treated them as either/or, so a capability following the
    documented "implement tools() too; don't fold tools into the middleware
    override" pattern silently lost its plain tools under ReAct (they still
    reached `block.tools`/Graph, but never `create_agent()`'s tool binding).
    """

    class _ComposingCapability(AgentCapability[_StackConfig, _StackConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id="composing_cap",
            version="1.0.0",
            name="cap.composing_cap.name",
            description="cap.composing_cap.description",
            icon="Extension",
        )
        ConfigModel = _StackConfig

        def tools(self, ctx: CapabilityContext[_StackConfig, EmptyModel]) -> list[Any]:
            del ctx

            @tool
            def composing_probe(x: str) -> str:
                """A probe tool."""
                return x

            return [composing_probe]

        def middleware(
            self, ctx: CapabilityContext[_StackConfig, EmptyModel]
        ) -> list[AgentMiddleware]:
            del ctx
            return [_NamedMiddleware("composing_cap-hook")]

    registry = CapabilityRegistry()
    registry.register(_ComposingCapability())
    contexts = _contexts(registry, {"composing_cap": {}})
    block = build_capability_agent_block(registry, contexts)

    assert {t.name for t in block.tools} == {"composing_probe"}
    tool_carriers = [mw for mw in block.middleware if hasattr(mw, "tools")]
    assert len(tool_carriers) == 1
    assert [t.name for t in tool_carriers[0].tools] == ["composing_probe"]
    named = [mw for mw in block.middleware if isinstance(mw, _NamedMiddleware)]
    assert [mw.label for mw in named] == ["composing_cap-hook"]


def test_two_capabilities_exposing_same_tool_name_raises() -> None:
    registry = CapabilityRegistry()
    registry.register(_tool_capability("cap_a", "shared_tool"))
    registry.register(_tool_capability("cap_b", "shared_tool"))

    contexts = _contexts(registry, {"cap_a": {}, "cap_b": {}})

    with pytest.raises(CapabilityAssemblyError, match="shared_tool"):
        build_capability_agent_block(registry, contexts)


def test_one_capability_returning_two_same_named_tools_raises() -> None:
    """
    PR #2067 review: the collision guard used to check `owner != cap_id`
    only, so a SINGLE capability's own `tools()` returning two DIFFERENT
    tool objects with the same `.name` silently kept whichever won in
    `tools_by_name` — and a `HitlSpec` naming that tool could then bind to
    the wrong object. "Tools must be uniquely named" now holds within one
    capability's own list too, not just across capabilities.
    """

    class _DupeCap(AgentCapability[_StackConfig, _StackConfig, EmptyModel]):
        manifest = CapabilityManifest(
            id="dupe_cap",
            version="1.0.0",
            name="cap.dupe_cap.name",
            description="cap.dupe_cap.description",
            icon="Extension",
        )
        ConfigModel = _StackConfig

        def tools(self, ctx: CapabilityContext[_StackConfig, EmptyModel]) -> list[Any]:
            del ctx

            @tool("dupe_tool")
            def _first(x: str) -> str:
                """First."""
                return x

            @tool("dupe_tool")
            def _second(x: str) -> str:
                """Second — same name as _first, a capability-authoring bug."""
                return x

            return [_first, _second]

    registry = CapabilityRegistry()
    registry.register(_DupeCap())
    contexts = _contexts(registry, {"dupe_cap": {}})

    with pytest.raises(CapabilityAssemblyError, match="dupe_tool"):
        build_capability_agent_block(registry, contexts)


# ---------------------------------------------------------------------------
# Demo capability tool callable in chat (enabled in code — no product surface)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demo_capability_tool_is_callable_in_chat_when_enabled() -> None:
    registry = CapabilityRegistry()
    registry.register(DemoEchoCapability())
    registry.validate(env={})

    model = ScriptedModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("demo_echo", {"text": "hello"}, "c-1")],
            ),
            AIMessage(content="echoed"),
        ]
    )
    agent = _build_capability_agent(
        model, registry, {"demo_echo": {"uppercase": True}}, approval_enabled=False
    )

    res = await agent.ainvoke(
        {"messages": [HumanMessage("echo hello")]}, _cfg("t-demo")
    )

    tool_messages = [m for m in res["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    # The uppercase config reached the tool through the middleware closure,
    # never through the LLM-visible tool signature.
    assert str(tool_messages[0].content) == "HELLO"


@pytest.mark.asyncio
async def test_demo_capability_config_defaults_apply() -> None:
    registry = CapabilityRegistry()
    registry.register(DemoEchoCapability())
    # Boot always validates (folding chat parts into the UiPart union, #1977)
    # before any tool runs; the demo tool's artifact relies on that.
    registry.validate(env={})

    model = ScriptedModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[_tool_call("demo_echo", {"text": "hello"}, "c-1")],
            ),
            AIMessage(content="echoed"),
        ]
    )
    agent = _build_capability_agent(
        model, registry, {"demo_echo": {}}, approval_enabled=False
    )

    res = await agent.ainvoke({"messages": [HumanMessage("echo")]}, _cfg("t-demo-def"))
    tool_messages = [m for m in res["messages"] if isinstance(m, ToolMessage)]
    assert str(tool_messages[0].content) == "hello"


def test_context_slice_validation_rejects_bad_config() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        build_capability_context(
            DemoEchoCapability(),
            identity=_identity(),
            services=RuntimeServices(),
            config={"uppercase": "not-a-bool"},
        )
    assert DemoEchoConfig(uppercase=True).uppercase is True


# ---------------------------------------------------------------------------
# HitlSpec gating through FredHitlMiddleware (RFC §5.4)
# ---------------------------------------------------------------------------


def _gadget_script() -> list[AIMessage]:
    return [
        AIMessage(
            content="",
            tool_calls=[_tool_call("demo_gadget", {"path": "/workspace/a"}, "g-1")],
        ),
        AIMessage(content="gadget done"),
    ]


def _gadget_registry(**cap_kwargs: Any) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(_GadgetCapability(**cap_kwargs))
    return registry


@pytest.mark.asyncio
async def test_hitl_require_gates_and_proceed_resumes() -> None:
    registry = _gadget_registry(require=True, question="Run the gadget?")
    agent = _build_capability_agent(
        ScriptedModel(script=_gadget_script()), registry, {"demo_gadget": {}}
    )
    cfg = _cfg("t-hitl-require")

    res = await agent.ainvoke({"messages": [HumanMessage("use the gadget")]}, cfg)
    assert "__interrupt__" in res
    payload = res["__interrupt__"][0].value
    assert payload["question"] == "Run the gadget?"
    assert payload["metadata"]["tool_name"] == "demo_gadget"
    assert GADGET_RUNS == []

    res = await agent.ainvoke(Command(resume={"choice_id": "proceed"}), cfg)
    assert GADGET_RUNS == [{"path": "/workspace/a"}]
    assert str(res["messages"][-1].content) == "gadget done"


@pytest.mark.asyncio
async def test_hitl_when_predicate_sees_typed_context_and_real_args() -> None:
    seen: list[HitlGateRequest] = []

    def outside_workspace(request: HitlGateRequest) -> bool:
        seen.append(request)
        path = str(request.tool_call["args"].get("path", ""))
        return not path.startswith(request.context.config.workspace_root)

    registry = _gadget_registry(when=outside_workspace)
    agent = _build_capability_agent(
        ScriptedModel(script=_gadget_script()),
        registry,
        {"demo_gadget": {"workspace_root": "/workspace"}},
    )

    res = await agent.ainvoke(
        {"messages": [HumanMessage("gadget")]}, _cfg("t-hitl-when")
    )

    # Inside the configured workspace root → predicate says no gate.
    assert "__interrupt__" not in res
    assert GADGET_RUNS == [{"path": "/workspace/a"}]
    assert len(seen) == 1
    assert seen[0].context.config.workspace_root == "/workspace"
    assert seen[0].tool is not None and seen[0].tool.name == "demo_gadget"


@pytest.mark.asyncio
async def test_hitl_raising_when_predicate_fails_closed_to_interrupt() -> None:
    def broken(request: HitlGateRequest) -> bool:
        raise ValueError("predicate exploded")

    registry = _gadget_registry(when=broken)
    agent = _build_capability_agent(
        ScriptedModel(script=_gadget_script()), registry, {"demo_gadget": {}}
    )

    res = await agent.ainvoke(
        {"messages": [HumanMessage("gadget")]}, _cfg("t-hitl-raise")
    )

    assert "__interrupt__" in res
    assert GADGET_RUNS == []


@pytest.mark.asyncio
async def test_hitl_spec_require_false_does_not_gate_tool() -> None:
    """A capability tool with an explicit non-gating spec (`require=False`, no
    `when`) is NOT gated, even with a mutating-looking name — the capability's
    own `HitlSpec` is authoritative for its tools; #1978 retired the legacy
    name-prefix heuristics entirely, so there is no fallback gate to defer to
    (RFC §5.4)."""

    registry = _gadget_registry(require=False)  # no `when` either
    agent = _build_capability_agent(
        ScriptedModel(script=_gadget_script()), registry, {"demo_gadget": {}}
    )

    res = await agent.ainvoke(
        {"messages": [HumanMessage("gadget")]}, _cfg("t-hitl-spec-wins")
    )

    assert "__interrupt__" not in res
    assert GADGET_RUNS == [{"path": "/workspace/a"}]


@pytest.mark.asyncio
async def test_operator_exact_list_still_overrides_capability_spec() -> None:
    registry = _gadget_registry(require=False)
    agent = _build_capability_agent(
        ScriptedModel(script=_gadget_script()),
        registry,
        {"demo_gadget": {}},
        always_require_tools=["demo_gadget"],
    )

    res = await agent.ainvoke(
        {"messages": [HumanMessage("gadget")]}, _cfg("t-hitl-operator")
    )

    assert "__interrupt__" in res
    assert GADGET_RUNS == []


@pytest.mark.asyncio
async def test_capability_require_gates_even_when_operator_approval_disabled() -> None:
    """The operator `enabled` toggle controls PLATFORM gating; it does not
    silence a capability author's own safety declaration (fail-closed,
    decision recorded on #1973)."""

    registry = _gadget_registry(require=True)
    agent = _build_capability_agent(
        ScriptedModel(script=_gadget_script()),
        registry,
        {"demo_gadget": {}},
        approval_enabled=False,
    )

    res = await agent.ainvoke(
        {"messages": [HumanMessage("gadget")]}, _cfg("t-hitl-disabled")
    )

    assert "__interrupt__" in res
    assert GADGET_RUNS == []


@pytest.mark.asyncio
async def test_hitl_cancel_still_replans_for_capability_tools() -> None:
    registry = _gadget_registry(require=True)
    agent = _build_capability_agent(
        ScriptedModel(script=_gadget_script()), registry, {"demo_gadget": {}}
    )
    cfg = _cfg("t-hitl-cancel")

    res = await agent.ainvoke({"messages": [HumanMessage("gadget")]}, cfg)
    assert "__interrupt__" in res
    res = await agent.ainvoke(Command(resume="cancel"), cfg)

    assert GADGET_RUNS == []
    assert str(res["messages"][-1].content) == "gadget done"
