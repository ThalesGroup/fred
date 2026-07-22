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
- `FredWorkspaceFs` exposes the team-rooted virtual filesystem so agents read and
  write files by path rather than through raw workspace plumbing.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections.abc import Awaitable, Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from typing import Protocol, TypedDict, cast

import httpx
from fred_core.common import OwnerFilter
from fred_core.common.team_id import is_personal_team_id
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_core.portable import LoggingTracer, MetricsProvider, Tracer, get_tracer
from fred_core.security.oidc import get_keycloak_client_id, get_keycloak_url
from fred_core.store.vector_search import VectorSearchHit, select_citable_sources
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    FsEntry,
    GeoPart,
    JsonScalar,
    PortableContext,
    PortableEnvironment,
    PublishedArtifact,
    RuntimeContext,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import (
    AgentAssetPort,
    ChatModelFactoryPort,
    DocumentContentPort,
    DocumentFolderPort,
    DocumentPortCallError,
    DocumentRawContent,
    DocumentSearchPort,
    DocumentSearchResult,
    DocumentSummarizePort,
    DocumentSummaryResult,
    DocumentTreePort,
    DocumentTreeResult,
    FolderDocumentEntry,
    SpanPort,
    ToolInvokerPort,
    ToolProviderPort,
    TracerPort,
    WorkspaceFileNotFound,
    WorkspaceFsPort,
)
from fred_sdk.support.builtins import (
    TOOL_REF_GEO_RENDER_POINTS,
    TOOL_REF_KNOWLEDGE_SEARCH,
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
)
from langchain_core.tools import BaseTool
from langfuse import Langfuse
from langfuse.types import TraceContext as LangfuseTraceContext

from fred_runtime.common.kf_document_client import KfDocumentClient
from fred_runtime.common.kf_tag_client import KfTagClient
from fred_runtime.common.kf_vectorsearch_client import VectorSearchClient
from fred_runtime.common.kf_workspace_client import (
    KfWorkspaceClient,
    WorkspaceRetrievalError,
)
from fred_runtime.common.mcp_runtime import MCPRuntime
from fred_runtime.common.structures import AgentSettingsLike
from fred_runtime.runtime_context import get_runtime_context
from fred_runtime.runtime_support import (
    get_document_library_tags_ids,
    get_document_uids,
    get_rag_knowledge_scope,
    get_search_policy,
    get_vector_search_scopes,
    refresh_user_access_token_from_keycloak,
)

logger = logging.getLogger(__name__)

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

    @property
    def span_id(self) -> str:
        return self._span.id

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

    @property
    def propagator(self):  # type: ignore[override]
        """
        Return a no-op propagator for Langfuse spans.

        Why this exists:
        - the SDK tracer contract expects a propagator even when unused

        How to use it:
        - accessed implicitly by runtime code that propagates context

        Example:
        - `headers = {}; tracer.propagator.inject_to_carrier(headers)`
        """

    def shutdown(self) -> None:
        """
        Shutdown hook for API symmetry.

        Why this exists:
        - the tracer contract expects a safe cleanup hook

        How to use it:
        - call at process shutdown; Langfuse has no explicit flush here

        Example:
        - `tracer.shutdown()`
        """

        return None

    def start_span(
        self,
        name: str,
        *,
        context: object | None = None,
        attributes: Mapping[str, object] | None = None,
        parent: "SpanPort | None" = None,
        **kwargs: object,
    ) -> SpanPort:
        portable_context = (
            context
            if isinstance(context, PortableContext)
            else PortableContext(
                request_id="unknown",
                correlation_id="unknown",
                actor="unknown",
                tenant="unknown",
                environment=PortableEnvironment.DEV,
            )
        )
        trace_seed = (
            portable_context.trace_id
            or portable_context.request_id
            or portable_context.correlation_id
            or portable_context.session_id
            or portable_context.actor
        )
        trace_id = self._client.create_trace_id(seed=trace_seed)
        metadata: dict[str, object] = {
            "agent_id": portable_context.agent_id,
            "agent_name": portable_context.agent_name,
            "session_id": portable_context.session_id,
            "fred_session_id": portable_context.session_id,
            "exchange_id": portable_context.baggage.get("exchange_id"),
            "checkpoint_id": portable_context.baggage.get("checkpoint_id"),
            "correlation_id": portable_context.correlation_id,
            "trace_id": portable_context.trace_id,
            "request_id": portable_context.request_id,
            "actor": portable_context.actor,
            "user_id": portable_context.user_id,
            "user_name": portable_context.user_name,
            "team_id": portable_context.team_id,
            "agent_instance_id": portable_context.baggage.get("agent_instance_id"),
            "template_agent_id": portable_context.baggage.get("template_agent_id"),
            "execution_action": portable_context.baggage.get("execution_action"),
            "tenant": portable_context.tenant,
            "environment": portable_context.environment.value,
        }
        if portable_context.baggage:
            metadata["baggage"] = dict(portable_context.baggage)
        if attributes:
            metadata.update(attributes)
        if kwargs:
            metadata.update(kwargs)
        trace_context: LangfuseTraceContext = {"trace_id": trace_id}
        parent_span_id = parent.span_id if parent is not None else None
        if parent_span_id is not None:
            trace_context["parent_span_id"] = parent_span_id
        span = cast(
            "_LangfuseSpanLike",
            self._client.start_observation(
                name=name,
                as_type="span",
                trace_context=trace_context,
                metadata=metadata,
            ),
        )
        return LangfuseSpanAdapter(span)


_LANGFUSE_TRACER: TracerPort | None | bool = False


class _LangfuseSpanLike(Protocol):
    id: str

    def update(
        self, *, metadata: Mapping[str, object] | None = None, **kwargs
    ) -> object:
        pass

    def end(self, *, end_time: int | None = None) -> object:
        pass


def build_langfuse_tracer() -> TracerPort | None:
    """
    Return a shared Langfuse tracer when credentials are configured.
    """

    global _LANGFUSE_TRACER
    if _LANGFUSE_TRACER is not False:
        return _LANGFUSE_TRACER if isinstance(_LANGFUSE_TRACER, TracerPort) else None

    has_public = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
    has_secret = bool(os.getenv("LANGFUSE_SECRET_KEY"))
    if has_public and has_secret:
        try:
            _LANGFUSE_TRACER = LangfuseTracerAdapter(Langfuse())
        except Exception:
            logger.exception("[V2][TRACING] Failed to initialize Langfuse tracer.")
            _LANGFUSE_TRACER = None
    else:
        _LANGFUSE_TRACER = None
    return _LANGFUSE_TRACER if isinstance(_LANGFUSE_TRACER, TracerPort) else None


def build_default_tracer() -> TracerPort:
    """
    Resolve the runtime tracer with a clear fallback order.

    Why this exists:
    - keep tracing always-on and understandable in dev environments

    How to use it:
    - call when assembling `RuntimeServices`

    Example:
    - `services = RuntimeServices(tracer=build_default_tracer(), ...)`
    """

    langfuse = build_langfuse_tracer()
    if langfuse is not None:
        return langfuse

    configured = get_tracer()
    if type(configured) is Tracer:
        return LoggingTracer()
    return configured


class DefaultFredChatModelFactory(ChatModelFactoryPort):
    """
    Thin adapter over Fred's current global default chat model.

    This keeps the v2 runtime executable today without baking the global model
    lookup directly into the runtime implementation itself.
    """

    def build(self, definition, binding):  # type: ignore[override]
        """
        Build the default chat model for v2 runtimes.

        Why this exists:
        - v2 runtime needs a default model without binding to agentic-backend

        How to use it:
        - call via the `ChatModelFactoryPort` interface

        Example:
            >>> model = DefaultFredChatModelFactory().build(None, None)
        """
        return get_runtime_context().get_default_chat_model()


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
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self._settings = settings
        self.rebind(binding)

    def rebind(self, binding: BoundRuntimeContext) -> None:
        self._binding = binding
        self._search_client = VectorSearchClient(
            agent=_VectorSearchAgentShim(binding=binding, settings=self._settings)
        )
        self._builtins: dict[str, ToolHandler] = {
            TOOL_REF_KNOWLEDGE_SEARCH: self._invoke_knowledge_search,
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
            and not is_personal_team_id(self._settings.team_id)
            else OwnerFilter.PERSONAL,
            team_id=self._settings.team_id
            if not is_personal_team_id(self._settings.team_id)
            else None,
            session_id=runtime_context.session_id,
            include_session_scope=include_session_scope,
            include_corpus_scope=include_corpus_scope,
        )

        # Only expose the fields the LLM needs for citation and reasoning.
        # URL and operational fields are excluded to prevent the model from
        # reproducing broken or internal paths in its reply.
        _LLM_FIELDS = {
            "uid",
            "title",
            "content",
            "file_name",
            "page",
            "section",
            "score",
        }

        def _llm_slice(hit: VectorSearchHit) -> dict[str, object]:
            return {
                k: v for k, v in hit.model_dump(mode="json").items() if k in _LLM_FIELDS
            }

        # `sources` is narrowed separately from the model-visible content: never
        # a dataset pointer chunk (no real content to cite), and never a hit
        # that's noise relative to the best match in this call
        # (RAG-DATASET-DISCOVERY-RFC.md §7). This builtin tool predates
        # capability config fields, so unlike document_access's
        # `min_source_score_ratio`, the ratio here is the shared default, not
        # yet independently tunable per agent instance.
        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.JSON,
                    data={
                        "query": query,
                        "hits": [_llm_slice(hit) for hit in hits],
                    },
                ),
            ),
            sources=select_citable_sources(hits),
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


def _narrow_scope_ids(
    outer: Sequence[str] | None, inner: Sequence[str] | None
) -> list[str] | None:
    """
    Bound one scope level (`inner`) by a broader one (`outer`) — the pilot's
    scoping-precedence primitive (CAPAB-01 #1906).

    Semantics (empty/None = "no bound at this level"):
    - `inner` empty  → inherit `outer` unchanged;
    - `outer` empty  → `outer` is unbounded, so keep `inner` as-is;
    - both present   → intersection, so the result is a subset of BOTH.

    Used at the adapter seam to enforce `params ⊆ session_binding`; the
    capability uses the same primitive to enforce
    `turn_option ⊆ capability_config`. Chained, they give
    `turn_option ⊆ capability_config ⊆ session_binding`.
    """

    if not inner:
        return list(outer) if outer else None
    if not outer:
        return list(inner)
    allowed = set(outer)
    return [value for value in inner if value in allowed]


class DocumentSearchAdapter(DocumentSearchPort):
    """
    Runtime adapter behind `RuntimeServices.document_search` (CAPAB-01 #1906).

    Mirrors `FredKnowledgeSearchToolInvoker`: it captures the per-turn binding
    PRIVATELY (through `_VectorSearchAgentShim` + `VectorSearchClient`, which own
    the access token and its refresh) and exposes ONLY the capability-safe
    `search(...)` surface. The raw token and the binding NEVER cross into
    `CapabilityContext` — the capability reaches this port through
    `ctx.services.document_search` and passes scope PARAMETERS, never identity.

    Scope enforcement (session-binding seam): the caller-supplied
    `library_tag_ids` / `document_uids` are the capability's already-narrowed
    scope (`turn_option ⊆ capability_config`); this adapter intersects them with
    the session binding's own scope so the effective set is
    `⊆ session_binding` — completing `turn_option ⊆ capability_config ⊆
    session_binding`. General-only mode short-circuits to no hits, matching the
    builtin `knowledge.search` path.
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self._settings = settings
        self.rebind(binding)

    def rebind(self, binding: BoundRuntimeContext) -> None:
        # Hold the binding privately; the shim owns token access + refresh.
        self._binding = binding
        self._search_client = VectorSearchClient(
            agent=_VectorSearchAgentShim(binding=binding, settings=self._settings)
        )

    async def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        library_tag_ids: Sequence[str] | None = None,
        document_uids: Sequence[str] | None = None,
        search_policy: str | None = None,
        attachments_only: bool = False,
    ) -> DocumentSearchResult:
        runtime_context = self._binding.runtime_context
        if get_rag_knowledge_scope(runtime_context) == "general_only":
            return DocumentSearchResult(hits=())

        top_k = top_k if isinstance(top_k, int) and top_k > 0 else 8

        # Session-binding seam: bound the capability's params by the session's
        # own scope so the effective set stays `⊆ session_binding`.
        effective_libs = _narrow_scope_ids(
            get_document_library_tags_ids(runtime_context), library_tag_ids
        )
        effective_uids = _narrow_scope_ids(
            get_document_uids(runtime_context), document_uids
        )
        policy = search_policy or get_search_policy(runtime_context)

        team_id = self._settings.team_id
        scoped_team = bool(team_id) and not is_personal_team_id(team_id)
        include_session_scope, include_corpus_scope = get_vector_search_scopes(
            runtime_context
        )
        if attachments_only:
            # Capability-pinned scope: the conversation's session-scoped
            # documents (attached files) only, never the corpus.
            include_session_scope, include_corpus_scope = True, False

        hits = await self._search_client.search(
            question=query,
            top_k=top_k,
            document_library_tags_ids=effective_libs,
            document_uids=effective_uids,
            search_policy=policy,
            owner_filter=OwnerFilter.TEAM if scoped_team else OwnerFilter.PERSONAL,
            team_id=team_id if scoped_team else None,
            session_id=runtime_context.session_id,
            include_session_scope=include_session_scope,
            include_corpus_scope=include_corpus_scope,
        )
        return DocumentSearchResult(hits=tuple(hits))


class AgentConfigAssetsAdapter(AgentAssetPort):
    """
    Runtime adapter behind `RuntimeServices.agent_assets` (#1903, RFC §3.4/§3.8).

    Stores one agent instance's capability config assets under the KF path
    `teams/{team}/agents/{agent_instance_id}/config/{key}` through the unified
    `/fs` routes. The team and agent instance come from the privately-captured
    binding/settings — a capability only ever names the slot-relative `key`, so
    it can never write outside its own instance's config area. KF-side, reads
    are team-membership-gated (any user chatting with the agent) and writes
    require the team resource-update permission (`ScopedAreaFilesystem`).
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self._settings = settings
        self._binding = binding
        self._client = KfWorkspaceClient(
            agent=_WorkspaceAgentShim(binding=binding, settings=settings)
        )

    def _config_path(self, key: str) -> str:
        team = (
            getattr(self._binding.runtime_context, "team_id", None)
            or self._settings.team_id
        )
        instance = getattr(self._binding.runtime_context, "agent_instance_id", None)
        if not team or not instance:
            raise RuntimeError(
                "Agent-config assets require a team and an agent instance in "
                "the session context."
            )
        parts = [p for p in key.strip().replace("\\", "/").split("/") if p]
        if not parts or ".." in parts:
            raise ValueError(f"Invalid agent asset key: {key!r}")
        return f"teams/{team}/agents/{instance}/config/{'/'.join(parts)}"

    async def store(
        self,
        key: str,
        content: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        await self._client.fs_upload(
            self._config_path(key),
            content,
            filename or key.rsplit("/", 1)[-1],
            content_type=content_type,
        )
        return key

    async def fetch(self, key: str) -> bytes:
        blob = await self._client.fs_download_blob(self._config_path(key))
        return blob.bytes

    async def delete(self, key: str) -> None:
        try:
            await self._client.fs_delete(self._config_path(key))
        except WorkspaceRetrievalError:
            pass


class DocumentContentAdapter(DocumentContentPort):
    """
    Runtime adapter behind `RuntimeServices.document_content` (#1903).

    Fetches a corpus document's ORIGINAL bytes by uid with the acting user's
    identity (KF enforces document-level access). Same doctrine as
    `DocumentSearchAdapter`: the binding/token stay private; the capability
    passes only the document uid.
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self._client = KfDocumentClient(
            agent=_VectorSearchAgentShim(binding=binding, settings=settings)
        )

    async def fetch_raw(self, document_uid: str) -> DocumentRawContent:
        blob = await self._client.fetch_raw_content(document_uid=document_uid)
        return DocumentRawContent(
            content=blob.bytes,
            content_type=blob.content_type,
            filename=blob.filename,
        )


class DocumentFolderAdapter(DocumentFolderPort):
    """
    Runtime adapter behind `RuntimeServices.document_folders` (#1903).

    Resolves an author folder string to a DOCUMENT tag id in the bound space:
    the agent's team when one is set, else the acting user's personal space —
    the same scoping rule Kea's `_KfTagFolderResolver` applied.
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self._settings = settings
        self._client = KfTagClient(
            agent=_VectorSearchAgentShim(binding=binding, settings=settings)
        )

    async def resolve_folder(self, folder: str) -> str | None:
        team_id = self._settings.team_id
        scoped_team = bool(team_id) and not is_personal_team_id(team_id)
        return await self._client.resolve_folder(
            folder,
            owner_filter=OwnerFilter.TEAM if scoped_team else OwnerFilter.PERSONAL,
            team_id=team_id if scoped_team else None,
        )

    async def list_folder_documents(
        self, folder_tag_id: str
    ) -> tuple[FolderDocumentEntry, ...]:
        pairs = await self._client.browse_documents_by_tag(folder_tag_id)
        return tuple(
            FolderDocumentEntry(document_uid=uid, document_name=name)
            for uid, name in pairs
        )


def _wrap_document_port_error(exc: Exception) -> DocumentPortCallError:
    """
    Map an httpx transport failure onto the SDK-typed `DocumentPortCallError`
    so capabilities can render an actionable `is_error` tool result without
    importing the adapter's HTTP stack.
    """

    timed_out = isinstance(exc, httpx.TimeoutException)
    status_code = (
        exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    )
    detail = str(exc).strip() or type(exc).__name__
    return DocumentPortCallError(detail, timed_out=timed_out, status_code=status_code)


class DocumentTreeAdapter(DocumentTreePort):
    """
    Runtime adapter behind `RuntimeServices.document_tree`.

    Same shape as `DocumentSearchAdapter`: the per-turn binding is captured
    PRIVATELY (through `_VectorSearchAgentShim` + `KfDocumentClient`, which own
    the access token and its refresh) and only the capability-safe `tree(...)`
    surface is exposed. The caller-supplied `library_tag_ids` are the
    capability's already-narrowed scope; this adapter intersects them with the
    session binding's own library scope and stamps the owner_filter/team_id
    seam, so the Knowledge Flow listing can never leak folders across team
    boundaries.
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self._settings = settings
        self.rebind(binding)

    def rebind(self, binding: BoundRuntimeContext) -> None:
        self._binding = binding
        self._client = KfDocumentClient(
            agent=_VectorSearchAgentShim(binding=binding, settings=self._settings)
        )

    async def tree(
        self,
        *,
        working_directory: str | None = None,
        library_tag_ids: Sequence[str] | None = None,
        max_chars: int = 6000,
    ) -> DocumentTreeResult:
        runtime_context = self._binding.runtime_context
        effective_libs = _narrow_scope_ids(
            get_document_library_tags_ids(runtime_context), library_tag_ids
        )
        team_id = self._settings.team_id
        scoped_team = bool(team_id) and not is_personal_team_id(team_id)
        try:
            result = await self._client.tree(
                working_directory=working_directory,
                tag_ids=effective_libs,
                max_chars=max_chars,
                owner_filter=OwnerFilter.TEAM if scoped_team else OwnerFilter.PERSONAL,
                team_id=team_id if scoped_team else None,
            )
        except httpx.HTTPError as exc:
            raise _wrap_document_port_error(exc) from exc
        return DocumentTreeResult(tree=result.tree, truncated=result.truncated)


class DocumentSummarizeAdapter(DocumentSummarizePort):
    """
    Runtime adapter behind `RuntimeServices.document_summarize`.

    No scope narrowing here: the caller already holds a concrete
    `document_uid` (from a search hit, tree listing, or the conversation's
    attached-files context), and Knowledge Flow's own per-document ReBAC is
    the real authorization gate. The binding/token stay private;
    `KfDocumentClient` applies the extended summarize read timeout.
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self._settings = settings
        self.rebind(binding)

    def rebind(self, binding: BoundRuntimeContext) -> None:
        self._binding = binding
        self._client = KfDocumentClient(
            agent=_VectorSearchAgentShim(binding=binding, settings=self._settings)
        )

    async def summarize(
        self,
        document_uid: str,
        *,
        instruction: str | None = None,
        max_chars: int = 2000,
    ) -> DocumentSummaryResult:
        try:
            result = await self._client.summarize(
                document_uid=document_uid,
                instruction=instruction,
                max_chars=max_chars,
            )
        except httpx.HTTPError as exc:
            raise _wrap_document_port_error(exc) from exc
        return DocumentSummaryResult(
            document_uid=result.document_uid,
            summary=result.summary,
            shrunk_for_budget=result.shrunk_for_budget,
            keywords=tuple(result.keywords),
        )


class FredMcpToolProvider(ToolProviderPort):
    """
    Fred runtime bridge exposing UI-configured MCP tools to v2 ReAct agents.

    Intent:
    - keep the v2 agent definition generic
    - reuse the existing MCP catalog and per-agent `mcp_servers` settings
    - avoid pushing MCP wiring details into the author-facing SDK
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
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
        # #1978: the active MCP servers are on the settings, not the tuning
        # payload — the MCP tuning trio was retired.
        return bool(getattr(self._settings, "active_mcp_servers", ()))


class FredWorkspaceFs(WorkspaceFsPort):
    """
    Fred-side adapter exposing the team-rooted virtual filesystem to v2 runtimes.

    Agents address files by short, author-relative paths. This adapter injects the team and
    acting user from the verified session context and forwards a full team-rooted path to
    Knowledge Flow over the unified ``/fs`` routes:

    - a bare path        -> ``teams/{team}/users/{uid}/...`` (private to the acting user)
    - a leading ``shared/`` -> ``teams/{team}/shared/...``    (team-shared)
    - an absolute ``/teams/{t}/...`` is accepted only when ``t`` is the session team (§7.1)
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self._settings = settings
        self._agent = _WorkspaceAgentShim(binding=binding, settings=settings)
        self._workspace_client = KfWorkspaceClient(agent=self._agent)
        self._binding = binding

    def bind(self, binding: BoundRuntimeContext) -> None:
        self._binding = binding
        self._agent.rebind(binding)

    # ---- session context (the only source of team/user) ----
    def _session_team(self) -> str:
        team = (
            getattr(self._binding.runtime_context, "team_id", None)
            or self._settings.team_id
        )
        if not team:
            raise RuntimeError(
                "Workspace filesystem requires a team in the session context."
            )
        return str(team)

    def _session_user(self) -> str:
        uid = getattr(self._binding.runtime_context, "user_id", None)
        if not uid:
            raise RuntimeError(
                "Workspace filesystem requires a user in the session context."
            )
        return str(uid)

    def _session_agent_instance_id(self) -> str:
        # The agents subtree is keyed by the immutable per-team agent_instance_id
        # (FILES-04 / docs/swift/design/FILESYSTEM.md), injected from the execution grant
        # — never the template agent_id, never agent-supplied.
        aid = getattr(self._binding.runtime_context, "agent_instance_id", None)
        if not aid:
            raise RuntimeError(
                "Workspace filesystem requires an agent instance in the session context."
            )
        return str(aid)

    def _token(self) -> str:
        return _workspace_access_token(self._binding.runtime_context)

    # ---- path relativization (§7.1 security rule) ----
    def _resolve(self, path: str, *, allow_root: bool = False) -> str:
        team = self._session_team()
        # Bare agent paths resolve to the running agent's own per-user space
        # (FILES-04 / docs/swift/design/FILESYSTEM.md), not Mon espace.
        agent_root = (
            f"teams/{team}/agents/{self._session_agent_instance_id()}"
            f"/users/{self._session_user()}"
        )
        parts = [p for p in (path or "").strip().replace("\\", "/").split("/") if p]
        if ".." in parts:
            raise ValueError("Path cannot contain parent path segments")
        if not parts:
            if allow_root:
                return agent_root
            raise ValueError("Path cannot be empty")
        head = parts[0]
        if head == "teams":
            # absolute restatement: must name the session team, never another
            if len(parts) < 2 or parts[1] != team:
                named = parts[1] if len(parts) > 1 else ""
                raise PermissionError(
                    f"Path team '{named}' is not the session team '{team}'."
                )
            return "/".join(parts)
        if head == "shared":
            # Team-shared reads (e.g. resolve_template's team step) stay addressable;
            # write/delete into shared is rejected separately (agents never share).
            return f"teams/{team}/" + "/".join(parts)
        return f"{agent_root}/" + "/".join(parts)

    def _agent_root(self) -> str:
        return (
            f"teams/{self._session_team()}/agents/{self._session_agent_instance_id()}"
            f"/users/{self._session_user()}"
        )

    def _resolve_owned(self, path: str) -> str:
        """
        Resolve a path the agent must own — used for write and delete.

        Agents read team-shared files and their own space, but may only *mutate*
        inside their own agents subtree. A path resolving outside it — into
        ``shared/`` (G3: agents never share), Mon espace, or a sibling agent's
        subtree (G2) — is a hard ``PermissionError`` (FILES-04).
        """
        resolved = self._resolve(path)
        root = self._agent_root()
        if resolved != root and not resolved.startswith(root + "/"):
            raise PermissionError(
                f"Agents may only write inside their own space; '{path}' resolves outside it."
            )
        return resolved

    def _clean_parts(self, path: str) -> list[str]:
        parts = [p for p in (path or "").strip().replace("\\", "/").split("/") if p]
        if ".." in parts:
            raise ValueError("Path cannot contain parent path segments")
        return parts

    def _resolve_user(self, path: str) -> str:
        # Explicit read of the run user's Mon espace (FILES-04) — same
        # user the agent acts for; KF enforces own-uid ownership. v1 reads the whole
        # Mon espace; selection-scoping (§7.3) is deferred hardening, like G1b.
        return f"teams/{self._session_team()}/users/{self._session_user()}/" + "/".join(
            self._clean_parts(path)
        )

    def _resolve_team(self, path: str) -> str:
        # Explicit read of the team's Espace d'equipe; governed by the user's team read.
        return f"teams/{self._session_team()}/shared/" + "/".join(
            self._clean_parts(path)
        )

    # ---- operations ----
    async def _download(self, resolved: str, original: str) -> bytes:
        try:
            blob = await self._workspace_client.fs_download_blob(
                resolved, self._token()
            )
        except WorkspaceRetrievalError as e:
            if e.status_code == 404:
                raise WorkspaceFileNotFound(original) from e
            raise
        return blob.bytes

    async def read_bytes(self, path: str) -> bytes:
        return await self._download(self._resolve(path), path)

    async def read_text(self, path: str) -> str:
        return (await self.read_bytes(path)).decode("utf-8")

    async def read_user_bytes(self, path: str) -> bytes:
        return await self._download(self._resolve_user(path), path)

    async def read_team_bytes(self, path: str) -> bytes:
        return await self._download(self._resolve_team(path), path)

    async def write(
        self,
        path: str,
        content: bytes,
        *,
        content_type: str | None = None,
        title: str | None = None,
    ) -> PublishedArtifact:
        resolved = self._resolve_owned(path)
        file_name = resolved.rsplit("/", 1)[-1]
        result = await self._workspace_client.fs_upload(
            resolved, content, file_name, content_type
        )
        return PublishedArtifact(
            key=result.key,
            file_name=result.file_name or file_name,
            size=result.size,
            href=result.download_url,
            document_uid=_coerce_optional_string(result.document_uid),
            mime=content_type,
            title=title or file_name,
        )

    async def ls(self, path: str = "") -> list[FsEntry]:
        entries = await self._workspace_client.fs_list(
            self._resolve(path, allow_root=True), self._token()
        )
        return [
            FsEntry(path=entry.path, size=entry.size, is_dir=entry.is_directory())
            for entry in entries
        ]

    async def delete(self, path: str) -> None:
        await self._workspace_client.fs_delete(self._resolve_owned(path), self._token())

    async def link_for(self, path: str) -> PublishedArtifact:
        resolved = self._resolve(path)
        link = await self._workspace_client.fs_share(resolved, self._token())
        file_name = link.file_name or resolved.rsplit("/", 1)[-1]
        return PublishedArtifact(
            key=resolved,
            file_name=file_name,
            size=link.size or 0,
            href=link.download_url,
            mime=link.mime,
            title=file_name,
        )


class _VectorSearchAgentShim:
    """
    Minimal object accepted by the existing Knowledge Flow clients.

    This is a deliberate bridge:
    - the new v2 runtime should not inherit from legacy agent base classes
    - the existing HTTP clients still expect an agent-like object for token and
      KPI context
    """

    def __init__(
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
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
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
    ) -> None:
        self.runtime_context = binding.runtime_context
        self.agent_settings = settings

    def rebind(self, binding: BoundRuntimeContext) -> None:
        self.runtime_context = binding.runtime_context

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
        self, *, binding: BoundRuntimeContext, settings: AgentSettingsLike
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
    raw_refresh = payload.get("refresh_token")
    new_refresh_token: str = (
        raw_refresh if isinstance(raw_refresh, str) and raw_refresh else refresh_token
    )
    if not isinstance(new_access_token, str) or not new_access_token:
        raise RuntimeError(
            "Keycloak refresh response did not include a valid access_token."
        )

    runtime_context.access_token = new_access_token
    runtime_context.refresh_token = new_refresh_token

    expires_at = payload.get("expires_at_timestamp")
    if isinstance(expires_at, (int, float)):
        runtime_context.access_token_expires_at = int(expires_at)

    return new_access_token


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
            latency_ms = _observation_latency_ms(raw.get("latency"))
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
        latency_ms = _observation_latency_ms(raw.get("latency"))
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


def _observation_latency_ms(raw_latency: object) -> int:
    # Langfuse public API expresses observation latency in seconds (same as trace latency).
    if isinstance(raw_latency, bool):
        return 0
    if isinstance(raw_latency, int | float):
        return max(0, int(float(raw_latency) * 1000))
    if isinstance(raw_latency, str):
        try:
            return max(0, int(float(raw_latency.strip()) * 1000))
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


class KPIWriterMetricsAdapter(MetricsProvider):
    """
    Adapts a fred-core BaseKPIWriter to the MetricsProvider protocol.

    Why this exists:
    - RuntimeServices.metrics expects a MetricsProvider
    - Fred's existing KPI infrastructure (Prometheus, OpenSearch) implements BaseKPIWriter
    - this adapter bridges them without touching the KPI infrastructure

    How to use it:
    - wrap the result of get_kpi_writer() when constructing RuntimeServices
    - Example: `RuntimeServices(metrics=KPIWriterMetricsAdapter(get_kpi_writer()))`
    """

    def __init__(self, kpi: BaseKPIWriter) -> None:
        self._kpi = kpi

    @contextmanager
    def timer(
        self,
        name: str,
        *,
        dims: dict[str, str | None] | None = None,
    ) -> Generator[dict[str, str | None], None, None]:
        with self._kpi.timer(
            name,
            dims=dims,
            actor=KPIActor(type="system"),
        ) as recorded_dims:
            yield recorded_dims
