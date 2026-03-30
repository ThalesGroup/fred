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
Bootstrap helpers that still connect legacy factory code to v2 runtimes.

Why this module exists:
- `AgentFactory` still supports both legacy `AgentFlow` and v2 runtimes
- the v2 runtime construction path needs old request settings, old service
  adapters, and toolset-registry handlers
- keeping that bootstrap here makes the migration boundary explicit instead of
  hiding it inside the generic factory

How to use it:
- call `build_v2_session_agent(...)` from `AgentFactory` after a typed v2
  definition and effective legacy settings have already been resolved

Example:
- `session_agent = build_v2_session_agent(definition=definition, effective_settings=settings, binding=binding, chat_model_factory=factory, checkpointer=checkpointer)`
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

from agentic_backend.application_context import get_kpi_writer
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.v2.contracts.context import BoundRuntimeContext
from agentic_backend.core.agents.v2.contracts.models import (
    AgentDefinition,
    DeepAgentDefinition,
    GraphAgentDefinition,
    ReActAgentDefinition,
)
from agentic_backend.core.agents.v2.contracts.runtime import (
    ChatModelFactoryPort,
    RuntimeServices,
    ToolInvokerPort,
)
from agentic_backend.core.agents.v2.deep import DeepAgentRuntime
from agentic_backend.core.agents.v2.graph import GraphRuntime
from agentic_backend.core.agents.v2.react.react_runtime import ReActRuntime
from agentic_backend.core.agents.v2.runtime_support import (
    FredSqlCheckpointer,
    V2SessionAgent,
)
from agentic_backend.core.agents.v2.support.authored_toolsets import (
    AuthoredToolRuntimePorts,
    build_authored_tool_handlers,
)
from agentic_backend.integrations.v2_runtime.adapters import (
    CompositeToolInvoker,
    FredArtifactPublisher,
    FredKnowledgeSearchToolInvoker,
    FredMcpToolProvider,
    FredResourceReader,
    build_langfuse_tracer,
)


def build_v2_session_agent(
    *,
    definition: AgentDefinition,
    effective_settings: AgentSettings,
    binding: BoundRuntimeContext,
    chat_model_factory: ChatModelFactoryPort,
    checkpointer: FredSqlCheckpointer | None,
) -> V2SessionAgent:
    """
    Build one ready-to-bind `V2SessionAgent` from legacy-facing factory inputs.

    Why this function exists:
    - `AgentFactory` still operates in the old settings/request world
    - v2 runtime construction needs several adapters and a composite tool
      invoker, but that assembly is migration glue rather than core runtime
      behavior
    - extracting it here keeps `AgentFactory` smaller and makes the legacy
      bootstrap boundary obvious

    How to use it:
    - call after `build_bound_runtime_context(...)`
    - pass the already selected `chat_model_factory` and optional shared
      `checkpointer`

    Example:
    - `session_agent = build_v2_session_agent(definition=definition, effective_settings=settings, binding=binding, chat_model_factory=factory, checkpointer=None)`
    """

    base_tool_invoker = FredKnowledgeSearchToolInvoker(
        binding=binding,
        settings=effective_settings,
    )
    tool_provider = FredMcpToolProvider(
        binding=binding,
        settings=effective_settings,
    )
    artifact_publisher = FredArtifactPublisher(
        binding=binding,
        settings=effective_settings,
    )
    resource_reader = FredResourceReader(
        binding=binding,
        settings=effective_settings,
    )
    services = RuntimeServices(
        tracer=build_langfuse_tracer(),
        chat_model_factory=chat_model_factory,
        tool_invoker=_build_v2_tool_invoker(
            definition=definition,
            binding=binding,
            effective_settings=effective_settings,
            base_tool_invoker=base_tool_invoker,
            ports=AuthoredToolRuntimePorts(
                chat_model_factory=chat_model_factory,
                artifact_publisher=artifact_publisher,
                resource_reader=resource_reader,
                fallback_tool_invoker=base_tool_invoker,
            ),
        ),
        tool_provider=tool_provider,
        artifact_publisher=artifact_publisher,
        resource_reader=resource_reader,
        kpi=get_kpi_writer(),
        checkpointer=checkpointer if checkpointer is not None else MemorySaver(),
    )
    runtime = _build_runtime(definition=definition, services=services)
    runtime.bind(binding)
    return V2SessionAgent(runtime=runtime)


def _build_runtime(
    *,
    definition: AgentDefinition,
    services: RuntimeServices,
) -> ReActRuntime | DeepAgentRuntime | GraphRuntime:
    """
    Instantiate the concrete v2 runtime for one resolved definition.

    Why this function exists:
    - the bootstrap path should keep family selection in one explicit place
    - the returned runtime still shares the same `RuntimeServices` contract

    How to use it:
    - call only from `build_v2_session_agent(...)`

    Example:
    - `runtime = _build_runtime(definition=definition, services=services)`
    """

    if isinstance(definition, DeepAgentDefinition):
        return DeepAgentRuntime(definition=definition, services=services)
    if isinstance(definition, ReActAgentDefinition):
        return ReActRuntime(definition=definition, services=services)
    if isinstance(definition, GraphAgentDefinition):
        return GraphRuntime(definition=definition, services=services)
    raise NotImplementedError(
        f"V2 execution category '{definition.execution_category.value}' is not wired yet."
    )


def _build_v2_tool_invoker(
    *,
    definition: AgentDefinition,
    binding: BoundRuntimeContext,
    effective_settings: AgentSettings,
    base_tool_invoker: ToolInvokerPort,
    ports: AuthoredToolRuntimePorts,
) -> ToolInvokerPort:
    """
    Add locally registered authored-tool handlers on top of the fallback invoker.

    Why this function exists:
    - Python-authored `ReActAgent.tools` are registered in the process-local
      toolset registry
    - the legacy bootstrap path must expose them through the same invoker port as
      built-in Fred tools

    How to use it:
    - call while assembling `RuntimeServices`

    Example:
    - `tool_invoker = _build_v2_tool_invoker(definition=definition, binding=binding, effective_settings=settings, base_tool_invoker=base, ports=ports)`
    """

    toolset_key = getattr(definition, "toolset_key", None)
    if not isinstance(definition, ReActAgentDefinition):
        return base_tool_invoker

    handlers = build_authored_tool_handlers(
        definition=definition,
        toolset_key=toolset_key,
        binding=binding,
        settings=effective_settings,
        ports=ports,
    )
    if not handlers:
        return base_tool_invoker
    return CompositeToolInvoker(
        handlers=handlers,
        fallback=base_tool_invoker,
    )
