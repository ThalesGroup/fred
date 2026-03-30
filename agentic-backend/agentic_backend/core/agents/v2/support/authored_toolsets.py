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
Process-local registry for Python-authored `ReActAgent.tools`.

Why this module exists:
- this file is only for local Python tools declared by an agent author with
  `class MyAgent(ReActAgent): tools = (...)`
- these authored tools are not built-in Fred tools and are not MCP/runtime tools
- Fred reconstructs runtimes later from definitions/settings, so it needs a
  stable way to find the original Python tool handlers again

What this file is not for:
- not for the native built-in catalog in `support/builtins/`
- not for MCP/runtime tools
- not for the final tool aggregation passed to `create_agent(...)` or
  `create_deep_agent(...)`

How to use it:
- `authoring.py` registers one authored toolset by `toolset_key`
- runtime bootstrap looks up the same `toolset_key` later to rebuild handlers

Example:
- register:
  `register_authored_toolset(AuthoredToolsetRegistration(...))`
- runtime lookup:
  `spec = get_authored_tool_spec(toolset_key=toolset_key, tool_ref="policy.search")`
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from agentic_backend.common.structures import AgentSettings

from ..contracts.context import (
    BoundRuntimeContext,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from ..contracts.models import ReActAgentDefinition
from ..contracts.runtime import (
    ArtifactPublisherPort,
    ChatModelFactoryPort,
    ResourceReaderPort,
    ToolInvokerPort,
)

AuthoredToolHandler = Callable[
    [ToolInvocationRequest], ToolInvocationResult | Awaitable[ToolInvocationResult]
]


@dataclass(frozen=True)
class AuthoredToolSpec:
    """
    Metadata for one Python-authored local tool.

    Why this exists:
    - runtime code needs the authored tool ref, schema, optional runtime name,
      and description without importing the original Python function directly

    How to use it:
    - store it inside one `AuthoredToolsetRegistration.tool_specs` mapping

    Example:
    - `AuthoredToolSpec(tool_ref="policy.search", args_schema=SearchArgs, runtime_name="policy_search")`
    """

    tool_ref: str
    args_schema: type[BaseModel]
    runtime_name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class AuthoredToolRuntimePorts:
    """
    Runtime ports exposed to Python-authored tool handlers.

    Why this exists:
    - Python-authored tools may need the same runtime capabilities as other Fred
      tools, such as model access, artifact publishing, resource reading, or a
      fallback tool invoker

    How to use it:
    - runtime bootstrap populates this once when it binds authored handlers

    Example:
    - `ports = AuthoredToolRuntimePorts(chat_model_factory=factory, fallback_tool_invoker=invoker)`
    """

    chat_model_factory: ChatModelFactoryPort | None = None
    artifact_publisher: ArtifactPublisherPort | None = None
    resource_reader: ResourceReaderPort | None = None
    fallback_tool_invoker: ToolInvokerPort | None = None


AuthoredToolsetHandlerFactory = Callable[
    [
        ReActAgentDefinition,
        BoundRuntimeContext,
        AgentSettings,
        AuthoredToolRuntimePorts,
    ],
    Mapping[str, AuthoredToolHandler],
]


@dataclass(frozen=True)
class AuthoredToolsetRegistration:
    """
    One registered set of Python-authored tools for a `ReActAgent` class.

    Why this exists:
    - `authoring.py` needs to register a whole authored toolset under one stable
      `toolset_key`
    - runtime bootstrap later needs both the authored tool specs and a way to
      bind the actual handlers

    How to use it:
    - create one registration per authored `ReActAgent` subclass
    - register it once during class initialization

    Example:
    - `register_authored_toolset(AuthoredToolsetRegistration(toolset_key="authored.my.module.Agent", tool_specs=specs, bind_handlers=factory))`
    """

    toolset_key: str
    tool_specs: Mapping[str, AuthoredToolSpec]
    bind_handlers: AuthoredToolsetHandlerFactory


_AUTHORED_TOOLSET_REGISTRY: dict[str, AuthoredToolsetRegistration] = {}


def register_authored_toolset(registration: AuthoredToolsetRegistration) -> None:
    """
    Register one Python-authored toolset by stable key.

    Why this exists:
    - authored toolsets are created at import/class-definition time
    - later runtime bootstrap needs a deterministic lookup by `toolset_key`

    How to use it:
    - call once from `authoring.py` after the authored tools were normalized

    Example:
    - `register_authored_toolset(registration)`
    """

    existing = _AUTHORED_TOOLSET_REGISTRY.get(registration.toolset_key)
    if existing is not None and existing is not registration:
        raise RuntimeError(
            f"Authored toolset {registration.toolset_key!r} is already registered."
        )
    _AUTHORED_TOOLSET_REGISTRY[registration.toolset_key] = registration


def get_authored_toolset_registration(
    toolset_key: str | None,
) -> AuthoredToolsetRegistration | None:
    """
    Look up one authored toolset registration by key.

    Why this exists:
    - callers should not read the process-local registry dictionary directly

    How to use it:
    - pass the optional `toolset_key` from a ReAct-family definition

    Example:
    - `registration = get_authored_toolset_registration(toolset_key)`
    """

    if not isinstance(toolset_key, str) or not toolset_key.strip():
        return None
    return _AUTHORED_TOOLSET_REGISTRY.get(toolset_key.strip())


def get_authored_tool_spec(
    *,
    toolset_key: str | None,
    tool_ref: str,
) -> AuthoredToolSpec | None:
    """
    Return one Python-authored tool spec from a registered toolset.

    Why this exists:
    - runtime tool resolution needs authored tool metadata without pulling in
      the whole registration object

    How to use it:
    - pass the current `toolset_key` plus the exact `tool_ref`

    Example:
    - `spec = get_authored_tool_spec(toolset_key=toolset_key, tool_ref="policy.search")`
    """

    registration = get_authored_toolset_registration(toolset_key)
    if registration is None:
        return None
    return registration.tool_specs.get(tool_ref)


def build_authored_tool_handlers(
    *,
    definition: ReActAgentDefinition,
    toolset_key: str | None,
    binding: BoundRuntimeContext,
    settings: AgentSettings,
    ports: AuthoredToolRuntimePorts,
) -> dict[str, AuthoredToolHandler]:
    """
    Bind the runtime handlers for one authored Python toolset.

    Why this exists:
    - runtime bootstrap needs the actual callable handlers later, after the
      authored toolset was only remembered by `toolset_key`

    How to use it:
    - call during runtime bootstrap for ReAct-family definitions only

    Example:
    - `handlers = build_authored_tool_handlers(definition=definition, toolset_key=toolset_key, binding=binding, settings=settings, ports=ports)`
    """

    registration = get_authored_toolset_registration(toolset_key)
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
