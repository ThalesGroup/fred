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

from fred_sdk import MCP_SERVER_KNOWLEDGE_FLOW_TABULAR
from fred_sdk.contracts.context import BoundRuntimeContext, ToolInvocationResult
from fred_sdk.contracts.runtime import TracerPort
from langchain_core.tools import BaseTool, StructuredTool

from ..capabilities.mcp import McpPromptGroup
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
    # Originating MCP catalog server id, `None` for non-MCP tools. Lets
    # `build_runtime_tool_prompt_suffix` group the tool listing by server
    # (#2455).
    mcp_server_id: str | None = None


def tabular_tools_bound(bound_tools: Sequence[BoundTool]) -> bool:
    """
    Tell whether the tabular MCP server is actually bound to this agent
    instance, i.e. whether it can run `read_query`/`search_tabular_values`
    against a SQL-queryable attachment dataset.

    Why this exists:
    - `general_assistant` (the default agent template) ships with zero
      default capabilities — operators tick tools on per instance — so a CSV
      attachment can have a real dataset while the calling agent has no tool
      to query it. The attachment prompt suffix must not promise a
      capability this agent instance cannot use.
    """

    return any(
        bound_tool.mcp_server_id == MCP_SERVER_KNOWLEDGE_FLOW_TABULAR
        for bound_tool in bound_tools
    )


def _tool_summary(description: str) -> str:
    """
    One-line summary of a tool's description: its opening paragraph, with
    internal newlines/indentation collapsed to single spaces.

    Why this exists:
    - the `tools` API parameter already carries the full description (used
      for argument-schema generation); repeating it in the prompt body would
      duplicate everything the provider sends per call. Only the opening
      paragraph survives — the model still needs to know what a tool *does*
      to decide which one to call, but not *how* to call it (#2412).
    - `partition("\n\n")` matches how FastApiMCP itself joins `summary +
      "\n\n" + docstring` (`convert.py`), and — unlike a first-*line* cut —
      tolerates a hand-wrapped opening sentence spanning two source lines,
      which is this repo's normal docstring style.
    - `.strip()` up front means a description opening with a blank line
      doesn't yield an empty summary; every step here is IndexError-safe on
      an empty string, no extra branch needed.
    """

    first_paragraph = description.strip().partition("\n\n")[0]
    return " ".join(first_paragraph.split())


def build_runtime_tool_prompt_suffix(
    bound_tools: Sequence[BoundTool],
    *,
    mcp_prompt_groups: Sequence[McpPromptGroup] = (),
    capability_tools: Sequence[BaseTool] = (),
) -> str:
    """
    Render the tool-availability suffix appended to the ReAct system prompt.

    Why this exists:
    - the model should see the exact tools and names it may call in this runtime
    - one renderer keeps the prompt contract stable as tool bindings evolve
    - each tool's rendered line is a one-line summary, not its full
      description (see `_tool_summary`) — a tool's docstring should open with
      a self-contained summary paragraph that includes any cross-tool
      disambiguation cue ("use this instead of X for...", "call before doing
      Y"), since text placed after the first blank line is still sent to the
      model via `tools`, but only once it is already deciding to call that
      specific tool, not while comparing it against the others
    - when `mcp_prompt_groups` is given, tools tagged with a matching
      `mcp_server_id` (see `BoundTool`) render under that group's `Tools for
      {title}:` header, with the group's `agent_instructions` inlined
      immediately after — replacing the `_McpInstructionsMiddleware`
      per-model-call delivery removed 2026-08-27 (#2455,
      `RUNTIME-EXECUTION-CONTRACT.md` §8.63). Untagged tools, or tools whose
      tag matches no given group, render under a flat `Other tools:` bucket
      ahead of the named groups — or, when no group renders at all (the
      default for every caller that doesn't pass `mcp_prompt_groups`, e.g.
      Deep agents), as today's plain flat list with no extra heading.
    - `capability_tools` covers tools a native Fred capability contributes via
      `tools(ctx)` (e.g. `document_access`'s `list_document_tree`,
      `document_verbatim`'s `read_document`) — these reach the model's actual
      tool-calling set through `ToolCarrierMiddleware`
      (`fred_runtime.capabilities.assembly`), never through `bound_tools`, so
      without this parameter they were invisible in this directory even
      though the model could call them (#2455 follow-up, same day: found by
      inspecting the rendered prompt after the MCP grouping work landed).
      They join the `Other tools:` bucket — no per-capability header yet,
      unlike MCP servers, since capability tools carry no analogous
      group/title tag today. A tool name already present in `bound_tools` is
      skipped here rather than rendered twice.

    How to use:
    - call after binding tools and append the returned text to the system prompt

    Example:
    - `system_prompt += build_runtime_tool_prompt_suffix(bound_tools, mcp_prompt_groups=block.mcp_prompt_groups, capability_tools=block.tools)`
    """

    bound_names = {bound_tool.runtime_name for bound_tool in bound_tools}
    extra_tools = [tool for tool in capability_tools if tool.name not in bound_names]

    if not bound_tools and not extra_tools:
        return (
            "\n\nTool availability:\n"
            "- No external tool is available in this session.\n"
            "- Do not claim any search, database lookup, or API call unless it actually happened.\n"
            "- Answer directly without repeating capability disclaimers.\n"
        )

    groups_by_id = {group.server_id: group for group in mcp_prompt_groups}
    grouped_tools: dict[str, list[BoundTool]] = {}
    ungrouped_names: list[str] = []
    ungrouped_summaries: dict[str, str] = {}
    for bound_tool in bound_tools:
        if bound_tool.mcp_server_id in groups_by_id:
            grouped_tools.setdefault(bound_tool.mcp_server_id, []).append(bound_tool)
        else:
            ungrouped_names.append(bound_tool.runtime_name)
            ungrouped_summaries[bound_tool.runtime_name] = _tool_summary(
                bound_tool.description
            )
    for tool in extra_tools:
        ungrouped_names.append(tool.name)
        ungrouped_summaries[tool.name] = _tool_summary(tool.description)

    lines = ["\n\n# Available tools (exact names)"]

    if ungrouped_names:
        if grouped_tools:
            lines.append("\nOther tools:")
        for name in ungrouped_names:
            lines.append(f"- {name}: {ungrouped_summaries[name]}")

    for group in mcp_prompt_groups:
        tools_in_group = grouped_tools.get(group.server_id)
        if not tools_in_group:
            # An active capability whose tools didn't resolve this turn — no
            # empty header for the model to puzzle over.
            continue
        lines.append(f"\nTools for {group.title}:")
        for bound_tool in tools_in_group:
            lines.append(
                f"- {bound_tool.runtime_name}: {_tool_summary(bound_tool.description)}"
            )
        if group.agent_instructions:
            lines.append(f"\n{group.agent_instructions}")

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
                from .react_tracing import active_agent_span

                attributes = {
                    "tool_name": spec.runtime_name,
                    "tool_ref": spec.tool_ref,
                    **dict(spec.build_trace_attributes(normalized_payload)),
                }
                span = self._tracer.start_span(
                    name=spec.trace_span_name,
                    context=self._binding.portable_context,
                    attributes=attributes,
                    parent=active_agent_span.get(),
                )
                # A tool span without its arguments and result shows only that
                # a tool ran and how long it took — not enough to tell a bad
                # retrieval from a bad answer, which is the usual reason for
                # opening a trace at all.
                if self._tracer.captures_content:
                    span.set_io(input=normalized_payload)
            try:
                rendered_result, artifact = await spec.invoke(normalized_payload)
                if span is not None:
                    span.set_attribute("status", "ok")
                    if self._tracer is not None and self._tracer.captures_content:
                        span.set_io(output=rendered_result)
                return (rendered_result, artifact)
            except Exception as exc:
                if span is not None:
                    span.set_attribute("status", "error")
                    span.set_attribute("error_type", type(exc).__name__)
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
            mcp_server_id=spec.mcp_server_id,
        )
