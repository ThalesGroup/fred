"""
Minimal runtime for v2 deep-agent definitions.

This runtime deliberately reuses the ReAct transport/event layer and only swaps
the compiled agent constructor to `deepagents.create_deep_agent`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer

from .context import BoundRuntimeContext
from .models import DeepAgentDefinition
from .react_runtime import (
    ReActInput,
    ReActOutput,
    ReActRuntime,
    _build_guardrail_suffix,
    _build_runtime_tool_prompt_suffix,
    _CompiledReActAgent,
    _render_prompt_template,
    _TransportBackedReActExecutor,
)
from .runtime import Executor

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
    - same typed input/output and events as ReAct
    - deep-agent planner/runtime from `deepagents`
    """

    definition: DeepAgentDefinition

    async def build_executor(
        self, binding: BoundRuntimeContext
    ) -> Executor[ReActInput, ReActOutput]:
        if self._model is None:
            raise RuntimeError("DeepAgentRuntime model is not initialized.")

        policy = self.definition.policy()
        if policy.tool_approval.enabled:
            raise NotImplementedError(
                "DeepAgentRuntime does not support tool approval in this minimal version."
            )
        if policy.tool_selection.max_tool_calls_per_turn is not None:
            raise NotImplementedError(
                "DeepAgentRuntime does not support per-turn tool-call limits in this minimal version."
            )

        bound_tools = self._build_tools(binding)
        system_prompt = _render_prompt_template(
            policy.system_prompt_template,
            binding=binding,
            agent_id=self.definition.agent_id,
        )
        system_prompt = (
            f"{system_prompt}"
            f"{_build_runtime_tool_prompt_suffix(bound_tools)}"
            f"{_build_guardrail_suffix(self.definition)}"
            f"{_FILESYSTEM_DISABLED_PROMPT_SUFFIX}"
        )
        compiled_agent = _create_compiled_deep_agent(
            model=self._model,
            tools=[bound_tool.tool for bound_tool in bound_tools],
            system_prompt=system_prompt,
            checkpointer=self.services.checkpointer,
            middleware=_build_deepagent_runtime_middleware(),
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

    kwargs: dict[str, object] = {}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer

    return cast(
        _CompiledReActAgent,
        create_deep_agent(
            model=model,
            tools=list(tools),
            system_prompt=system_prompt,
            middleware=list(middleware),
            **kwargs,
        ),
    )


def _build_deepagent_runtime_middleware() -> list[AgentMiddleware]:
    return [
        ToolCallLimitMiddleware(
            tool_name=tool_name,
            run_limit=0,
            exit_behavior="continue",
        )
        for tool_name in _FILESYSTEM_TOOL_NAMES
    ]
