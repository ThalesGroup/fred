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
Resolution of Fred tool sources to one shared v2 runtime-tool format.

Why this module exists:
- the thin layer that finally passes tools to `create_agent(...)` or
  `create_deep_agent(...)` should not need to know whether a tool came from a
  built-in Fred capability, a registered Python toolset, or a runtime provider
  such as MCP
- this module performs that earlier source-specific resolution once and returns
  one shared `FredRuntimeToolSpec` shape

How to use:
- `ReActRuntime` or `DeepAgentRuntime` creates `ReActRuntimeToolResolver(...)`
- `resolve_tools()` returns normalized runtime-tool specs
- `react_tool_binding.py` then only wraps those specs as LangChain tools

Example:
- `resolver = ReActRuntimeToolResolver(...); runtime_tools = resolver.resolve_tools()`
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from ..contracts.context import (
    ArtifactPublishRequest,
    BoundRuntimeContext,
    ResourceFetchRequest,
    ResourceScope,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from ..contracts.models import ToolRefRequirement
from ..contracts.runtime import RuntimeServices
from ..support.authored_toolsets import get_authored_tool_spec
from ..support.builtins import (
    BuiltinToolBackend,
    BuiltinToolSpec,
    get_builtin_tool_spec,
)
from .react_tool_rendering import (
    normalize_runtime_provider_artifact,
    render_tool_result,
    stringify_tool_output,
)
from .react_tool_utils import sanitize_tool_name

logger = logging.getLogger(__name__)

RuntimeToolInvoke = Callable[
    [dict[str, object]],
    Awaitable[tuple[str, ToolInvocationResult | None]],
]
RuntimeToolTraceAttrs = Callable[[dict[str, object]], Mapping[str, object]]


class ToolPayloadModel(BaseModel):
    """
    Fallback schema for declared tools without a specific JSON schema.

    Why this exists:
    - some transport-routed tools still only expose a generic JSON payload
    - the runtime resolver still needs one schema when no richer registered schema
      exists

    How to use:
    - use when resolving a declared tool that only accepts a generic JSON payload

    Example:
    - `args_schema = ToolPayloadModel`
    """

    payload: dict[str, object] = Field(
        default_factory=dict,
        description="JSON payload forwarded to the platform tool transport.",
    )


@dataclass(frozen=True, slots=True)
class FredRuntimeToolSpec:
    """
    One normalized Fred runtime tool before LangChain binding.

    Why this exists:
    - ReAct and Deep should not bind built-ins, registered tools, and provider
      tools through different final code paths
    - this spec captures the common shape all tool sources must reach first

    How to use:
    - source-specific adapter methods return this spec
    - `react_tool_binding.py` then turns it into the final `StructuredTool`

    Example:
    - `spec = resolver.resolve_tools()[0]`
    """

    runtime_name: str
    description: str
    args_schema: object
    tool_ref: str
    invoke: RuntimeToolInvoke
    trace_span_name: str = "tool.invoke"
    build_trace_attributes: RuntimeToolTraceAttrs = field(default=lambda payload: {})


class ReActRuntimeToolResolver:
    """
    Resolve ReAct/Deep tool sources to `FredRuntimeToolSpec`.

    Why this exists:
    - source-specific logic belongs before the thin LangChain binding layer
    - this keeps the final binder close to "take resolved tools, wrap them, pass
      them to `create_agent(...)` or `create_deep_agent(...)`"

    How to use:
    - instantiate with declared tool refs, optional toolset key, runtime services,
      and the bound runtime context
    - call `resolve_tools()`

    Example:
    - `resolver = ReActRuntimeToolResolver(...); specs = resolver.resolve_tools()`
    """

    def __init__(
        self,
        *,
        declared_tool_refs: tuple[ToolRefRequirement, ...],
        toolset_key: str | None,
        services: RuntimeServices,
        binding: BoundRuntimeContext,
    ) -> None:
        """
        Store the collaborators needed to resolve one runtime tool surface.

        Why this exists:
        - tool resolution needs declared refs, runtime ports, and the current bound
          execution context
        - constructor injection keeps resolution deterministic and testable

        How to use:
        - pass the validated declared refs plus the active runtime services

        Example:
        - `ReActRuntimeToolResolver(declared_tool_refs=refs, toolset_key=key, services=services, binding=binding)`
        """

        self._declared_tool_refs = declared_tool_refs
        self._toolset_key = toolset_key
        self._services = services
        self._binding = binding

    def resolve_tools(self) -> list[FredRuntimeToolSpec]:
        """
        Resolve declared and runtime-provider tools to normalized runtime specs.

        Why this exists:
        - the final binding layer should not care where tools came from
        - this function centralizes naming and source-specific resolution once

        How to use:
        - call during ReAct or Deep executor construction before LangChain binding

        Example:
        - `runtime_tools = resolver.resolve_tools()`
        """

        logger.debug(
            "[V2][TOOL_RESOLVER] start toolset_key=%r declared_tool_refs=%r",
            self._toolset_key,
            [r.tool_ref for r in self._declared_tool_refs],
        )
        specs: list[FredRuntimeToolSpec] = []
        used_names: set[str] = set()
        specs.extend(self._resolve_declared_tools(used_names=used_names))
        specs.extend(self._resolve_runtime_provider_tools(used_names=used_names))
        logger.debug(
            "[V2][TOOL_RESOLVER] resolved %d tool(s): %r",
            len(specs),
            [s.runtime_name for s in specs],
        )
        return specs

    def _resolve_declared_tools(
        self, *, used_names: set[str]
    ) -> list[FredRuntimeToolSpec]:
        """
        Resolve declared Fred tool refs to runtime-tool specs.

        Why this exists:
        - declared tools may come from built-ins, registered toolsets, or generic
          transport-routed refs
        - those cases should converge here before the final binding step

        How to use:
        - call from `resolve_tools()`

        Example:
        - `declared_specs = self._resolve_declared_tools(used_names=used_names)`
        """

        if not self._declared_tool_refs:
            return []

        specs: list[FredRuntimeToolSpec] = []
        for requirement in self._declared_tool_refs:
            registered_spec = get_authored_tool_spec(
                toolset_key=self._toolset_key,
                tool_ref=requirement.tool_ref,
            )
            tool_name = self._claim_runtime_name(
                tool_ref=requirement.tool_ref,
                registered_runtime_name=(
                    registered_spec.runtime_name
                    if registered_spec is not None
                    else None
                ),
                used_names=used_names,
            )

            builtin_spec = get_builtin_tool_spec(requirement.tool_ref)
            if builtin_spec is not None:
                specs.append(
                    self._resolve_builtin_tool(
                        requirement=requirement,
                        tool_name=tool_name,
                        description=(
                            requirement.description
                            or builtin_spec.default_description
                            or f"Platform-routed tool {requirement.tool_ref}."
                        ),
                        builtin_spec=builtin_spec,
                    )
                )
                continue

            if registered_spec is not None:
                specs.append(
                    self._resolve_transport_declared_tool(
                        requirement=requirement,
                        tool_name=tool_name,
                        description=(
                            requirement.description
                            or registered_spec.description
                            or f"Platform-routed tool {requirement.tool_ref}."
                        ),
                        args_schema=registered_spec.args_schema,
                    )
                )
                continue

            specs.append(
                self._resolve_transport_declared_tool(
                    requirement=requirement,
                    tool_name=tool_name,
                    description=(
                        requirement.description
                        or f"Platform-routed tool {requirement.tool_ref}."
                    ),
                    args_schema=ToolPayloadModel,
                )
            )
        return specs

    def _resolve_runtime_provider_tools(
        self, *, used_names: set[str]
    ) -> list[FredRuntimeToolSpec]:
        """
        Resolve runtime-provider tools such as MCP tools to runtime specs.

        Why this exists:
        - provider tools already exist as LangChain tools, but Fred still wants one
          stable tracing and result contract before binding

        How to use:
        - call from `resolve_tools()` after declared tools have claimed names

        Example:
        - `provider_specs = self._resolve_runtime_provider_tools(used_names=used_names)`
        """

        tool_provider = self._services.tool_provider
        if tool_provider is None:
            return []

        specs: list[FredRuntimeToolSpec] = []
        for raw_runtime_tool in tool_provider.get_tools():
            runtime_tool = cast(BaseTool, raw_runtime_tool)
            tool_name = runtime_tool.name.strip()
            if not tool_name:
                raise RuntimeError(
                    "Runtime-provided tool has an empty name. "
                    "Provider tools must expose a non-empty unique name."
                )
            if tool_name in used_names:
                raise RuntimeError(
                    f"Duplicate tool name {tool_name!r} detected across declared and runtime-provided tools. "
                    "Tool names must be unique in one ReAct runtime."
                )
            used_names.add(tool_name)
            description = runtime_tool.description.strip() or "No description provided."
            specs.append(
                self._resolve_runtime_provider_tool(
                    runtime_tool=runtime_tool,
                    tool_name=tool_name,
                    description=description,
                )
            )
        return specs

    def _resolve_builtin_tool(
        self,
        *,
        requirement: ToolRefRequirement,
        tool_name: str,
        description: str,
        builtin_spec: BuiltinToolSpec,
    ) -> FredRuntimeToolSpec:
        """
        Resolve one built-in Fred tool to the shared runtime-tool spec.

        Why this exists:
        - built-ins still use a few distinct Fred ports internally
        - that source-specific port logic belongs here, not in the final LangChain
          binding layer

        How to use:
        - call while resolving declared built-ins

        Example:
        - `spec = self._resolve_builtin_tool(...)`
        """

        backend = builtin_spec.backend
        if backend == BuiltinToolBackend.TOOL_INVOKER:
            return self._resolve_transport_declared_tool(
                requirement=requirement,
                tool_name=tool_name,
                description=description,
                args_schema=builtin_spec.args_schema,
            )

        if backend == BuiltinToolBackend.ARTIFACT_PUBLISHER:
            artifact_publisher = self._services.artifact_publisher
            if artifact_publisher is None:
                raise RuntimeError(
                    "ReActRuntime requires RuntimeServices.artifact_publisher for artifacts.publish_text."
                )

            async def _invoke(
                payload: dict[str, object],
            ) -> tuple[str, ToolInvocationResult]:
                file_name = str(payload["file_name"])
                artifact = await artifact_publisher.publish(
                    ArtifactPublishRequest(
                        file_name=file_name,
                        content_bytes=str(payload["content"]).encode("utf-8"),
                        key=self._optional_str(payload.get("key")),
                        content_type=str(
                            payload.get("content_type") or "text/plain; charset=utf-8"
                        ),
                        title=self._optional_str(payload.get("title")),
                    )
                )
                result = ToolInvocationResult(
                    tool_ref=requirement.tool_ref,
                    blocks=(
                        ToolContentBlock(
                            kind=ToolContentKind.TEXT,
                            text=f"Published {artifact.file_name} for the user.",
                        ),
                    ),
                    ui_parts=(artifact.to_link_part(),),
                )
                return (render_tool_result(result), result)

            return FredRuntimeToolSpec(
                runtime_name=tool_name,
                description=description,
                args_schema=builtin_spec.args_schema,
                tool_ref=requirement.tool_ref,
                invoke=_invoke,
                trace_span_name="artifact.publish",
                build_trace_attributes=lambda payload: {
                    "artifact_file_name": str(payload.get("file_name") or ""),
                },
            )

        if backend == BuiltinToolBackend.RESOURCE_READER:
            resource_reader = self._services.resource_reader
            if resource_reader is None:
                raise RuntimeError(
                    "ReActRuntime requires RuntimeServices.resource_reader for resources.fetch_text."
                )

            async def _invoke(
                payload: dict[str, object],
            ) -> tuple[str, ToolInvocationResult]:
                scope = self._resource_scope_from_payload(payload.get("scope"))
                resource = await resource_reader.fetch(
                    ResourceFetchRequest(
                        key=str(payload["key"]),
                        scope=scope,
                        target_user_id=self._optional_str(
                            payload.get("target_user_id")
                        ),
                    )
                )
                result = ToolInvocationResult(
                    tool_ref=requirement.tool_ref,
                    blocks=(
                        ToolContentBlock(
                            kind=ToolContentKind.TEXT,
                            text=resource.as_text(),
                        ),
                    ),
                )
                return (render_tool_result(result), result)

            return FredRuntimeToolSpec(
                runtime_name=tool_name,
                description=description,
                args_schema=builtin_spec.args_schema,
                tool_ref=requirement.tool_ref,
                invoke=_invoke,
                trace_span_name="resource.fetch",
                build_trace_attributes=lambda payload: {
                    "resource_key": str(payload.get("key") or ""),
                    "resource_scope": self._resource_scope_from_payload(
                        payload.get("scope")
                    ).value,
                },
            )

        raise RuntimeError(
            f"Unsupported built-in tool backend {backend!r} for {requirement.tool_ref}."
        )

    def _resolve_transport_declared_tool(
        self,
        *,
        requirement: ToolRefRequirement,
        tool_name: str,
        description: str,
        args_schema: object,
    ) -> FredRuntimeToolSpec:
        """
        Resolve one declared tool that executes through `ToolInvokerPort`.

        Why this exists:
        - built-in invoker tools, registered Python tools, and generic fallback
          declared tools all share the same execution port
        - keeping that shared path here avoids repeating it in the final binder

        How to use:
        - call whenever a declared tool ultimately routes through `ToolInvokerPort`

        Example:
        - `spec = self._resolve_transport_declared_tool(...)`
        """

        tool_invoker = self._require_tool_invoker(tool_ref=requirement.tool_ref)

        async def _invoke(
            payload: dict[str, object],
        ) -> tuple[str, ToolInvocationResult]:
            result = await tool_invoker.invoke(
                ToolInvocationRequest(
                    tool_ref=requirement.tool_ref,
                    payload=payload,
                    context=self._binding.portable_context,
                )
            )
            return (render_tool_result(result), result)

        return FredRuntimeToolSpec(
            runtime_name=tool_name,
            description=description,
            args_schema=args_schema,
            tool_ref=requirement.tool_ref,
            invoke=_invoke,
        )

    def _resolve_runtime_provider_tool(
        self,
        *,
        runtime_tool: BaseTool,
        tool_name: str,
        description: str,
    ) -> FredRuntimeToolSpec:
        """
        Resolve one runtime-provider tool such as MCP to the shared runtime format.

        Why this exists:
        - provider tools already exist as callable LangChain tools
        - Fred still wants them normalized to the same result/tracing contract as
          declared tools before the final binding step

        How to use:
        - call while resolving runtime-provider tools

        Example:
        - `spec = self._resolve_runtime_provider_tool(...)`
        """

        async def _invoke(
            payload: dict[str, object],
        ) -> tuple[str, ToolInvocationResult | None]:
            raw_result = await runtime_tool.ainvoke(payload)
            if isinstance(raw_result, ToolInvocationResult):
                return (render_tool_result(raw_result), raw_result)
            if isinstance(raw_result, tuple) and len(raw_result) == 2:
                artifact = normalize_runtime_provider_artifact(raw_result[1])
                rendered_content = stringify_tool_output(raw_result[0]).strip()
                if rendered_content:
                    return (rendered_content, artifact)
                if artifact is not None:
                    return (render_tool_result(artifact), artifact)
                return (stringify_tool_output(raw_result[0]), None)
            return (stringify_tool_output(raw_result), None)

        return FredRuntimeToolSpec(
            runtime_name=tool_name,
            description=description,
            args_schema=getattr(runtime_tool, "args_schema", None),
            tool_ref=tool_name,
            invoke=_invoke,
            trace_span_name="v2.react.runtime_tool",
        )

    def _claim_runtime_name(
        self,
        *,
        tool_ref: str,
        registered_runtime_name: str | None,
        used_names: set[str],
    ) -> str:
        """
        Reserve one unique LangChain-safe tool name for a runtime tool.

        Why this exists:
        - LangChain tool names must be unique inside one execution
        - Fred tool refs can collide after sanitization or registry overrides

        How to use:
        - call before adding one resolved tool to the runtime list

        Example:
        - `tool_name = self._claim_runtime_name(tool_ref="knowledge.search", ...)`
        """

        base_name = sanitize_tool_name(tool_ref)
        if isinstance(registered_runtime_name, str) and registered_runtime_name.strip():
            base_name = sanitize_tool_name(registered_runtime_name)

        tool_name = base_name
        suffix = 2
        while tool_name in used_names:
            tool_name = f"{base_name}_{suffix}"
            suffix += 1
        used_names.add(tool_name)
        return tool_name

    def _require_tool_invoker(self, *, tool_ref: str):
        """
        Return the Fred transport tool invoker or raise one clear runtime error.

        Why this exists:
        - several declared-tool sources depend on the same transport port
        - one helper keeps the missing-port error consistent

        How to use:
        - call before resolving a transport-routed tool

        Example:
        - `tool_invoker = self._require_tool_invoker(tool_ref=requirement.tool_ref)`
        """

        tool_invoker = self._services.tool_invoker
        if tool_invoker is None:
            raise RuntimeError(
                f"ReActRuntime requires RuntimeServices.tool_invoker for {tool_ref}."
            )
        return tool_invoker

    @staticmethod
    def _optional_str(value: object) -> str | None:
        """
        Normalize one optional payload value to `str | None`.

        Why this exists:
        - some built-in tool adapters accept optional string fields
        - they should share one tiny conversion helper instead of repeating it

        How to use:
        - call when reading optional string values from normalized payloads

        Example:
        - `title = self._optional_str(payload.get("title"))`
        """

        if value is None:
            return None
        return str(value)

    @staticmethod
    def _resource_scope_from_payload(value: object) -> ResourceScope:
        """
        Convert one payload value to `ResourceScope`.

        Why this exists:
        - resource tools may receive either the enum or its raw string value
        - one helper keeps that validation local to resource resolution

        How to use:
        - call when adapting payloads for `resources.fetch_text`

        Example:
        - `scope = self._resource_scope_from_payload(payload.get("scope"))`
        """

        if isinstance(value, ResourceScope):
            return value
        if isinstance(value, str):
            return ResourceScope(value)
        raise RuntimeError("resources.fetch_text received an invalid scope.")
