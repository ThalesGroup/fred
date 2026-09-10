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

import logging
from collections.abc import Mapping, Sequence
from typing import cast

from fred_core.kpi import BaseKPIWriter
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ToolApprovalPolicy
from fred_sdk.contracts.runtime import Executor, TracerPort
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer

from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.react.middleware.hitl import (
    CapabilityHitlBinding,
    FredHitlMiddleware,
)
from fred_runtime.react.middleware.tool_observability import (
    ToolObservabilityMiddleware,
)
from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
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
from fred_runtime.react.react_tool_binding import (
    ReActToolBinder,
)
from fred_runtime.react.react_tool_binding import (
    tabular_tools_bound as _tabular_tools_bound,
)
from fred_runtime.react.react_tool_resolution import ReActRuntimeToolResolver

logger = logging.getLogger(__name__)

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

        # DeepAgentRuntime overrides build_executor wholesale, so it needs its
        # own copy of ReActRuntime's "[V2][EXECUTOR] build start" line under
        # this module's own logger to stay distinguishable in the logs.
        logger.debug(
            "[V2][EXECUTOR] build start runtime=%s agent=%s declared_tool_refs=%r toolset_key=%r",
            type(self).__name__,
            self.definition.agent_id,
            [r.tool_ref for r in self.definition.declared_tool_refs],
            self._toolset_key(),
        )

        policy = self.definition.policy()
        if policy.system_prompt_template is None:
            raise RuntimeError(
                "DeepAgentRuntime requires a non-empty system_prompt_template."
            )
        if policy.tool_selection.max_tool_calls_per_turn is not None:
            raise NotImplementedError(
                "DeepAgentRuntime does not support per-turn tool-call limits in this minimal version."
            )
        capability_block = self._capability_block

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
            agent_id=self.definition.agent_id,
            tool_suffix=_build_runtime_tool_prompt_suffix(
                bound_tools,
                mcp_prompt_groups=(
                    capability_block.mcp_prompt_groups
                    if capability_block is not None
                    else ()
                ),
                capability_tools=(
                    capability_block.tools if capability_block is not None else ()
                ),
            ),
            runtime_suffixes=(
                _filesystem_prompt_suffix(
                    filesystem_tools_enabled=filesystem_tools_enabled
                ),
            ),
            tabular_tools_available=_tabular_tools_bound(bound_tools),
        )
        available_tool_names = {
            bound_tool.runtime_name
            for bound_tool in bound_tools
            if bound_tool.runtime_name
        }
        compiled_agent = _create_compiled_deep_agent(
            model=self._model,
            tools=[bound_tool.tool for bound_tool in bound_tools],
            system_prompt=system_prompt,
            checkpointer=cast(Checkpointer, self.services.checkpointer),
            middleware=_build_deepagent_runtime_middleware(
                filesystem_tools_enabled=filesystem_tools_enabled,
                tracer=self.services.tracer,
                kpi=self.services.kpi_writer,
                binding=binding,
                approval_policy=policy.tool_approval,
                available_tool_names=available_tool_names,
                capability_block=capability_block,
            ),
        )
        return _TransportBackedReActExecutor(
            compiled_agent=compiled_agent,
            binding=binding,
            services=self.services,
            runtime_class_name=type(self).__name__,
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
    approval_policy: ToolApprovalPolicy,
    available_tool_names: set[str] | frozenset[str],
    capability_block: CapabilityAgentBlock | None = None,
) -> list[AgentMiddleware]:
    """
    Assemble Deep's middleware list: capability stack, platform observability,
    the HITL gate (capability-declared and operator-configured approval
    alike), then the filesystem-tool guard — same relative order as
    `build_react_platform_middleware_frame` (`after_model` hooks run in
    REVERSE list order, so the filesystem guard still blocks a disabled call
    before the human gate ever sees it). RUNTIME-EXECUTION-CONTRACT.md §8.76.
    """
    capability_hitl: Mapping[str, CapabilityHitlBinding] | None = (
        capability_block.hitl if capability_block is not None else None
    )
    middleware: list[AgentMiddleware] = [
        *(capability_block.middleware if capability_block is not None else ()),
        TracingKpiMiddleware(
            tracer=tracer,
            kpi=kpi,
            binding=binding,
        ),
        ToolObservabilityMiddleware(kpi=kpi, binding=binding),
        FredHitlMiddleware(
            binding=binding,
            approval_policy=approval_policy,
            available_tool_names=available_tool_names,
            capability_hitl=capability_hitl,
        ),
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
