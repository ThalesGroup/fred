from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from agentic_backend.common.structures import AgentSettings

from .context import BoundRuntimeContext, ToolInvocationRequest, ToolInvocationResult
from .runtime import (
    ArtifactPublisherPort,
    ChatModelFactoryPort,
    ResourceReaderPort,
    ToolInvokerPort,
)

ToolHandler = Callable[
    [ToolInvocationRequest], ToolInvocationResult | Awaitable[ToolInvocationResult]
]


@dataclass(frozen=True)
class ToolRefSpec:
    tool_ref: str
    args_schema: type[BaseModel]
    runtime_name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ToolsetRuntimePorts:
    chat_model_factory: ChatModelFactoryPort | None = None
    artifact_publisher: ArtifactPublisherPort | None = None
    resource_reader: ResourceReaderPort | None = None
    fallback_tool_invoker: ToolInvokerPort | None = None


ToolsetHandlerFactory = Callable[
    [object, BoundRuntimeContext, AgentSettings, ToolsetRuntimePorts],
    Mapping[str, ToolHandler],
]


@dataclass(frozen=True)
class ToolsetRegistration:
    toolset_key: str
    tool_specs: Mapping[str, ToolRefSpec]
    bind_handlers: ToolsetHandlerFactory


_TOOLSET_REGISTRY: dict[str, ToolsetRegistration] = {}


def register_toolset(registration: ToolsetRegistration) -> None:
    existing = _TOOLSET_REGISTRY.get(registration.toolset_key)
    if existing is not None and existing is not registration:
        raise RuntimeError(
            f"Toolset {registration.toolset_key!r} is already registered."
        )
    _TOOLSET_REGISTRY[registration.toolset_key] = registration


def get_toolset_registration(toolset_key: str | None) -> ToolsetRegistration | None:
    if not isinstance(toolset_key, str) or not toolset_key.strip():
        return None
    return _TOOLSET_REGISTRY.get(toolset_key.strip())


def get_registered_tool_spec(
    *,
    toolset_key: str | None,
    tool_ref: str,
) -> ToolRefSpec | None:
    registration = get_toolset_registration(toolset_key)
    if registration is None:
        return None
    return registration.tool_specs.get(tool_ref)


def build_registered_tool_handlers(
    *,
    definition: object,
    toolset_key: str | None,
    binding: BoundRuntimeContext,
    settings: AgentSettings,
    ports: ToolsetRuntimePorts,
) -> dict[str, ToolHandler]:
    registration = get_toolset_registration(toolset_key)
    if registration is None:
        return {}
    return dict(
        registration.bind_handlers(
            definition,
            binding,
            settings,
            ports,
        )
    )
