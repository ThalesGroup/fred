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
`GraphRuntime`: the lifecycle of a graph agent (bind, activate, build its
executor) and the bridge that exposes selected capabilities' tools to its nodes.
"""

from __future__ import annotations

import logging
from typing import cast

from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
    ToolApprovalPolicy,
)
from fred_sdk.contracts.runtime import (
    AgentRuntime,
    Executor,
    RuntimeServices,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
)
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from fred_runtime.capabilities.assembly import CapabilityAgentBlock
from fred_runtime.capabilities.errors import CapabilityAssemblyError
from fred_runtime.graph.graph_executor import GraphExecutor
from fred_runtime.runtime_support.checkpoints import (
    checkpoint_namespace,
)
from fred_runtime.runtime_support.tool_approval import ToolApproval

logger = logging.getLogger(__name__)


class GraphRuntime(AgentRuntime[GraphAgentDefinition, BaseModel, BaseModel]):
    """
    Runtime implementation for `GraphAgentDefinition`.

    Where to look when debugging:
    - runtime tool/model wiring: `on_activate(...)`
    - executor construction: `build_executor(...)`
    """

    def __init__(
        self,
        *,
        definition: GraphAgentDefinition,
        services: RuntimeServices,
        capability_block: CapabilityAgentBlock | None = None,
    ):
        super().__init__(definition=definition, services=services)
        self._model: BaseChatModel | None = None
        # Used when no checkpointer is injected, so HITL and cross-turn state
        # still work for this runtime's lifetime (executors are rebuilt on bind).
        self._memory_checkpointer: InMemorySaver | None = None
        # Selected capabilities' tools (Graph bridge, NOTES-GRAPH-CAPABILITY-
        # BRIDGE.md Phase 4). None when the agent selects no capabilities.
        self._capability_block = capability_block

    def on_bind(self, binding: BoundRuntimeContext) -> None:
        if self.services.tool_provider is not None:
            self.services.tool_provider.bind(binding)
        if self.services.workspace_fs is not None:
            self.services.workspace_fs.bind(binding)

    async def on_activate(self, binding: BoundRuntimeContext) -> None:
        if self.services.chat_model_factory is not None:
            self._model = cast(
                BaseChatModel,
                self.services.chat_model_factory.build(self.definition, binding),
            )
        if self.services.tool_provider is not None:
            await self.services.tool_provider.activate()

    async def build_executor(
        self, binding: BoundRuntimeContext
    ) -> Executor[BaseModel, BaseModel]:
        mcp_tools = (
            cast(tuple[BaseTool, ...], self.services.tool_provider.get_tools())
            if self.services.tool_provider is not None
            else ()
        )
        capability_tools = _adapted_capability_tools(
            self._capability_block,
            mcp_tool_names={tool.name for tool in mcp_tools},
        )
        portable = binding.portable_context
        graph_checkpoint_ns = checkpoint_namespace(
            agent_instance_id=portable.baggage.get("agent_instance_id"),
            agent_id=self.definition.agent_id,
        )
        checkpointer = self.services.checkpointer
        if checkpointer is None:
            if self._memory_checkpointer is None:
                self._memory_checkpointer = InMemorySaver()
            checkpointer = self._memory_checkpointer
        return GraphExecutor(
            definition=self.definition,
            binding=binding,
            services=self.services,
            model=self._model,
            runtime_tools=mcp_tools + capability_tools,
            checkpointer=cast(BaseCheckpointSaver, checkpointer),
            checkpoint_ns=graph_checkpoint_ns,
            tool_approval=ToolApproval(
                approval_policy=ToolApprovalPolicy(),
                capability_hitl=self._capability_block.hitl
                if self._capability_block
                else None,
            ),
        )

    async def on_dispose(self) -> None:
        if self.services.tool_provider is not None:
            await self.services.tool_provider.aclose()
        self._model = None
        self._memory_checkpointer = None


def _adapted_capability_tools(
    capability_block: CapabilityAgentBlock | None,
    *,
    mcp_tool_names: set[str],
) -> tuple[BaseTool, ...]:
    """
    Bridge a Graph agent's selected-capability tools into `runtime_tools`
    (NOTES-GRAPH-CAPABILITY-BRIDGE.md Phase 4).

    Each tool is re-wrapped by `_adapt_capability_tool_for_graph` (see there
    for why a plain merge would silently drop `ToolInvocationResult` sources).

    Also raises the capability-vs-MCP tool name collision deferred from
    Phase 2 (`assembly.build_capability_agent_block` cannot see MCP-resolved
    names; this is the first place both sources are in scope together): a
    capability tool must never silently shadow, or be shadowed by, an
    MCP-resolved runtime tool of the same name.
    """
    if capability_block is None or not capability_block.tools:
        return ()
    adapted: list[BaseTool] = []
    for source_tool in capability_block.tools:
        if source_tool.name in mcp_tool_names:
            raise CapabilityAssemblyError(
                f"Tool '{source_tool.name}' is exposed by both a capability and "
                "an MCP server selected on this agent. Capability and MCP tool "
                "names must be unique."
            )
        adapted.append(_adapt_capability_tool_for_graph(source_tool))
    return tuple(adapted)


def _adapt_capability_tool_for_graph(source_tool: BaseTool) -> BaseTool:
    """
    Wrap one ReAct-shaped capability tool so it survives a Graph node's
    plain-dict `invoke_runtime_tool` call intact.

    Why this exists (NOTES-GRAPH-CAPABILITY-BRIDGE.md Phase 1/4,
    `test_capability_tool_return_convention.py`): a capability tool built
    with `@tool(..., response_format="content_and_artifact")` (the
    `document_access` convention) silently loses its `ToolInvocationResult`
    artifact when invoked through `BaseTool.ainvoke()` with a plain args dict
    — the shape `invoke_runtime_tool` uses, as opposed to the `ToolCall` dict
    `create_agent()`'s real ReAct loop uses. `.ainvoke()`'s response-shape
    handling is what drops it; calling the tool's own underlying `.coroutine`
    directly sidesteps `.ainvoke()` entirely and returns the function's real
    Python return value, with no ambiguity.

    The wrapper then re-shapes that return value into the one convention
    Phase 1 proved survives a plain-dict `.ainvoke()` unchanged: a bare
    `ToolInvocationResult`, no `response_format` override (LangChain's
    "content" default already does the right thing here).
    - `(content, artifact)` 2-tuple AND `source_tool.response_format ==
      "content_and_artifact"`: keep the artifact. Gated on the tool's own
      declared response_format (CAPAB-02), not "any 2-tuple" — a plain tool
      whose normal return value happens to be some unrelated 2-tuple must
      round-trip unchanged, not have its second element silently
      reinterpreted as an artifact. **If the artifact's own `blocks` are
      empty, `content` is folded in as one `ToolContentBlock` before the
      artifact is returned** (PR #2067 review): `document_access`'s tools
      duplicate their answer into `blocks` themselves, but a tool that puts
      its actual answer only in `content`, with an artifact carrying
      nothing but `ui_parts`, would lose it — discarding `content` outright would
      silently drop the answer for any such tool. This is a safety net, not
      a substitute for a capability author populating `blocks` directly
      (`document_access` is still the reference pattern to copy).
    - anything else (already a bare `ToolInvocationResult`, or any other
      capability tool return): pass through unchanged.

    A SYNC tool (`.func`, no `.coroutine`) with `content_and_artifact` cannot
    be adapted this way at all — there's no coroutine for this wrapper to
    call — so it's refused loudly instead (CAPAB-02): every capability tool
    in this codebase is `async def` today specifically so that never fires.

    `document_access`'s tool definition itself is untouched by this — the
    adaptation lives entirely at this bridge/merge seam, not in capability
    authoring (RFC invariant B).
    """
    coroutine = getattr(source_tool, "coroutine", None)
    if coroutine is None:
        # A sync-only tool (`.func`, no `.coroutine`) whose response_format
        # is "content_and_artifact" would silently lose its artifact under a
        # plain-dict `.ainvoke()`, exactly like the async case above — but
        # there is no `.coroutine` for this function to call, so it cannot be
        # adapted the same way. Refuse loudly rather than pass it through
        # broken (RFC §3.9 "never silently degrade"); every capability tool
        # in this codebase is `async def` today (CAPAB-02) specifically so
        # this branch never fires in practice.
        if getattr(source_tool, "response_format", "content") == "content_and_artifact":
            raise CapabilityAssemblyError(
                f"Capability tool '{source_tool.name}' is synchronous "
                "(no .coroutine) with response_format='content_and_artifact', "
                "which loses its artifact under a Graph agent's plain-dict "
                "invocation. Make the tool `async def`, or return a bare "
                "ToolInvocationResult (no response_format override)."
            )
        # Any other sync tool (a plain string/JSON return, no artifact to
        # lose) passes through unchanged — nothing for this adapter to do.
        return source_tool

    # Gate the tuple-unwrap on the tool's OWN declared response_format,
    # rather than "any 2-tuple" — a plain tool returning some unrelated
    # 2-tuple (not the content_and_artifact convention) must round-trip
    # through this adapter unchanged, not have its second element silently
    # reinterpreted as an artifact.
    is_content_and_artifact = (
        getattr(source_tool, "response_format", "content") == "content_and_artifact"
    )

    async def _invoke(**kwargs: object) -> object:
        raw = await coroutine(**kwargs)
        if is_content_and_artifact and isinstance(raw, tuple) and len(raw) == 2:
            content, artifact = raw
            # PR #2067 review (Codex): keeping ONLY the artifact is correct
            # for a tool like `document_access`'s, whose artifact duplicates
            # its answer into `blocks` — but a tool may instead put
            # the actual answer in `content` and an artifact carrying only
            # `ui_parts` (a UI card), never `blocks`. Unwrapping to the
            # artifact alone would silently drop the answer for any such
            # tool. If the artifact has no `blocks` of its own, fold the
            # discarded `content` in as one — never lose the answer just
            # because a capability author didn't think to duplicate it.
            if (
                isinstance(artifact, ToolInvocationResult)
                and not artifact.blocks
                and isinstance(content, str)
                and content
            ):
                artifact = artifact.model_copy(
                    update={
                        "blocks": (
                            ToolContentBlock(kind=ToolContentKind.TEXT, text=content),
                        )
                    }
                )
            return artifact
        return raw

    return StructuredTool.from_function(
        name=source_tool.name,
        description=source_tool.description,
        args_schema=source_tool.args_schema,
        coroutine=_invoke,
    )
