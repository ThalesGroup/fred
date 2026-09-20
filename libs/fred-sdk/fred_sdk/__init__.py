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

Capabilities (modular agent features)
-------------------------------------
    from fred_sdk import AgentCapability, CapabilityManifest, CapabilityContext

MCP server references
---------------------
    from fred_sdk import MCPServerRef, MCP_SERVER_KNOWLEDGE_FLOW_CORPUS

What is NOT exported here (execution engine, lives in fred-runtime):
    - ReActRuntime, GraphRuntime, DeepAgentRuntime  → fred_runtime.react / .graph / .deep
    - ChatModelFactoryPort, RuntimeServices          → fred_sdk.contracts.runtime (ports only)
    - BoundRuntimeContext, PortableContext           → platform execution context
    - ReActInput, ReActOutput, ReActMessage          → runtime transport types
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
        MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
        MCP_SERVER_KNOWLEDGE_FLOW_TEXT,
        MCPServerRef,
    )
    from fred_sdk.contracts.capability import (
        AgentCapability,
        AssetSlot,
        CapabilityContext,
        CapabilityIdentity,
        CapabilityManifest,
        ChatControlSpec,
        EmptyModel,
        HitlGateRequest,
        HitlSpec,
        SaveContext,
        SidePanelSpec,
        TeamScopePolicy,
        UploadedFile,
        chat_part_kind,
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
        PendingToolCall,
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
        TOOL_REF_GEO_RENDER_POINTS,
        TOOL_REF_KNOWLEDGE_SEARCH,
        TOOL_REF_RESOURCES_FETCH_TEXT,
        TOOL_REF_SIMILARITY_SEARCH,
        TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
    )

# Exported name -> module that defines it. Importing the whole authoring surface
# eagerly pulled langchain, langgraph and the full fred_core tree into any pod
# that merely touched a submodule (e.g. `import fred_sdk.knowledge_base`).
_LAZY: dict[str, str] = {
    # ReAct agent authoring
    "ModelInvocationError": "fred_sdk.authoring.api",
    "ReActAgent": "fred_sdk.authoring.api",
    "ToolContext": "fred_sdk.authoring.api",
    "ToolInvocationError": "fred_sdk.authoring.api",
    "ToolOutput": "fred_sdk.authoring.api",
    "UIHints": "fred_sdk.authoring.api",
    "prompt_md": "fred_sdk.authoring.api",
    "tool": "fred_sdk.authoring.api",
    "ui_field": "fred_sdk.authoring.api",
    "inspect_agent": "fred_sdk.authoring.inspection",
    # MCP server references
    "MCP_SERVER_KNOWLEDGE_FLOW_CORPUS": "fred_sdk.authoring.knowledge_flow_mcp",
    "MCP_SERVER_KNOWLEDGE_FLOW_FS": "fred_sdk.authoring.knowledge_flow_mcp",
    "MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS": "fred_sdk.authoring.knowledge_flow_mcp",
    "MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS": "fred_sdk.authoring.knowledge_flow_mcp",
    "MCP_SERVER_KNOWLEDGE_FLOW_TABULAR": "fred_sdk.authoring.knowledge_flow_mcp",
    "MCP_SERVER_KNOWLEDGE_FLOW_TEXT": "fred_sdk.authoring.knowledge_flow_mcp",
    "MCPServerRef": "fred_sdk.authoring.knowledge_flow_mcp",
    # Capability authoring
    "AgentCapability": "fred_sdk.contracts.capability",
    "AssetSlot": "fred_sdk.contracts.capability",
    "CapabilityContext": "fred_sdk.contracts.capability",
    "CapabilityIdentity": "fred_sdk.contracts.capability",
    "CapabilityManifest": "fred_sdk.contracts.capability",
    "ChatControlSpec": "fred_sdk.contracts.capability",
    "EmptyModel": "fred_sdk.contracts.capability",
    "HitlGateRequest": "fred_sdk.contracts.capability",
    "HitlSpec": "fred_sdk.contracts.capability",
    "SaveContext": "fred_sdk.contracts.capability",
    "SidePanelSpec": "fred_sdk.contracts.capability",
    "TeamScopePolicy": "fred_sdk.contracts.capability",
    "UploadedFile": "fred_sdk.contracts.capability",
    "chat_part_kind": "fred_sdk.contracts.capability",
    # Request context and shared tool/agent result types
    "AgentInvocationResult": "fred_sdk.contracts.context",
    "FsEntry": "fred_sdk.contracts.context",
    "InvocationScope": "fred_sdk.contracts.context",
    "PublishedArtifact": "fred_sdk.contracts.context",
    "RuntimeContext": "fred_sdk.contracts.context",
    "ToolContentKind": "fred_sdk.contracts.context",
    # Evaluation contracts
    "EvalStep": "fred_sdk.contracts.eval",
    "EvalTrace": "fred_sdk.contracts.eval",
    # Agent definition metadata and policies
    "DeepAgentDefinition": "fred_sdk.contracts.models",
    "ExecutionCategory": "fred_sdk.contracts.models",
    "FieldSpec": "fred_sdk.contracts.models",
    "FieldType": "fred_sdk.contracts.models",
    "ReActAgentDefinition": "fred_sdk.contracts.models",
    "ReActPolicy": "fred_sdk.contracts.models",
    "ToolApprovalPolicy": "fred_sdk.contracts.models",
    "ToolRefRequirement": "fred_sdk.contracts.models",
    "TuningScalar": "fred_sdk.contracts.models",
    "TuningValue": "fred_sdk.contracts.models",
    # Human-in-the-loop, thoughts, workspace filesystem port
    "HumanChoiceOption": "fred_sdk.contracts.runtime",
    "HumanInputRequest": "fred_sdk.contracts.runtime",
    "PendingToolCall": "fred_sdk.contracts.runtime",
    "ThoughtDeltaEvent": "fred_sdk.contracts.runtime",
    "ThoughtEndEvent": "fred_sdk.contracts.runtime",
    "ThoughtKind": "fred_sdk.contracts.runtime",
    "ThoughtRecord": "fred_sdk.contracts.runtime",
    "ThoughtStartEvent": "fred_sdk.contracts.runtime",
    "WorkspaceFileNotFound": "fred_sdk.contracts.runtime",
    "WorkspaceFsPort": "fred_sdk.contracts.runtime",
    # Graph agent authoring
    "GraphAgent": "fred_sdk.graph.authoring.api",
    "GraphWorkflow": "fred_sdk.graph.authoring.api",
    "StepResult": "fred_sdk.graph.authoring.api",
    "WorkflowNode": "fred_sdk.graph.authoring.api",
    "choice_step": "fred_sdk.graph.authoring.api",
    "finalize_step": "fred_sdk.graph.authoring.api",
    "intent_router_step": "fred_sdk.graph.authoring.api",
    "model_text_step": "fred_sdk.graph.authoring.api",
    "structured_model_step": "fred_sdk.graph.authoring.api",
    "typed_node": "fred_sdk.graph.authoring.api",
    # Team / multi-agent authoring
    "AgentSpec": "fred_sdk.graph.authoring.team_api",
    "TeamAgent": "fred_sdk.graph.authoring.team_api",
    "TeamInput": "fred_sdk.graph.authoring.team_api",
    "TeamMemberResult": "fred_sdk.graph.authoring.team_api",
    "TeamState": "fred_sdk.graph.authoring.team_api",
    # Shared types visible inside node handlers and tool contexts
    "GraphExecutionOutput": "fred_sdk.graph.runtime",
    "GraphNodeContext": "fred_sdk.graph.runtime",
    "GraphNodeResult": "fred_sdk.graph.runtime",
    "ThoughtWriter": "fred_sdk.graph.runtime",
    # Resource loading helpers
    "load_agent_prompt_markdown": "fred_sdk.resources",
    "load_packaged_markdown": "fred_sdk.resources",
    # Built-in tool references
    "TOOL_REF_ARTIFACTS_PUBLISH_TEXT": "fred_sdk.support.builtins",
    "TOOL_REF_GEO_RENDER_POINTS": "fred_sdk.support.builtins",
    "TOOL_REF_KNOWLEDGE_SEARCH": "fred_sdk.support.builtins",
    "TOOL_REF_RESOURCES_FETCH_TEXT": "fred_sdk.support.builtins",
    "TOOL_REF_SIMILARITY_SEARCH": "fred_sdk.support.builtins",
    "TOOL_REF_TRACES_SUMMARIZE_CONVERSATION": "fred_sdk.support.builtins",
}


def __getattr__(name: str) -> object:
    module_path = _LAZY.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value  # resolved once, then a normal global
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


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
    "PendingToolCall",
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
    "ToolRefRequirement",
    "TuningScalar",
    "TuningValue",
    # Capability authoring (#1973, RFC AGENT-CAPABILITY-RFC.md §3)
    "AgentCapability",
    "AssetSlot",
    "CapabilityContext",
    "CapabilityIdentity",
    "CapabilityManifest",
    "ChatControlSpec",
    "EmptyModel",
    "HitlGateRequest",
    "HitlSpec",
    "SaveContext",
    "SidePanelSpec",
    "TeamScopePolicy",
    "UploadedFile",
    "chat_part_kind",
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
    "TOOL_REF_GEO_RENDER_POINTS",
    "TOOL_REF_KNOWLEDGE_SEARCH",
    "TOOL_REF_RESOURCES_FETCH_TEXT",
    "TOOL_REF_SIMILARITY_SEARCH",
    "TOOL_REF_TRACES_SUMMARIZE_CONVERSATION",
]
