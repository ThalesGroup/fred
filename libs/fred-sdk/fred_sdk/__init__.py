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
fred-sdk public authoring surface.

Everything an agent author needs is importable directly from this package.
No submodule paths are required.

ReAct agents
------------
    from fred_sdk import ReActAgent, tool, ToolContext, ToolOutput

Graph agents
------------
    from fred_sdk import GraphAgent, GraphWorkflow, typed_node, StepResult

Team agents
-----------
    from fred_sdk import TeamAgent, AgentSpec

Human-in-the-loop
-----------------
    from fred_sdk import HumanInputRequest, HumanChoiceOption

MCP server references
---------------------
    from fred_sdk import MCPServerRef, MCP_SERVER_KNOWLEDGE_FLOW_CORPUS

What is NOT exported here (execution engine, lives in fred-runtime):
    - ReActRuntime, GraphRuntime, DeepAgentRuntime  → fred_runtime.react / .graph / .deep
    - ChatModelFactoryPort, RuntimeServices          → fred_sdk.contracts.runtime (ports only)
    - BoundRuntimeContext, PortableContext           → platform execution context
    - ReActInput, ReActOutput, ReActMessage          → runtime transport types
"""

# ---------------------------------------------------------------------------
# ReAct agent authoring
# ---------------------------------------------------------------------------
from fred_sdk.authoring.api import (
    ModelInvocationError,
    ReActAgent,
    ToolContext,
    ToolInvocationError,
    ToolOutput,
    UIHints,
    prompt_md,
    tool,
    ui_field,
)
from fred_sdk.authoring.inspection import inspect_agent

# ---------------------------------------------------------------------------
# MCP server references
# ---------------------------------------------------------------------------
from fred_sdk.authoring.knowledge_flow_mcp import (
    MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
    MCP_SERVER_KNOWLEDGE_FLOW_FS,
    MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS,
    MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS,
    MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
    MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
    MCPServerRef,
)
from fred_sdk.contracts.context import (
    AgentInvocationResult,
    FsEntry,
    InvocationScope,
    PublishedArtifact,
    RuntimeContext,
    ToolContentKind,
)
from fred_sdk.contracts.eval import EvalStep, EvalTrace
from fred_sdk.contracts.models import (
    DeepAgentDefinition,
    ExecutionCategory,
    FieldSpec,
    FieldType,
    GuardrailDefinition,
    ReActAgentDefinition,
    ReActPolicy,
    ToolApprovalPolicy,
    ToolRefRequirement,
    TuningScalar,
    TuningValue,
)
from fred_sdk.contracts.runtime import (
    HumanChoiceOption,
    HumanInputRequest,
    ThoughtDeltaEvent,
    ThoughtEndEvent,
    ThoughtKind,
    ThoughtRecord,
    ThoughtStartEvent,
    WorkspaceFileNotFound,
    WorkspaceFsPort,
)

# ---------------------------------------------------------------------------
# Graph agent authoring
# ---------------------------------------------------------------------------
from fred_sdk.graph.authoring.api import (
    GraphAgent,
    GraphWorkflow,
    StepResult,
    WorkflowNode,
    choice_step,
    finalize_step,
    intent_router_step,
    model_text_step,
    structured_model_step,
    typed_node,
)

# ---------------------------------------------------------------------------
# Team / multi-agent authoring
# ---------------------------------------------------------------------------
from fred_sdk.graph.authoring.team_api import (
    AgentSpec,
    TeamAgent,
    TeamInput,
    TeamMemberResult,
    TeamState,
)

# ---------------------------------------------------------------------------
# Shared types visible to agent authors inside node handlers and tool contexts
# ---------------------------------------------------------------------------
from fred_sdk.graph.runtime import (
    GraphExecutionOutput,
    GraphNodeContext,
    GraphNodeResult,
    ThoughtWriter,
)

# ---------------------------------------------------------------------------
# Resource loading helpers
# ---------------------------------------------------------------------------
from fred_sdk.resources import (
    load_agent_prompt_markdown,
    load_packaged_markdown,
)

# ---------------------------------------------------------------------------
# Built-in tool references
# ---------------------------------------------------------------------------
from fred_sdk.support.builtins import (
    TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
    TOOL_REF_ATTACHMENTS_READ_IMAGE,
    TOOL_REF_GEO_RENDER_POINTS,
    TOOL_REF_KNOWLEDGE_SEARCH,
    TOOL_REF_LOGS_QUERY,
    TOOL_REF_RESOURCES_FETCH_TEXT,
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
)

# ---------------------------------------------------------------------------
# Public surface declaration
# ---------------------------------------------------------------------------
__all__ = [
    # ReAct authoring
    "ReActAgent",
    "tool",
    "ToolContext",
    "ToolOutput",
    "UIHints",
    "ui_field",
    "prompt_md",
    "ToolInvocationError",
    "ModelInvocationError",
    "inspect_agent",
    # MCP server references
    "MCPServerRef",
    "MCP_SERVER_KNOWLEDGE_FLOW_CORPUS",
    "MCP_SERVER_KNOWLEDGE_FLOW_FS",
    "MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS",
    "MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS",
    "MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS",
    "MCP_SERVER_KNOWLEDGE_FLOW_TABULAR",
    "MCP_SERVER_KNOWLEDGE_FLOW_TEXT",
    # Graph authoring
    "GraphAgent",
    "GraphWorkflow",
    "StepResult",
    "WorkflowNode",
    "typed_node",
    "choice_step",
    "finalize_step",
    "intent_router_step",
    "model_text_step",
    "structured_model_step",
    # Team authoring
    "TeamAgent",
    "AgentSpec",
    "TeamInput",
    "TeamMemberResult",
    "TeamState",
    # Shared types authors encounter in node/tool contexts
    "GraphExecutionOutput",
    "GraphNodeContext",
    "GraphNodeResult",
    "AgentInvocationResult",
    "FsEntry",
    "InvocationScope",
    "PublishedArtifact",
    "WorkspaceFsPort",
    "WorkspaceFileNotFound",
    "HumanInputRequest",
    "HumanChoiceOption",
    "ThoughtKind",
    "ThoughtStartEvent",
    "ThoughtDeltaEvent",
    "ThoughtEndEvent",
    "ThoughtRecord",
    "ThoughtWriter",
    # Agent definition metadata and policies (used when subclassing GraphAgent/ReActAgent)
    "ExecutionCategory",
    "DeepAgentDefinition",
    "ReActAgentDefinition",
    "ReActPolicy",
    "ToolApprovalPolicy",
    "FieldSpec",
    "FieldType",
    "GuardrailDefinition",
    "ToolRefRequirement",
    "TuningScalar",
    "TuningValue",
    # Evaluation contracts (POST /agents/evaluate)
    "EvalStep",
    "EvalTrace",
    # Request context (language, user, session info visible inside nodes)
    "RuntimeContext",
    "ToolContentKind",
    # Resource helpers
    "load_agent_prompt_markdown",
    "load_packaged_markdown",
    # Built-in tool references
    "TOOL_REF_ARTIFACTS_PUBLISH_TEXT",
    "TOOL_REF_ATTACHMENTS_READ_IMAGE",
    "TOOL_REF_GEO_RENDER_POINTS",
    "TOOL_REF_KNOWLEDGE_SEARCH",
    "TOOL_REF_LOGS_QUERY",
    "TOOL_REF_RESOURCES_FETCH_TEXT",
    "TOOL_REF_TRACES_SUMMARIZE_CONVERSATION",
]
