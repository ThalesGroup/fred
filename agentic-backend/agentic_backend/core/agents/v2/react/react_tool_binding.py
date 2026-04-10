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
Final LangChain binding layer for resolved ReAct/Deep tools.

Why this module exists:
- once Fred has already resolved built-in tools, registered Python tools, and
  runtime-provider tools to one shared `FredRuntimeToolSpec`, the last step should
  be small and boring
- this module is that last step: wrap resolved runtime tools as LangChain tools and
  render the prompt suffix listing the exact tool names available to the agent

How to use:
- `ReActRuntime` or `DeepAgentRuntime` resolves tools first through
  `ReActRuntimeToolResolver`
- this binder then turns those resolved specs into the final tools passed to
  `create_agent(...)` or `create_deep_agent(...)`

Example:
- `bound_tools = ReActToolBinder(runtime_tools=runtime_tools, tracer=tracer, binding=binding).build_tools()`
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from langchain_core.tools import BaseTool, StructuredTool

from ..contracts.context import BoundRuntimeContext, ToolInvocationResult
from ..contracts.runtime import TracerPort
from .react_tool_resolution import FredRuntimeToolSpec
from .react_tool_utils import normalize_payload


@dataclass(frozen=True, slots=True)
class BoundTool:
    """
    One LangChain tool plus the Fred runtime name/description metadata.

    Why this exists:
    - the runtime needs both the executable LangChain tool and the metadata used
      to explain tool availability in the system prompt
    - one small container keeps those values together without coupling them to the
      runtime class

    How to use:
    - create through `ReActToolBinder.build_tools()`

    Example:
    - `for bound_tool in bound_tools: bound_tool.tool`
    """

    runtime_name: str
    description: str
    tool: BaseTool


def build_runtime_tool_prompt_suffix(bound_tools: Sequence[BoundTool]) -> str:
    """
    Render the tool-availability suffix appended to the ReAct system prompt.

    Why this exists:
    - the model should see the exact tools and names it may call in this runtime
    - one renderer keeps the prompt contract stable as tool bindings evolve

    How to use:
    - call after binding tools and append the returned text to the system prompt

    Example:
    - `system_prompt += build_runtime_tool_prompt_suffix(bound_tools)`
    """

    if not bound_tools:
        return (
            "\n\nTool availability:\n"
            "- No external tool is available in this session.\n"
            "- Do not claim any search, database lookup, or API call unless it actually happened.\n"
            "- Answer directly without repeating capability disclaimers.\n"
        )

    lines = ["\n\nAvailable tools (exact names):"]
    for bound_tool in bound_tools:
        lines.append(f"- {bound_tool.runtime_name}: {bound_tool.description}")
    lines.extend(
        [
            "Tool calling rules:",
            "- Use only the tools listed above.",
            "- Follow each tool's JSON argument schema exactly.",
            "- Never invent tool names or tool results.",
        ]
    )
    return "\n".join(lines)


class ReActToolBinder:
    """
    Turn resolved runtime-tool specs into the final LangChain tool list.

    Why this exists:
    - the true v2 thin layer should not know where tools came from
    - once tool resolution is done, this binder only applies shared payload
      normalization, tracing, and `StructuredTool` wrapping

    How to use:
    - pass the already resolved runtime-tool specs plus the active tracer/binding
    - call `build_tools()`

    Example:
    - `binder = ReActToolBinder(runtime_tools=runtime_tools, tracer=tracer, binding=binding)`
    """

    def __init__(
        self,
        *,
        runtime_tools: Sequence[FredRuntimeToolSpec],
        tracer: TracerPort | None,
        binding: BoundRuntimeContext,
    ) -> None:
        """
        Store the resolved runtime tools and tracing context.

        Why this exists:
        - the final binding step only needs the already-resolved runtime tools plus
          the current execution context for tracing

        How to use:
        - pass the list returned by `ReActRuntimeToolResolver.resolve_tools()`

        Example:
        - `ReActToolBinder(runtime_tools=runtime_tools, tracer=tracer, binding=binding)`
        """

        self._runtime_tools = tuple(runtime_tools)
        self._tracer = tracer
        self._binding = binding

    def build_tools(self) -> list[BoundTool]:
        """
        Build the complete LangChain tool list for one runtime.

        Why this exists:
        - ReAct and Deep both need the same final list of LangChain tools
        - binding all resolved tools through one method keeps the last integration
          layer uniform

        How to use:
        - call once during runtime build

        Example:
        - `bound_tools = binder.build_tools()`
        """

        return [self._bind_runtime_tool_spec(spec=spec) for spec in self._runtime_tools]

    def _bind_runtime_tool_spec(self, *, spec: FredRuntimeToolSpec) -> BoundTool:
        """
        Turn one resolved runtime-tool spec into the final LangChain tool object.

        Why this exists:
        - every tool source should share the same final LangChain binding path
        - this keeps the layer passed to `create_agent(...)` or `create_deep_agent(...)`
          as thin as possible

        How to use:
        - call after `ReActRuntimeToolResolver` has already done source-specific work

        Example:
        - `bound_tool = self._bind_runtime_tool_spec(spec=spec)`
        """

        async def _invoke_bound_tool(
            **payload: object,
        ) -> tuple[str, ToolInvocationResult | None]:
            normalized_payload = cast(
                dict[str, object],
                normalize_payload(dict(payload)),
            )
            span = None
            if self._tracer is not None:
                attributes = {
                    "tool_name": spec.runtime_name,
                    "tool_ref": spec.tool_ref,
                    **dict(spec.build_trace_attributes(normalized_payload)),
                }
                span = self._tracer.start_span(
                    name=spec.trace_span_name,
                    context=self._binding.portable_context,
                    attributes=attributes,
                )
            try:
                rendered_result, artifact = await spec.invoke(normalized_payload)
                if span is not None:
                    span.set_attribute("status", "ok")
                return (rendered_result, artifact)
            except Exception:
                if span is not None:
                    span.set_attribute("status", "error")
                raise
            finally:
                if span is not None:
                    span.end()

        return BoundTool(
            runtime_name=spec.runtime_name,
            description=spec.description,
            tool=StructuredTool.from_function(
                func=None,
                coroutine=_invoke_bound_tool,
                name=spec.runtime_name,
                description=spec.description,
                args_schema=cast(Any, spec.args_schema),
                response_format="content_and_artifact",
            ),
        )
