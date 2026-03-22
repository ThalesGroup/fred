"""
Public v2 API surface with lazy exports.

Why this file is intentionally lazy:
- importing `agentic_backend.core.agents.v2.<submodule>` first loads this
  package module
- eager imports here can create startup-time circular imports with
  `application_context`
- runtime code should not depend on package import side effects
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from .authoring import (
        MCP_SERVER_KNOWLEDGE_FLOW_CORPUS,
        MCP_SERVER_KNOWLEDGE_FLOW_FS,
        MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS,
        MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS,
        MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
        MCPServerRef,
        ToolContext,
        ToolOutput,
        inspect_agent,
        prompt_md,
        tool,
    )
    from .authoring import (
        ReActAgent as AuthoredReActAgent,
    )
    from .contracts.context import (
        ArtifactPublishRequest,
        ArtifactScope,
        BoundRuntimeContext,
        FetchedResource,
        PortableContext,
        PortableEnvironment,
        PublishedArtifact,
        ResourceFetchRequest,
        ResourceScope,
        ToolContentBlock,
        ToolContentKind,
        ToolInvocationRequest,
        ToolInvocationResult,
        UiPart,
    )
    from .contracts.models import (
        AgentDefinition,
        AgentInspection,
        AgentPreview,
        DeepAgentDefinition,
        ExecutionCategory,
        GraphAgentDefinition,
        GraphConditionalDefinition,
        GraphDefinition,
        GraphEdgeDefinition,
        GraphNodeDefinition,
        GraphNodeShape,
        GraphRouteDefinition,
        GuardrailDefinition,
        PreviewKind,
        ProxyAgentDefinition,
        ProxySpec,
        ProxyTransportKind,
        ReActAgentDefinition,
        ReActPolicy,
        ToolApprovalPolicy,
        ToolRefRequirement,
        ToolRequirement,
        ToolSelectionPolicy,
    )
    from .contracts.runtime import (
        AgentRuntime,
        ArtifactPublisherPort,
        AssistantDeltaRuntimeEvent,
        AwaitingHumanRuntimeEvent,
        ChatModelFactoryPort,
        CheckpointStrategy,
        ExecutionConfig,
        Executor,
        FinalRuntimeEvent,
        HumanChoiceOption,
        HumanInputRequest,
        ResourceReaderPort,
        RuntimeEvent,
        RuntimeEventKind,
        RuntimeServices,
        SpanPort,
        StatusRuntimeEvent,
        TokenProviderPort,
        ToolCallRuntimeEvent,
        ToolInvokerPort,
        ToolProviderPort,
        ToolResultRuntimeEvent,
        TracerPort,
    )
    from .deep import DeepAgentRuntime
    from .graph import (
        GraphExecutionOutput,
        GraphNodeContext,
        GraphNodeHandler,
        GraphNodeResult,
        GraphRuntime,
    )
    from .react.react_runtime import (
        ReActInput,
        ReActMessage,
        ReActMessageRole,
        ReActOutput,
        ReActRuntime,
        ReActToolCall,
    )
    from .resources import load_agent_prompt_markdown, load_packaged_markdown

__all__ = [
    "AgentDefinition",
    "AgentInspection",
    "AgentPreview",
    "AgentRuntime",
    "ArtifactPublishRequest",
    "ArtifactPublisherPort",
    "ArtifactScope",
    "AssistantDeltaRuntimeEvent",
    "AuthoredReActAgent",
    "AwaitingHumanRuntimeEvent",
    "BoundRuntimeContext",
    "ChatModelFactoryPort",
    "CheckpointStrategy",
    "DeepAgentDefinition",
    "DeepAgentRuntime",
    "ExecutionCategory",
    "ExecutionConfig",
    "Executor",
    "FetchedResource",
    "FinalRuntimeEvent",
    "GraphAgentDefinition",
    "GraphConditionalDefinition",
    "GraphDefinition",
    "GraphEdgeDefinition",
    "GraphExecutionOutput",
    "GraphNodeContext",
    "GraphNodeDefinition",
    "GraphNodeHandler",
    "GraphNodeResult",
    "GraphNodeShape",
    "GraphRouteDefinition",
    "GraphRuntime",
    "GuardrailDefinition",
    "HumanChoiceOption",
    "HumanInputRequest",
    "MCPServerRef",
    "MCP_SERVER_KNOWLEDGE_FLOW_CORPUS",
    "MCP_SERVER_KNOWLEDGE_FLOW_FS",
    "MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS",
    "MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS",
    "MCP_SERVER_KNOWLEDGE_FLOW_TABULAR",
    "PortableContext",
    "PortableEnvironment",
    "PreviewKind",
    "ProxyAgentDefinition",
    "ProxySpec",
    "ProxyTransportKind",
    "PublishedArtifact",
    "ReActAgentDefinition",
    "ReActInput",
    "ReActMessage",
    "ReActMessageRole",
    "ReActOutput",
    "ReActPolicy",
    "ReActRuntime",
    "ReActToolCall",
    "ResourceFetchRequest",
    "ResourceReaderPort",
    "ResourceScope",
    "RuntimeEvent",
    "RuntimeEventKind",
    "RuntimeServices",
    "SpanPort",
    "StatusRuntimeEvent",
    "TokenProviderPort",
    "ToolApprovalPolicy",
    "ToolCallRuntimeEvent",
    "ToolContentBlock",
    "ToolContentKind",
    "ToolContext",
    "ToolInvocationRequest",
    "ToolInvocationResult",
    "ToolInvokerPort",
    "ToolOutput",
    "ToolProviderPort",
    "ToolRefRequirement",
    "ToolRequirement",
    "ToolResultRuntimeEvent",
    "ToolSelectionPolicy",
    "TracerPort",
    "UiPart",
    "inspect_agent",
    "load_agent_prompt_markdown",
    "load_packaged_markdown",
    "prompt_md",
    "tool",
]


def _module_exports(
    *, module: str, names: tuple[str, ...]
) -> dict[str, tuple[str, str]]:
    return {name: (module, name) for name in names}


_EXPORTS: Final[dict[str, tuple[str, str]]] = {}
_EXPORTS.update(
    _module_exports(
        module="authoring",
        names=(
            "MCPServerRef",
            "MCP_SERVER_KNOWLEDGE_FLOW_CORPUS",
            "MCP_SERVER_KNOWLEDGE_FLOW_FS",
            "MCP_SERVER_KNOWLEDGE_FLOW_OPENSEARCH_OPS",
            "MCP_SERVER_KNOWLEDGE_FLOW_STATISTICS",
            "MCP_SERVER_KNOWLEDGE_FLOW_TABULAR",
            "ToolContext",
            "ToolOutput",
            "inspect_agent",
            "prompt_md",
            "tool",
        ),
    )
)
_EXPORTS["AuthoredReActAgent"] = ("authoring", "ReActAgent")
_EXPORTS.update(
    _module_exports(
        module="contracts.context",
        names=(
            "ArtifactPublishRequest",
            "ArtifactScope",
            "BoundRuntimeContext",
            "FetchedResource",
            "PortableContext",
            "PortableEnvironment",
            "PublishedArtifact",
            "ResourceFetchRequest",
            "ResourceScope",
            "ToolContentBlock",
            "ToolContentKind",
            "ToolInvocationRequest",
            "ToolInvocationResult",
            "UiPart",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="contracts.models",
        names=(
            "AgentDefinition",
            "AgentInspection",
            "AgentPreview",
            "DeepAgentDefinition",
            "ExecutionCategory",
            "GraphAgentDefinition",
            "GraphConditionalDefinition",
            "GraphDefinition",
            "GraphEdgeDefinition",
            "GraphNodeDefinition",
            "GraphNodeShape",
            "GraphRouteDefinition",
            "GuardrailDefinition",
            "PreviewKind",
            "ProxyAgentDefinition",
            "ProxySpec",
            "ProxyTransportKind",
            "ReActAgentDefinition",
            "ReActPolicy",
            "ToolApprovalPolicy",
            "ToolRefRequirement",
            "ToolRequirement",
            "ToolSelectionPolicy",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="contracts.runtime",
        names=(
            "AgentRuntime",
            "ArtifactPublisherPort",
            "AssistantDeltaRuntimeEvent",
            "AwaitingHumanRuntimeEvent",
            "ChatModelFactoryPort",
            "CheckpointStrategy",
            "ExecutionConfig",
            "Executor",
            "FinalRuntimeEvent",
            "HumanChoiceOption",
            "HumanInputRequest",
            "ResourceReaderPort",
            "RuntimeEvent",
            "RuntimeEventKind",
            "RuntimeServices",
            "SpanPort",
            "StatusRuntimeEvent",
            "TokenProviderPort",
            "ToolCallRuntimeEvent",
            "ToolInvokerPort",
            "ToolProviderPort",
            "ToolResultRuntimeEvent",
            "TracerPort",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="deep",
        names=("DeepAgentRuntime",),
    )
)
_EXPORTS.update(
    _module_exports(
        module="graph",
        names=(
            "GraphExecutionOutput",
            "GraphNodeContext",
            "GraphNodeHandler",
            "GraphNodeResult",
            "GraphRuntime",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="react.react_runtime",
        names=(
            "ReActInput",
            "ReActMessage",
            "ReActMessageRole",
            "ReActOutput",
            "ReActRuntime",
            "ReActToolCall",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="resources",
        names=(
            "load_agent_prompt_markdown",
            "load_packaged_markdown",
        ),
    )
)


if set(__all__) != set(_EXPORTS):
    missing = sorted(set(__all__) - set(_EXPORTS))
    extra = sorted(set(_EXPORTS) - set(__all__))
    raise RuntimeError(
        f"v2 package export map mismatch: missing={missing!r} extra={extra!r}"
    )


def __getattr__(name: str) -> object:
    export = _EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
