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
from fred_runtime.runtime_support.ask_user import AskUserArgs, ask_user
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
        capability_tools = _capability_tools(
            self._capability_block,
            mcp_tool_names={tool.name for tool in mcp_tools},
        )
        platform_tools = _ask_user_tool(
            binding, existing_names={tool.name for tool in mcp_tools + capability_tools}
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
            runtime_tools=mcp_tools + capability_tools + platform_tools,
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


def _capability_tools(
    capability_block: CapabilityAgentBlock | None,
    *,
    mcp_tool_names: set[str],
) -> tuple[BaseTool, ...]:
    """Keep original capability tools and reject collisions with MCP tools."""
    if capability_block is None or not capability_block.tools:
        return ()
    for source_tool in capability_block.tools:
        if source_tool.name in mcp_tool_names:
            raise CapabilityAssemblyError(
                f"Tool '{source_tool.name}' is exposed by both a capability and "
                "an MCP server selected on this agent. Capability and MCP tool "
                "names must be unique."
            )
    return capability_block.tools


def _ask_user_tool(
    binding: BoundRuntimeContext, *, existing_names: set[str]
) -> tuple[BaseTool, ...]:
    """Expose platform questions to interactive Graph nodes only."""
    if binding.runtime_context.ask_user is not True:
        return ()
    if "ask_user" in existing_names:
        raise CapabilityAssemblyError(
            "Platform ask_user tool collides with another runtime tool"
        )

    async def invoke(**payload: object) -> tuple[str, None]:
        return await ask_user(payload, language=binding.runtime_context.language), None

    return (
        StructuredTool.from_function(
            func=None,
            coroutine=invoke,
            name="ask_user",
            description="Ask the user a question and continue after their answer.",
            args_schema=AskUserArgs,
            response_format="content_and_artifact",
        ),
    )
