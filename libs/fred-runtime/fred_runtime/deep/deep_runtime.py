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
Minimal runtime for v2 deep-agent definitions.

This runtime deliberately reuses the ReAct transport/event layer and only swaps
the compiled agent constructor to `deepagents.create_deep_agent`.

How to read this file:
- a deep agent is still in the ReAct family at the Fred contract level
- it keeps the same typed input/output and runtime events as `ReActRuntime`
- the only intended difference here is the internal planning/execution engine
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from fred_core.kpi import BaseKPIWriter
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.runtime import Executor, TracerPort
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer

from fred_runtime.react.middleware.tool_observability import (
    ToolObservabilityMiddleware,
)
from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
from fred_runtime.react.react_model_adapter import (
    REACT_MODEL_OPERATION_ROUTING,
)
from fred_runtime.react.react_model_adapter import (
    infer_react_model_operation_from_messages as _infer_react_model_operation_from_messages,
)
from fred_runtime.react.react_prompting import (
    compose_system_prompt as _compose_system_prompt,
)
from fred_runtime.react.react_prompting import (
    render_prompt_template as _render_prompt_template,
)
from fred_runtime.react.react_runtime import (
    ReActInput,
    ReActOutput,
    ReActRuntime,
    _build_runtime_tool_prompt_suffix,
    _CompiledReActAgent,
    _TransportBackedReActExecutor,
)
from fred_runtime.react.react_tool_binding import ReActToolBinder
from fred_runtime.react.react_tool_resolution import ReActRuntimeToolResolver
from fred_runtime.runtime_context import get_runtime_context

_FILESYSTEM_TOOL_NAMES: tuple[str, ...] = (
    "ls",
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "grep",
    "execute",
)

_FILESYSTEM_DISABLED_PROMPT_SUFFIX = (
    "\n\nFilesystem tools are disabled in this runtime. "
    "Do not call ls/read_file/write_file/edit_file/glob/grep/execute."
)


class DeepAgentRuntime(ReActRuntime):
    """
    Runtime implementation for `DeepAgentDefinition`.

    Scope is intentionally minimal:
    - deep agents are specialized ReAct agents in Fred v2
    - same typed input/output and events as ReAct
    - deep-agent planner/runtime from `deepagents`
    """

    async def build_executor(
        self, binding: BoundRuntimeContext
    ) -> Executor[ReActInput, ReActOutput]:
        if self._model is None:
            raise RuntimeError("DeepAgentRuntime model is not initialized.")

        policy = self.definition.policy()
        if policy.system_prompt_template is None:
            raise RuntimeError(
                "DeepAgentRuntime requires a non-empty system_prompt_template."
            )
        if policy.tool_approval.enabled:
            raise NotImplementedError(
                "DeepAgentRuntime does not support tool approval in this minimal version."
            )
        if policy.tool_selection.max_tool_calls_per_turn is not None:
            raise NotImplementedError(
                "DeepAgentRuntime does not support per-turn tool-call limits in this minimal version."
            )

        runtime_tools = ReActRuntimeToolResolver(
            declared_tool_refs=self.definition.declared_tool_refs,
            toolset_key=self._toolset_key(),
            services=self.services,
            binding=binding,
        ).resolve_tools()
        bound_tools = ReActToolBinder(
            runtime_tools=runtime_tools,
            tracer=self.services.tracer,
            binding=binding,
        ).build_tools()
        filesystem_tools_enabled = _allows_standard_filesystem_tools(bound_tools)
        system_prompt = _render_prompt_template(
            policy.system_prompt_template,
            binding=binding,
            agent_id=self.definition.agent_id,
        )
        system_prompt = _compose_system_prompt(
            system_prompt,
            binding=binding,
            definition=self.definition,
            agent_id=self.definition.agent_id,
            tool_suffix=_build_runtime_tool_prompt_suffix(bound_tools),
            runtime_suffixes=(
                _filesystem_prompt_suffix(
                    filesystem_tools_enabled=filesystem_tools_enabled
                ),
            ),
        )
        compiled_agent = _create_compiled_deep_agent(
            model=self._model,
            tools=[bound_tool.tool for bound_tool in bound_tools],
            system_prompt=system_prompt,
            checkpointer=cast(Checkpointer, self.services.checkpointer),
            middleware=_build_deepagent_runtime_middleware(
                filesystem_tools_enabled=filesystem_tools_enabled,
                tracer=self.services.tracer,
                kpi=get_runtime_context().get_kpi_writer(),
                binding=binding,
            ),
        )
        return _TransportBackedReActExecutor(
            compiled_agent=compiled_agent,
            binding=binding,
            services=self.services,
        )


def _create_compiled_deep_agent(
    *,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
    checkpointer: Checkpointer,
    middleware: Sequence[AgentMiddleware],
) -> _CompiledReActAgent:
    try:
        from deepagents import create_deep_agent
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "DeepAgentRuntime requires the optional `deepagents` package."
        ) from exc

    if checkpointer is None:
        return cast(
            _CompiledReActAgent,
            create_deep_agent(
                model=model,
                tools=list(tools),
                system_prompt=system_prompt,
                middleware=list(middleware),
            ),
        )

    return cast(
        _CompiledReActAgent,
        create_deep_agent(
            model=model,
            tools=list(tools),
            system_prompt=system_prompt,
            middleware=list(middleware),
            checkpointer=checkpointer,
        ),
    )


def _allows_standard_filesystem_tools(bound_tools: Sequence[object]) -> bool:
    """
    Tell Deep runtime whether standard filesystem tools are actually available.

    Why this exists:
    - Deep should only disable filesystem operations when the runtime did not
      inject the standard filesystem MCP tools
    - this keeps filesystem enablement declarative: if the definition/bootstrap
      path provides the tools, Deep should pass them through unchanged

    How to use it:
    - call after tool binding and before building the deep-agent middleware
    - pass the resolved bound tools for the current run

    Example:
    - `enabled = _allows_standard_filesystem_tools(bound_tools)`
    """
    tool_names = {
        getattr(getattr(bound_tool, "tool", bound_tool), "name", "").strip()
        for bound_tool in bound_tools
    }
    return any(tool_name in tool_names for tool_name in _FILESYSTEM_TOOL_NAMES)


def _filesystem_prompt_suffix(*, filesystem_tools_enabled: bool) -> str:
    """
    Return the Deep prompt suffix that explains filesystem availability.

    Why this exists:
    - Deep should only warn the model away from filesystem calls when the
      standard filesystem tool set is absent
    - keeping this in one helper avoids mismatches between prompt text and
      middleware policy

    How to use it:
    - call while assembling the final system prompt for one Deep run

    Example:
    - `suffix = _filesystem_prompt_suffix(filesystem_tools_enabled=False)`
    """
    if filesystem_tools_enabled:
        return ""
    return _FILESYSTEM_DISABLED_PROMPT_SUFFIX


def _build_deepagent_runtime_middleware(
    *,
    filesystem_tools_enabled: bool,
    tracer: TracerPort | None,
    kpi: BaseKPIWriter | None,
    binding: BoundRuntimeContext,
) -> list[AgentMiddleware]:
    """
    Build Deep runtime middleware: platform observability first, then the
    filesystem-tool policy guard.

    Why this exists:
    - Deep used to bypass `build_react_platform_middleware_frame()` entirely
      (it overrides `build_executor`, so it never went through
      `_create_compiled_react_agent`), which meant a Deep turn emitted no
      `[LLM][CALL]`/`[LLM][RESPONSE]` logs, no `llm.call_latency_ms` KPI, and
      no `agent.tool.invocation.*` audit events — the same
      `TracingKpiMiddleware`/`ToolObservabilityMiddleware` pair ReAct always
      gets. `create_deep_agent` accepts a plain `middleware=` list, so the
      fix is to hand it the same two middleware instances, same order, no
      new machinery.
    - when the standard filesystem MCP tools are absent, Deep should block
      accidental filesystem calls explicitly
    - when those tools are present, Deep should not add special blocking and
      should let the injected MCP tool surface behave normally

    How to use it:
    - call once while creating the compiled deep agent
    - pass whether standard filesystem tools are available in the resolved tool
      list, plus the same tracer/kpi/binding used to build the tool bindings

    Example:
    - `middleware = _build_deepagent_runtime_middleware(filesystem_tools_enabled=True, tracer=tracer, kpi=kpi, binding=binding)`
    """
    middleware: list[AgentMiddleware] = [
        TracingKpiMiddleware(
            tracer=tracer,
            kpi=kpi,
            binding=binding,
            infer_operation_from_messages=_infer_react_model_operation_from_messages,
            default_operation=REACT_MODEL_OPERATION_ROUTING,
        ),
        ToolObservabilityMiddleware(kpi=kpi, binding=binding),
    ]
    if filesystem_tools_enabled:
        return middleware

    for tool_name in _FILESYSTEM_TOOL_NAMES:
        middleware.append(
            cast(
                AgentMiddleware,
                ToolCallLimitMiddleware(
                    tool_name=tool_name,
                    run_limit=0,
                    exit_behavior="continue",
                ),
            )
        )
    return middleware
