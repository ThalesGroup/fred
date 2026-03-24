"""
Small adapters that make the v2 runtime usable immediately.

Why this file exists:
- The core v2 contracts should stay platform-agnostic.
- Fred still needs a small bridge to exercise those contracts today.
- These adapters are intentionally thin and explicit so they do not become a
  hidden second runtime framework.

Current scope:
- `DefaultFredChatModelFactory` bridges the shared Fred chat model into the
  v2 `ChatModelFactoryPort`.
- `InProcessToolInvoker` lets developers run new v2 agents locally or in tests
  before a full transport-backed tool invoker is wired.
- `FredArtifactPublisher` and `FredResourceReader` make Fred-managed files feel
  like explicit business capabilities rather than raw workspace plumbing.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, cast

import httpx
from fred_core import (
    LogFilter,
    LogQuery,
    LogQueryResult,
    get_keycloak_client_id,
    get_keycloak_url,
)
from fred_core.common import OwnerFilter
from langchain_core.tools import BaseTool
from langfuse import Langfuse

from agentic_backend.application_context import get_app_context, get_default_chat_model
from agentic_backend.common.kf_logs_client import KfLogsClient
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient
from agentic_backend.common.kf_workspace_client import (
    KfWorkspaceClient,
    WorkspaceRetrievalError,
    WorkspaceUploadError,
)
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.common.structures import AgentSettings
from agentic_backend.common.user_token_refresher import (
    refresh_user_access_token_from_keycloak,
)
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    get_document_library_tags_ids,
    get_document_uids,
    get_rag_knowledge_scope,
    get_search_policy,
    get_vector_search_scopes,
)
from agentic_backend.core.agents.v2.authoring.api import (
    ArtifactPublicationError,
    ResourceFetchError,
    ResourceNotFoundError,
)
from agentic_backend.core.agents.v2.contracts.context import (
    ArtifactPublishRequest,
    ArtifactScope,
    BoundRuntimeContext,
    FetchedResource,
    JsonScalar,
    PortableContext,
    PublishedArtifact,
    ResourceFetchRequest,
    ResourceScope,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from agentic_backend.core.agents.v2.contracts.runtime import (
    ArtifactPublisherPort,
    ChatModelFactoryPort,
    ResourceReaderPort,
    SpanPort,
    ToolInvokerPort,
    ToolProviderPort,
    TracerPort,
)
from agentic_backend.core.agents.v2.support.builtins import (
    TOOL_REF_GEO_RENDER_POINTS,
    TOOL_REF_KNOWLEDGE_SEARCH,
    TOOL_REF_LOGS_QUERY,
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
)
from agentic_backend.core.chatbot.chat_schema import GeoPart

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agentic_backend.core.agents.agent_flow import AgentFlow

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_LEVEL_ORDER: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_DEFAULT_LOG_MAX_GROUPS = 8
_DEFAULT_LOG_SAMPLES = 20
_TRACE_MODEL_SPAN_NAMES = frozenset({"v2.graph.model", "v2.react.model"})
_TRACE_AWAIT_HUMAN_SPAN_NAMES = frozenset({"v2.graph.await_human"})
_TRACE_TOOL_SPAN_NAMES = frozenset(
    {"v2.graph.tool", "v2.graph.runtime_tool", "tool.invoke"}
)


class LangfuseSpanAdapter(SpanPort):
    """
    Thin `SpanPort` adapter over a Langfuse span.

    Attributes are buffered and flushed as metadata updates to keep the runtime
    tracing contract generic and side-effect free.
    """

    def __init__(self, span: "_LangfuseSpanLike"):
        self._span = span
        self._metadata: dict[str, object] = {}
        self._ended = False

    def set_attribute(self, key: str, value: JsonScalar) -> None:
        if self._ended:
            return
        self._metadata[key] = value

    def end(self) -> None:
        if self._ended:
            return
        try:
            if self._metadata:
                self._span.update(metadata=dict(self._metadata))
            self._span.end()
        finally:
            self._ended = True


class LangfuseTracerAdapter(TracerPort):
    """
    Langfuse-backed implementation of the v2 runtime tracing port.
    """

    def __init__(self, client: Langfuse):
        self._client = client

    def start_span(
        self,
        *,
        name: str,
        context: PortableContext,
        attributes: Mapping[str, JsonScalar] | None = None,
    ) -> SpanPort:
        trace_seed = (
            context.trace_id
            or context.correlation_id
            or context.request_id
            or context.session_id
            or context.actor
        )
        trace_id = self._client.create_trace_id(seed=trace_seed)
        metadata: dict[str, object] = {
            "agent_id": context.agent_id,
            "agent_name": context.agent_name,
            "session_id": context.session_id,
            "fred_session_id": context.session_id,
            "correlation_id": context.correlation_id,
            "request_id": context.request_id,
            "actor": context.actor,
            "user_id": context.user_id,
            "user_name": context.user_name,
            "team_id": context.team_id,
            "tenant": context.tenant,
            "environment": context.environment.value,
        }
        if attributes:
            metadata.update(attributes)
        span = cast(
            "_LangfuseSpanLike",
            self._client.start_observation(
                name=name,
                as_type="span",
                trace_context={"trace_id": trace_id},
                metadata=metadata,
            ),
        )
        return LangfuseSpanAdapter(span)


_LANGFUSE_TRACER: TracerPort | None | bool = False


class _LangfuseSpanLike(Protocol):
    def update(
        self, *, metadata: Mapping[str, object] | None = None, **kwargs
    ) -> object: ...

    def end(self, *, end_time: int | None = None) -> object: ...


def build_langfuse_tracer() -> TracerPort | None:
    """
    Return a shared Langfuse tracer when credentials are configured.
    """

    global _LANGFUSE_TRACER
    if _LANGFUSE_TRACER is not False:
        return _LANGFUSE_TRACER if isinstance(_LANGFUSE_TRACER, TracerPort) else None

    has_public = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
    has_secret = bool(os.getenv("LANGFUSE_SECRET_KEY"))
    if not (has_public and has_secret):
        _LANGFUSE_TRACER = None
        return None

    try:
        _LANGFUSE_TRACER = LangfuseTracerAdapter(Langfuse())
    except Exception:
        logger.exception("[V2][TRACING] Failed to initialize Langfuse tracer.")
        _LANGFUSE_TRACER = None
    return _LANGFUSE_TRACER if isinstance(_LANGFUSE_TRACER, TracerPort) else None


class DefaultFredChatModelFactory(ChatModelFactoryPort):
    """
    Thin adapter over Fred's current global default chat model.

    This keeps the v2 runtime executable today without baking the global model
    lookup directly into the runtime implementation itself.
    """

    def build(self, definition, binding):  # type: ignore[override]
        return get_default_chat_model()


ToolHandler = Callable[
    [ToolInvocationRequest], ToolInvocationResult | Awaitable[ToolInvocationResult]
]


class InProcessToolInvoker(ToolInvokerPort):
    """
    Minimal local tool invoker keyed by declared tool ref.

    This is a development bridge, not a final transport layer. Its value is to
    let the new v2 definitions run against typed tool contracts immediately
    while Fred's longer-term registry or MCP-backed invocation path is designed.
    """

    def __init__(self, *, handlers: Mapping[str, ToolHandler]):
        self._handlers = dict(handlers)

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        handler = self._handlers.get(request.tool_ref)
        if handler is None:
            raise RuntimeError(
                f"No in-process tool handler registered for {request.tool_ref!r}."
            )
        result = handler(request)
        if inspect.isawaitable(result):
            return await result
        return result


class CompositeToolInvoker(ToolInvokerPort):
    """
    Dispatch local registered tool refs first, then fall back to Fred defaults.

    This is the runtime bridge that lets a declarative v2 definition expose
    domain-specific tool refs without teaching the shared runtime about each
    business tool individually.
    """

    def __init__(
        self,
        *,
        handlers: Mapping[str, ToolHandler],
        fallback: ToolInvokerPort | None = None,
    ) -> None:
        self._handlers = dict(handlers)
        self._fallback = fallback

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        handler = self._handlers.get(request.tool_ref)
        if handler is not None:
            result = handler(request)
            if inspect.isawaitable(result):
                return await result
            return result
        if self._fallback is None:
            raise RuntimeError(f"No tool handler registered for {request.tool_ref!r}.")
        return await self._fallback.invoke(request)


@dataclass(frozen=True)
class _LogEventSnapshot:
    source: str
    ts: float
    level: str
    logger: str
    file: str
    line: int
    msg: str
    extra: dict[str, object] | None


class _GroupedLogEvent(TypedDict):
    source: str
    level: str
    file: str
    line: int
    msg: str
    count: int
    first_ts: float
    last_ts: float


class _TraceAggregate(TypedDict):
    name: str
    count: int
    total_ms: int
    max_ms: int


class FredKnowledgeSearchToolInvoker(ToolInvokerPort):
    """
    First concrete Fred-side tool invoker for v2 agents.

    Current scope:
    - exposes transport-independent built-in tool refs from `builtin_tools.py`

    Why this limited shape is intentional:
    - it makes the new RAG agent immediately useful from the UI
    - it keeps the first production integration small
    - it leaves room for a later registry/MCP-backed invoker without changing the
      agent definition contract again
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self._settings = settings
        self.rebind(binding)

    def rebind(self, binding: BoundRuntimeContext) -> None:
        self._binding = binding
        self._search_client = VectorSearchClient(
            agent=_VectorSearchAgentShim(binding=binding, settings=self._settings)
        )
        self._logs_client = KfLogsClient(
            agent=_VectorSearchAgentShim(binding=binding, settings=self._settings)
        )
        self._builtins: dict[str, ToolHandler] = {
            TOOL_REF_KNOWLEDGE_SEARCH: self._invoke_knowledge_search,
            TOOL_REF_LOGS_QUERY: self._invoke_logs_query,
            TOOL_REF_TRACES_SUMMARIZE_CONVERSATION: self._invoke_traces_summarize_conversation,
            TOOL_REF_GEO_RENDER_POINTS: self._invoke_geo_render_points,
        }

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        handler = self._builtins.get(request.tool_ref)
        if handler is not None:
            result = handler(request)
            if inspect.isawaitable(result):
                return await result
            return result
        raise RuntimeError(f"Unsupported Fred tool ref: {request.tool_ref!r}")

    async def _invoke_knowledge_search(
        self, request: ToolInvocationRequest
    ) -> ToolInvocationResult:
        payload = request.payload
        nested_payload = payload.get("payload")
        nested_dict = nested_payload if isinstance(nested_payload, dict) else None
        query = payload.get("query")
        if not isinstance(query, str) and nested_dict is not None:
            query = nested_dict.get("query")
        if not isinstance(query, str) or not query.strip():
            raise RuntimeError("knowledge.search requires a non-empty query")

        top_k_raw = payload.get("top_k", 8)
        if not isinstance(top_k_raw, int) and nested_dict is not None:
            top_k_raw = nested_dict.get("top_k", 8)
        top_k = top_k_raw if isinstance(top_k_raw, int) and top_k_raw > 0 else 8

        runtime_context = self._binding.runtime_context
        if get_rag_knowledge_scope(runtime_context) == "general_only":
            return ToolInvocationResult(
                tool_ref=request.tool_ref,
                blocks=(
                    ToolContentBlock(
                        kind=ToolContentKind.JSON,
                        data={
                            "sources": [],
                            "note": "Corpus retrieval skipped in general-only mode.",
                        },
                    ),
                ),
                sources=(),
            )

        include_session_scope, include_corpus_scope = get_vector_search_scopes(
            runtime_context
        )
        hits = await self._search_client.search(
            question=query,
            top_k=top_k,
            document_library_tags_ids=get_document_library_tags_ids(runtime_context),
            document_uids=get_document_uids(runtime_context),
            search_policy=get_search_policy(runtime_context),
            owner_filter=OwnerFilter.TEAM
            if self._settings.team_id
            else OwnerFilter.PERSONAL,
            team_id=self._settings.team_id,
            session_id=runtime_context.session_id,
            include_session_scope=include_session_scope,
            include_corpus_scope=include_corpus_scope,
        )

        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.JSON,
                    data={
                        "query": query,
                        "hits": [
                            hit.model_dump(mode="json")
                            if hasattr(hit, "model_dump")
                            else hit
                            for hit in hits
                        ],
                    },
                ),
            ),
            sources=tuple(hits),
        )

    async def _invoke_logs_query(
        self, request: ToolInvocationRequest
    ) -> ToolInvocationResult:
        payload = request.payload
        window_minutes = _positive_int(payload.get("window_minutes"), default=5)
        limit = _positive_int(payload.get("limit"), default=500, maximum=5000)
        max_events = _positive_int(payload.get("max_events"), default=200, maximum=1000)
        min_level_raw = payload.get("min_level")
        if not isinstance(min_level_raw, str) or min_level_raw not in _LEVEL_ORDER:
            min_level: LogLevel = "WARNING"
        else:
            min_level = cast(LogLevel, min_level_raw)
        include_agentic = bool(payload.get("include_agentic", True))
        include_knowledge_flow = bool(payload.get("include_knowledge_flow", True))

        log_query = _build_log_query(
            window_minutes=window_minutes,
            limit=limit,
            min_level=min_level,
        )
        events, warnings = await self._fetch_logs(
            log_query=log_query,
            include_agentic=include_agentic,
            include_knowledge_flow=include_knowledge_flow,
        )
        digest = _build_log_digest(
            events=events,
            warnings=warnings,
            window_minutes=window_minutes,
            max_events=max_events,
        )

        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.JSON,
                    data=digest,
                ),
            ),
            sources=(),
        )

    async def _invoke_traces_summarize_conversation(
        self, request: ToolInvocationRequest
    ) -> ToolInvocationResult:
        payload = request.payload
        session_id = (
            _coerce_optional_string(payload.get("fred_session_id"))
            or _coerce_optional_string(payload.get("session_id"))
            or self._binding.runtime_context.session_id
        )
        trace_limit = _positive_int(payload.get("trace_limit"), default=50, maximum=200)
        top_spans = _positive_int(payload.get("top_spans"), default=10, maximum=50)
        include_timeline = bool(payload.get("include_timeline", True))

        query_filters = {
            "fred_session_id": session_id,
            "agent_name": _coerce_optional_string(payload.get("agent_name")),
            "agent_id": _coerce_optional_string(payload.get("agent_id")),
            "team_id": _coerce_optional_string(payload.get("team_id"))
            or self._settings.team_id,
            "user_name": _coerce_optional_string(payload.get("user_name")),
            "trace_limit": trace_limit,
            "top_spans": top_spans,
            "include_timeline": include_timeline,
        }

        if _langfuse_credentials() is None:
            logger.info(
                "[V2][TRACES] summarize_conversation skipped: Langfuse credentials are not configured."
            )
            return ToolInvocationResult(
                tool_ref=request.tool_ref,
                blocks=(
                    ToolContentBlock(
                        kind=ToolContentKind.TEXT,
                        text=(
                            "Performance trace summary is not enabled in this environment "
                            "(Langfuse is not configured)."
                        ),
                    ),
                    ToolContentBlock(
                        kind=ToolContentKind.JSON,
                        data={
                            "status": "disabled",
                            "reason": "langfuse_not_configured",
                            "query_filters": query_filters,
                        },
                    ),
                ),
            )

        try:
            digest = await asyncio.to_thread(
                _summarize_langfuse_conversation,
                query_filters=query_filters,
            )
        except Exception as exc:
            logger.warning(
                "[V2][TRACES] summarize_conversation failed: %s",
                exc,
                exc_info=True,
            )
            return ToolInvocationResult(
                tool_ref=request.tool_ref,
                blocks=(
                    ToolContentBlock(
                        kind=ToolContentKind.TEXT,
                        text=(
                            "Langfuse summary failed. Check LANGFUSE_HOST/"
                            "LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY and trace filters."
                        ),
                    ),
                    ToolContentBlock(
                        kind=ToolContentKind.JSON,
                        data={
                            "status": "error",
                            "error": str(exc),
                            "query_filters": query_filters,
                        },
                    ),
                ),
                is_error=True,
            )

        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.TEXT,
                    text=_render_trace_digest_summary(digest),
                ),
                ToolContentBlock(
                    kind=ToolContentKind.JSON,
                    data=digest,
                ),
            ),
        )

    def _invoke_geo_render_points(
        self, request: ToolInvocationRequest
    ) -> ToolInvocationResult:
        payload = request.payload
        title_raw = payload.get("title")
        title = (
            title_raw.strip()
            if isinstance(title_raw, str) and title_raw.strip()
            else "Map results"
        )
        popup_property_raw = payload.get("popup_property")
        popup_property = (
            popup_property_raw.strip()
            if isinstance(popup_property_raw, str) and popup_property_raw.strip()
            else None
        )
        fit_bounds = bool(payload.get("fit_bounds", True))
        raw_points = payload.get("points")
        if not isinstance(raw_points, list) or not raw_points:
            raise RuntimeError("geo.render_points requires a non-empty points list")

        features: list[dict[str, object]] = []
        point_labels: list[str] = []
        for index, raw_point in enumerate(raw_points, start=1):
            if not isinstance(raw_point, dict):
                raise RuntimeError(
                    f"geo.render_points point #{index} must be an object"
                )

            latitude = _coerce_float(raw_point.get("latitude"))
            longitude = _coerce_float(raw_point.get("longitude"))
            if latitude is None or longitude is None:
                raise RuntimeError(
                    f"geo.render_points point #{index} requires numeric latitude and longitude"
                )

            name_raw = raw_point.get("name")
            name = (
                name_raw.strip()
                if isinstance(name_raw, str) and name_raw.strip()
                else None
            )
            if name is not None:
                point_labels.append(name)

            properties_raw = raw_point.get("properties")
            properties = (
                dict(properties_raw) if isinstance(properties_raw, dict) else {}
            )
            if name is not None and "name" not in properties:
                properties["name"] = name

            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [longitude, latitude],
                    },
                    "properties": properties,
                }
            )

        summary = _summarize_geo_points(
            title=title, point_labels=point_labels, count=len(features)
        )
        geo_part = GeoPart(
            geojson={"type": "FeatureCollection", "features": features},
            popup_property=popup_property,
            fit_bounds=fit_bounds,
        )
        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.TEXT,
                    text=summary,
                ),
            ),
            ui_parts=(geo_part,),
        )

    async def _fetch_logs(
        self,
        *,
        log_query: LogQuery,
        include_agentic: bool,
        include_knowledge_flow: bool,
    ) -> tuple[list[_LogEventSnapshot], list[str]]:
        events: list[_LogEventSnapshot] = []
        warnings: list[str] = []

        if include_agentic:
            try:
                store = get_app_context().get_log_store()
                result = await asyncio.to_thread(store.query, log_query)
                events.extend(_snap_log_events("agentic", result))
            except Exception as exc:
                logger.warning("v2 logs.query: agentic logs query failed: %s", exc)
                warnings.append(f"agentic logs query failed: {exc}")

        if include_knowledge_flow:
            try:
                result = await self._logs_client.query(log_query)
                events.extend(_snap_log_events("knowledge_flow", result))
            except Exception as exc:
                logger.warning(
                    "v2 logs.query: knowledge-flow logs query failed: %s", exc
                )
                warnings.append(f"knowledge-flow logs query failed: {exc}")

        return events, warnings


class FredMcpToolProvider(ToolProviderPort):
    """
    Fred runtime bridge exposing UI-configured MCP tools to v2 ReAct agents.

    Intent:
    - keep the v2 agent definition generic
    - reuse the existing MCP catalog and per-agent `mcp_servers` settings
    - avoid pushing MCP wiring details into the author-facing SDK
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self._settings = settings
        self._agent = _McpRuntimeAgentShim(binding=binding, settings=settings)
        self._mcp_runtime: MCPRuntime | None = None

    def bind(self, binding: BoundRuntimeContext) -> None:
        self._agent.rebind(binding)

    async def activate(self) -> None:
        if not self._has_configured_servers():
            return
        if self._mcp_runtime is None:
            self._mcp_runtime = MCPRuntime(agent=self._agent)
        await self._mcp_runtime.init()

    def get_tools(self) -> tuple[BaseTool, ...]:
        if not self._has_configured_servers():
            return ()
        if self._mcp_runtime is None:
            raise RuntimeError(
                "FredMcpToolProvider is not activated. Call activate() before requesting tools."
            )
        return tuple(self._mcp_runtime.get_tools())

    async def aclose(self) -> None:
        if self._mcp_runtime is None:
            return
        await self._mcp_runtime.aclose()
        self._mcp_runtime = None

    def _has_configured_servers(self) -> bool:
        tuning = self._settings.tuning
        if tuning is None:
            return False
        return bool(tuning.mcp_servers)


class FredArtifactPublisher(ArtifactPublisherPort):
    """
    Fred-side adapter exposing generated-file publication to v2 runtimes.

    This keeps agent code focused on the business intent:
    "publish this report for the user" or "store this agent note", while the
    adapter handles tokens, agent scope, and the Knowledge Flow storage API.
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self._settings = settings
        self._agent = _WorkspaceAgentShim(binding=binding, settings=settings)
        self._workspace_client = KfWorkspaceClient(agent=cast("AgentFlow", self._agent))
        self._binding = binding

    def bind(self, binding: BoundRuntimeContext) -> None:
        self._binding = binding
        self._agent.rebind(binding)

    async def publish(self, request: ArtifactPublishRequest) -> PublishedArtifact:
        key = request.key or _default_artifact_key(
            binding=self._binding,
            file_name=request.file_name,
        )
        content_type = request.content_type or "application/octet-stream"

        try:
            if request.scope == ArtifactScope.USER:
                result = await self._workspace_client.upload_user_blob(
                    key=key,
                    file_content=request.content_bytes,
                    filename=request.file_name,
                    content_type=content_type,
                )
            elif request.scope == ArtifactScope.AGENT_CONFIG:
                result = await self._workspace_client.upload_agent_config_blob(
                    key=key,
                    file_content=request.content_bytes,
                    filename=request.file_name,
                    agent_id=self._settings.id,
                    content_type=content_type,
                )
            elif request.scope == ArtifactScope.AGENT_USER:
                target_user_id = (
                    request.target_user_id or self._binding.runtime_context.user_id
                )
                if not target_user_id:
                    raise RuntimeError(
                        "agent_user artifact publication requires a target_user_id or a bound runtime_context.user_id."
                    )
                result = await self._workspace_client.upload_agent_user_blob(
                    key=key,
                    file_content=request.content_bytes,
                    filename=request.file_name,
                    agent_id=self._settings.id,
                    target_user_id=target_user_id,
                    content_type=content_type,
                )
            else:
                raise RuntimeError(f"Unsupported artifact scope: {request.scope!r}")
        except WorkspaceUploadError as e:
            raise ArtifactPublicationError(
                f"Could not publish '{request.file_name}': {e}"
            ) from e

        return PublishedArtifact(
            scope=request.scope,
            key=result.key,
            file_name=result.file_name,
            size=result.size,
            href=result.download_url,
            document_uid=_coerce_optional_string(result.document_uid),
            mime=content_type,
            title=request.title or request.file_name,
            link_kind=request.link_kind,
        )


class FredResourceReader(ResourceReaderPort):
    """
    Fred-side adapter exposing existing workspace resources to v2 runtimes.

    This is the complement of `FredArtifactPublisher`:
    - admins place templates or configuration files in Fred storage
    - v2 agents fetch them through a typed runtime capability
    - agent code stays focused on business intent instead of storage URLs
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self._settings = settings
        self._agent = _WorkspaceAgentShim(binding=binding, settings=settings)
        self._workspace_client = KfWorkspaceClient(agent=cast("AgentFlow", self._agent))
        self._binding = binding

    def bind(self, binding: BoundRuntimeContext) -> None:
        self._binding = binding
        self._agent.rebind(binding)

    async def fetch(self, request: ResourceFetchRequest) -> FetchedResource:
        access_token = _workspace_access_token(self._binding.runtime_context)

        try:
            if request.scope == ResourceScope.USER:
                blob = await self._workspace_client.fetch_user_blob(
                    key=request.key,
                    access_token=access_token,
                )
            elif request.scope == ResourceScope.AGENT_CONFIG:
                blob = await self._workspace_client.fetch_agent_config_blob(
                    key=request.key,
                    access_token=access_token,
                    agent_id=self._settings.id,
                )
            elif request.scope == ResourceScope.AGENT_USER:
                target_user_id = (
                    request.target_user_id or self._binding.runtime_context.user_id
                )
                if not target_user_id:
                    raise RuntimeError(
                        "agent_user resource fetch requires a target_user_id or a bound runtime_context.user_id."
                    )
                blob = await self._workspace_client.fetch_agent_user_blob(
                    key=request.key,
                    access_token=access_token,
                    agent_id=self._settings.id,
                    target_user_id=target_user_id,
                )
            else:
                raise RuntimeError(f"Unsupported resource scope: {request.scope!r}")
        except WorkspaceRetrievalError as e:
            if e.status_code == 404:
                raise ResourceNotFoundError(request.key) from e
            raise ResourceFetchError(f"Could not fetch '{request.key}': {e}") from e

        return FetchedResource(
            scope=request.scope,
            key=request.key,
            file_name=blob.filename,
            size=blob.size,
            content_bytes=blob.bytes,
            content_type=blob.content_type,
        )


class _VectorSearchAgentShim:
    """
    Minimal object accepted by the existing Knowledge Flow clients.

    This is a deliberate bridge:
    - the new v2 runtime should not inherit from `AgentFlow`
    - the existing HTTP clients still expect an agent-like object for token and
      KPI context
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self.runtime_context = binding.runtime_context
        self.agent_settings = settings

    def refresh_user_access_token(self) -> str:
        return _refresh_runtime_context_access_token(self.runtime_context)


class _McpRuntimeAgentShim:
    """
    Minimal agent-like bridge expected by the existing MCP runtime/toolkit.

    This stays internal to the v2 adapter layer so the author-facing SDK remains
    unaware of MCP lifecycle details.
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self.runtime_context = binding.runtime_context
        self.agent_settings = settings

    def rebind(self, binding: BoundRuntimeContext) -> None:
        self.runtime_context = binding.runtime_context

    def get_id(self) -> str:
        return self.agent_settings.id

    def get_agent_tunings(self) -> AgentTuning:
        tuning = self.agent_settings.tuning
        if tuning is None:
            raise RuntimeError(
                f"Agent {self.agent_settings.id!r} has no tuning payload; MCP tools cannot be resolved."
            )
        return tuning

    def get_agent_settings(self) -> AgentSettings:
        return self.agent_settings

    def get_runtime_context(self) -> RuntimeContext:
        return self.runtime_context

    def refresh_user_access_token(self) -> str:
        return _refresh_runtime_context_access_token(self.runtime_context)


class _WorkspaceAgentShim:
    """
    Minimal bridge expected by the existing Fred workspace client.

    The v2 runtime should talk in terms of "publish this artifact". This shim
    lets Fred reuse its real workspace storage path without turning definitions
    into storage-aware classes.
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettings
    ) -> None:
        self.runtime_context = binding.runtime_context
        self.agent_settings = settings

    def rebind(self, binding: BoundRuntimeContext) -> None:
        self.runtime_context = binding.runtime_context

    def refresh_user_access_token(self) -> str:
        return _refresh_runtime_context_access_token(self.runtime_context)


def _workspace_access_token(runtime_context: RuntimeContext) -> str:
    current = runtime_context.access_token
    if isinstance(current, str) and current:
        return current
    return _refresh_runtime_context_access_token(runtime_context)


def _refresh_runtime_context_access_token(runtime_context: RuntimeContext) -> str:
    refresh_token = runtime_context.refresh_token
    if not refresh_token:
        raise RuntimeError(
            "Cannot refresh user access token: refresh_token missing from runtime context."
        )

    keycloak_url = get_keycloak_url()
    client_id = get_keycloak_client_id()
    if not keycloak_url:
        raise RuntimeError("User security realm_url is not configured for Keycloak.")
    if not client_id:
        raise RuntimeError("User security client_id is not configured for Keycloak.")

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

    runtime_context.access_token = new_access_token
    runtime_context.refresh_token = new_refresh_token

    expires_at = payload.get("expires_at_timestamp")
    if expires_at is not None:
        try:
            runtime_context.access_token_expires_at = int(expires_at)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Keycloak refresh response returned an invalid expires_at_timestamp."
            ) from exc

    return new_access_token


def _default_artifact_key(*, binding: BoundRuntimeContext, file_name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name.strip()).strip("._")
    if not safe_name:
        safe_name = "artifact.bin"
    session_id = binding.runtime_context.session_id or "sessionless"
    return f"v2/{session_id}/{uuid.uuid4().hex[:12]}/{safe_name}"


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_optional_string(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, int | float):
        return None if value == 0 else str(value)
    return str(value)


def _summarize_geo_points(*, title: str, point_labels: list[str], count: int) -> str:
    if count <= 0:
        return f"{title}: no points to display."
    if point_labels:
        preview = ", ".join(point_labels[:3])
        if len(point_labels) > 3:
            preview += ", ..."
        return f"{title}: displaying {count} point(s) on the map ({preview})."
    return f"{title}: displaying {count} point(s) on the map."


def _positive_int(value: object, *, default: int, maximum: int | None = None) -> int:
    if not isinstance(value, int) or value <= 0:
        return default
    if maximum is not None and value > maximum:
        return maximum
    return value


def _build_log_query(
    *, window_minutes: int, limit: int, min_level: LogLevel
) -> LogQuery:
    now = datetime.now(UTC)
    since = (now - timedelta(minutes=window_minutes)).isoformat()
    until = now.isoformat()
    return LogQuery(
        since=since,
        until=until,
        limit=limit,
        order="desc",
        filters=LogFilter(level_at_least=min_level),
    )


def _snap_log_events(source: str, result: LogQueryResult) -> list[_LogEventSnapshot]:
    snapshots: list[_LogEventSnapshot] = []
    for event in result.events:
        snapshots.append(
            _LogEventSnapshot(
                source=source,
                ts=event.ts,
                level=event.level,
                logger=event.logger,
                file=event.file,
                line=event.line,
                msg=event.msg,
                extra=event.extra,
            )
        )
    return snapshots


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_log_msg(msg: str, max_len: int = 180) -> str:
    trimmed = re.sub(r"\s+", " ", msg or "").strip()
    return trimmed[:max_len]


def _summarize_log_counts(
    events: list[_LogEventSnapshot],
) -> list[dict[str, object]]:
    counts: dict[str, dict[str, int]] = {}
    for event in events:
        counts.setdefault(event.source, {})
        counts[event.source][event.level] = counts[event.source].get(event.level, 0) + 1

    summaries: list[dict[str, object]] = []
    for source in sorted(counts):
        level_counts = counts[source]
        ordered_counts = {
            level: level_counts[level]
            for level in _LEVEL_ORDER
            if level in level_counts
        }
        summaries.append({"source": source, "levels": ordered_counts})
    return summaries


def _group_log_events(events: list[_LogEventSnapshot]) -> list[_GroupedLogEvent]:
    groups: dict[tuple[str, str, str, int, str], _GroupedLogEvent] = {}
    for event in events:
        msg_key = _normalize_log_msg(event.msg)
        key = (event.source, event.level, event.file, event.line, msg_key)
        if key not in groups:
            groups[key] = {
                "source": event.source,
                "level": event.level,
                "file": event.file,
                "line": event.line,
                "msg": msg_key,
                "count": 1,
                "first_ts": event.ts,
                "last_ts": event.ts,
            }
        else:
            group = groups[key]
            group["count"] += 1
            group["first_ts"] = min(group["first_ts"], event.ts)
            group["last_ts"] = max(group["last_ts"], event.ts)

    return sorted(
        groups.values(),
        key=lambda group: (-group["count"], -group["last_ts"]),
    )


def _log_rule_hints(events: list[_LogEventSnapshot]) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()

    for event in events:
        blob = (event.msg or "").lower()
        if event.extra:
            try:
                blob += " " + json.dumps(event.extra).lower()
            except Exception:
                logger.warning("v2 logs.query: failed to json.dumps log extra")

        if (
            ("401" in blob or "unauthorized" in blob)
            and ("rebac" in blob or "permission" in blob or "forbidden" in blob)
            and "rebac" not in seen
        ):
            seen.add("rebac")
            hints.append(
                f"Missing ReBAC permission (evidence: {_fmt_ts(event.ts)} {event.file}:{event.line} {event.msg})"
            )
        if (
            "connection refused" in blob or "connection reset" in blob
        ) and "conn" not in seen:
            seen.add("conn")
            hints.append(
                f"Downstream service connectivity issue (evidence: {_fmt_ts(event.ts)} {event.file}:{event.line} {event.msg})"
            )
        if ("timeout" in blob or "timed out" in blob) and "timeout" not in seen:
            seen.add("timeout")
            hints.append(
                f"Timeout from dependency or upstream (evidence: {_fmt_ts(event.ts)} {event.file}:{event.line} {event.msg})"
            )

    return hints


def _build_log_digest(
    *,
    events: list[_LogEventSnapshot],
    warnings: list[str],
    window_minutes: int,
    max_events: int,
) -> dict[str, object]:
    if not events:
        return {
            "window_minutes": window_minutes,
            "event_count": 0,
            "warnings": warnings,
            "counts_by_source": [],
            "top_groups": [],
            "sample_lines": [],
            "rule_hints": [],
            "note": "No log events in this window.",
        }

    events_sorted = sorted(events, key=lambda event: event.ts)
    if len(events_sorted) > max_events:
        events_sorted = events_sorted[-max_events:]

    grouped = _group_log_events(events_sorted)[:_DEFAULT_LOG_MAX_GROUPS]
    samples = events_sorted[-_DEFAULT_LOG_SAMPLES:]
    return {
        "window_minutes": window_minutes,
        "event_count": len(events),
        "warnings": warnings,
        "counts_by_source": _summarize_log_counts(events_sorted),
        "top_groups": [
            {
                **group,
                "first_ts": _fmt_ts(group["first_ts"]),
                "last_ts": _fmt_ts(group["last_ts"]),
            }
            for group in grouped
        ],
        "sample_lines": [
            {
                "timestamp": _fmt_ts(event.ts),
                "source": event.source,
                "level": event.level,
                "file": event.file,
                "line": event.line,
                "msg": event.msg,
            }
            for event in samples
        ],
        "rule_hints": _log_rule_hints(events_sorted),
    }


def _render_trace_digest_summary(digest: dict[str, object]) -> str:
    status = str(digest.get("status") or "unknown")
    if status != "ok":
        return (
            f"Langfuse conversation summary status={status}. "
            "No matching trace was found with the requested filters."
        )

    selected = digest.get("selected_trace")
    selected_trace = selected if isinstance(selected, dict) else {}
    trace_id = str(selected_trace.get("trace_id") or "n/a")
    agent_name = str(selected_trace.get("agent_name") or "n/a")
    session_id = str(selected_trace.get("fred_session_id") or "n/a")
    bottleneck = str(digest.get("bottleneck") or "unknown")
    bottleneck_ms = _safe_int(digest.get("bottleneck_ms"))
    tool_total_ms = _safe_int(digest.get("tool_total_ms"))
    model_total_ms = _safe_int(digest.get("model_total_ms"))
    await_total_ms = _safe_int(digest.get("await_human_total_ms"))
    trace_total_ms = _safe_int(digest.get("trace_total_ms"))
    unclassified_total_ms = _safe_int(digest.get("unclassified_total_ms"))
    instrumentation_gap = bool(digest.get("instrumentation_gap_detected"))
    return (
        "Conversation trace summary:\n"
        f"- trace_id: {trace_id}\n"
        f"- agent: {agent_name}\n"
        f"- fred_session_id: {session_id}\n"
        f"- bottleneck: {bottleneck} ({bottleneck_ms} ms)\n"
        f"- trace_total_ms: {trace_total_ms}\n"
        f"- model_total_ms: {model_total_ms}\n"
        f"- tool_total_ms: {tool_total_ms}\n"
        f"- await_human_total_ms: {await_total_ms}\n"
        f"- unclassified_total_ms: {unclassified_total_ms}\n"
        f"- instrumentation_gap_detected: {str(instrumentation_gap).lower()}"
    )


def _summarize_langfuse_conversation(
    *,
    query_filters: dict[str, object],
) -> dict[str, object]:
    credentials = _langfuse_credentials()
    if credentials is None:
        raise RuntimeError(
            "Langfuse credentials are not configured. Expected LANGFUSE_HOST, "
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY."
        )
    host, public_key, secret_key = credentials
    trace_limit = _positive_int(
        query_filters.get("trace_limit"), default=50, maximum=200
    )
    top_spans = _positive_int(query_filters.get("top_spans"), default=10, maximum=50)
    include_timeline = bool(query_filters.get("include_timeline", True))

    traces_payload = _langfuse_get_json(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
        path="/api/public/traces",
        params={"limit": str(trace_limit)},
    )
    raw_traces = traces_payload.get("data")
    traces = raw_traces if isinstance(raw_traces, list) else []

    matched: list[dict[str, object]] = []
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        metadata = trace.get("metadata")
        md = metadata if isinstance(metadata, dict) else {}
        if not _trace_matches_filters(md, query_filters):
            continue
        matched.append(trace)

    if not matched:
        return {
            "status": "not_found",
            "query_filters": query_filters,
            "candidate_trace_count": len(traces),
            "note": "No trace matched the requested conversation filters.",
        }

    selected_trace = max(
        matched,
        key=lambda trace: str(trace.get("timestamp") or trace.get("updatedAt") or ""),
    )
    trace_id = _coerce_optional_string(selected_trace.get("id"))
    if not trace_id:
        return {
            "status": "not_found",
            "query_filters": query_filters,
            "candidate_trace_count": len(traces),
            "note": "Selected trace did not expose a valid trace id.",
        }

    trace_detail = _langfuse_get_json(
        host=host,
        public_key=public_key,
        secret_key=secret_key,
        path=f"/api/public/traces/{trace_id}",
    )
    raw_observations = trace_detail.get("observations")
    observations = raw_observations if isinstance(raw_observations, list) else []
    span_rows = _extract_interesting_spans(observations)
    span_rows.sort(key=lambda row: str(row.get("start_time") or ""))

    top_latency_rows = sorted(
        span_rows,
        key=lambda row: _safe_int(row.get("latency_ms")),
        reverse=True,
    )[:top_spans]

    node_totals = _aggregate_by_key(span_rows, key_name="node_id")
    model_totals = _aggregate_by_key(
        [row for row in span_rows if row.get("category") == "model"],
        key_name="operation_label",
    )
    tool_totals = _aggregate_by_key(
        [row for row in span_rows if row.get("category") == "tool"],
        key_name="tool_label",
    )

    model_total_ms = sum(
        _safe_int(row.get("latency_ms"))
        for row in span_rows
        if row.get("category") == "model"
    )
    tool_total_ms = sum(
        _safe_int(row.get("latency_ms"))
        for row in span_rows
        if row.get("category") == "tool"
    )
    await_human_total_ms = sum(
        _safe_int(row.get("latency_ms"))
        for row in span_rows
        if row.get("category") == "await_human"
    )
    trace_total_ms = _trace_total_latency_ms(selected_trace=selected_trace)
    instrumented_total_ms = model_total_ms + tool_total_ms + await_human_total_ms
    unclassified_total_ms = max(0, trace_total_ms - instrumented_total_ms)
    bottleneck, bottleneck_ms = _classify_trace_bottleneck(
        model_total_ms=model_total_ms,
        tool_total_ms=tool_total_ms,
        await_human_total_ms=await_human_total_ms,
        trace_total_ms=trace_total_ms,
        unclassified_total_ms=unclassified_total_ms,
        interesting_span_count=len(span_rows),
    )

    selected_metadata = selected_trace.get("metadata")
    selected_md = selected_metadata if isinstance(selected_metadata, dict) else {}
    digest: dict[str, object] = {
        "status": "ok",
        "query_filters": query_filters,
        "selected_trace": {
            "trace_id": trace_id,
            "timestamp": selected_trace.get("timestamp"),
            "name": selected_trace.get("name"),
            "latency_s": selected_trace.get("latency"),
            "agent_id": selected_md.get("agent_id"),
            "agent_name": selected_md.get("agent_name"),
            "team_id": selected_md.get("team_id"),
            "user_id": selected_md.get("user_id"),
            "user_name": selected_md.get("user_name"),
            "fred_session_id": selected_md.get("fred_session_id")
            or selected_md.get("session_id"),
            "correlation_id": selected_md.get("correlation_id"),
            "request_id": selected_md.get("request_id"),
        },
        "observation_count": len(observations),
        "interesting_span_count": len(span_rows),
        "top_spans_by_latency": top_latency_rows,
        "node_totals_ms": node_totals,
        "model_operation_totals_ms": model_totals,
        "tool_totals_ms": tool_totals,
        "model_total_ms": model_total_ms,
        "tool_total_ms": tool_total_ms,
        "await_human_total_ms": await_human_total_ms,
        "trace_total_ms": trace_total_ms,
        "instrumented_total_ms": instrumented_total_ms,
        "unclassified_total_ms": unclassified_total_ms,
        "instrumentation_gap_detected": bottleneck == "instrumentation_gap",
        "bottleneck": bottleneck,
        "bottleneck_ms": bottleneck_ms,
        "recommendations": _trace_recommendations(bottleneck),
    }
    if include_timeline:
        digest["timeline"] = span_rows
    return digest


def _trace_matches_filters(
    metadata: dict[str, object], query_filters: dict[str, object]
) -> bool:
    def _matches(key: str, metadata_keys: tuple[str, ...] = ()) -> bool:
        raw = query_filters.get(key)
        expected = _coerce_optional_string(raw)
        if not expected:
            return True
        values = [metadata.get(key), *[metadata.get(alias) for alias in metadata_keys]]
        return any(_coerce_optional_string(value) == expected for value in values)

    return (
        _matches("fred_session_id", metadata_keys=("session_id",))
        and _matches("agent_name")
        and _matches("agent_id")
        and _matches("team_id")
        and _matches("user_name")
    )


def _extract_interesting_spans(observations: list[object]) -> list[dict[str, object]]:
    interesting_prefixes = ("v2.graph.", "v2.react.")
    interesting_names = {
        "agent.stream",
        "tool.invoke",
        "artifact.publish",
        "resource.fetch",
    }
    rows: list[dict[str, object]] = []
    for raw in observations:
        if not isinstance(raw, dict):
            continue
        obs_type = str(raw.get("type") or "")
        if obs_type == "GENERATION":
            latency_ms = _safe_int(raw.get("latency"))
            metadata = raw.get("metadata")
            md = metadata if isinstance(metadata, dict) else {}
            operation = _coerce_optional_string(raw.get("name"))
            model_name = _coerce_optional_string(
                raw.get("model")
            ) or _coerce_optional_string(md.get("model_name"))
            rows.append(
                {
                    "name": "langfuse.generation",
                    "start_time": raw.get("startTime"),
                    "end_time": raw.get("endTime"),
                    "latency_ms": latency_ms,
                    "node_id": _coerce_optional_string(md.get("node_id")),
                    "step_index": _safe_int(md.get("step_index")),
                    "operation": operation,
                    "tool_ref": None,
                    "tool_name": None,
                    "tool_label": "n/a",
                    "operation_label": operation or "generation",
                    "model_name": model_name,
                    "status": _coerce_optional_string(md.get("status")),
                    "stage": _coerce_optional_string(md.get("stage")),
                    "category": "model",
                }
            )
            continue
        if obs_type != "SPAN":
            continue
        name = str(raw.get("name") or "")
        if not (name.startswith(interesting_prefixes) or name in interesting_names):
            continue
        metadata = raw.get("metadata")
        md = metadata if isinstance(metadata, dict) else {}
        latency_ms = _safe_int(raw.get("latency"))
        node_id = _coerce_optional_string(md.get("node_id"))
        operation = _coerce_optional_string(md.get("operation"))
        tool_ref = _coerce_optional_string(md.get("tool_ref"))
        tool_name = _coerce_optional_string(md.get("tool_name"))
        model_name = _coerce_optional_string(md.get("model_name"))
        category = "other"
        if name in _TRACE_MODEL_SPAN_NAMES:
            category = "model"
        elif name in _TRACE_TOOL_SPAN_NAMES:
            category = "tool"
        elif name in _TRACE_AWAIT_HUMAN_SPAN_NAMES:
            category = "await_human"
        rows.append(
            {
                "name": name,
                "start_time": raw.get("startTime"),
                "end_time": raw.get("endTime"),
                "latency_ms": latency_ms,
                "node_id": node_id,
                "step_index": _safe_int(md.get("step_index")),
                "operation": operation,
                "tool_ref": tool_ref,
                "tool_name": tool_name,
                "tool_label": tool_ref or tool_name or "n/a",
                "operation_label": operation or "n/a",
                "model_name": model_name,
                "status": _coerce_optional_string(md.get("status")),
                "stage": _coerce_optional_string(md.get("stage")),
                "category": category,
            }
        )
    return rows


def _aggregate_by_key(
    rows: list[dict[str, object]],
    *,
    key_name: str,
) -> list[_TraceAggregate]:
    totals: dict[str, _TraceAggregate] = {}
    for row in rows:
        label = _coerce_optional_string(row.get(key_name)) or "n/a"
        latency_ms = _safe_int(row.get("latency_ms"))
        if label not in totals:
            totals[label] = {
                "name": label,
                "count": 1,
                "total_ms": latency_ms,
                "max_ms": latency_ms,
            }
        else:
            aggregate = totals[label]
            aggregate["count"] += 1
            aggregate["total_ms"] += latency_ms
            aggregate["max_ms"] = max(aggregate["max_ms"], latency_ms)
    return sorted(
        totals.values(),
        key=lambda aggregate: (aggregate["total_ms"], aggregate["max_ms"]),
        reverse=True,
    )


def _classify_trace_bottleneck(
    *,
    model_total_ms: int,
    tool_total_ms: int,
    await_human_total_ms: int,
    trace_total_ms: int,
    unclassified_total_ms: int,
    interesting_span_count: int,
) -> tuple[str, int]:
    instrumented_total_ms = model_total_ms + tool_total_ms + await_human_total_ms
    if instrumented_total_ms == 0:
        if trace_total_ms > 0 or interesting_span_count > 0:
            return "instrumentation_gap", max(trace_total_ms, unclassified_total_ms)
        return "unknown", 0
    if unclassified_total_ms > max(model_total_ms, tool_total_ms, await_human_total_ms):
        return "instrumentation_gap", unclassified_total_ms
    candidates = {
        "model_latency": model_total_ms,
        "tool_latency": tool_total_ms,
        "awaiting_human": await_human_total_ms,
    }
    bottleneck = max(candidates, key=lambda key: candidates[key])
    return bottleneck, candidates[bottleneck]


def _trace_recommendations(bottleneck: str) -> list[str]:
    if bottleneck == "instrumentation_gap":
        return [
            "Instrument model/tool calls as child spans to avoid opaque top-level latency.",
            "Capture model_name, tool_name/tool_ref, and operation on each child span.",
        ]
    if bottleneck == "model_latency":
        return [
            "Inspect analysis prompt/context size and reduce low-signal retrieved text.",
            "Split heavy analysis into smaller model operations when possible.",
        ]
    if bottleneck == "tool_latency":
        return [
            "Inspect downstream tool backend latency and scope filters.",
            "Validate retrieval query width (top_k, corpus scope, selected libraries).",
        ]
    if bottleneck == "awaiting_human":
        return [
            "Treat this as business wait time, not backend compute latency.",
            "Track HITL wait separately from runtime performance metrics.",
        ]
    return ["No dominant bottleneck found; inspect top span timeline manually."]


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(float(value.strip())))
        except ValueError:
            return 0
    return 0


def _trace_total_latency_ms(*, selected_trace: dict[str, object]) -> int:
    raw_latency = selected_trace.get("latency")
    if isinstance(raw_latency, bool):
        return 0
    if isinstance(raw_latency, int | float):
        # Langfuse public trace latency is expressed in seconds.
        return max(0, int(float(raw_latency) * 1000))
    if isinstance(raw_latency, str):
        try:
            return max(0, int(float(raw_latency.strip()) * 1000))
        except ValueError:
            return 0
    return 0


def _langfuse_credentials() -> tuple[str, str, str] | None:
    host = _coerce_optional_string(os.getenv("LANGFUSE_HOST"))
    public_key = _coerce_optional_string(os.getenv("LANGFUSE_PUBLIC_KEY"))
    secret_key = _coerce_optional_string(os.getenv("LANGFUSE_SECRET_KEY"))
    if not host or not public_key or not secret_key:
        return None
    return host.rstrip("/"), public_key, secret_key


def _langfuse_get_json(
    *,
    host: str,
    public_key: str,
    secret_key: str,
    path: str,
    params: Mapping[str, str] | None = None,
) -> dict[str, object]:
    url = f"{host}{path}"
    try:
        response = httpx.get(
            url,
            params=dict(params) if params else None,
            auth=(public_key, secret_key),
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.text
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "")[:300]
        raise RuntimeError(
            f"Langfuse API HTTP {exc.response.status_code} for {path}: {body}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Langfuse API connection failed for {path}: {exc}") from exc

    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Langfuse API returned non-JSON payload for {path}."
        ) from exc
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"Langfuse API returned unexpected payload shape for {path}."
        )
    return raw
