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
Reusable FastAPI app factory for Fred agent pods.

Why this module exists:
- every agent pod (rags-v2, future pods) needs identical execution plumbing:
  RuntimeConfig wiring, BoundRuntimeContext construction, ReActRuntime lifecycle,
  and `POST /agents/execute` / `POST /agents/execute/stream` endpoints
- duplicating that across pods causes divergence bugs and maintenance overhead

How to use it:
- call `create_agent_app(registry, config)` in your pod's `main.py`
- the returned FastAPI app already exposes:
    POST {config.app.base_url}/agents/execute                           — terminal RuntimeEvent JSON
    POST {config.app.base_url}/agents/execute/stream                    — stream RuntimeEvent JSON over SSE
    GET  {config.app.base_url}/agents                                   — list registered agent IDs
    GET  {config.app.base_url}/agents/sessions                          — list session IDs for a user (history store)
    GET  {config.app.base_url}/agents/sessions/{session_id}/messages    — conversation history (history store)
- pass `extra_routers` to mount additional domain-specific routers under `config.app.base_url`

Example:
    from fred_runtime.app import create_agent_app, load_agent_pod_config
    from myapp.agents.registry import REGISTRY

    config = load_agent_pod_config()
    app = create_agent_app(registry=REGISTRY, config=config)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fred_core.logs.log_setup import log_setup
from fred_core.logs.memory_log_store import RamLogStore
from fred_core.security.oidc import get_keycloak_client_id, get_keycloak_url
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    AgentInvocationResult,
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    AgentTuning,
    ExecutionCategory,
    GraphAgentDefinition,
    MCPServerConfiguration,
    ReActAgentDefinition,
)
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    AgentInvokerPort,
    ExecutionConfig,
    RuntimeServices,
)
from fred_sdk.graph.graph_runtime import GraphRuntime
from fred_sdk.react.react_runtime import ReActRuntime
from fred_sdk.support.authored_toolsets import (
    AuthoredToolRuntimePorts,
    build_authored_tool_handlers,
)
from pydantic import BaseModel, Field, model_validator

from fred_runtime.common.kf_markdown_media_client import KfMarkdownMediaClient

from ..common.structures import AgentSettingsLike
from ..integrations.v2_runtime.adapters import (
    CompositeToolInvoker,
    FredArtifactPublisher,
    FredKnowledgeSearchToolInvoker,
    FredMcpToolProvider,
    FredResourceReader,
    build_default_tracer,
)
from ..runtime_context import (
    RuntimeConfig,
    get_runtime_context,
    set_runtime_context,
)
from ..runtime_context import RuntimeContext as FredRuntimeContext
from ..runtime_support import refresh_user_access_token_from_keycloak
from .config import AgentPodConfig
from .observability_factory import bootstrap_observability

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checkpoint admin response models
# ---------------------------------------------------------------------------


class _CheckpointThreadSummary(BaseModel):
    """One row in the checkpoint thread listing."""

    thread_id: str
    checkpoint_count: int
    latest_created_at: str | None


class _CheckpointEntry(BaseModel):
    """Lightweight view of a single checkpoint row (no deserialized blobs)."""

    checkpoint_id: str
    parent_checkpoint_id: str | None
    created_at: str | None
    metadata: dict[str, Any]


class _CheckpointThreadDetail(BaseModel):
    """All checkpoints for one thread, newest first."""

    thread_id: str
    checkpoints: list[_CheckpointEntry]


class _CheckpointStorageStats(BaseModel):
    """Aggregate storage counts across all three checkpointer tables."""

    thread_count: int
    checkpoint_count: int
    blob_count: int
    pending_write_count: int
    checkpoint_bytes_approx: int
    blob_bytes_approx: int


# ---------------------------------------------------------------------------
# Chat model factory builder
# ---------------------------------------------------------------------------


def _build_chat_model_factory(config: AgentPodConfig) -> Any:
    """
    Build a ChatModelFactoryPort for the configured model backend.

    Resolution:
    - the resolved mandatory `models_catalog.yaml` path is attached during
      `load_agent_pod_config()`
    - this function loads it and builds a `RoutedChatModelFactory` backed by
      `ModelRoutingResolver`
    - rules in the catalog are evaluated per-request against the real
      `BoundRuntimeContext` (agent_id, team_id, user_id)

    Why this returns a ChatModelFactoryPort (not a zero-arg callable):
    - `RoutedChatModelFactory.build(definition, binding)` receives the full
      runtime context per invocation, enabling per-request rule evaluation.
    """
    from ..model_routing import (
        ModelRoutingResolver,
        RoutedChatModelFactory,
        load_model_catalog,
    )

    catalog_path = config.get_models_catalog_path()
    if not catalog_path:
        raise RuntimeError(
            "AgentPodConfig is missing the resolved models catalog path. "
            "Use load_agent_pod_config() for pod startup."
        )

    catalog = load_model_catalog(catalog_path)
    policy = catalog.to_policy()
    logger.info(
        "[fred-runtime] model routing from catalog=%s profiles=%d rules=%d",
        catalog_path,
        len(policy.profiles),
        len(policy.rules),
    )
    return RoutedChatModelFactory(resolver=ModelRoutingResolver(policy))


@dataclass(slots=True)
class _PodAgentSettings:
    """
    Minimal settings object expected by fred-runtime adapter ports.

    Why this exists:
    - the reusable pod app executes raw `ReActAgentDefinition` objects, not the
      richer settings model assembled inside agentic-backend
    - runtime adapters still need a small identity/tuning object so authored
      tools, Fred built-ins, and MCP defaults behave the same way in pods

    How to use it:
    - build one from the current agent definition for each request
    - pass it to the fred-runtime adapter constructors

    Example:
    - `settings = _build_agent_settings(definition)`
    """

    id: str
    name: str
    team_id: str | None
    tuning: AgentTuning | None


class _MediaClientAgentAdapter:
    """
    Small bridge exposing token refresh to the markdown media client.

    Why this exists:
    - authored tools may call `ctx.fetch_media(...)`
    - `KfMarkdownMediaClient` expects an agent-like object with runtime context,
      settings, and a token-refresh hook

    How to use it:
    - instantiate only from `_build_media_fetcher(...)`

    Example:
    - `adapter = _MediaClientAgentAdapter(binding=binding, settings=settings)`
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: _PodAgentSettings
    ) -> None:
        self.runtime_context = binding.runtime_context
        self.agent_settings: AgentSettingsLike = settings

    def refresh_user_access_token(self) -> str:
        """
        Refresh the user access token for media downloads.

        Why this exists:
        - media fetch retries need the same Keycloak refresh path as other
          runtime adapters

        How to use it:
        - called by `KfMarkdownMediaClient` when the current token is expired

        Example:
        - `token = adapter.refresh_user_access_token()`
        """

        refresh_token = self.runtime_context.refresh_token
        if not refresh_token:
            raise RuntimeError(
                "Cannot refresh user access token: refresh_token missing from runtime context."
            )

        keycloak_url = get_keycloak_url()
        client_id = get_keycloak_client_id()
        if not keycloak_url:
            raise RuntimeError(
                "User security realm_url is not configured for Keycloak."
            )
        if not client_id:
            raise RuntimeError(
                "User security client_id is not configured for Keycloak."
            )

        payload = refresh_user_access_token_from_keycloak(
            keycloak_url=keycloak_url,
            client_id=client_id,
            refresh_token=refresh_token,
        )
        new_access_token = payload.get("access_token")
        new_refresh_token = payload.get("refresh_token") or refresh_token
        if not isinstance(new_access_token, str) or not new_access_token:
            raise RuntimeError(
                "Keycloak refresh response did not include a valid access_token."
            )

        self.runtime_context.access_token = new_access_token
        self.runtime_context.refresh_token = new_refresh_token
        return new_access_token


def _definition_to_agent_tuning(
    definition: ReActAgentDefinition | GraphAgentDefinition,
) -> AgentTuning:
    """
    Project one ReAct definition into the public runtime tuning shape.

    Why this exists:
    - pod metadata endpoints and managed-instance execution both need the same
      "default tuning" view of a registered template without importing
      agentic-backend catalog helpers

    How to use it:
    - call for template metadata responses or when building adapter settings

    Example:
    - `tuning = _definition_to_agent_tuning(definition)`
    """

    return AgentTuning(
        role=definition.role,
        description=definition.description,
        tags=list(definition.tags),
        fields=list(definition.fields),
        mcp_servers=list(definition.default_mcp_servers),
    )


def _build_agent_settings(
    definition: ReActAgentDefinition | GraphAgentDefinition,
    *,
    team_id: str | None = None,
) -> _PodAgentSettings:
    """
    Derive the minimal runtime settings object for one pod-hosted agent.

    Why this exists:
    - fred-runtime adapter ports operate on a small settings contract rather
      than raw definitions
    - pod execution should still honor default MCP servers and agent identity
      the same way the backend bootstrap does

    How to use it:
    - call once per request before constructing runtime adapter ports

    Example:
    - `settings = _build_agent_settings(definition)`
    """

    return _PodAgentSettings(
        id=definition.agent_id,
        name=definition.agent_id,
        team_id=team_id,
        tuning=_definition_to_agent_tuning(definition),
    )


def _build_media_fetcher(*, binding: BoundRuntimeContext, settings: _PodAgentSettings):
    """
    Build the media-fetcher port exposed to Python-authored tool handlers.

    Why this exists:
    - authored tools can fetch packaged markdown media through `ctx.fetch_media`
    - the SDK expects a small async callable, not a concrete fred-runtime client

    How to use it:
    - pass the current binding and agent settings while assembling authored-tool
      runtime ports

    Example:
    - `media_fetcher = _build_media_fetcher(binding=binding, settings=settings)`
    """

    adapter = _MediaClientAgentAdapter(binding=binding, settings=settings)
    client: KfMarkdownMediaClient | None = None

    async def _fetch_media(document_uid: str, file_name: str) -> bytes:
        """
        Fetch one packaged media asset lazily through Knowledge Flow.

        Why this exists:
        - media support should be available to authored tools without incurring
          client setup cost when no tool uses it

        How to use it:
        - invoked by the authored-tool runtime when a tool calls
          `ctx.fetch_media(...)`

        Example:
        - `payload = await media_fetcher("doc-123", "image.png")`
        """

        nonlocal client
        if client is None:
            client = KfMarkdownMediaClient(agent=adapter)
        return await client.fetch_media(document_uid, file_name)

    return _fetch_media


class LocalRegistryAgentInvoker(AgentInvokerPort):
    """
    In-process AgentInvokerPort for pod-local agent execution.

    Why this exists:
    - TeamAgent nodes call context.invoke_agent(...) to dispatch sub-agents
    - when all agents are co-located in the same pod there is no need for HTTP
    - this invoker runs the sub-agent through the same runtime stack, sharing
      the caller's access token and registry

    How to use it:
    - injected automatically by _build_runtime_services when a registry is present
    - no configuration required from agent authors
    """

    def __init__(
        self,
        registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
        access_token: str | None,
    ) -> None:
        self._registry = registry
        self._access_token = access_token

    async def invoke(self, request: AgentInvocationRequest) -> AgentInvocationResult:
        definition = self._registry.get(request.agent_id)
        if definition is None:
            return AgentInvocationResult(
                agent_id=request.agent_id,
                content=f"Agent '{request.agent_id}' is not registered in this pod.",
                is_error=True,
            )

        execute_request = _AgentExecuteRequest.model_construct(
            agent_id=request.agent_id,
            agent_instance_id=None,
            message=request.message,
            context=request.context.model_dump(mode="json"),
            resume_payload=None,
        )

        content_parts: list[str] = []
        async for payload in _iterate_runtime_event_payloads(
            definition,
            execute_request,
            access_token=self._access_token,
            team_id=request.context.team_id,
            registry=self._registry,
        ):
            kind = payload.get("kind")
            if kind == "final":
                return AgentInvocationResult(
                    agent_id=request.agent_id,
                    content=payload.get("content", ""),
                    is_error=False,
                )
            if kind == "assistant_delta":
                content_parts.append(payload.get("delta", ""))
            elif kind == "node_error":
                return AgentInvocationResult(
                    agent_id=request.agent_id,
                    content=payload.get("error_message", "Unknown error"),
                    is_error=True,
                )

        return AgentInvocationResult(
            agent_id=request.agent_id,
            content="".join(content_parts),
            is_error=not content_parts,
        )


def _build_runtime_services(
    definition: ReActAgentDefinition | GraphAgentDefinition,
    binding: BoundRuntimeContext,
    *,
    team_id: str | None = None,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition] | None = None,
    access_token: str | None = None,
) -> RuntimeServices:
    """
    Assemble the full `RuntimeServices` bundle for one pod request.

    Why this exists:
    - authored local tools, Fred built-ins, MCP tools, resource reads, and
      artifact publication now all share one runtime contract in `fred-sdk`
    - the reusable pod app must mirror the same binding-aware service assembly
      already used by agentic-backend, or declared tools fail at runtime

    How to use it:
    - call from `_stream(...)` after the request binding is constructed
    - create a fresh service bundle per request so binding-scoped adapters stay
      aligned with the current session/user/token context
    - pass `registry` and `access_token` to enable in-process agent-to-agent calls
      (required for TeamAgent mode="route")

    Example:
    - `services = _build_runtime_services(definition, binding, registry=registry, access_token=token)`
    """

    runtime_config = get_runtime_context().config
    settings = _build_agent_settings(definition, team_id=team_id)
    base_tool_invoker = FredKnowledgeSearchToolInvoker(
        binding=binding,
        settings=settings,
    )
    tool_provider = FredMcpToolProvider(
        binding=binding,
        settings=settings,
    )
    artifact_publisher = FredArtifactPublisher(
        binding=binding,
        settings=settings,
    )
    resource_reader = FredResourceReader(
        binding=binding,
        settings=settings,
    )
    handlers = (
        build_authored_tool_handlers(
            definition=definition,  # type: ignore[arg-type]
            toolset_key=getattr(definition, "toolset_key", None),
            binding=binding,
            settings=settings,
            ports=AuthoredToolRuntimePorts(
                chat_model_factory=runtime_config.chat_model_factory,
                artifact_publisher=artifact_publisher,
                resource_reader=resource_reader,
                fallback_tool_invoker=base_tool_invoker,
                media_fetcher=_build_media_fetcher(binding=binding, settings=settings),
            ),
        )
        if isinstance(definition, ReActAgentDefinition)
        else {}
    )
    tool_invoker = (
        CompositeToolInvoker(
            handlers=handlers,
            fallback=base_tool_invoker,
        )
        if handlers
        else base_tool_invoker
    )
    agent_invoker = (
        LocalRegistryAgentInvoker(
            registry=registry,
            access_token=access_token,
        )
        if registry is not None
        else None
    )
    return RuntimeServices(
        tracer=build_default_tracer(),
        chat_model_factory=runtime_config.chat_model_factory,
        tool_invoker=tool_invoker,
        tool_provider=tool_provider,
        artifact_publisher=artifact_publisher,
        resource_reader=resource_reader,
        checkpointer=runtime_config.checkpointer,
        agent_invoker=agent_invoker,
    )


def _normalize_base_url(base_url: str) -> str:
    """
    Normalize the configured FastAPI base URL for router and docs mounting.

    Why this exists:
    - pod apps should honor `config.app.base_url` consistently
    - normalization avoids accidental double slashes from empty or trailing-slash
      values

    How to use it:
    - call once inside `create_agent_app(...)`

    Example:
    - `_normalize_base_url("/rags/v1/") == "/rags/v1"`
    """

    cleaned = base_url.strip()
    if not cleaned or cleaned == "/":
        return ""
    return f"/{cleaned.strip('/')}"


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------


class _AgentExecuteRequest(BaseModel):
    """
    Input payload for the agent execution endpoints.

    Normal turn:
    ```json
    {"agent_id": "sentinel.react.v2", "message": "hello", "context": {"session_id": "..."}}
    ```

    HITL resume (message may be empty — graph resumes from the checkpointed interrupt):
    ```json
    {"agent_id": "sentinel.react.v2", "message": "", "context": {"session_id": "..."},
     "resume_payload": {"approved": true, "exchange_id": "..."}}
    ```
    """

    agent_id: str | None = Field(default=None, min_length=1)
    agent_instance_id: str | None = Field(default=None, min_length=1)
    message: str = Field(default="")
    context: dict[str, Any] | None = None
    resume_payload: Any | None = Field(
        default=None,
        description=(
            "HITL resume data returned by the caller after an AwaitingHumanRuntimeEvent. "
            "When set, the graph is resumed from its checkpointed interrupt state using "
            "LangGraph Command(resume=...) — the message field is ignored."
        ),
    )

    @model_validator(mode="after")
    def _require_message_or_resume(self) -> "_AgentExecuteRequest":
        """
        Validate the execution target and turn shape for one request.

        Why this exists:
        - the pod now supports both direct template execution (`agent_id`) and
          managed instance execution (`agent_instance_id`), but exactly one
          target must be provided

        How to use it:
        - validation runs automatically when FastAPI parses the request body

        Example:
        - `{"agent_instance_id": "uuid", "message": "hello"}`
        """

        if bool(self.agent_id) == bool(self.agent_instance_id):
            raise ValueError("Provide exactly one of agent_id or agent_instance_id")
        if self.resume_payload is None and not self.message.strip():
            raise ValueError("message is required when resume_payload is not set")
        return self


class _AgentTemplateSummary(BaseModel):
    template_agent_id: str
    title: str
    description: str
    kind: ExecutionCategory
    default_tuning: AgentTuning
    available_mcp_servers: list[MCPServerConfiguration] = Field(default_factory=list)


class _ResolvedAgentInstance(BaseModel):
    agent_instance_id: str
    template_agent_id: str
    owner_scope: str
    owner_user_id: str | None = None
    owner_team_id: str | None = None
    enabled: bool = True
    tuning: AgentTuning


@dataclass(slots=True)
class _ResolvedExecutionTarget:
    definition: ReActAgentDefinition | GraphAgentDefinition
    effective_agent_id: str
    team_id: str | None = None


def _apply_runtime_tuning(
    definition: ReActAgentDefinition | GraphAgentDefinition, tuning: AgentTuning
) -> ReActAgentDefinition | GraphAgentDefinition:
    """
    Overlay persisted business tuning onto one registered ReAct template.

    Why this exists:
    - control-plane stores the full effective tuning for a managed agent
      instance, and the pod must execute that tuning without depending on the
      old agentic-backend definition factory

    How to use it:
    - call after resolving an `agent_instance_id` from control-plane

    Example:
    - `definition = _apply_runtime_tuning(template_definition, resolution.tuning)`
    """

    return definition.model_copy(
        update={
            "role": tuning.role,
            "description": tuning.description,
            "tags": tuple(tuning.tags),
            "fields": tuple(field.model_copy(deep=True) for field in tuning.fields),
            "default_mcp_servers": tuple(
                server.model_copy(deep=True) for server in tuning.mcp_servers
            ),
        }
    )


def _available_mcp_servers_for_definition(
    definition: ReActAgentDefinition | GraphAgentDefinition,
) -> list[MCPServerConfiguration]:
    """
    Resolve the concrete MCP catalog entries referenced by one agent template.

    Why this exists:
    - the frontend create/edit flow needs user-facing MCP names and
      descriptions, not just logical server ids, when showing the tunable tool
      surface of a registered template

    How to use it:
    - call while building `/agents/templates` responses

    Example:
    - `servers = _available_mcp_servers_for_definition(definition)`
    """

    mcp_configuration = get_runtime_context().config.mcp_configuration
    if mcp_configuration is None:
        return []
    resolved: list[MCPServerConfiguration] = []
    for server_ref in definition.default_mcp_servers:
        server = mcp_configuration.get_server(server_ref.id)
        if server is not None:
            resolved.append(server)
    return resolved


async def _resolve_agent_instance(
    *,
    request: _AgentExecuteRequest,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    access_token: str | None,
    control_plane_url: str | None,
) -> _ResolvedExecutionTarget:
    """
    Resolve a direct or managed execution target into a concrete definition.

    Why this exists:
    - `/agents/execute*` now supports both raw template execution and managed
      agent instances stored in control-plane, while the lower runtime path
      still wants one concrete `ReActAgentDefinition`

    How to use it:
    - call from execute routes before invoking the runtime

    Example:
    - `target = await _resolve_agent_instance(...)`
    """

    if request.agent_id is not None:
        definition = registry.get(request.agent_id)
        if definition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown agent_id: {request.agent_id!r}. "
                f"Known agents: {list(registry.keys())}",
            )
        return _ResolvedExecutionTarget(
            definition=definition,
            effective_agent_id=definition.agent_id,
        )

    if control_plane_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Managed agent instances require platform.control_plane_url in the pod configuration."
            ),
        )

    url = (
        f"{control_plane_url.rstrip('/')}/agent-instances/"
        f"{request.agent_instance_id}/runtime"
    )
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=404, detail=response.text or "Unknown agent instance."
        )
    if response.status_code == status.HTTP_403_FORBIDDEN:
        raise HTTPException(status_code=403, detail=response.text or "Forbidden.")
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Failed to resolve agent instance '{request.agent_instance_id}' through control-plane: "
                f"{response.text or response.reason_phrase}"
            ),
        )

    resolution = _ResolvedAgentInstance.model_validate(response.json())
    definition = registry.get(resolution.template_agent_id)
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Resolved template_agent_id '{resolution.template_agent_id}' is not registered in this pod."
            ),
        )
    return _ResolvedExecutionTarget(
        definition=_apply_runtime_tuning(definition, resolution.tuning),
        effective_agent_id=resolution.agent_instance_id,
        team_id=resolution.owner_team_id,
    )


async def _write_turn_history(
    *,
    session_id: str,
    user_id: str,
    request_message: str | None,
    payloads: list[dict[str, Any]],
    history_store: Any,
) -> None:
    """
    Persist one agent turn to the history store.

    Why this helper exists:
    - both ``/agents/execute`` and ``/agents/execute/stream`` produce the same
      sequence of runtime-event payloads; this function maps those payloads to
      ``ChatMessage`` rows and writes them in one batch

    Why this is a separate async function and not inline:
    - the streaming endpoint calls it with ``asyncio.ensure_future`` so the DB
      write does not block the SSE response to the client
    - the non-streaming endpoint can ``await`` it directly before returning

    How to use it:
    - call after the executor generator is exhausted
    - ``payloads`` is the list of ``dict`` produced by ``_iterate_runtime_event_payloads``
    - silently no-ops when ``session_id`` or ``history_store`` is absent

    Event-to-message mapping:
    - ``tool_call`` → ``Role.assistant / Channel.tool_call``
    - ``tool_result`` → ``Role.tool / Channel.tool_result``
    - ``awaiting_human`` → ``Role.system / Channel.system_note``
    - ``node_error`` → ``Role.system / Channel.error``
    - ``final`` → ``Role.assistant / Channel.final`` (terminal answer)
    - user request → ``Role.user / Channel.final`` (prepended)
    """
    from fred_core.history.history_schema import (
        Channel,
        ChatMessage,
        ChatTokenUsage,
        Role,
        TextPart,
        make_assistant_final,
        make_tool_call,
        make_tool_result,
        make_user_text,
    )

    try:
        base_rank: int = await history_store.next_rank(session_id)
    except Exception:
        logger.exception(
            "[fred-runtime][history] Failed to query next_rank session_id=%s",
            session_id,
        )
        return

    exchange_id = str(uuid4())
    messages: list[ChatMessage] = []
    rank = base_rank

    # 1. User message — prepended before any agent events
    if request_message:
        messages.append(make_user_text(session_id, exchange_id, rank, request_message))
        rank += 1

    # 2. Map runtime events to messages
    final_content = ""
    final_token_usage: ChatTokenUsage | None = None
    final_model: str | None = None
    final_finish_reason: str | None = None

    for payload in payloads:
        kind = payload.get("kind")

        if kind == "tool_call":
            messages.append(
                make_tool_call(
                    session_id,
                    exchange_id,
                    rank,
                    call_id=payload["call_id"],
                    name=payload["tool_name"],
                    args=payload.get("arguments", {}),
                )
            )
            rank += 1

        elif kind == "tool_result":
            messages.append(
                make_tool_result(
                    session_id,
                    exchange_id,
                    rank,
                    call_id=payload["call_id"],
                    content=payload.get("content", ""),
                    ok=not payload.get("is_error", False),
                )
            )
            rank += 1

        elif kind == "awaiting_human":
            req = payload.get("request", {})
            question = req.get("question") or req.get("title") or "HITL pause"
            messages.append(
                ChatMessage(
                    session_id=session_id,
                    exchange_id=exchange_id,
                    rank=rank,
                    timestamp=datetime.utcnow(),
                    role=Role.system,
                    channel=Channel.system_note,
                    parts=[TextPart(text=question)],
                )
            )
            rank += 1

        elif kind == "node_error":
            messages.append(
                ChatMessage(
                    session_id=session_id,
                    exchange_id=exchange_id,
                    rank=rank,
                    timestamp=datetime.utcnow(),
                    role=Role.system,
                    channel=Channel.error,
                    parts=[TextPart(text=payload.get("error_message", "node error"))],
                )
            )
            rank += 1

        elif kind == "final":
            final_content = payload.get("content", "")
            tu = payload.get("token_usage")
            if tu:
                final_token_usage = ChatTokenUsage(
                    input_tokens=tu.get("input_tokens", 0),
                    output_tokens=tu.get("output_tokens", 0),
                    total_tokens=tu.get("total_tokens", 0),
                )
            final_model = payload.get("model_name")
            final_finish_reason = payload.get("finish_reason")

    # 3. Terminal assistant message (from FinalRuntimeEvent)
    if final_content or final_model:
        messages.append(
            make_assistant_final(
                session_id,
                exchange_id,
                rank,
                text=final_content,
                model=final_model,
                usage=final_token_usage,
                finish_reason=final_finish_reason,
            )
        )

    if not messages:
        return

    try:
        await history_store.save(
            session_id=session_id,
            messages=messages,
            user_id=user_id,
        )
    except Exception:
        logger.exception(
            "[fred-runtime][history] Failed to write turn history session_id=%s",
            session_id,
        )


def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


async def _stream(
    definition: ReActAgentDefinition | GraphAgentDefinition,
    request: _AgentExecuteRequest,
    access_token: str | None = None,
    *,
    team_id: str | None = None,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition] | None = None,
) -> AsyncIterator[str]:
    """
    Execute one agent turn and yield SSE-framed RuntimeEvent JSON.

    Why this helper exists:
    - keeps the streaming FastAPI endpoint thin
    - shares the same runtime-event production path as `/agents/execute`

    History write:
    - events are collected while yielding
    - after the stream closes, history is written as a fire-and-forget background
      task so the SSE connection is not held open waiting for the DB write
    """
    ctx = request.context or {}
    session_id: str | None = ctx.get("session_id")
    user_id: str = ctx.get("user_id") or "unknown"

    collected: list[dict[str, Any]] = []
    async for payload in _iterate_runtime_event_payloads(
        definition,
        request,
        access_token=access_token,
        team_id=team_id,
        registry=registry,
    ):
        collected.append(payload)
        yield _sse(json.dumps(payload, ensure_ascii=False))

    # Fire-and-forget: write history after the SSE stream is fully sent.
    # The client already received all events before this task begins.
    if session_id:
        history_store = get_runtime_context().config.history_store
        if history_store is not None:
            asyncio.ensure_future(
                _write_turn_history(
                    session_id=session_id,
                    user_id=user_id,
                    request_message=request.message,
                    payloads=collected,
                    history_store=history_store,
                )
            )


async def _iterate_runtime_event_payloads(
    definition: ReActAgentDefinition | GraphAgentDefinition,
    request: _AgentExecuteRequest,
    access_token: str | None = None,
    *,
    team_id: str | None = None,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Execute one agent turn and yield runtime-event payloads as JSON-ready dicts.

    Why this helper exists:
    - both `/agents/execute` and `/agents/execute/stream` should share the same
      runtime wiring and event production path
    - keeping the generator payload-oriented lets the HTTP layer choose whether
      it renders SSE or returns a terminal JSON response

    access_token:
    - the user's JWT forwarded from agentic-backend via the Authorization header
    - stored in RuntimeContext so KF tool adapters can use it for outbound calls
      (same path as local agents in agentic-backend)
    - None in local dev when security is disabled
    """

    request_id = str(uuid4())
    ctx = request.context or {}
    correlation_id = ctx.get("correlation_id", request_id)
    resolved_team_id = team_id or ctx.get("team_id")

    portable_context = PortableContext(
        request_id=request_id,
        correlation_id=correlation_id,
        actor=ctx.get("user_id", "anonymous"),
        tenant=ctx.get("tenant", "default"),
        environment=PortableEnvironment.DEV,
        agent_id=definition.agent_id,
        agent_name=definition.agent_id,
        session_id=ctx.get("session_id"),
        user_id=ctx.get("user_id"),
        team_id=resolved_team_id,
    )

    runtime_context = RuntimeContext(
        session_id=ctx.get("session_id"),
        user_id=ctx.get("user_id"),
        language=ctx.get("language"),
        access_token=access_token,
    )

    binding = BoundRuntimeContext(
        runtime_context=runtime_context,
        portable_context=portable_context,
    )

    services = _build_runtime_services(
        definition,
        binding,
        team_id=resolved_team_id,
        registry=registry,
        access_token=access_token,
    )
    if isinstance(definition, GraphAgentDefinition):
        runtime: ReActRuntime | GraphRuntime = GraphRuntime(
            definition=definition,
            services=services,
        )
    else:
        runtime = ReActRuntime(
            definition=definition,
            services=services,
        )
    runtime.bind(binding)

    # thread_id = session_id enables LangGraph checkpointing: the agent
    # resumes its graph state from the SQL checkpointer on every turn.
    # When session_id is absent (e.g. one-shot calls) thread_id=None and
    # LangGraph runs stateless — no checkpoint written or read.
    execution_config = ExecutionConfig(
        thread_id=ctx.get("session_id"),
        resume_payload=request.resume_payload,
    )

    try:
        await runtime.activate()
        executor = await runtime.get_executor()
        if isinstance(definition, GraphAgentDefinition):
            # Graph agents receive their typed input schema; the agent's
            # build_turn_state() maps it to graph state before the first node runs.
            # The standard contract is a single "message" field in the input schema.
            # On a HITL resume the runtime ignores input entirely (state is loaded
            # from the checkpoint), so bypass validation with model_construct.
            input_cls = definition.input_model()
            if request.resume_payload is not None:
                graph_input = input_cls.model_construct(message="")
            else:
                graph_input = input_cls.model_validate(
                    {"message": request.message or ""}
                )
            executor_input: ReActInput | object = graph_input
        else:
            # On HITL resume, messages are ignored by the codec — the graph
            # resumes from its checkpointed interrupt via Command(resume=...).
            # On a normal turn, the user message is the only input.
            executor_input = ReActInput(
                messages=(
                    ()
                    if request.resume_payload is not None
                    else (
                        ReActMessage(
                            role=ReActMessageRole.USER, content=request.message
                        ),
                    )
                ),
            )
        async for event in executor.stream(executor_input, execution_config):
            payload = event.model_dump(mode="json")
            if not isinstance(payload, dict):
                raise RuntimeError(
                    "RuntimeEvent payload must serialize to a JSON object."
                )
            yield payload
    except Exception as exc:
        logger.exception(
            "[fred-runtime] agent execution error agent_id=%s", definition.agent_id
        )
        yield {"error": str(exc)}
    finally:
        await runtime.dispose()


def _terminal_execute_payload(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Select the terminal JSON payload returned by `/agents/execute`.

    Why this helper exists:
    - non-streaming callers want one deterministic response object
    - different runtimes may emit several intermediate events before the
      terminal outcome, so the endpoint should consistently return the final
      event when present and otherwise fall back to the last emitted payload

    How to use it:
    - pass the collected event payloads from `_iterate_runtime_event_payloads`

    Example:
    - `payload = _terminal_execute_payload(payloads)`
    """

    if not payloads:
        return {"error": "Agent execution produced no runtime events."}
    for payload in reversed(payloads):
        if payload.get("kind") == "final":
            return payload
    return payloads[-1]


# ---------------------------------------------------------------------------
# Router builder
# ---------------------------------------------------------------------------


def _build_agent_router(
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    security_enabled: bool,
) -> APIRouter:
    """
    Build the FastAPI router for agent execution.

    Why this is a function rather than a module-level router:
    - the registry is provided at app-creation time, not import time
    - each call produces an isolated router instance bound to that registry
    - security_enabled controls whether get_current_user is applied as a dependency
    """
    from fred_core.security.oidc import get_current_user

    router = APIRouter(prefix="/agents", tags=["Agents"])

    # Build the dependency list once — empty when security is off so that
    # local-dev pods start without any Keycloak configuration.
    _auth_deps = [Depends(get_current_user)] if security_enabled else []

    def _resolve_definition(
        agent_id: str,
    ) -> ReActAgentDefinition | GraphAgentDefinition:
        """
        Resolve one registered agent definition or raise a 404 HTTP error.

        Why this helper exists:
        - both execute routes should share the same lookup and error wording

        How to use it:
        - call from the route handlers after request validation

        Example:
        - `definition = _resolve_definition(request.agent_id)`
        """

        definition = registry.get(agent_id)
        if definition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown agent_id: {agent_id!r}. "
                f"Known agents: {list(registry.keys())}",
            )
        return definition

    @router.get("")
    async def list_agents() -> list[str]:
        """Return the agent IDs registered in this pod."""
        return list(registry.keys())

    @router.get("/templates")
    async def list_agent_templates() -> list[_AgentTemplateSummary]:
        """
        Return the executable agent templates registered in this pod.

        Why this endpoint exists:
        - control-plane business admin flows need a read-only catalog of
          executable templates without exposing runtime CRUD or class-path
          authoring

        How to use it:
        - call from control-plane to aggregate template metadata across pods

        Example:
        - `GET /fred/agents/v2/agents/templates`
        """

        return [
            _AgentTemplateSummary(
                template_agent_id=definition.agent_id,
                title=definition.role,
                description=definition.description,
                kind=definition.execution_category,
                default_tuning=_definition_to_agent_tuning(definition),
                available_mcp_servers=_available_mcp_servers_for_definition(definition),
            )
            for definition in registry.values()
        ]

    @router.get("/sessions", dependencies=_auth_deps)
    async def list_sessions(user_id: str) -> list[str]:
        """
        Return the session IDs for a user, most recent first.

        GET <configured base_url>/agents/sessions?user_id=<user_id>
        Authorization: Bearer <user JWT> (same auth as execute endpoints)
        Response: JSON array of session_id strings

        Why this endpoint exists:
        - the UI needs to list past conversations for a returning user
        - the checkpointer has no user_id index; only the history store does

        How to use it:
        - GET /agents/sessions?user_id=alice
        - returns ["session-3", "session-1", ...]  most recent first
        """
        history_store = get_runtime_context().config.history_store
        if history_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No history store configured — session listing is unavailable.",
            )
        return await history_store.list_sessions(user_id=user_id)

    @router.get("/sessions/{session_id}/messages", dependencies=_auth_deps)
    async def get_session_messages(session_id: str) -> list[dict[str, Any]]:
        """
        Return the conversation history for a session as a flat message list.

        GET <configured base_url>/agents/sessions/{session_id}/messages
        Authorization: Bearer <user JWT> (same auth as execute endpoints)
        Response: JSON array of ChatMessage objects (role/channel/parts/metadata).

        Why the history store is the source of truth:
        - the history store writes one row per message, keyed by (session_id, rank)
        - it is agent-type-agnostic and works for both ReAct and Graph agents
        - the checkpointer (former source) only works for agents with a ``messages``
          channel in state and is not queryable per user_id

        Returns 503 when no history store is configured (stateless pod mode).
        Returns [] when the session exists but has no rows yet.
        """
        history_store = get_runtime_context().config.history_store
        if history_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No history store configured — session history is unavailable.",
            )
        messages = await history_store.get(session_id=session_id)
        return [m.model_dump(mode="json", exclude_none=True) for m in messages]

    # ------------------------------------------------------------------
    # Checkpoint admin endpoints
    # ------------------------------------------------------------------

    def _get_checkpointer():
        cp = get_runtime_context().config.checkpointer
        if cp is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No checkpointer configured — storage is unavailable.",
            )
        return cp

    @router.get("/checkpoints", dependencies=_auth_deps)
    async def list_checkpoint_threads(
        limit: int = 100,
    ) -> list[_CheckpointThreadSummary]:
        """
        List all checkpoint threads stored in this pod.

        GET <base_url>/agents/checkpoints?limit=<n>

        Returns one summary row per thread_id: checkpoint count and the timestamp
        of the latest checkpoint.  Useful to see which sessions have live
        checkpoint state and how many turns each has accumulated.

        Returns 503 when the pod has no persistent storage configured.
        """
        from sqlalchemy import desc, func, select

        cp = _get_checkpointer()
        await cp._ensure_tables()
        ct = cp.checkpoints_table
        async with cp.store.begin() as conn:
            stmt = (
                select(
                    ct.c.thread_id,
                    func.count(ct.c.checkpoint_id).label("cnt"),
                    func.max(ct.c.created_at).label("latest"),
                )
                .group_by(ct.c.thread_id)
                .order_by(desc(func.max(ct.c.created_at)))
                .limit(limit)
            )
            rows = (await conn.execute(stmt)).fetchall()
        return [
            _CheckpointThreadSummary(
                thread_id=str(row.thread_id),
                checkpoint_count=int(row.cnt),
                latest_created_at=str(row.latest) if row.latest else None,
            )
            for row in rows
        ]

    @router.get("/checkpoints/_stats", dependencies=_auth_deps)
    async def get_checkpoint_storage_stats() -> _CheckpointStorageStats:
        """
        Return aggregate storage statistics across all three checkpointer tables.

        GET <base_url>/agents/checkpoints/_stats

        Reports thread count, checkpoint count, blob count, pending write count,
        and approximate byte sizes for the checkpoint and blob tables.
        Useful to assess storage growth before planning a purge strategy.

        Returns 503 when the pod has no persistent storage configured.
        """
        from sqlalchemy import func, select

        cp = _get_checkpointer()
        await cp._ensure_tables()
        ct, bt, wt = cp.checkpoints_table, cp.blobs_table, cp.writes_table

        async with cp.store.begin() as conn:
            thread_count = (
                await conn.execute(select(func.count(func.distinct(ct.c.thread_id))))
            ).scalar() or 0

            cp_count = (
                await conn.execute(select(func.count(ct.c.checkpoint_id)))
            ).scalar() or 0

            cp_bytes = (
                await conn.execute(select(func.sum(func.length(ct.c.checkpoint_blob))))
            ).scalar() or 0

            blob_count = (
                await conn.execute(select(func.count(bt.c.version)))
            ).scalar() or 0

            blob_bytes = (
                await conn.execute(select(func.sum(func.length(bt.c.value_blob))))
            ).scalar() or 0

            write_count = (
                await conn.execute(select(func.count(wt.c.idx)))
            ).scalar() or 0

        return _CheckpointStorageStats(
            thread_count=int(thread_count),
            checkpoint_count=int(cp_count),
            blob_count=int(blob_count),
            pending_write_count=int(write_count),
            checkpoint_bytes_approx=int(cp_bytes),
            blob_bytes_approx=int(blob_bytes),
        )

    @router.get("/checkpoints/{thread_id}", dependencies=_auth_deps)
    async def get_checkpoint_thread(thread_id: str) -> _CheckpointThreadDetail:
        """
        Return all checkpoints for one thread, newest first.

        GET <base_url>/agents/checkpoints/{thread_id}

        Lists checkpoint_id, parent_checkpoint_id, created_at, and the raw
        metadata dict (step count, source, writes summary) for each checkpoint.
        Blobs are not deserialized — this is a lightweight structural view.

        Returns 503 when no checkpointer is configured.
        Returns an empty checkpoints list when the thread has no rows.
        """
        from sqlalchemy import desc, select

        cp = _get_checkpointer()
        await cp._ensure_tables()
        ct = cp.checkpoints_table
        async with cp.store.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        ct.c.checkpoint_id,
                        ct.c.parent_checkpoint_id,
                        ct.c.created_at,
                        ct.c.metadata_json,
                    )
                    .where(ct.c.thread_id == thread_id)
                    .order_by(desc(ct.c.created_at), desc(ct.c.checkpoint_id))
                )
            ).fetchall()
        return _CheckpointThreadDetail(
            thread_id=thread_id,
            checkpoints=[
                _CheckpointEntry(
                    checkpoint_id=str(row.checkpoint_id),
                    parent_checkpoint_id=(
                        str(row.parent_checkpoint_id)
                        if row.parent_checkpoint_id
                        else None
                    ),
                    created_at=str(row.created_at) if row.created_at else None,
                    metadata=dict(row.metadata_json or {}),
                )
                for row in rows
            ],
        )

    @router.delete(
        "/checkpoints/{thread_id}",
        dependencies=_auth_deps,
        status_code=status.HTTP_204_NO_CONTENT,
        response_model=None,
    )
    async def delete_checkpoint_thread(thread_id: str) -> None:
        """
        Purge all checkpoint data for one thread.

        DELETE <base_url>/agents/checkpoints/{thread_id}

        Deletes all rows in the checkpoints, blobs, and writes tables for the
        given thread_id.  This is irreversible — the agent will lose the ability
        to resume from any prior HITL pause or conversation state for this thread.

        History store rows (session_history) are NOT deleted — only checkpoint
        state is purged.  Use this to reclaim storage from stale or test sessions.

        Returns 204 on success, 503 when no checkpointer is configured.
        """
        cp = _get_checkpointer()
        await cp.adelete_thread(thread_id)

    @router.post("/execute", dependencies=_auth_deps)
    async def execute(
        request: _AgentExecuteRequest, http_request: Request
    ) -> JSONResponse:
        """
        Execute one agent turn and return the terminal RuntimeEvent as JSON.

        POST <configured base_url>/agents/execute
        Authorization: Bearer <user JWT forwarded from agentic-backend>
        Body: {"agent_id": "...", "message": "...", "context": {...}}
        Response: application/json containing the terminal runtime payload

        The Bearer token is the user's Keycloak JWT forwarded by agentic-backend.
        It is stored in RuntimeContext.access_token so KF tool adapters can use it
        for outbound calls — the same pattern as local agents in agentic-backend.
        """

        auth = http_request.headers.get("Authorization", "")
        access_token = auth.removeprefix("Bearer ").strip() or None
        target = await _resolve_agent_instance(
            request=request,
            registry=registry,
            access_token=access_token,
            control_plane_url=get_runtime_context().config.control_plane_url,
        )
        payloads = [
            payload
            async for payload in _iterate_runtime_event_payloads(
                target.definition,
                request,
                access_token=access_token,
                team_id=target.team_id,
                registry=registry,
            )
        ]
        # Write history after generator is fully consumed.
        # Can await here — no SSE response to block.
        ctx = request.context or {}
        session_id: str | None = ctx.get("session_id")
        if session_id:
            history_store = get_runtime_context().config.history_store
            if history_store is not None:
                await _write_turn_history(
                    session_id=session_id,
                    user_id=ctx.get("user_id") or "unknown",
                    request_message=request.message,
                    payloads=payloads,
                    history_store=history_store,
                )
        return JSONResponse(_terminal_execute_payload(payloads))

    @router.post("/execute/stream", dependencies=_auth_deps)
    async def execute_stream(
        request: _AgentExecuteRequest, http_request: Request
    ) -> StreamingResponse:
        """
        Stream RuntimeEvent JSON over SSE for a single agent invocation.

        POST <configured base_url>/agents/execute/stream
        Authorization: Bearer <user JWT forwarded from agentic-backend>
        Body: {"agent_id": "...", "message": "...", "context": {...}}
        Response: text/event-stream, each `data:` line is a RuntimeEvent JSON

        The Bearer token is the user's Keycloak JWT forwarded by agentic-backend.
        It is stored in RuntimeContext.access_token so KF tool adapters can use it
        for outbound calls — the same pattern as local agents in agentic-backend.
        """
        auth = http_request.headers.get("Authorization", "")
        access_token = auth.removeprefix("Bearer ").strip() or None
        target = await _resolve_agent_instance(
            request=request,
            registry=registry,
            access_token=access_token,
            control_plane_url=get_runtime_context().config.control_plane_url,
        )
        return StreamingResponse(
            _stream(
                target.definition,
                request,
                access_token=access_token,
                team_id=target.team_id,
                registry=registry,
            ),
            media_type="text/event-stream",
        )

    return router


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def create_agent_app(
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    config: AgentPodConfig,
    extra_routers: list[APIRouter] | None = None,
) -> FastAPI:
    """
    Create a ready-to-serve FastAPI app for a Fred agent pod.

    Why this exists:
    - every agent pod needs the same execution endpoints, RuntimeConfig wiring,
      lifespan hook, and security middleware — this factory provides all of it
      so pods contain zero infrastructure code

    How to use it:
    - call from your pod's `main.py` after loading your config
    - security is taken from `config.security` — no separate parameter needed

    Example:
    ```python
    from fred_runtime.app import create_agent_app, load_agent_pod_config
    from myapp.agents.registry import REGISTRY

    config = load_agent_pod_config()
    app = create_agent_app(registry=REGISTRY, config=config)
    ```

    Parameters:
    - registry: maps agent_id → ReActAgentDefinition; built at startup, read-only
    - config: AgentPodConfig loaded from `config/configuration.yaml`
    - extra_routers: additional APIRouter instances mounted under `config.app.base_url`

    Security (from config.security):
    - when `config.security.user.enabled` is True:
        - initializes Keycloak JWT validation (initialize_user_security)
        - adds Depends(get_current_user) to POST /agents/execute and
          POST /agents/execute/stream
    - `config.security.authorized_origins` controls CORS (when non-empty)
    - routes, docs, and OpenAPI are mounted under `config.app.base_url`
    """

    security = config.security
    base_url = _normalize_base_url(config.app.base_url)
    user_security = security.user if security is not None else None
    security_enabled: bool = (
        user_security.enabled if user_security is not None else False
    )
    authorized_origins: list[str] = (
        [str(o).rstrip("/") for o in security.authorized_origins]
        if security is not None and security.authorized_origins
        else []
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- Observability bootstrap ---
        # Must happen first so every subsequent logger call uses the correct
        # formatter, handlers (Rich + StoreEmitHandler), and noisy-lib filters —
        # the same stack that agentic-backend uses via the same log_setup call.
        log_setup(
            service_name=config.app.name,
            log_level=config.app.log_level,
            store=RamLogStore(),
        )
        # Bootstrap the global tracer and metrics provider from pod config.
        # The backend (logging, null, langfuse, …) is declared in configuration.yaml.
        # Credentials stay in .env.
        bootstrap_observability(config.observability)

        # Initialize Keycloak inbound validation before any request is handled.
        if security_enabled and user_security is not None:
            from fred_core.security.oidc import initialize_user_security

            initialize_user_security(user_security)

        chat_factory = _build_chat_model_factory(config)

        # SQL checkpointer — always initialized from config.storage.postgres.
        # Uses SQLite (via aiosqlite) when no Postgres host is set (local dev).
        # Uses asyncpg Postgres in production.
        # Provides durable LangGraph session state keyed by session_id.
        sql_engine = None
        checkpointer = None
        history_store = None
        try:
            from fred_core.history.postgres_history_store import PostgresHistoryStore
            from fred_core.sql.base_sql import create_async_engine_from_config

            from ..runtime_support.sql_checkpointer import FredSqlCheckpointer

            sql_engine = create_async_engine_from_config(config.storage.postgres)
            checkpointer = FredSqlCheckpointer(sql_engine)
            history_store = PostgresHistoryStore(sql_engine)
            logger.info(
                "[fred-runtime] SQL checkpointer and history store ready (dialect=%s)",
                sql_engine.dialect.name,
            )
        except Exception:
            logger.exception(
                "[fred-runtime] Failed to initialize SQL storage — running stateless"
            )

        # MCP catalog — resolved during config bootstrap from `mcp_catalog.yaml`
        # and attached internally to the typed pod config.
        mcp_configuration = config.get_mcp_configuration()

        runtime_config = RuntimeConfig(
            knowledge_flow_url=config.ai.knowledge_flow_url,
            timeouts=config.ai.timeout,
            chat_model_factory=chat_factory,
            checkpointer=checkpointer,
            history_store=history_store,
            mcp_configuration=mcp_configuration,
            control_plane_url=config.platform.control_plane_url,
        )
        set_runtime_context(FredRuntimeContext(runtime_config))
        logger.info(
            "[fred-runtime] agent pod started — base_url=%s kf=%s security=%s "
            "checkpointer=%s history=%s agents=%s",
            base_url or "/",
            config.ai.knowledge_flow_url,
            "enabled" if security_enabled else "disabled",
            "sql" if checkpointer is not None else "none",
            "sql" if history_store is not None else "none",
            list(registry.keys()),
        )
        yield

        # Graceful shutdown — dispose the SQL engine connection pool.
        if sql_engine is not None:
            await sql_engine.dispose()
            logger.info("[fred-runtime] SQL engine disposed")

    app = FastAPI(
        title=config.app.name,
        version="0.1.0",
        docs_url=f"{base_url}/docs" if base_url else "/docs",
        redoc_url=f"{base_url}/redoc" if base_url else "/redoc",
        openapi_url=f"{base_url}/openapi.json" if base_url else "/openapi.json",
        lifespan=lifespan,
    )

    # CORS — only added when security is provided so local-dev pods stay simple.
    if authorized_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=authorized_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "Authorization"],
        )
        logger.debug("[fred-runtime] CORS allow_origins=%s", authorized_origins)

    api_router = APIRouter(prefix=base_url)
    api_router.include_router(
        _build_agent_router(registry, security_enabled=security_enabled)
    )

    for extra in extra_routers or []:
        api_router.include_router(extra)

    app.include_router(api_router)

    if config.app.openai_compat:
        from .openai_compat_router import create_openai_compat_router

        openai_router = create_openai_compat_router(
            registry, security_enabled=security_enabled
        )
        app.include_router(openai_router, prefix="/v1")
        logger.info("[fred-runtime] OpenAI-compat endpoints enabled at /v1")

    return app
