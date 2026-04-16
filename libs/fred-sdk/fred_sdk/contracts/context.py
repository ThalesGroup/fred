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
Context and capability payloads shared by the v2 runtime surface.

Why this module exists:
- keep portable execution context and typed capability payloads explicit
- give v2 runtimes one Fred-owned contract for tool calls, artifact publication,
  and resource reads
- make the current migration state visible: `portable_context` is the preferred
  long-term contract, while `runtime_context` remains a transitional compatibility
  bridge for existing Fred behavior that has not been ported yet

How to use:
- prefer `PortableContext` when propagating tracing, identity, and small portable
  execution metadata
- prefer explicit request/result models (`ToolInvocationRequest`,
  `ArtifactPublishRequest`, `ResourceFetchRequest`) over direct service or storage
  client access
- use `BoundRuntimeContext.runtime_context` only when one existing Fred behavior
  still depends on legacy runtime fields and no narrower v2 capability exists yet

Example:
- `binding.portable_context.session_id`
- `await services.resource_reader.fetch(ResourceFetchRequest(key="template.md"))`
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Dict, Literal, Optional

from fred_core.store import VectorSearchHit
from pydantic import BaseModel, ConfigDict, Field

# NOTE: This module is the canonical home for portable context + UI parts.
# Keep Link/Geo parts and RuntimeContext here to avoid circular imports.


class LinkKind(str, Enum):
    citation = "citation"  # source supporting the answer
    download = "download"  # file to fetch (pdf, csv, etc.)
    external = "external"  # generic external link
    dashboard = "dashboard"  # e.g., Grafana, Kibana
    related = "related"  # further reading
    view = "view"  # for pdf preview


class LinkPart(BaseModel):
    """
    Why this exists:
      - The UI needs a typed, explicit way to render links without parsing free text.
      - Lets agents express intent (citation/download/etc.) so the UI can group + style.
    """

    type: Literal["link"] = "link"
    href: Optional[str] = None  # absolute URL
    title: Optional[str] = None  # human label; fallback to href if None
    kind: LinkKind = LinkKind.external
    rel: Optional[str] = None  # e.g. "noopener", "noreferrer", "ugc"
    mime: Optional[str] = None  # e.g. "application/pdf"
    source_id: Optional[str] = None
    # ^ if this link corresponds to a VectorSearchHit (metadata.sources),
    #   set source_id = hit.id so the UI can cross-highlight.
    document_uid: Optional[str] = None
    file_name: Optional[str] = None


class GeoPart(BaseModel):
    """
    Why this exists:
      - Maps shouldn't be 'imagined' from text. We carry real data (GeoJSON FeatureCollection)
        so the UI can render it with Leaflet immediately.
      - Optional presentation hints keep style logic minimal in the UI.
    """

    type: Literal["geo"] = "geo"
    # Strict GeoJSON to avoid format proliferation; agents must normalize before emitting.
    # Expecting: {"type":"FeatureCollection","features":[...]}
    geojson: Dict[str, Any]
    # Optional UI hints; the UI should treat all as best-effort:
    popup_property: Optional[str] = None  # property to show in popups if present
    fit_bounds: bool = True  # auto-fit map to the features
    style: Optional[Dict[str, Any]] = None
    # e.g. {"weight":2,"opacity":0.8,"fillOpacity":0.1}


class RuntimeContext(BaseModel):
    """
    Runtime-scoped context passed with a request.

    Why: carry per-request identity, selection, and auth data to runtime services.
    How: attach a RuntimeContext to the runtime binding or execution request.
    Example:
        >>> ctx = RuntimeContext(session_id="s-1", user_id="u-1")
    """

    language: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    user_groups: list[str] | None = None
    selected_document_libraries_ids: list[str] | None = None
    selected_document_uids: list[str] | None = None
    selected_chat_context_ids: list[str] | None = None
    search_policy: str | None = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    access_token_expires_at: Optional[int] = None
    attachments_markdown: Optional[str] = (
        None  # if the session has some attachement files, this will hold their markdown representation
    )
    search_rag_scope: Optional[Literal["corpus_only", "hybrid", "general_only"]] = None
    deep_search: Optional[bool] = None
    include_session_scope: Optional[bool] = None
    include_corpus_scope: Optional[bool] = None


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class PortableEnvironment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


JsonScalar = str | int | float | bool | None


class PortableContext(FrozenModel):
    """
    Portable cross-platform execution context.

    This is intentionally narrower than Fred RuntimeContext and aligns with the
    capability-oriented SDK shape: correlation, identity, environment, and small
    non-sensitive baggage.
    """

    request_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)
    tenant: str = Field(..., min_length=1)
    environment: PortableEnvironment
    trace_id: str | None = None
    client_app: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    agent_version: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    team_id: str | None = None
    baggage: dict[str, str] = Field(default_factory=dict)


class ToolInvocationRequest(FrozenModel):
    tool_ref: str = Field(..., min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)
    context: PortableContext
    timeout_ms: int = Field(default=5000, ge=100)
    idempotency_key: str | None = None


class ToolContentKind(str, Enum):
    TEXT = "text"
    JSON = "json"


class ToolContentBlock(FrozenModel):
    kind: ToolContentKind
    text: str | None = None
    data: dict[str, object] | None = None


UiPart = Annotated[LinkPart | GeoPart, Field(discriminator="type")]


class ToolInvocationResult(FrozenModel):
    tool_ref: str = Field(..., min_length=1)
    blocks: tuple[ToolContentBlock, ...] = ()
    sources: tuple[VectorSearchHit, ...] = ()
    ui_parts: tuple[UiPart, ...] = ()
    is_error: bool = False


class AgentInvocationRequest(FrozenModel):
    """
    Typed request to invoke a registered fred v2 agent from a graph node.

    Why this model exists:
    - gives the ``AgentInvokerPort`` a stable, versioned contract that is
      independent of transport (in-process, Temporal child workflow, HTTP)
    - keeps ``agent_id`` and ``message`` explicit rather than scattered kwargs

    How to use it:
    - constructed automatically by ``GraphNodeContext.invoke_agent``; authors
      do not need to build this directly
    """

    agent_id: str = Field(..., min_length=1)
    """Stable definition ref of the target agent (e.g. ``"v2.sample.resume_parser"``)."""

    message: str = Field(..., min_length=1)
    """The user-turn message sent to the target agent."""

    context: PortableContext
    """Propagated execution context (identity, tracing, tenant, session)."""


class AgentInvocationResult(FrozenModel):
    """
    Typed output returned when one agent invokes another.

    Why this model exists:
    - agents return richer output than tools: structured text, optional UI
      parts (maps, links), and ranked sources
    - using ``content: str`` rather than ``blocks: tuple[ToolContentBlock, ...]``
      matches the agent output contract (``GraphExecutionOutput``) and gives
      callers a direct, readable field without block-list traversal
    - having a distinct type from ``ToolInvocationResult`` makes the call-site
      intent clear: this is an agent-to-agent interaction, not a tool call

    How to use it:
    - read ``result.content`` for the agent's primary text response
    - read ``result.ui_parts`` for any structured UI elements the agent produced
    - read ``result.sources`` for any knowledge sources the agent cited
    - check ``result.is_error`` before trusting ``content``

    Example::

        result = await context.invoke_agent(
            agent_id="v2.sample.screening.resume_parser",
            message=f"Parse this resume: {resume_text}",
        )
        if not result.is_error:
            parsed_json = result.content
    """

    agent_id: str = Field(..., min_length=1)
    """The agent that was invoked."""

    content: str = ""
    """Primary text response from the agent."""

    sources: tuple[VectorSearchHit, ...] = ()
    """Knowledge sources cited by the agent, if any."""

    ui_parts: tuple[UiPart, ...] = ()
    """Structured UI elements produced by the agent (maps, download links, etc.)."""

    is_error: bool = False
    """True when the agent failed; ``content`` may contain an error description."""


class ArtifactScope(str, Enum):
    """
    Where a generated file should live in Fred.

    This is a business choice, not an implementation detail:
    - `USER` for files handed back to the end user
    - `AGENT_CONFIG` for agent-managed shared assets
    - `AGENT_USER` for agent-private notes scoped to one user
    """

    USER = "user"
    AGENT_CONFIG = "agent_config"
    AGENT_USER = "agent_user"


class ResourceScope(str, Enum):
    """
    Where an already-existing Fred resource should be read from.

    This is the other half of artifact publication:
    - admins upload shared templates and configuration under `AGENT_CONFIG`
    - users and agents exchange generated files under `USER`
    - agents can keep per-user notes or resources under `AGENT_USER`
    """

    USER = "user"
    AGENT_CONFIG = "agent_config"
    AGENT_USER = "agent_user"


class ArtifactPublishRequest(FrozenModel):
    """
    Typed request to publish a generated artifact through Fred storage.

    The goal is to let agents express "publish this report for the user" without
    hard-coding URLs, storage paths, or transport details.
    """

    file_name: str = Field(..., min_length=1)
    content_bytes: bytes = Field(..., min_length=1)
    scope: ArtifactScope = ArtifactScope.USER
    key: str | None = None
    content_type: str | None = None
    title: str | None = None
    link_kind: LinkKind = LinkKind.download
    target_user_id: str | None = None


class PublishedArtifact(FrozenModel):
    """
    Stable description of a file that Fred stored for an agent run.

    Returning this object instead of a raw URL keeps the capability explicit and
    makes it easy to convert the result into the UI-facing `LinkPart`.
    """

    scope: ArtifactScope
    key: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    size: int = Field(..., ge=0)
    href: str | None = None
    document_uid: str | None = None
    mime: str | None = None
    title: str | None = None
    link_kind: LinkKind = LinkKind.download

    def to_link_part(self) -> LinkPart:
        return LinkPart(
            href=self.href,
            title=self.title or self.file_name,
            kind=self.link_kind,
            mime=self.mime,
            document_uid=self.document_uid,
            file_name=self.file_name,
        )


class ResourceFetchRequest(FrozenModel):
    """
    Typed request to read a resource that already exists in Fred storage.

    This gives v2 agents a clear business story for templates and supporting
    assets: ask Fred for "the configured template" or "the per-user note",
    rather than constructing storage URLs or workspace paths by hand.
    """

    key: str = Field(..., min_length=1)
    scope: ResourceScope = ResourceScope.AGENT_CONFIG
    target_user_id: str | None = None


class FetchedResource(FrozenModel):
    """
    Stable description of a resource fetched from Fred storage.

    A business node can inspect metadata, decode text when appropriate, or pass
    the bytes to a downstream renderer without knowing anything about the
    underlying workspace transport.
    """

    scope: ResourceScope
    key: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    size: int = Field(..., ge=0)
    content_bytes: bytes = Field(default=b"")
    content_type: str | None = None

    def as_text(self, *, encoding: str = "utf-8") -> str:
        return self.content_bytes.decode(encoding)


class BoundRuntimeContext(FrozenModel):
    """
    Platform bind result combining the Fred RuntimeContext with a portable
    context that can be propagated through tracing, tool invocation, and
    future registry integrations.

    Important migration note:
    - `portable_context` is the preferred v2 contract for new code
    - `runtime_context` remains available because current production v2 runtimes
      still depend on legacy Fred fields for concerns such as language, auth token
      refresh, and some retrieval/session behavior
    - new helpers and new runtime capabilities should prefer explicit ports or
      `portable_context` instead of expanding direct `runtime_context` usage
    """

    runtime_context: RuntimeContext = Field(
        ...,
        description=(
            "Legacy Fred runtime context kept as a transitional compatibility bridge. "
            "New v2 code should prefer portable_context or explicit runtime ports when possible."
        ),
    )
    portable_context: PortableContext = Field(
        ...,
        description=(
            "Preferred portable execution context for v2 code. "
            "Use this for tracing, correlation, identity, and small non-sensitive execution metadata."
        ),
    )
