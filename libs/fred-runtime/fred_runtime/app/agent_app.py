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
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fred_core.common.config_loader import get_config
from fred_core.history.history_schema import ChatMessage
from fred_core.kpi import KPIMiddleware
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_core.logs.log_setup import log_setup
from fred_core.logs.memory_log_store import RamLogStore
from fred_core.security.models import AuthorizationError
from fred_core.security.oidc import get_keycloak_client_id, get_keycloak_url
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    OrganizationPermission,
    TeamPermission,
)
from fred_core.security.rebac.rebac_factory import rebac_factory
from fred_core.security.structure import KeycloakUser, is_service_agent
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    AgentInvocationResult,
    BoundRuntimeContext,
    ConversationTurn,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.eval import EvalStep, EvalTrace
from fred_sdk.contracts.execution import (
    ExecutionGrantAction,
    RuntimeExecuteRequest,
)
from fred_sdk.contracts.models import (
    AgentTuning,
    ExecutionCategory,
    GraphAgentDefinition,
    MCPServerConfiguration,
    ReActAgentDefinition,
    TuningValue,
)
from fred_sdk.contracts.react_contract import ReActInput, ReActMessage, ReActMessageRole
from fred_sdk.contracts.runtime import (
    AgentInvokerPort,
    ChatModelFactoryPort,
    ExecutionConfig,
    HistoryStorePort,
    RuntimeErrorEvent,
    RuntimeEvent,
    RuntimeServices,
)
from fred_sdk.contracts.ui_part_union import current_ui_part_union
from fred_sdk.support.authored_toolsets import (
    AuthoredToolRuntimePorts,
    build_authored_tool_handlers,
)
from pydantic import BaseModel, Field, TypeAdapter, model_validator

from fred_runtime.capabilities import boot_capability_registry
from fred_runtime.common.kf_markdown_media_client import KfMarkdownMediaClient
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.react.react_runtime import ReActRuntime
from fred_runtime.runtime_support.checkpoints import load_checkpoint

from ..common.structures import AgentSettingsLike
from ..integrations.inprocess_toolkit_registry import build_inprocess_toolkit
from ..integrations.v2_runtime.adapters import (
    CompositeToolInvoker,
    FredKnowledgeSearchToolInvoker,
    FredMcpToolProvider,
    FredWorkspaceFs,
    KPIWriterMetricsAdapter,
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
from .container import build_pod_container
from .context import AuditEventRecord, KpiTurnRecord, PodApplicationContext
from .dependencies import (
    attach_pod_container,
    get_pod_container,
    get_pod_container_from_app,
)
from .observability_factory import bootstrap_observability

logger = logging.getLogger(__name__)
_audit_logger = logging.getLogger("fred.security.audit")


def _emit_audit_event(
    container: PodApplicationContext,
    level: str,
    name: str,
    **fields: object,
) -> None:
    """Append one security audit event to the container ring buffer and audit logger."""
    event = cast(
        AuditEventRecord,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "audit_event": name,
            **{k: v for k, v in fields.items() if v is not None},
        },
    )
    with container._audit_events_lock:
        container.audit_events_buffer.append(event)
    getattr(_audit_logger, level)("[SECURITY] %s", name, extra=dict(event))


def _build_config_provider(config: AgentPodConfig) -> Callable[[], AgentPodConfig]:
    """
    Expose the pod configuration through the shared FastAPI config dependency.

    Why this function exists:
    - shared security helpers in `fred-core` resolve configuration through
      `Depends(get_config)`, even when they are mounted inside an agent pod
    - agent pods must therefore provide the same dependency override contract
      as the other Fred backends

    How to use it:
    - call once from `create_agent_app(...)`
    - assign the returned callable to `app.dependency_overrides[get_config]`

    Example:
    - `app.dependency_overrides[get_config] = _build_config_provider(config)`
    """

    def _provide_config() -> AgentPodConfig:
        return config

    return _provide_config


# ---------------------------------------------------------------------------
# Checkpoint admin response models
# ---------------------------------------------------------------------------


class _CheckpointThreadSummary(BaseModel):
    """
    One row in the checkpoint thread listing.

    session_id is the public-facing conversation identity and equals the
    LangGraph thread_id internally. Always use session_id in APIs and the CLI.

    Size semantics:
    - checkpoint_bytes_total: sum of checkpoint_blob lengths (lightweight
      pointer structures, typically <10 KB per checkpoint).
    - blob_count / blob_bytes_total: the channel state blobs shared across
      all checkpoints for this session. LangGraph deduplicates blobs by
      (channel, version), so blob_count is the number of unique channel
      snapshots, not one-per-checkpoint. This is where conversation history
      and tool outputs actually live and tends to grow with turn count.
    - pending_write_count: uncommitted writes left over from an interrupted
      turn; non-zero usually means the pod crashed mid-turn.
    """

    session_id: str
    checkpoint_count: int
    first_created_at: str | None
    latest_created_at: str | None
    checkpoint_bytes_total: int
    blob_count: int
    blob_bytes_total: int
    pending_write_count: int


class _CheckpointEntry(BaseModel):
    """
    Lightweight view of a single checkpoint row (no deserialized blobs).

    Size semantics:
    - checkpoint_bytes: size of the checkpoint_blob for this specific row.
      This is the msgpack-serialized pointer structure (channel→version map),
      not the channel values themselves. Typically 100 B – 5 KB.
    - pending_write_count: number of pending writes in the writes table
      associated with this checkpoint_id. Should be 0 for a clean state;
      non-zero suggests an interrupted turn write.
    - node_names: the graph node(s) that wrote output at this step,
      extracted from metadata_json.writes. Empty for source="input" (human
      turn received, no node ran yet).
    """

    checkpoint_id: str
    parent_checkpoint_id: str | None
    created_at: str | None
    step: int | None
    source: str | None
    node_names: list[str]
    checkpoint_bytes: int
    pending_write_count: int
    metadata: dict[str, Any]


class _CheckpointThreadDetail(BaseModel):
    """All checkpoints for one session, newest first."""

    session_id: str
    checkpoints: list[_CheckpointEntry]


class _CheckpointStorageStats(BaseModel):
    """
    Aggregate storage statistics across all three checkpointer tables.

    Interpretation guide:
    - checkpoint_bytes_approx: total size of checkpoint pointer structures.
      Low per-checkpoint cost; multiply by checkpoint_count for estimate.
    - blob_bytes_approx: total size of channel state blobs. This is the
      dominant cost — message history, tool outputs, and graph state all
      live here. Grows with total conversation turns across all sessions.
    - pending_write_count: should be 0 in steady state; non-zero indicates
      writes from interrupted turns that were never cleaned up.
    """

    thread_count: int
    checkpoint_count: int
    blob_count: int
    pending_write_count: int
    checkpoint_bytes_approx: int
    blob_bytes_approx: int


class _RuntimeErrorPayload(BaseModel):
    """
    Structured execution error payload returned by runtime HTTP endpoints.

    Why this exists:
    - `/agents/execute` can fail before a terminal `RuntimeEvent` is produced
    - exposing a typed fallback payload keeps the OpenAPI contract explicit and
      avoids unstructured `{"error": ...}` blobs in generated clients
    """

    error: str = Field(..., min_length=1)


# Built lazily and refreshed whenever the `UiPart` union changes: capability
# chat parts join the union at registry boot (#1977), so an adapter frozen at
# import time would reject registered capability parts on runtime events.
_execute_response_adapter_cache: tuple[Any, TypeAdapter[Any]] | None = None


def _execute_response_adapter() -> TypeAdapter[Any]:
    global _execute_response_adapter_cache

    union_token = current_ui_part_union()
    cache = _execute_response_adapter_cache
    if cache is None or cache[0] is not union_token:
        cache = (union_token, TypeAdapter(RuntimeEvent | _RuntimeErrorPayload))
        _execute_response_adapter_cache = cache
    return cache[1]


# ---------------------------------------------------------------------------
# Chat model factory builder
# ---------------------------------------------------------------------------


def _build_chat_model_factory(config: AgentPodConfig) -> ChatModelFactoryPort:
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
        raw_refresh = payload.get("refresh_token")
        new_refresh_token: str = (
            raw_refresh
            if isinstance(raw_refresh, str) and raw_refresh
            else refresh_token
        )
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

        context_dict = request.context.model_dump(mode="json")
        context_dict.setdefault("execution_action", ExecutionGrantAction.EXECUTE.value)
        # RFC AGENT-INVOKE: apply the caller's per-call scope onto the callee's
        # retrieval context. These keys are read back when the callee's
        # RuntimeContext is built, so they narrow its document/library/search world.
        # Scope narrows only; the callee still runs under the delegated identity.
        if request.scope is not None:
            if request.scope.document_uids is not None:
                context_dict["selected_document_uids"] = list(
                    request.scope.document_uids
                )
            if request.scope.library_ids is not None:
                context_dict["selected_document_libraries_ids"] = list(
                    request.scope.library_ids
                )
            if request.scope.search_policy is not None:
                context_dict["search_policy"] = request.scope.search_policy
        execute_request = _AgentExecuteRequest.model_construct(
            agent_id=request.agent_id,
            agent_instance_id=None,
            message=request.message,
            context=context_dict,
            resume_payload=None,
            invocation_turns=request.prior_turns,
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
    workspace_fs = FredWorkspaceFs(
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
                workspace_fs=workspace_fs,
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
        metrics=KPIWriterMetricsAdapter(runtime_config.kpi_writer),
        chat_model_factory=runtime_config.chat_model_factory,
        tool_invoker=tool_invoker,
        tool_provider=tool_provider,
        workspace_fs=workspace_fs,
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
    checkpoint_id: str | None = Field(default=None, min_length=1)
    resume_payload: Any | None = Field(
        default=None,
        description=(
            "HITL resume data returned by the caller after an AwaitingHumanRuntimeEvent. "
            "When set, the graph is resumed from its checkpointed interrupt state using "
            "LangGraph Command(resume=...) — the message field is ignored."
        ),
    )
    invocation_turns: tuple[ConversationTurn, ...] = Field(
        default=(),
        description="Prior conversation turns forwarded by the calling agent.",
    )
    inline_tuning: dict[str, TuningValue] | None = Field(
        default=None,
        description="Optional inline tuning overrides. Honored only in agent_id (direct template) mode.",
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


def _to_internal_request(r: RuntimeExecuteRequest) -> "_AgentExecuteRequest":
    """
    Bridge a public RuntimeExecuteRequest to the internal execution model.

    Why this exists:
    - The HTTP routes now accept RuntimeExecuteRequest (the frozen public contract)
    - The internal plumbing (_iterate_runtime_event_payloads, _stream, etc.) still
      reads from _AgentExecuteRequest for backward compatibility
    - This bridge is intentionally transitional; internal helpers will migrate
      to RuntimeExecuteRequest directly in a subsequent phase

    How to use:
    - Call from the execute route handlers before passing to internal helpers
    """
    return _AgentExecuteRequest.model_construct(
        agent_id=r.agent_id,
        agent_instance_id=r.agent_instance_id,
        message=r.input,
        context=r.to_legacy_context() or None,
        checkpoint_id=r.checkpoint_id,
        resume_payload=r.resume_payload,
        invocation_turns=r.invocation_turns,
        inline_tuning=r.inline_tuning,
    )


class _AgentTemplateSummary(BaseModel):
    template_agent_id: str
    title: str
    description: str
    description_by_lang: dict[str, str] | None = None
    kind: ExecutionCategory
    default_tuning: AgentTuning
    available_mcp_servers: list[MCPServerConfiguration] = Field(default_factory=list)


class _McpCatalogEntry(BaseModel):
    id: str
    name: str
    description: str | None = None
    enabled: bool
    transport: str | None = None


class _McpCatalogResponse(BaseModel):
    servers: list[_McpCatalogEntry]


class _ResolvedAgentInstance(BaseModel):
    agent_instance_id: str
    template_agent_id: str
    display_name: str = ""
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
    agent_instance_name: str | None = None


def _apply_runtime_tuning(
    definition: ReActAgentDefinition | GraphAgentDefinition,
    tuning: AgentTuning,
    available_mcp_servers: list[MCPServerConfiguration],
) -> ReActAgentDefinition | GraphAgentDefinition:
    """
    Overlay persisted business tuning onto one registered agent template.

    Why this exists:
    - control-plane stores the full effective tuning for a managed agent
      instance, and the pod must execute that tuning without depending on the
      old agentic-backend definition factory

    How to use it:
    - call after resolving an `agent_instance_id` from control-plane

    Example:
    - `definition = _apply_runtime_tuning(template_definition, resolution.tuning, catalog)`
    """

    mcp_servers = tuning.mcp_servers
    if tuning.selected_mcp_server_ids is not None:
        selected = frozenset(tuning.selected_mcp_server_ids)
        mcp_servers = [s for s in mcp_servers if s.id in selected]

    update: dict[str, object] = {
        "role": tuning.role,
        "description": tuning.description,
        "tags": tuple(tuning.tags),
        "fields": tuple(field.model_copy(deep=True) for field in tuning.fields),
        "default_mcp_servers": tuple(
            server.model_copy(deep=True) for server in mcp_servers
        ),
        # Forward all values for all agent types so every execution surface can
        # read admin-set tuning (graph steps via context.tuning_values, ReAct
        # prompting via definition.tuning_values).
        "tuning_values": dict(tuning.values),
    }
    if isinstance(definition, ReActAgentDefinition):
        # Also overlay system_prompt_template directly for ReAct runtime compatibility.
        base_system_prompt = str(getattr(definition, "system_prompt_template", ""))
        effective_system_prompt = base_system_prompt
        system_prompt = tuning.values.get("prompts.system")
        if isinstance(system_prompt, str) and system_prompt.strip():
            effective_system_prompt = system_prompt
        available_by_id = {server.id: server for server in available_mcp_servers}
        fragments = [
            catalog_entry.agent_instructions.strip()
            for server_ref in mcp_servers
            if (catalog_entry := available_by_id.get(server_ref.id)) is not None
            and isinstance(catalog_entry.agent_instructions, str)
            and catalog_entry.agent_instructions.strip()
        ]
        if fragments:
            effective_system_prompt = f"{effective_system_prompt}\n\n" + "\n\n".join(
                fragments
            )
        if effective_system_prompt != base_system_prompt:
            update["system_prompt_template"] = effective_system_prompt
    return definition.model_copy(update=update)


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
    team_id: str | None = None,
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
        # Direct agent_id execution takes no grant, so it is the enforcement point
        # for agent visibility: a non-public agent (AgentDefinition.public=False) is
        # internal — it may only be executed through a managed instance (whose
        # enrollment is admin-gated), never directly by id. Treat it as unknown so
        # its existence is not even confirmed. See AGENT-VISIBILITY-RFC §3.1.
        if definition is None or not getattr(definition, "public", True):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown agent_id: {request.agent_id!r}.",
            )
        if request.inline_tuning:
            available_mcp_servers = _available_mcp_servers_for_definition(definition)
            definition = _apply_runtime_tuning(
                definition,
                AgentTuning(
                    role=definition.role,
                    description=definition.description,
                    tags=list(definition.tags),
                    fields=list(definition.fields),
                    mcp_servers=list(definition.default_mcp_servers),
                    values=request.inline_tuning,
                ),
                available_mcp_servers,
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

    # Team-scoped resolution (RUNTIME-07 rev. 2). The pod resolves the instance's
    # template + tuning from the control-plane binding scoped to the caller's team
    # (ReBAC-gated, store.get_for_team) — the replacement for the signed grant.
    # The end user has already been authorized at this pod (Keycloak + OpenFGA).
    if team_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Managed agent instance execution requires a team context "
                "(runtime_context.team_id)."
            ),
        )
    url = (
        f"{control_plane_url.rstrip('/')}/teams/{team_id}/agent-instances/"
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
    available_mcp_servers = _available_mcp_servers_for_definition(definition)
    return _ResolvedExecutionTarget(
        definition=_apply_runtime_tuning(
            definition, resolution.tuning, available_mcp_servers
        ),
        effective_agent_id=resolution.agent_instance_id,
        team_id=resolution.owner_team_id,
        agent_instance_name=resolution.display_name or None,
    )


def _make_user_dependency(
    get_current_user_fn: Callable[..., KeycloakUser | Awaitable[KeycloakUser]],
    security_enabled: bool,
) -> Callable[..., KeycloakUser | None]:
    """
    Build a FastAPI dependency that returns the authenticated user or None.

    Why this factory exists:
    - FastAPI requires a single stable callable for Depends().
    - Conditional function redefinition triggers basedpyright reportRedeclaration.
    - This factory produces one of two stable callables without redefinition.

    Returns a dependency that:
    - injects KeycloakUser when security_enabled=True
    - returns None when security_enabled=False (local dev mode)
    """
    if security_enabled:

        def _dep_with_auth(
            user: KeycloakUser = Depends(get_current_user_fn),
        ) -> KeycloakUser | None:
            return user

        return _dep_with_auth
    else:

        def _dep_noop() -> KeycloakUser | None:
            return None

        return _dep_noop


async def _authorize_execution_or_raise(
    request: RuntimeExecuteRequest,
    authenticated_user: KeycloakUser | None,
    container: PodApplicationContext,
) -> None:
    """
    Pod-side OpenFGA authorization for one execution request (RUNTIME-07 rev. 2).

    The pod is the execution authority. Identity is proven by the Keycloak JWT
    (`authenticated_user`); authorization is decided HERE, per request, by an
    OpenFGA check on the team the caller is acting in. This is the model already
    homologated on `main` (agentic-backend), re-instantiated per pod — it replaces
    the control-plane-signed grant, which is being removed.

    Behaviour:
    - security disabled (no authenticated user) → skip (dev/local).
    - ReBAC engine absent or disabled (Noop) → skip (identity-only dev posture);
      the C3 profile guarantees an enabled engine in classified deployments.
    - otherwise require the caller to hold `CAN_READ` on the requested team — the
      same relation the control-plane required before it would mint a grant. The
      team is caller-supplied but safe: OpenFGA only authorizes teams the user
      actually holds a relation to. Authorization and denial are both audited;
      any OpenFGA denial fails closed (403).

    Covers execute, execute/stream, evaluate AND resume — every path funnels
    through this call, so no half-authenticated session is possible.

    Direct template execution (`agent_id`) is **forbidden under the c3 profile**
    (RUNTIME-07 F-D); in dev/non-c3 it stays identity-only. Managed execution
    (`agent_instance_id`) requires a team and an OpenFGA grant whenever ReBAC is
    active; a missing team then fails closed.
    """
    if authenticated_user is None:
        # Security disabled (dev mode) — no identity to authorize.
        return
    profile = getattr(get_runtime_context().config, "security_profile", None)

    # Direct template execution (agent_id): no team scope, no managed instance.
    if request.agent_id is not None:
        if profile == "c3":
            _emit_audit_event(
                container,
                "warning",
                "direct_execution_forbidden",
                user_id=authenticated_user.uid,
                agent_id=request.agent_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "direct agent_id execution is not permitted under the c3 "
                    "security profile; use a managed agent instance"
                ),
            )
        # dev / non-c3: identity-only (no team to authorize against).
        return

    # Managed execution (agent_instance_id).
    rebac = get_runtime_context().config.rebac_engine
    if rebac is None or not rebac.enabled:
        # ReBAC not active (Noop / unconfigured) — identity-only dev posture. The
        # c3 profile guarantees an enabled engine in production (fail-closed).
        return
    team_id = request.effective_team_id()
    if team_id is None:
        _emit_audit_event(
            container,
            "warning",
            "managed_execution_without_team",
            user_id=authenticated_user.uid,
            agent_instance_id=request.agent_instance_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "managed agent instance execution requires a team context "
                "(runtime_context.team_id)"
            ),
        )
    if is_service_agent(authenticated_user):
        # Solution A (RFC EVAL-AUTH): a service identity (the evaluation worker) is
        # recognized for execution, scoped to the request team_id, without any stored
        # OpenFGA relation. Legitimacy is anchored upstream at campaign creation. The
        # team_id is guaranteed non-None above, so this stays team-scoped (never global).
        _emit_audit_event(
            container,
            "info",
            "service_agent_authorized",
            user_id=authenticated_user.uid,
            team_id=team_id,
            agent_instance_id=request.agent_instance_id,
        )
        return
    try:
        await rebac.check_user_team_permission_or_raise(
            authenticated_user, TeamPermission.CAN_READ, team_id
        )
    except AuthorizationError as exc:
        _emit_audit_event(
            container,
            "warning",
            "rebac_denied",
            user_id=authenticated_user.uid,
            team_id=team_id,
            agent_instance_id=request.agent_instance_id,
            reason=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"user {authenticated_user.uid!r} is not authorized for "
                f"team {team_id!r}"
            ),
        ) from exc
    _emit_audit_event(
        container,
        "info",
        "rebac_authorized",
        user_id=authenticated_user.uid,
        team_id=team_id,
        agent_instance_id=request.agent_instance_id,
    )


async def _enforce_session_ownership(
    request: RuntimeExecuteRequest,
    authenticated_user: KeycloakUser | None,
    container: PodApplicationContext,
) -> None:
    """
    Private-per-owner session policy (RUNTIME-07 rev. 2, finding F-C).

    Conversations are private to their owner. When security is enabled and the
    request targets an EXISTING session, the authenticated user must own it. A
    brand-new session is allowed (the caller becomes its owner). This blocks a
    same-team user from continuing or resuming another user's private session by
    guessing its `session_id` / `checkpoint_id` — the team OpenFGA check alone
    would not catch an intra-team cross-user access.
    """
    if authenticated_user is None:
        return  # security disabled (dev) — no identity to enforce
    session_id = request.effective_session_id()
    if not session_id:
        return
    history_store = get_runtime_context().config.history_store
    if history_store is None:
        return
    if not await history_store.session_exists(session_id):
        return  # new session — the caller becomes its owner
    if await history_store.session_belongs_to_user(session_id, authenticated_user.uid):
        return  # caller owns this session
    _emit_audit_event(
        container,
        "warning",
        "session_owner_mismatch",
        user_id=authenticated_user.uid,
        session_id=session_id,
        agent_instance_id=request.agent_instance_id,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"session {session_id!r} does not belong to the authenticated user",
    )


async def _caller_can_manage_platform(caller: KeycloakUser | None) -> bool:
    """True when the caller holds org-level ``can_manage_platform`` (CTRLP-12 C1).

    The delete endpoints use this as an **admin branch**: a platform service
    principal — e.g. the control-plane lifecycle worker erasing a conversation at
    window expiry — may delete a session it does not personally own. Only the
    per-user *ownership* check is waived; *authentication* stays enforced upstream
    by ``_authenticated_user``.

    Fails closed: returns False when there is no caller or when ReBAC is disabled
    (dev/no-security), so ownership behaviour is unchanged there and the bypass
    activates only when ReBAC is actually enforcing and the org permission is
    granted. Reuses the AUTHZ-01 ``can_manage_platform`` permission — no second
    bypass is forked.
    """
    if caller is None:
        return False
    rebac = get_runtime_context().config.rebac_engine
    if rebac is None or not rebac.enabled:
        return False
    return await rebac.has_user_permission(
        caller, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )


async def _authorize_and_resolve(
    request: RuntimeExecuteRequest,
    *,
    authenticated_user: KeycloakUser | None,
    container: PodApplicationContext,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    access_token: str | None,
) -> tuple["_AgentExecuteRequest", _ResolvedExecutionTarget]:
    """
    Shared pre-execution gate for execute / execute-stream / evaluate (and HITL
    resume, which is a field on those endpoints) — RUNTIME-07 rev. 2.

    The pod is the execution authority: there is NO control-plane-signed grant.
    1. validate checkpoint/session access,
    2. authorize the caller against OpenFGA on their team (identity = Keycloak JWT),
    3. resolve the managed instance template + tuning from the control-plane,
       team-scoped and ReBAC-gated (config only — never a secret or capability),
    4. cross-check the resolved owner team against the caller's claimed team.

    Returns the internal request plus the resolved execution target.
    """
    # F-B: identity is the validated Keycloak JWT, never the request body. Stamp
    # user_id from the token and neutralize any body-supplied credentials — the pod
    # uses the header bearer for downstream (knowledge-flow) calls and trusts no
    # caller-provided user_id / access_token / refresh_token.
    if authenticated_user is not None:
        base_ctx = request.runtime_context or RuntimeContext()
        request.runtime_context = base_ctx.model_copy(
            # F-B: neutralize body-supplied tokens (not secrets — set to None).
            update={
                "user_id": authenticated_user.uid,
                "access_token": access_token,
                "refresh_token": None,  # nosec B105
                "access_token_expires_at": None,  # nosec B105
            }
        )
    await _validate_session_checkpoint_access(request)
    await _enforce_session_ownership(request, authenticated_user, container)
    await _authorize_execution_or_raise(request, authenticated_user, container)
    internal_req = _to_internal_request(request)
    target = await _resolve_agent_instance(
        request=internal_req,
        registry=registry,
        access_token=access_token,
        control_plane_url=get_runtime_context().config.control_plane_url,
        team_id=request.effective_team_id(),
    )
    _validate_resolved_team(request, target.team_id, container)
    return internal_req, target


def _validate_resolved_team(
    request: RuntimeExecuteRequest,
    resolved_team_id: str | None,
    container: PodApplicationContext,
) -> None:
    """
    Cross-check the resolved instance owner team against the caller's claim.

    Team-scoped resolution already restricts the lookup to the caller's team, so a
    mismatch should be impossible; this is defense-in-depth and an audit anchor.
    Skipped for direct template execution (no team scope).
    """
    if resolved_team_id is None:
        return
    claimed = request.effective_team_id()
    if claimed is not None and claimed != resolved_team_id:
        _emit_audit_event(
            container,
            "warning",
            "team_binding_mismatch",
            claimed_team_id=claimed,
            resolved_team_id=resolved_team_id,
            agent_instance_id=request.agent_instance_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"resolved owner team {resolved_team_id!r} does not match "
                f"requested team {claimed!r}"
            ),
        )


async def _validate_session_checkpoint_access(
    request: RuntimeExecuteRequest,
) -> None:
    """
    Validate session/checkpoint consistency for resume-capable runtime requests.

    Why this exists:
    - the runtime must reject stale or non-waiting checkpoint resumes before
      execution starts, instead of surfacing them as late runtime errors
    - this is the smallest backend-completeness guard we can enforce locally
      without inventing new control-plane session authority models

    How to use it:
    - call from `/agents/execute` and `/agents/execute/stream` after grant
      validation and before target resolution
    - this helper is intentionally conservative: it only validates local
      session/checkpoint consistency that the runtime can prove itself

    Example:
    - `await _validate_session_checkpoint_access(request)`
    """

    needs_checkpoint_validation = (
        request.checkpoint_id is not None or request.resume_payload is not None
    )
    if not needs_checkpoint_validation:
        return

    session_id = request.effective_session_id()
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required when checkpoint_id or resume_payload is set.",
        )

    checkpointer = get_runtime_context().config.checkpointer
    if checkpointer is None:
        return

    checkpoint = await load_checkpoint(
        checkpointer,
        thread_id=session_id,
        checkpoint_id=request.checkpoint_id,
    )
    if checkpoint is None:
        detail = (
            "No pending checkpoint was found for this session."
            if request.resume_payload is not None
            else "checkpoint_id is unknown for this session."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    channel_values = checkpoint.get("channel_values", {})
    if not isinstance(channel_values, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="checkpoint payload is malformed for this session.",
        )

    if request.resume_payload is None:
        return

    if channel_values.get("runtime_kind") != "graph_v2":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="checkpoint is not resumable through the graph runtime.",
        )
    if channel_values.get("pending") is not True:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="checkpoint is not waiting for resume.",
        )

    resolved_checkpoint_id = channel_values.get(
        "pending_checkpoint_id"
    ) or checkpoint.get("id")
    if request.checkpoint_id is not None and (
        not isinstance(resolved_checkpoint_id, str)
        or resolved_checkpoint_id != request.checkpoint_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="checkpoint_id does not match the pending checkpoint for this session.",
        )


async def _write_turn_history(
    *,
    session_id: str,
    user_id: str,
    request_message: str | None,
    payloads: list[dict[str, Any]],
    history_store: HistoryStorePort,
    team_id: str | None = None,
    agent_instance_id: str | None = None,
    exchange_id: str | None = None,
    resume_payload: Any | None = None,
) -> None:
    """
    Persist one agent turn to the history store.

    Why this helper exists:
    - both ``/agents/execute`` and ``/agents/execute/stream`` produce the same
      sequence of runtime-event payloads; this function maps those payloads to
      ``ChatMessage`` rows and writes them in one batch

    Why this is a separate async function and not inline:
    - the streaming endpoint calls it with ``asyncio.create_task`` so the DB
      write does not block the SSE response to the client
    - the non-streaming endpoint can ``await`` it directly before returning

    How to use it:
    - call after the executor generator is exhausted
    - ``payloads`` is the list of ``dict`` produced by ``_iterate_runtime_event_payloads``
    - ``resume_payload`` is set for HITL resume turns; the user's choice is stored
      as a ``Channel.hitl_response`` row instead of a plain user text row
    - silently no-ops when ``session_id`` or ``history_store`` is absent

    Event-to-message mapping:
    - ``tool_call``      → ``Role.assistant / Channel.tool_call``
    - ``tool_result``    → ``Role.tool    / Channel.tool_result``
    - ``awaiting_human`` → ``Role.system  / Channel.hitl_request`` (full choices)
    - ``node_error``     → ``Role.system  / Channel.error``
    - ``final``          → ``Role.assistant / Channel.final`` (answer + sources)
    - user request       → ``Role.user   / Channel.final`` (prepended)
    - HITL resume        → ``Role.user   / Channel.hitl_response`` (choice made)
    """
    from fred_core.history.history_schema import (
        Channel,
        ChatMessage,
        ChatTokenUsage,
        Role,
        TextPart,
        make_assistant_final,
        make_hitl_request,
        make_hitl_response,
        make_tool_call,
        make_tool_result,
        make_user_text,
    )
    from fred_core.store.vector_search import VectorSearchHit

    try:
        base_rank: int = await history_store.next_rank(session_id)
    except Exception:
        logger.exception(
            "[fred-runtime][history] Failed to query next_rank session_id=%s",
            session_id,
        )
        return

    exchange_id = exchange_id or str(uuid4())
    messages: list[ChatMessage] = []
    rank = base_rank

    # 1. Opening row: user text on normal turns, HITL response on resume turns.
    if resume_payload is not None:
        # Extract choice_id from whatever shape the resume payload takes.
        if isinstance(resume_payload, dict):
            choice_id = str(resume_payload.get("choice_id") or "")
        elif isinstance(resume_payload, str):
            choice_id = resume_payload
        else:
            choice_id = str(resume_payload)
        if choice_id:
            messages.append(
                make_hitl_response(session_id, exchange_id, rank, choice_id=choice_id)
            )
            rank += 1
    elif request_message:
        messages.append(make_user_text(session_id, exchange_id, rank, request_message))
        rank += 1

    # 2. Map runtime events to messages
    final_content = ""
    final_sources: list[VectorSearchHit] = []
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
            # Store the full HITL gate definition — question and all choices —
            # so audit logs and UI replay have the complete structured record.
            req = payload.get("request", {})
            question = req.get("question") or req.get("title") or "HITL pause"
            raw_choices = req.get("choices") or []
            messages.append(
                make_hitl_request(
                    session_id,
                    exchange_id,
                    rank,
                    question=question,
                    choices=[
                        {
                            "id": c.get("id", ""),
                            "label": c.get("label", c.get("id", "")),
                        }
                        for c in raw_choices
                        if isinstance(c, dict)
                    ],
                    stage=req.get("stage"),
                    title=req.get("title"),
                )
            )
            rank += 1

        elif kind == "node_error":
            messages.append(
                ChatMessage(
                    session_id=session_id,
                    exchange_id=exchange_id,
                    rank=rank,
                    timestamp=datetime.now(timezone.utc),
                    role=Role.system,
                    channel=Channel.error,
                    parts=[TextPart(text=payload.get("error_message", "node error"))],
                )
            )
            rank += 1

        elif kind == "final":
            final_content = payload.get("content", "")
            raw_sources = payload.get("sources") or []
            final_sources = [
                VectorSearchHit.model_validate(s)
                for s in raw_sources
                if isinstance(s, dict)
            ]
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
                sources=final_sources if final_sources else None,
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
            team_id=team_id,
            agent_instance_id=agent_instance_id,
        )
    except Exception:
        logger.exception(
            "[fred-runtime][history] Failed to write turn history session_id=%s",
            session_id,
        )


def _sse(payload: str) -> str:
    return f"data: {payload}\n\n"


@dataclass(frozen=True)
class _TurnOutcome:
    model_name: str | None
    finish_reason: str
    token_usage: dict[str, Any] | None
    input_tokens: int | None
    output_tokens: int | None
    tool_count: int
    is_error: bool
    total_ms: int
    final_content: str | None


def _parse_turn_outcome(
    payloads: list[dict[str, Any]],
    turn_start: float,
) -> _TurnOutcome:
    total_ms = int((time.monotonic() - turn_start) * 1000)
    tool_count = sum(1 for p in payloads if p.get("kind") == "tool_call")
    final = next((p for p in reversed(payloads) if p.get("kind") == "final"), None)
    is_error = any(p.get("kind") == "execution_error" for p in payloads)
    token_usage: dict[str, Any] | None = final.get("token_usage") if final else None
    return _TurnOutcome(
        model_name=final.get("model_name") if final else None,
        finish_reason="error"
        if is_error
        else ((final.get("finish_reason") or "") if final else ""),
        token_usage=token_usage,
        input_tokens=token_usage.get("input_tokens") if token_usage else None,
        output_tokens=token_usage.get("output_tokens") if token_usage else None,
        tool_count=tool_count,
        is_error=is_error,
        total_ms=total_ms,
        final_content=(final.get("content") or None) if final else None,
    )


def _build_eval_trace(
    payloads: list[dict[str, Any]],
    input_text: str,
    agent_id: str,
    session_id: str,
    turn_start: float,
    agent_tags: tuple[str, ...] = (),
) -> EvalTrace:
    outcome = _parse_turn_outcome(payloads, turn_start)
    steps: list[EvalStep] = []
    retrieval_context: list[str] = []
    tools_called: list[str] = []
    error: str | None = None

    for p in payloads:
        kind = p.get("kind")
        if kind == "tool_call":
            steps.append(
                EvalStep(
                    kind="tool_call",
                    tool_name=p.get("tool_name"),
                    call_id=p.get("call_id"),
                    arguments=p.get("arguments") or {},
                )
            )
            if p.get("tool_name"):
                tools_called.append(p["tool_name"])
        elif kind == "tool_result":
            content = p.get("content", "")
            is_err = p.get("is_error", False)
            steps.append(
                EvalStep(
                    kind="tool_result",
                    tool_name=p.get("tool_name"),
                    call_id=p.get("call_id"),
                    content=content,
                    is_error=is_err,
                )
            )
            if not is_err:
                sources = p.get("sources") or []
                if sources:
                    retrieval_context.extend(
                        s["content"] for s in sources if s.get("content")
                    )
                elif content:
                    retrieval_context.append(content)
        elif kind == "final":
            steps.append(EvalStep(kind="final", content=p.get("content")))
        elif kind == "node_error":
            steps.append(
                EvalStep(
                    kind="node_error",
                    node_id=p.get("node_id"),
                    error_message=p.get("error_message"),
                )
            )
        elif kind == "awaiting_human":
            steps.append(EvalStep(kind="awaiting_human"))
        elif kind == "execution_error":
            error = p.get("message")

    return EvalTrace(
        session_id=session_id,
        agent_id=agent_id,
        agent_tags=agent_tags,
        input=input_text,
        output=outcome.final_content,
        error=error,
        latency_ms=outcome.total_ms,
        model_name=outcome.model_name,
        token_usage=outcome.token_usage,
        finish_reason=outcome.finish_reason or None,
        steps=tuple(steps),
        retrieval_context=tuple(retrieval_context),
        tools_called=tuple(tools_called),
    )


def _emit_turn_completed(
    container: PodApplicationContext,
    *,
    session_id: str | None,
    exchange_id: str,
    user_id: str,
    team_id: str | None,
    agent_instance_id: str | None,
    agent_instance_name: str | None,
    template_agent_id: str | None,
    payloads: list[dict[str, Any]],
    turn_start: float,
) -> None:
    """
    Emit turn KPIs after the SSE stream closes.

    Two metrics are emitted:

    agent.turn_completed (Histogram, ms):
      Low-cardinality Prometheus dims only — session_id and exchange_id are
      intentionally excluded to avoid high-cardinality label explosions.
      finish_reason="error" when the turn ended with execution_error instead
      of a normal final event.
      Quantities (token counters, tool count) become Prometheus counters via
      the KPI store's quantities path.

    agent.turn_error_total (Counter):
      Incremented only on execution_error turns.  Lets Prometheus alert on
      the error rate without filtering histograms by label value.
    """
    try:
        kpi = get_runtime_context().get_kpi_writer()
        outcome = _parse_turn_outcome(payloads, turn_start)
        runtime_id = get_runtime_context().config.service_name

        # Prometheus-safe dims: low-cardinality only.
        # session_id, exchange_id, user_id, agent_instance_id are per-turn
        # UUIDs — they must NOT become Prometheus labels (cardinality bomb).
        # They are available in history rows and SSE logs for per-turn tracing.
        prom_dims: dict[str, str | None] = {
            "team_id": team_id,
            "template_agent_id": template_agent_id,
            "agent_instance_id": agent_instance_id,
            "agent_instance_name": agent_instance_name,
            "runtime_id": runtime_id,
            "model_name": outcome.model_name,
            "finish_reason": outcome.finish_reason,
        }

        kpi.emit(
            name="agent.turn_completed",
            type="timer",
            value=outcome.total_ms,
            unit="ms",
            dims=prom_dims,
            quantities={
                "tool_count": outcome.tool_count,
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
            },
            actor=KPIActor(type="human", user_id=user_id),
        )

        if outcome.is_error:
            kpi.emit(
                name="agent.turn_error_total",
                type="counter",
                value=1,
                dims=prom_dims,
                actor=KPIActor(type="human", user_id=user_id),
            )

        # Append to container ring buffer (high-cardinality fields safe here).
        record = cast(
            KpiTurnRecord,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "exchange_id": exchange_id,
                "user_id": user_id,
                "total_ms": outcome.total_ms,
                "is_error": outcome.is_error,
                **prom_dims,
                "tool_count": outcome.tool_count,
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
            },
        )
        with container._kpi_turns_lock:
            container.kpi_turns_buffer.append(record)
    except Exception:
        logger.exception("[fred-runtime][kpi] Failed to emit agent.turn_completed")


async def _stream(
    definition: ReActAgentDefinition | GraphAgentDefinition,
    request: _AgentExecuteRequest,
    access_token: str | None = None,
    *,
    team_id: str | None = None,
    agent_instance_name: str | None = None,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition] | None = None,
    security_enabled: bool = False,
    container: PodApplicationContext,
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

    Team resolution:
    - team_id is resolved once here so KPI, history, and the agent runtime all
      see the same identity; in no-security standalone mode it defaults to
      "personal" when the caller omits it.
    """
    ctx = request.context or {}
    session_id: str | None = ctx.get("session_id")
    user_id: str = ctx.get("user_id") or "unknown"
    exchange_id = str(uuid4())
    turn_start = time.monotonic()

    # Resolve team identity once so all downstream calls (runtime, KPI, history)
    # carry the same value.  Standalone no-security default: "personal".
    resolved_team_id: str | None = team_id or ctx.get("team_id")
    if not security_enabled and not resolved_team_id:
        resolved_team_id = "personal"

    collected: list[dict[str, Any]] = []
    async for payload in _iterate_runtime_event_payloads(
        definition,
        request,
        access_token=access_token,
        team_id=resolved_team_id,
        registry=registry,
        exchange_id=exchange_id,
    ):
        collected.append(payload)
        yield _sse(json.dumps(payload, ensure_ascii=False))

    _emit_turn_completed(
        container,
        session_id=session_id,
        exchange_id=exchange_id,
        user_id=user_id,
        team_id=resolved_team_id,
        agent_instance_id=request.agent_instance_id,
        agent_instance_name=agent_instance_name,
        template_agent_id=definition.agent_id,
        payloads=collected,
        turn_start=turn_start,
    )

    # Fire-and-forget: write history after the SSE stream is fully sent.
    # The client already received all events before this task begins.
    if session_id:
        history_store = get_runtime_context().config.history_store
        if history_store is not None:
            asyncio.create_task(
                _write_turn_history(
                    session_id=session_id,
                    user_id=user_id,
                    request_message=request.message,
                    payloads=collected,
                    history_store=history_store,
                    team_id=resolved_team_id,
                    agent_instance_id=request.agent_instance_id,
                    exchange_id=exchange_id,
                    resume_payload=request.resume_payload,
                )
            )


async def _iterate_runtime_event_payloads(
    definition: ReActAgentDefinition | GraphAgentDefinition,
    request: _AgentExecuteRequest,
    access_token: str | None = None,
    *,
    team_id: str | None = None,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition] | None = None,
    exchange_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Execute one agent turn and yield runtime-event payloads as JSON-ready dicts.

    Why this helper exists:
    - both `/agents/execute` and `/agents/execute/stream` share the same runtime
      wiring and event production path
    - keeping the generator payload-oriented lets the HTTP layer choose whether
      it renders SSE or returns a terminal JSON response

    team_id:
    - callers are responsible for resolving the effective team before calling this
      function; see _stream() for the standalone "personal" default logic
    - None is accepted for agent-to-agent (AgentInvoker) invocations where no
      team scope is required

    access_token:
    - the user's JWT forwarded via the Authorization header
    - stored in RuntimeContext so KF tool adapters can use it for outbound calls
    - None in local dev when security is disabled
    """

    request_id = str(uuid4())
    ctx = request.context or {}
    correlation_id = ctx.get("correlation_id", request_id)
    resolved_team_id = team_id or ctx.get("team_id")
    execution_action = ctx.get("execution_action") or (
        ExecutionGrantAction.RESUME.value
        if request.resume_payload is not None
        else ExecutionGrantAction.EXECUTE.value
    )
    resolved_checkpoint_id = request.checkpoint_id or ctx.get("checkpoint_id")

    portable_context = PortableContext(
        request_id=request_id,
        correlation_id=correlation_id,
        actor=ctx.get("user_id", "anonymous"),
        tenant=ctx.get("tenant", "default"),
        environment=PortableEnvironment.DEV,
        trace_id=ctx.get("trace_id"),
        agent_id=definition.agent_id,
        agent_name=definition.agent_id,
        session_id=ctx.get("session_id"),
        user_id=ctx.get("user_id"),
        team_id=resolved_team_id,
        baggage={
            key: value
            for key, value in {
                "agent_instance_id": request.agent_instance_id,
                "template_agent_id": definition.agent_id,
                "checkpoint_id": resolved_checkpoint_id,
                "execution_action": execution_action,
                "exchange_id": exchange_id,
            }.items()
            if isinstance(value, str) and value
        },
    )

    runtime_context = RuntimeContext(
        session_id=ctx.get("session_id"),
        exchange_id=exchange_id,
        checkpoint_id=resolved_checkpoint_id,
        user_id=ctx.get("user_id"),
        team_id=resolved_team_id,
        user_groups=ctx.get("user_groups"),
        language=ctx.get("language"),
        access_token=access_token,
        refresh_token=ctx.get("refresh_token"),
        access_token_expires_at=ctx.get("access_token_expires_at"),
        trace_id=ctx.get("trace_id"),
        correlation_id=correlation_id,
        agent_instance_id=request.agent_instance_id,
        template_agent_id=definition.agent_id,
        execution_action=execution_action,
        # Chat options forwarded from the frontend RuntimeContext.
        # These were present in ctx but were silently dropped, causing
        # ContextAwareTool and all KF search helpers to always use defaults.
        selected_document_libraries_ids=ctx.get("selected_document_libraries_ids"),
        selected_document_uids=ctx.get("selected_document_uids"),
        selected_chat_context_ids=ctx.get("selected_chat_context_ids"),
        search_policy=ctx.get("search_policy"),
        search_rag_scope=ctx.get("search_rag_scope"),
        include_session_scope=ctx.get("include_session_scope"),
        include_corpus_scope=ctx.get("include_corpus_scope"),
        deep_search=ctx.get("deep_search"),
        # The marketplace/library prompt selected for the conversation. The
        # control-plane resolves the session's attached prompts into this scalar
        # at prepare-execution and the frontend forwards it — but it was also
        # silently dropped here, so no agent ever received a selected prompt.
        context_prompt_text=ctx.get("context_prompt_text"),
        # Rebuilt by the frontend from the attachments that currently exist.
        # When the final file is deleted this is absent, so the per-turn runtime
        # notice disappears without leaving a checkpointed system message behind.
        attachments_markdown=ctx.get("attachments_markdown"),
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
    # session_id drives LangGraph checkpointing: the agent resumes its graph
    # state on every turn. Falls back to request_id for one-shot calls so
    # LangGraph's checkpointer invariant (thread_id required internally) is met.
    execution_config = ExecutionConfig(
        session_id=ctx.get("session_id") or request_id,
        checkpoint_id=request.checkpoint_id,
        resume_payload=request.resume_payload,
        invocation_turns=getattr(request, "invocation_turns", ()),
    )

    runtime: ReActRuntime | GraphRuntime | None = None
    try:
        if isinstance(definition, GraphAgentDefinition):
            runtime = GraphRuntime(
                definition=definition,
                services=services,
            )
            runtime.bind(binding)
            await runtime.activate()
            executor = await runtime.get_executor()
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
            async for event in executor.stream(graph_input, execution_config):
                payload = event.model_dump(mode="json")
                if not isinstance(payload, dict):
                    raise RuntimeError(
                        "RuntimeEvent payload must serialize to a JSON object."
                    )
                yield payload
        else:
            runtime = ReActRuntime(
                definition=definition,
                services=services,
            )
            runtime.bind(binding)
            await runtime.activate()
            executor = await runtime.get_executor()
            # On HITL resume, messages are ignored by the codec — the graph
            # resumes from its checkpointed interrupt via Command(resume=...).
            # On a normal turn, the user message is the only input.
            react_input = ReActInput(
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
            async for event in executor.stream(react_input, execution_config):
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
        yield RuntimeErrorEvent(message=str(exc)).model_dump(mode="json")
    finally:
        if runtime is not None:
            await runtime.dispose()


def _terminal_execute_payload(
    payloads: list[dict[str, Any]],
) -> RuntimeEvent | _RuntimeErrorPayload:
    """
    Select and validate the terminal payload returned by `/agents/execute`.

    Why this helper exists:
    - non-streaming callers want one deterministic response object
    - different runtimes may emit several intermediate events before the
      terminal outcome, so the endpoint should consistently return the final
      event when present and otherwise fall back to the last emitted payload
    - the HTTP contract should stay strongly typed even when execution fails
      before producing a terminal runtime event

    How to use it:
    - pass the collected event payloads from `_iterate_runtime_event_payloads`

    Example:
    - `payload = _terminal_execute_payload(payloads)`
    """

    if not payloads:
        return _RuntimeErrorPayload(error="Agent execution produced no runtime events.")
    adapter = _execute_response_adapter()
    for payload in reversed(payloads):
        if payload.get("kind") == "final":
            return adapter.validate_python(payload)
    return adapter.validate_python(payloads[-1])


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

    # Used by non-execute routes that only need authentication (no user injection).
    _auth_deps = [Depends(get_current_user)] if security_enabled else []

    # Inject the authenticated user when security is enabled so that execute
    # handlers can perform the bearer-token / grant user_id correlation check.
    # Returns None in local-dev mode so dev pods start without Keycloak.
    _authenticated_user = _make_user_dependency(get_current_user, security_enabled)

    @router.get("")
    async def list_agents() -> list[str]:
        """Return the agent IDs registered in this pod."""
        return list(registry.keys())

    @router.get("/kpi-turns", dependencies=_auth_deps)
    async def get_kpi_turns(
        limit: int = 50,
        container: PodApplicationContext = Depends(get_pod_container),
        caller: KeycloakUser | None = Depends(_authenticated_user),
    ) -> list[KpiTurnRecord]:
        """
        Return recent agent.turn_completed KPI events, newest first.

        GET <base_url>/agents/kpi-turns?limit=50

        Each entry includes: ts, session_id, exchange_id, user_id, total_ms,
        is_error, team_id, template_agent_id, runtime_id, model_name,
        finish_reason, tool_count, input_tokens, output_tokens.

        Why this endpoint exists:
        - developers need to validate KPI emission from the CLI without
          Grafana or Prometheus; this exposes the pod-local ring buffer
        - max 200 entries retained in memory (oldest evicted automatically)
        """
        rebac = get_runtime_context().config.rebac_engine
        if caller is not None and rebac is not None and rebac.enabled:
            await rebac.check_user_permission_or_raise(
                caller, OrganizationPermission.CAN_READ_METRICS, ORGANIZATION_ID
            )
        with container._kpi_turns_lock:
            events = list(container.kpi_turns_buffer)
        events.reverse()
        return events[: max(1, limit)]

    @router.get("/audit-events", dependencies=_auth_deps)
    async def get_audit_events(
        limit: int = 50,
        container: PodApplicationContext = Depends(get_pod_container),
        caller: KeycloakUser | None = Depends(_authenticated_user),
    ) -> list[AuditEventRecord]:
        """
        Return recent security audit events, newest first.

        GET <base_url>/agents/audit-events?limit=50

        Audit events include: grant_validated, grant_validation_failed,
        grant_user_mismatch, grant_user_correlated.

        Why this endpoint exists:
        - security audit events go to the fred.security.audit logger AND to
          this ring buffer so the CLI can query them directly
        - max 200 entries retained in memory
        """
        rebac = get_runtime_context().config.rebac_engine
        if caller is not None and rebac is not None and rebac.enabled:
            await rebac.check_user_permission_or_raise(
                caller, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
            )
        with container._audit_events_lock:
            events = list(container.audit_events_buffer)
        events.reverse()
        return events[: max(1, limit)]

    @router.get("/templates")
    async def list_agent_templates(
        include_non_public: bool = False,
    ) -> list[_AgentTemplateSummary]:
        """
        Return the executable agent templates registered in this pod.

        Why this endpoint exists:
        - control-plane business admin flows need a read-only catalog of
          executable templates without exposing runtime CRUD or class-path
          authoring

        How to use it:
        - call from control-plane to aggregate template metadata across pods
        - pass `include_non_public=true` to also list internal agents
          (`AgentDefinition.public=False`) for tooling such as the self-test
          harness; the default catalog hides them (see AGENT-VISIBILITY-RFC)

        Example:
        - `GET /fred/agents/v2/agents/templates`
        """

        return [
            _AgentTemplateSummary(
                template_agent_id=definition.agent_id,
                title=definition.role,
                description=definition.description,
                description_by_lang=getattr(definition, "description_by_lang", None),
                kind=definition.execution_category,
                default_tuning=_definition_to_agent_tuning(definition),
                available_mcp_servers=_available_mcp_servers_for_definition(definition),
            )
            for definition in registry.values()
            if include_non_public or getattr(definition, "public", True)
        ]

    @router.get("/mcp-catalog")
    async def get_mcp_catalog() -> _McpCatalogResponse:
        """
        Return the full MCP server catalog declared in mcp_catalog.yaml.

        Why this endpoint exists:
        - control-plane drift detection needs to compare stored instance
          selections against the live pod catalog at listing time
        - returns ALL servers (enabled and disabled) so the caller can
          distinguish "configured but disabled" from "absent from catalog"

        How to use it:
        - call from control-plane agent-instance listing to populate
          catalog_warnings when stored mcp_server_ids are no longer present

        Example:
        - `GET /fred/agents/v2/agents/mcp-catalog`
        """
        mcp_configuration = get_runtime_context().config.mcp_configuration
        if mcp_configuration is None:
            return _McpCatalogResponse(servers=[])
        return _McpCatalogResponse(
            servers=[
                _McpCatalogEntry(
                    id=srv.id,
                    name=srv.name,
                    description=srv.description,
                    enabled=srv.enabled,
                    transport=srv.transport,
                )
                for srv in mcp_configuration.servers
            ]
        )

    @router.get("/sessions")
    async def list_sessions(
        caller: KeycloakUser | None = Depends(_authenticated_user),
        user_id: str | None = None,
    ) -> list[str]:
        """
        Return the session IDs for the authenticated user, most recent first.

        GET <configured base_url>/agents/sessions
        Authorization: Bearer <user JWT>

        Security: user identity is always extracted from the JWT token.
        The user_id query parameter is accepted only in dev mode (security
        disabled) for CLI convenience; it is ignored when security is enabled.
        """
        history_store = get_runtime_context().config.history_store
        if history_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No history store configured — session listing is unavailable.",
            )
        effective_uid = caller.uid if caller is not None else user_id
        if effective_uid is None:
            return []
        return await history_store.list_sessions(user_id=effective_uid)

    @router.get(
        "/sessions/{session_id}/messages",
        response_model=list[ChatMessage],
    )
    async def get_session_messages(
        session_id: str,
        caller: KeycloakUser | None = Depends(_authenticated_user),
    ) -> list[ChatMessage]:
        """
        Return the conversation history for a session as a flat message list.

        GET <configured base_url>/agents/sessions/{session_id}/messages
        Authorization: Bearer <user JWT>

        Security: only rows belonging to the authenticated user are returned.
        Returns [] when the session does not exist or belongs to another user —
        callers cannot distinguish the two cases by design.

        Returns 503 when no history store is configured (stateless pod mode).
        """
        history_store = get_runtime_context().config.history_store
        if history_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No history store configured — session history is unavailable.",
            )
        caller_uid = caller.uid if caller is not None else None
        return await history_store.get(session_id=session_id, user_id=caller_uid)

    @router.delete(
        "/sessions/{session_id}",
        status_code=status.HTTP_200_OK,
    )
    async def delete_session_history(
        session_id: str,
        caller: KeycloakUser | None = Depends(_authenticated_user),
    ) -> dict[str, int]:
        """
        Permanently delete history rows for a session.

        DELETE <base_url>/agents/sessions/{session_id}

        Security: only rows belonging to the authenticated user are deleted.
        Returns {"deleted": 0} when the session does not exist or belongs to
        another user — callers cannot distinguish the two cases by design.

        Checkpoint state is NOT touched; delete separately via
        DELETE /agents/checkpoints/{session_id} if required.

        Returns 503 when no history store is configured.
        """
        history_store = get_runtime_context().config.history_store
        if history_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No history store configured — session history is unavailable.",
            )
        caller_uid = caller.uid if caller is not None else None
        if await _caller_can_manage_platform(caller):
            # Platform admin (e.g. CTRLP-12 lifecycle erase-at-expiry): delete every
            # row for the session, not just the caller's — ownership is waived,
            # authentication stays enforced upstream.
            caller_uid = None
        count = await history_store.delete_session(
            session_id=session_id, user_id=caller_uid
        )
        return {"deleted": count}

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

    def _get_history_store_for_owned_access(
        caller: KeycloakUser | None,
    ) -> HistoryStorePort | None:
        """Return the history store used as ownership oracle, failing closed.

        Why this helper exists:
        - checkpoint tables do not carry user_id, so ownership checks depend on
          the history store
        - when security is enabled, proceeding without that oracle would leak
          checkpoint visibility across users

        How to use it:
        - call from checkpoint endpoints before listing or mutating per-session
          checkpoint data
        """
        if caller is None:
            return None
        history_store = get_runtime_context().config.history_store
        if history_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "No history store configured — ownership checks are unavailable."
                ),
            )
        return history_store

    @router.get("/checkpoints")
    async def list_checkpoint_threads(
        caller: KeycloakUser | None = Depends(_authenticated_user),
        limit: int = 100,
    ) -> list[_CheckpointThreadSummary]:
        """
        List all checkpoint threads stored in this pod, newest first.

        GET <base_url>/agents/checkpoints?limit=<n>

        Returns one summary row per session_id with:
        - checkpoint count and timestamps (first / latest)
        - total size of checkpoint pointer structures (checkpoint_bytes_total)
        - total channel-state blob count and bytes for the thread (blob_*)
        - pending uncommitted write count

        Blob bytes are aggregated at thread level because LangGraph deduplicates
        blobs by (channel, version) — the same blob version may be referenced
        by multiple checkpoints in the same thread.

        Returns 503 when the pod has no persistent storage configured.
        """
        from sqlalchemy import desc, func, select

        cp = _get_checkpointer()
        await cp._ensure_tables()
        ct = cp.checkpoints_table
        bt = cp.blobs_table
        wt = cp.writes_table

        async with cp.store.begin() as conn:
            # Subquery: blob aggregates per thread (deduped by channel/version)
            blob_sub = (
                select(
                    bt.c.thread_id,
                    func.count(bt.c.version).label("blob_cnt"),
                    func.sum(func.length(bt.c.value_blob)).label("blob_bytes"),
                )
                .group_by(bt.c.thread_id)
                .subquery("blob_agg")
            )
            # Subquery: pending write count per thread
            write_sub = (
                select(
                    wt.c.thread_id,
                    func.count(wt.c.idx).label("write_cnt"),
                )
                .group_by(wt.c.thread_id)
                .subquery("write_agg")
            )
            stmt = (
                select(
                    ct.c.thread_id,
                    func.count(ct.c.checkpoint_id).label("cnt"),
                    func.min(ct.c.created_at).label("first"),
                    func.max(ct.c.created_at).label("latest"),
                    func.sum(func.length(ct.c.checkpoint_blob)).label("cp_bytes"),
                    blob_sub.c.blob_cnt,
                    blob_sub.c.blob_bytes,
                    write_sub.c.write_cnt,
                )
                .outerjoin(blob_sub, blob_sub.c.thread_id == ct.c.thread_id)
                .outerjoin(write_sub, write_sub.c.thread_id == ct.c.thread_id)
                .group_by(
                    ct.c.thread_id,
                    blob_sub.c.blob_cnt,
                    blob_sub.c.blob_bytes,
                    write_sub.c.write_cnt,
                )
                .order_by(desc(func.max(ct.c.created_at)))
                .limit(limit)
            )
            rows = (await conn.execute(stmt)).fetchall()

        # Scope to the caller's own sessions using the history store as the
        # ownership oracle (checkpoint tables carry no user_id column).
        caller_uid = caller.uid if caller is not None else None
        history_store = _get_history_store_for_owned_access(caller)
        if caller_uid is not None and history_store is not None:
            owned = set(await history_store.list_sessions(user_id=caller_uid))
            rows = [r for r in rows if str(r.thread_id) in owned]

        return [
            _CheckpointThreadSummary(
                session_id=str(row.thread_id),
                checkpoint_count=int(row.cnt),
                first_created_at=str(row.first) if row.first else None,
                latest_created_at=str(row.latest) if row.latest else None,
                checkpoint_bytes_total=int(row.cp_bytes or 0),
                blob_count=int(row.blob_cnt or 0),
                blob_bytes_total=int(row.blob_bytes or 0),
                pending_write_count=int(row.write_cnt or 0),
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

    @router.get("/checkpoints/{session_id}")
    async def get_checkpoint_thread(
        session_id: str,
        caller: KeycloakUser | None = Depends(_authenticated_user),
    ) -> _CheckpointThreadDetail:
        """
        Return all checkpoints for one session, newest first.

        GET <base_url>/agents/checkpoints/{session_id}

        Each entry includes:
        - checkpoint_id, parent_checkpoint_id, created_at
        - step and source from metadata (LangGraph turn progression)
        - node_names: which graph node(s) produced output at this step
          (empty for source="input", i.e. human-turn ingestion checkpoints)
        - checkpoint_bytes: size of the checkpoint pointer structure blob
        - pending_write_count: uncommitted writes for this checkpoint_id
        - raw metadata dict for full inspection

        Blobs (channel state) are NOT deserialized — use checkpoint_bytes to
        understand the pointer structure cost.  Session-level blob totals are
        in the /checkpoints listing.

        Returns 503 when no checkpointer is configured.
        Returns an empty checkpoints list when the session has no rows.
        Returns 403 when the session does not belong to the authenticated user.
        """
        caller_uid = caller.uid if caller is not None else None
        history_store = _get_history_store_for_owned_access(caller)
        if (
            caller_uid is not None
            and history_store is not None
            and not await history_store.session_belongs_to_user(session_id, caller_uid)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied.",
            )

        from sqlalchemy import desc, func, select

        cp = _get_checkpointer()
        await cp._ensure_tables()
        ct = cp.checkpoints_table
        wt = cp.writes_table

        async with cp.store.begin() as conn:
            # Subquery: pending write count per checkpoint_id in this session
            write_sub = (
                select(
                    wt.c.checkpoint_id,
                    func.count(wt.c.idx).label("write_cnt"),
                )
                .where(wt.c.thread_id == session_id)
                .group_by(wt.c.checkpoint_id)
                .subquery("write_agg")
            )
            rows = (
                await conn.execute(
                    select(
                        ct.c.checkpoint_id,
                        ct.c.parent_checkpoint_id,
                        ct.c.created_at,
                        ct.c.metadata_json,
                        func.length(ct.c.checkpoint_blob).label("cp_bytes"),
                        write_sub.c.write_cnt,
                    )
                    .outerjoin(
                        write_sub,
                        write_sub.c.checkpoint_id == ct.c.checkpoint_id,
                    )
                    .where(ct.c.thread_id == session_id)
                    .order_by(desc(ct.c.created_at), desc(ct.c.checkpoint_id))
                )
            ).fetchall()

        def _node_names(meta: dict[str, Any]) -> list[str]:
            writes = meta.get("writes") or {}
            if isinstance(writes, dict):
                return [k for k in writes if k != "__error__"]
            return []

        return _CheckpointThreadDetail(
            session_id=session_id,
            checkpoints=[
                _CheckpointEntry(
                    checkpoint_id=str(row.checkpoint_id),
                    parent_checkpoint_id=(
                        str(row.parent_checkpoint_id)
                        if row.parent_checkpoint_id
                        else None
                    ),
                    created_at=str(row.created_at) if row.created_at else None,
                    step=meta.get("step"),
                    source=meta.get("source"),
                    node_names=_node_names(meta),
                    checkpoint_bytes=int(row.cp_bytes or 0),
                    pending_write_count=int(row.write_cnt or 0),
                    metadata=dict(meta),
                )
                for row in rows
                for meta in [dict(row.metadata_json or {})]
            ],
        )

    @router.delete(
        "/checkpoints/{session_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_model=None,
    )
    async def delete_checkpoint_thread(
        session_id: str,
        caller: KeycloakUser | None = Depends(_authenticated_user),
    ) -> None:
        """
        Purge all checkpoint data for one session.

        DELETE <base_url>/agents/checkpoints/{session_id}

        Security: the session must belong to the authenticated user.
        Returns 403 when ownership cannot be confirmed via the history store.

        Deletes all rows in the checkpoints, blobs, and writes tables.
        History store rows are NOT deleted — use DELETE /sessions/{session_id}
        to remove those separately.

        Returns 204 on success, 403 when not owned, 503 when no checkpointer.
        """
        caller_uid = caller.uid if caller is not None else None
        history_store = _get_history_store_for_owned_access(caller)
        if (
            not await _caller_can_manage_platform(caller)
            and caller_uid is not None
            and history_store is not None
            and not await history_store.session_belongs_to_user(session_id, caller_uid)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied.",
            )
        cp = _get_checkpointer()
        await cp.adelete_thread(session_id)

    @router.post(
        "/execute",
        response_model=RuntimeEvent | _RuntimeErrorPayload,
    )
    async def execute(
        request: RuntimeExecuteRequest,
        http_request: Request,
        authenticated_user: KeycloakUser | None = Depends(_authenticated_user),
        container: PodApplicationContext = Depends(get_pod_container),
    ) -> RuntimeEvent | _RuntimeErrorPayload:
        """
        Execute one agent turn and return the terminal RuntimeEvent as JSON.

        POST <configured base_url>/agents/execute
        Authorization: Bearer <user JWT>
        Body: RuntimeExecuteRequest (agent_instance_id + runtime_context.team_id for managed exec)
        Response: application/json containing the terminal runtime payload

        Security (RUNTIME-07 rev. 2 — the pod is the execution authority):
        - Identity is the caller's Keycloak JWT (validated against Keycloak JWKS).
        - Authorization is a pod-side OpenFGA check on runtime_context.team_id,
          enforced per request. There is NO control-plane-signed grant.
        - Managed instances resolve their template+tuning from the control-plane
          team-scoped binding (config only).

        Architectural note:
        - This endpoint does not implement pod discovery or routing.
          Those concerns belong to Kubernetes Service, Ingress, and Argo CD.
        """
        auth = http_request.headers.get("Authorization", "")
        access_token = auth.removeprefix("Bearer ").strip() or None

        exchange_id = str(uuid4())
        turn_start = time.monotonic()
        internal_req, target = await _authorize_and_resolve(
            request,
            authenticated_user=authenticated_user,
            container=container,
            registry=registry,
            access_token=access_token,
        )
        payloads = [
            payload
            async for payload in _iterate_runtime_event_payloads(
                target.definition,
                internal_req,
                access_token=access_token,
                team_id=target.team_id,
                registry=registry,
                exchange_id=exchange_id,
            )
        ]
        session_id: str | None = request.effective_session_id()
        user_id_str = request.effective_user_id() or "unknown"
        _emit_turn_completed(
            container,
            session_id=session_id,
            exchange_id=exchange_id,
            user_id=user_id_str,
            team_id=target.team_id,
            agent_instance_id=request.agent_instance_id,
            agent_instance_name=target.agent_instance_name,
            template_agent_id=target.definition.agent_id,
            payloads=payloads,
            turn_start=turn_start,
        )
        # Write history after generator is fully consumed.
        # Can await here — no SSE response to block.
        if session_id:
            history_store = get_runtime_context().config.history_store
            if history_store is not None:
                await _write_turn_history(
                    session_id=session_id,
                    user_id=user_id_str,
                    request_message=request.input,
                    payloads=payloads,
                    history_store=history_store,
                    team_id=target.team_id,
                    agent_instance_id=request.agent_instance_id,
                    exchange_id=exchange_id,
                    resume_payload=request.resume_payload,
                )
        return _terminal_execute_payload(payloads)

    @router.post(
        "/evaluate",
        response_model=EvalTrace,
    )
    async def evaluate(
        request: RuntimeExecuteRequest,
        http_request: Request,
        authenticated_user: KeycloakUser | None = Depends(_authenticated_user),
        container: PodApplicationContext = Depends(get_pod_container),
    ) -> EvalTrace:
        """
        Execute one agent turn and return a complete EvalTrace as JSON.

        POST <configured base_url>/agents/evaluate
        Authorization: Bearer <user JWT>
        Body: RuntimeExecuteRequest
        Response: EvalTrace — synchronous, no SSE, no Langfuse dependency

        Intended for evaluation harnesses (DeepEval, Promptfoo) that need
        input, output, retrieval_context, tools_called, and steps in one response.
        """
        auth = http_request.headers.get("Authorization", "")
        access_token = auth.removeprefix("Bearer ").strip() or None

        exchange_id = str(uuid4())
        turn_start = time.monotonic()
        internal_req, target = await _authorize_and_resolve(
            request,
            authenticated_user=authenticated_user,
            container=container,
            registry=registry,
            access_token=access_token,
        )
        payloads = [
            payload
            async for payload in _iterate_runtime_event_payloads(
                target.definition,
                internal_req,
                access_token=access_token,
                team_id=target.team_id,
                registry=registry,
                exchange_id=exchange_id,
            )
        ]
        session_id: str | None = request.effective_session_id()
        eval_session_id = session_id or str(uuid4())
        user_id_str = request.effective_user_id() or "unknown"
        _emit_turn_completed(
            container,
            session_id=session_id,
            exchange_id=exchange_id,
            user_id=user_id_str,
            team_id=target.team_id,
            agent_instance_id=request.agent_instance_id,
            agent_instance_name=target.agent_instance_name,
            template_agent_id=target.definition.agent_id,
            payloads=payloads,
            turn_start=turn_start,
        )
        if session_id:
            history_store = get_runtime_context().config.history_store
            if history_store is not None:
                await _write_turn_history(
                    session_id=session_id,
                    user_id=user_id_str,
                    request_message=request.input,
                    payloads=payloads,
                    history_store=history_store,
                    team_id=target.team_id,
                    agent_instance_id=request.agent_instance_id,
                    exchange_id=exchange_id,
                    resume_payload=request.resume_payload,
                )
        return _build_eval_trace(
            payloads=payloads,
            input_text=request.input or "",
            agent_id=target.definition.agent_id,
            agent_tags=target.definition.tags,
            session_id=eval_session_id,
            turn_start=turn_start,
        )

    @router.post(
        "/execute/stream",
    )
    async def execute_stream(
        request: RuntimeExecuteRequest,
        http_request: Request,
        authenticated_user: KeycloakUser | None = Depends(_authenticated_user),
        container: PodApplicationContext = Depends(get_pod_container),
    ) -> StreamingResponse:
        """
        Stream RuntimeEvent JSON over SSE for a single agent invocation.

        POST <configured base_url>/agents/execute/stream
        Authorization: Bearer <user JWT>
        Body: RuntimeExecuteRequest (agent_instance_id + runtime_context.team_id for managed exec)
        Response: text/event-stream, each `data:` line is a RuntimeEvent JSON

        Stream termination:
        - The stream ends by connection close after the `final` event is delivered.
          There is no sentinel frame. `final` is the only reliable end-of-turn signal.
        - If the execution pipeline raises an unhandled exception, a
          `RuntimeErrorEvent` (kind="execution_error") is emitted instead of `final`,
          and the stream closes immediately after. Clients dispatching on `kind` must
          handle this case; otherwise agent crashes will be silently ignored.

        TurnPersistedEvent:
        - `TurnPersistedEvent` (kind="turn_persisted") is defined in the contract but
          is NOT emitted over this stream. History is written fire-and-forget after the
          stream closes. Do not rely on it as an end-of-turn signal here.

        Security:
        - For managed execution (agent_instance_id), an execution_grant issued by
          control-plane is required. The runtime validates it structurally.
        - RBAC via Keycloak and REBAC via OpenFGA protect this endpoint.

        Architectural note:
        - This endpoint does not implement pod discovery or routing.
          Those concerns belong to Kubernetes Service, Ingress, and Argo CD.
        """
        auth = http_request.headers.get("Authorization", "")
        access_token = auth.removeprefix("Bearer ").strip() or None

        internal_req, target = await _authorize_and_resolve(
            request,
            authenticated_user=authenticated_user,
            container=container,
            registry=registry,
            access_token=access_token,
        )
        return StreamingResponse(
            _stream(
                target.definition,
                internal_req,
                access_token=access_token,
                team_id=target.team_id,
                agent_instance_name=target.agent_instance_name,
                registry=registry,
                security_enabled=security_enabled,
                container=container,
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

    # Capability discovery + boot validation (#1973, RFC §4) — at app
    # CONSTRUCTION, not lifespan (#1977): registered chat parts must join the
    # `UiPart` union at model-build time, before routes capture their
    # response-model schemas, so `app.openapi()` (and the offline
    # `generate_openapi.py` export, which never runs the lifespan) includes
    # capability parts with zero hand edits. Any invalid registration raises
    # a named CapabilityRegistrationError and still aborts pod startup —
    # `create_agent_app` runs during startup, just earlier and louder.
    capability_registry = boot_capability_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Boot order (must be preserved — each step depends on the previous):
        # 1. log_setup         — formatter/handlers ready for all subsequent logs
        # 2. initialize_kpi_writer — needed by bootstrap_observability
        # 3. bootstrap_observability — global tracer + metrics provider
        # 4. attach_pod_container — container in app.state before any request
        # 5. initialize_sql    — async, may take time
        # 6. start_metrics_exporter — prometheus thread, after KPI writer exists
        # 7. start_kpi_tasks   — asyncio tasks, after SQL engine is known
        # 8. set_runtime_context — wires all built parts into the global config
        log_setup(
            service_name=config.app.name,
            log_level=config.app.log_level,
            store=RamLogStore(),
        )
        container = build_pod_container(config)
        container.initialize_kpi_writer()
        bootstrap_observability(
            config.observability, kpi_writer=container.get_kpi_writer()
        )
        attach_pod_container(app, container)
        if security_enabled and user_security is not None:
            from fred_core.security.oidc import initialize_user_security

            initialize_user_security(user_security)
        if security is not None:
            # Enforce the hardened profile (C3) at startup — fails closed.
            from fred_core.security.oidc import apply_security_profile

            apply_security_profile(security)
        # Pod-side authorization engine (RUNTIME-07 rev. 2). The pod authorizes
        # every execution against OpenFGA; a disabled/Noop engine (dev) means
        # identity-only. Safe in all modes — the factory returns a Noop with a
        # KeycloackDisabled admin client when user/m2m auth is off.
        rebac_engine = rebac_factory(security) if security is not None else None
        chat_factory = _build_chat_model_factory(config)
        await container.initialize_sql()
        container.start_metrics_exporter()
        await container.start_kpi_tasks()
        checkpointer = container.get_checkpointer()
        history_store = container.get_history_store()
        if (checkpointer is None) != (history_store is None):
            raise RuntimeError(
                "Invalid runtime storage state: checkpointer and history store must be configured together."
            )
        set_runtime_context(
            FredRuntimeContext(
                RuntimeConfig(
                    knowledge_flow_url=config.ai.knowledge_flow_url,
                    service_name=config.app.name,
                    timeouts=config.ai.timeout,
                    chat_model_factory=chat_factory,
                    checkpointer=checkpointer,
                    history_store=history_store,
                    mcp_configuration=config.get_mcp_configuration(),
                    inprocess_toolkit_factory=build_inprocess_toolkit,
                    control_plane_url=config.platform.control_plane_url,
                    rebac_engine=rebac_engine,
                    security_profile=(
                        security.profile if security is not None else None
                    ),
                    kpi_writer=container.get_kpi_writer(),
                )
            )
        )
        logger.info(
            "[fred-runtime] agent pod started — base_url=%s kf=%s security=%s "
            "checkpointer=%s history=%s metrics=%s agents=%s",
            base_url or "/",
            config.ai.knowledge_flow_url,
            "enabled" if security_enabled else "disabled",
            "sql" if container.get_checkpointer() is not None else "none",
            "sql" if container.get_history_store() is not None else "none",
            "prometheus" if config.observability.kpi.prometheus.enabled else "logging",
            list(registry.keys()),
        )
        yield
        await container.shutdown()

    app = FastAPI(
        title=config.app.name,
        version="0.1.0",
        docs_url=f"{base_url}/docs" if base_url else "/docs",
        redoc_url=f"{base_url}/redoc" if base_url else "/redoc",
        openapi_url=f"{base_url}/openapi.json" if base_url else "/openapi.json",
        lifespan=lifespan,
    )
    app.dependency_overrides[get_config] = _build_config_provider(config)
    app.state.capability_registry = capability_registry

    # CORS — only added when security is provided so local-dev pods stay simple.
    if authorized_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=authorized_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "Authorization"],
        )
        logger.debug("[fred-runtime] CORS allow_origins=%s", authorized_origins)

    # KPI middleware — writer is lazily resolved from app.state because the
    # container (and its KPI writer) is only initialised during lifespan startup.
    app.add_middleware(
        KPIMiddleware,
        kpi=lambda: get_pod_container_from_app(app).get_kpi_writer(),
    )

    api_router = APIRouter(prefix=base_url)
    api_router.include_router(
        _build_agent_router(registry, security_enabled=security_enabled)
    )

    for extra in extra_routers or []:
        api_router.include_router(extra)

    app.include_router(api_router)

    if config.app.openai_compat:
        # F-A: the OpenAI-compat surface executes by agent_id (direct template),
        # which is forbidden under c3. Fail closed rather than expose it there.
        if security is not None and security.profile == "c3":
            raise RuntimeError(
                "security.profile='c3' forbids the OpenAI-compat surface: "
                "/v1/chat/completions executes by agent_id (direct template), "
                "which is not permitted under c3. Set app.openai_compat=false."
            )
        from .openai_compat_router import create_openai_compat_router

        openai_router = create_openai_compat_router(
            registry,
            security_enabled=security_enabled,
        )
        app.include_router(openai_router, prefix="/v1")
        logger.info("[fred-runtime] OpenAI-compat endpoints enabled at /v1")

    return app
