"""
Public v2 API surface with lazy exports.

Why this file is intentionally lazy:
- importing `agentic_backend.core.agents.v2.<submodule>` first loads this
  package module;
- eager imports here can create startup-time circular imports with
  `application_context`;
- runtime code should not depend on package import side effects.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from .authoring import ReActAgent as AuthoredReActAgent
    from .authoring import SearchBundle, ToolContext, ToolOutput, prompt_md, tool
    from .context import (
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
    from .graph_runtime import (
        GraphExecutionOutput,
        GraphNodeContext,
        GraphNodeHandler,
        GraphNodeResult,
        GraphRuntime,
    )
    from .inspection import inspect_agent
    from .lexicon_resources import (
        load_agent_lexicon_json,
        load_packaged_json_object,
    )
    from .models import (
        AgentDefinition,
        AgentInspection,
        AgentPreview,
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
        ToolCapabilityRequirement,
        ToolRefRequirement,
        ToolRequirement,
        ToolSelectionPolicy,
    )
    from .react_profiles import ReActProfile, get_react_profile, list_react_profiles
    from .react_runtime import (
        ReActInput,
        ReActMessage,
        ReActMessageRole,
        ReActOutput,
        ReActRuntime,
        ReActToolCall,
    )
    from .runtime import (
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
        WorkspaceClientFactoryPort,
        WorkspaceClientPort,
    )
    from .toolset_registry import (
        ToolHandler,
        ToolRefSpec,
        ToolsetRegistration,
        ToolsetRuntimePorts,
        build_registered_tool_handlers,
        get_registered_tool_spec,
        get_toolset_registration,
        register_toolset,
    )

__all__ = [
    "AgentDefinition",
    "AgentInspection",
    "AgentPreview",
    "AgentRuntime",
    "AuthoredReActAgent",
    "ArtifactPublishRequest",
    "ArtifactPublisherPort",
    "ArtifactScope",
    "AssistantDeltaRuntimeEvent",
    "AwaitingHumanRuntimeEvent",
    "BoundRuntimeContext",
    "ChatModelFactoryPort",
    "CheckpointStrategy",
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
    "GraphNodeShape",
    "GraphNodeResult",
    "GraphRouteDefinition",
    "GraphRuntime",
    "GuardrailDefinition",
    "HumanChoiceOption",
    "HumanInputRequest",
    "PortableContext",
    "PortableEnvironment",
    "PreviewKind",
    "PublishedArtifact",
    "ResourceFetchRequest",
    "ResourceReaderPort",
    "ResourceScope",
    "ProxyAgentDefinition",
    "ProxySpec",
    "ProxyTransportKind",
    "ReActInput",
    "ReActAgentDefinition",
    "ReActMessage",
    "ReActMessageRole",
    "ReActOutput",
    "ReActProfile",
    "ReActPolicy",
    "ReActRuntime",
    "ReActToolCall",
    "RuntimeEvent",
    "RuntimeEventKind",
    "RuntimeServices",
    "SpanPort",
    "StatusRuntimeEvent",
    "TokenProviderPort",
    "ToolCapabilityRequirement",
    "ToolCallRuntimeEvent",
    "ToolContentBlock",
    "ToolContentKind",
    "ToolInvocationRequest",
    "ToolInvocationResult",
    "ToolInvokerPort",
    "ToolProviderPort",
    "ToolRefRequirement",
    "ToolRefSpec",
    "ToolRequirement",
    "ToolResultRuntimeEvent",
    "ToolSelectionPolicy",
    "ToolApprovalPolicy",
    "ToolContext",
    "ToolHandler",
    "ToolOutput",
    "ToolsetRegistration",
    "ToolsetRuntimePorts",
    "TracerPort",
    "UiPart",
    "SearchBundle",
    "WorkspaceClientFactoryPort",
    "WorkspaceClientPort",
    "build_registered_tool_handlers",
    "get_react_profile",
    "get_registered_tool_spec",
    "get_toolset_registration",
    "inspect_agent",
    "list_react_profiles",
    "load_agent_lexicon_json",
    "load_packaged_json_object",
    "prompt_md",
    "register_toolset",
    "tool",
]


def _module_exports(
    *, module: str, names: tuple[str, ...]
) -> dict[str, tuple[str, str]]:
    return {name: (module, name) for name in names}


_EXPORTS: Final[dict[str, tuple[str, str]]] = {}
_EXPORTS.update(
    _module_exports(
        module="context",
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
        module="graph_runtime",
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
        module="models",
        names=(
            "AgentDefinition",
            "AgentInspection",
            "AgentPreview",
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
            "ToolCapabilityRequirement",
            "ToolRefRequirement",
            "ToolRequirement",
            "ToolSelectionPolicy",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="react_profiles",
        names=(
            "ReActProfile",
            "get_react_profile",
            "list_react_profiles",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="react_runtime",
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
        module="runtime",
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
            "WorkspaceClientFactoryPort",
            "WorkspaceClientPort",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="toolset_registry",
        names=(
            "ToolHandler",
            "ToolRefSpec",
            "ToolsetRegistration",
            "ToolsetRuntimePorts",
            "build_registered_tool_handlers",
            "get_registered_tool_spec",
            "get_toolset_registration",
            "register_toolset",
        ),
    )
)
_EXPORTS.update(
    _module_exports(
        module="lexicon_resources",
        names=(
            "load_agent_lexicon_json",
            "load_packaged_json_object",
        ),
    )
)
_EXPORTS.update(_module_exports(module="inspection", names=("inspect_agent",)))
_EXPORTS.update(
    _module_exports(
        module="authoring",
        names=(
            "SearchBundle",
            "ToolContext",
            "ToolOutput",
            "prompt_md",
            "tool",
        ),
    )
)
_EXPORTS["AuthoredReActAgent"] = ("authoring", "ReActAgent")


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
