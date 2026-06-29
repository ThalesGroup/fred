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
Exact catalog of native Fred built-in tools for v2 agents.

Why this module exists:
- an agent author can read one file to see which native Fred tools are already
  available when creating a new profile, ReAct agent, or Deep agent
- a Fred core developer can extend the native built-in catalog in one explicit
  place instead of scattering tool metadata across the runtime
- built-in tools are different from Python-authored tools and MCP/runtime tools
  because Fred ships them directly
- the runtime resolver needs one place to read the input schema and execution
  backend for each built-in tool

Exact built-in list today:
- `knowledge.search`: Fred's native RAG retrieval tool. It searches the current
  libraries, corpus, and session attachments and returns grounded snippets.
- `logs.query`: troubleshooting tool for recent backend logs from Agentic and
  Knowledge Flow.
- `traces.summarize_conversation`: observability tool that summarizes the recent
  execution trace of one Fred conversation.
- `geo.render_points`: UI helper that turns latitude/longitude points into a map
  payload Fred can render.
- `artifacts.publish_text`: output helper that creates a downloadable text
  artifact for the user.
- `resources.fetch_text`: configuration/support helper that loads a Fred-managed
  text resource by key and scope.
- `attachments.read_image`: multimodal helper that fetches one image (a
  conversation attachment or an image inside an ingested document) and hands its
  pixels to a vision-capable model without putting base64 in prompt text.

How to use it:
- agent author:
  import the `TOOL_REF_*` constants when a new agent definition should depend on
  one native Fred tool
- Fred core developer:
  update this catalog when adding a new native built-in tool to Fred itself
- runtime code:
  call `get_builtin_tool_spec(...)` when it needs the schema or backend for one
  built-in tool
- review/debug code:
  call `list_builtin_tool_specs()` when it needs the full native catalog

Example:
- agent author:
  `declared_tool_refs=(ToolRefRequirement(tool_ref=TOOL_REF_KNOWLEDGE_SEARCH),)`
- runtime:
  `spec = get_builtin_tool_spec(TOOL_REF_KNOWLEDGE_SEARCH)`
- review/debug:
  `all_specs = list_builtin_tool_specs()`
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TOOL_REF_KNOWLEDGE_SEARCH = "knowledge.search"
TOOL_REF_LOGS_QUERY = "logs.query"
TOOL_REF_TRACES_SUMMARIZE_CONVERSATION = "traces.summarize_conversation"
TOOL_REF_GEO_RENDER_POINTS = "geo.render_points"
TOOL_REF_ARTIFACTS_PUBLISH_TEXT = "artifacts.publish_text"
TOOL_REF_RESOURCES_FETCH_TEXT = "resources.fetch_text"
TOOL_REF_ATTACHMENTS_READ_IMAGE = "attachments.read_image"


class BuiltinToolBackend(str, Enum):
    """
    Execution backend used by one built-in Fred tool.

    Why this exists:
    - built-in tools are few, but they do not all execute through the same port
    - the runtime resolver needs one explicit backend choice instead of hidden
      conditionals spread across the codebase

    Current mapping:
    - `TOOL_INVOKER`: `knowledge.search`, `logs.query`,
      `traces.summarize_conversation`, `geo.render_points`,
      `attachments.read_image`
    - `WORKSPACE_WRITE`: `artifacts.publish_text`
    - `WORKSPACE_READ`: `resources.fetch_text`
    """

    TOOL_INVOKER = "tool_invoker"
    WORKSPACE_WRITE = "workspace_write"
    WORKSPACE_READ = "workspace_read"


class KnowledgeSearchToolArgs(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language search query to run against the selected corpus.",
    )
    top_k: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Maximum number of retrieved snippets to return.",
    )


class LogsQueryToolArgs(BaseModel):
    window_minutes: int = Field(
        default=5,
        ge=1,
        le=60,
        description="How far back to scan logs.",
    )
    limit: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Maximum number of events to fetch per backend.",
    )
    min_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="WARNING",
        description="Minimum log level to include in the query.",
    )
    include_agentic: bool = Field(
        default=True,
        description="Whether to include Agentic backend logs.",
    )
    include_knowledge_flow: bool = Field(
        default=True,
        description="Whether to include Knowledge Flow logs.",
    )
    max_events: int = Field(
        default=200,
        ge=50,
        le=1000,
        description="Cap the events kept in the returned triage digest.",
    )


class TracesSummarizeConversationToolArgs(BaseModel):
    fred_session_id: str | None = Field(
        default=None,
        description=(
            "Fred session id to inspect. If omitted, the currently bound session id "
            "is used."
        ),
    )
    agent_name: str | None = Field(
        default=None,
        description="Optional human-readable agent name filter (for example BidMgr).",
    )
    agent_id: str | None = Field(
        default=None,
        description="Optional agent id filter.",
    )
    team_id: str | None = Field(
        default=None,
        description="Optional team id filter.",
    )
    user_name: str | None = Field(
        default=None,
        description="Optional username filter.",
    )
    trace_limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="How many recent traces to scan before selecting a match.",
    )
    top_spans: int = Field(
        default=10,
        ge=1,
        le=50,
        description="How many top-latency spans to include in the digest.",
    )
    include_timeline: bool = Field(
        default=True,
        description="Whether to include a compact ordered span timeline.",
    )


class GeoPointArgs(BaseModel):
    name: str | None = Field(
        default=None,
        description="Human-readable point label shown in map popups when available.",
    )
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    properties: dict[str, object] = Field(
        default_factory=dict,
        description="Additional GeoJSON properties attached to the point.",
    )


class GeoRenderPointsToolArgs(BaseModel):
    title: str = Field(
        default="Map results",
        description="Short textual summary accompanying the rendered map.",
    )
    points: list[GeoPointArgs] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Latitude/longitude points to render as a GeoJSON feature collection.",
    )
    popup_property: str | None = Field(
        default="name",
        description="Feature property to show in popups when present.",
    )
    fit_bounds: bool = Field(
        default=True,
        description="Whether the UI should fit the map viewport to the returned features.",
    )


class ArtifactPublishTextToolArgs(BaseModel):
    file_name: str = Field(
        ...,
        min_length=1,
        description=(
            "File name (storage address) for the artifact in your workspace, for "
            "example report.md or summary.txt. Writing an existing name overwrites it."
        ),
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Full textual content to publish for the user.",
    )
    title: str | None = Field(
        default=None,
        description="Optional user-facing title shown for the returned download link.",
    )
    content_type: str = Field(
        default="text/plain; charset=utf-8",
        description="MIME type of the generated text artifact.",
    )


class ResourceFetchTextToolArgs(BaseModel):
    path: str = Field(
        ...,
        min_length=1,
        description=(
            "Team-rooted file path to read. A bare path is your private space "
            "(e.g. 'templates/notes.md'); prefix with 'shared/' for the team's shared space."
        ),
    )


class AttachmentsReadImageToolArgs(BaseModel):
    """
    Arguments for ``attachments.read_image`` (RUNTIME-08).

    The model never sees storage keys, internal paths, or presigned URLs. It
    references one image by an explicit source plus a stable id:

    - ``conversation_attachment``: an image uploaded as a chat attachment in the
      current conversation, referenced by ``attachment_id`` (session-scoped).
    - ``document_media``: an image stored inside an ingested document in the
      corpus, referenced by ``document_uid`` + ``file_name`` (ReBAC-scoped).

    The runtime resolves the reference, enforces authorization, fetches the
    image, and hands it to a vision-capable model as multimodal content.
    """

    source: Literal["conversation_attachment", "document_media"] = Field(
        ...,
        description=(
            "Where the image lives. Use 'conversation_attachment' for an image the "
            "user attached to this conversation, or 'document_media' for an image "
            "stored inside an ingested document/corpus item."
        ),
    )
    attachment_id: str | None = Field(
        default=None,
        description=(
            "Required when source is 'conversation_attachment'. The stable id of the "
            "chat attachment, as announced in the conversation attachment metadata."
        ),
    )
    document_uid: str | None = Field(
        default=None,
        description=(
            "Required when source is 'document_media'. The uid of the document that "
            "contains the image, as returned by knowledge.search results."
        ),
    )
    file_name: str | None = Field(
        default=None,
        description=(
            "Required when source is 'document_media'. The image file name within the "
            "document (for example 'page-1-image-2.png')."
        ),
    )

    @model_validator(mode="after")
    def _require_fields_for_source(self) -> "AttachmentsReadImageToolArgs":
        if self.source == "conversation_attachment":
            if not self.attachment_id:
                raise ValueError(
                    "attachment_id is required when source is 'conversation_attachment'."
                )
        elif self.source == "document_media":
            if not self.document_uid or not self.file_name:
                raise ValueError(
                    "document_uid and file_name are required when source is "
                    "'document_media'."
                )
        return self


@dataclass(frozen=True)
class BuiltinToolSpec:
    """
    Metadata describing one built-in Fred tool.

    Why this exists:
    - built-in tools need one compact declaration that pairs the stable tool ref
      with its input schema and runtime backend
    - the runtime resolver should read this data, not rebuild it

    Exact tools described by this catalog today:
    - `knowledge.search`: native Fred retrieval / RAG tool
    - `logs.query`: backend log triage tool
    - `traces.summarize_conversation`: conversation trace summary tool
    - `geo.render_points`: map-rendering helper
    - `artifacts.publish_text`: text artifact publishing helper
    - `resources.fetch_text`: Fred-managed text resource reader

    How to use it:
    - authors normally reference the `TOOL_REF_*` constants
    - runtime code reads `BuiltinToolSpec` when it needs the input schema,
      backend, or default description for one built-in tool

    Example:
    - `spec = get_builtin_tool_spec(TOOL_REF_KNOWLEDGE_SEARCH)`
    """

    tool_ref: str
    args_schema: type[BaseModel]
    backend: BuiltinToolBackend
    default_description: str


_BUILTIN_TOOL_SPECS: dict[str, BuiltinToolSpec] = {
    TOOL_REF_KNOWLEDGE_SEARCH: BuiltinToolSpec(
        tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
        args_schema=KnowledgeSearchToolArgs,
        backend=BuiltinToolBackend.TOOL_INVOKER,
        default_description=(
            "Search the selected document libraries and session attachments and "
            "return grounded snippets."
        ),
    ),
    TOOL_REF_LOGS_QUERY: BuiltinToolSpec(
        tool_ref=TOOL_REF_LOGS_QUERY,
        args_schema=LogsQueryToolArgs,
        backend=BuiltinToolBackend.TOOL_INVOKER,
        default_description="Query recent Agentic and Knowledge Flow logs.",
    ),
    TOOL_REF_TRACES_SUMMARIZE_CONVERSATION: BuiltinToolSpec(
        tool_ref=TOOL_REF_TRACES_SUMMARIZE_CONVERSATION,
        args_schema=TracesSummarizeConversationToolArgs,
        backend=BuiltinToolBackend.TOOL_INVOKER,
        default_description=(
            "Summarize one Fred conversation execution from Langfuse traces "
            "(bottlenecks, node path, and timing)."
        ),
    ),
    TOOL_REF_GEO_RENDER_POINTS: BuiltinToolSpec(
        tool_ref=TOOL_REF_GEO_RENDER_POINTS,
        args_schema=GeoRenderPointsToolArgs,
        backend=BuiltinToolBackend.TOOL_INVOKER,
        default_description="Render one or more latitude/longitude points as a map.",
    ),
    TOOL_REF_ARTIFACTS_PUBLISH_TEXT: BuiltinToolSpec(
        tool_ref=TOOL_REF_ARTIFACTS_PUBLISH_TEXT,
        args_schema=ArtifactPublishTextToolArgs,
        backend=BuiltinToolBackend.WORKSPACE_WRITE,
        default_description=(
            "Publish a generated text artifact for the user and return a download link."
        ),
    ),
    TOOL_REF_RESOURCES_FETCH_TEXT: BuiltinToolSpec(
        tool_ref=TOOL_REF_RESOURCES_FETCH_TEXT,
        args_schema=ResourceFetchTextToolArgs,
        backend=BuiltinToolBackend.WORKSPACE_READ,
        default_description="Fetch a Fred-managed text template or support resource.",
    ),
    TOOL_REF_ATTACHMENTS_READ_IMAGE: BuiltinToolSpec(
        tool_ref=TOOL_REF_ATTACHMENTS_READ_IMAGE,
        args_schema=AttachmentsReadImageToolArgs,
        backend=BuiltinToolBackend.TOOL_INVOKER,
        default_description=(
            "Inspect the full pixels/layout of an image — either a conversation "
            "attachment (by attachment_id) or an image inside an ingested document "
            "(by document_uid + file_name). Use this instead of document search when "
            "the question is about what the image actually shows."
        ),
    ),
}


def get_builtin_tool_spec(tool_ref: str) -> BuiltinToolSpec | None:
    """
    Return the built-in tool spec for one exact tool ref.

    Why this exists:
    - runtime code should ask one catalog for built-in tool metadata
    - returning `None` makes it explicit when a tool ref is not part of the small
      built-in catalog

    How to use:
    - pass the exact `tool_ref` declared by an agent

    Example:
    - `spec = get_builtin_tool_spec("knowledge.search")`
    """

    return _BUILTIN_TOOL_SPECS.get(tool_ref)


def list_builtin_tool_specs() -> tuple[BuiltinToolSpec, ...]:
    """
    Return the full built-in tool catalog as an ordered tuple.

    Why this exists:
    - inspection or debug code sometimes needs to show the complete built-in
      catalog without touching the private module dictionary

    How to use:
    - call when rendering diagnostics or validating the built-in tool surface

    Example:
    - `all_specs = list_builtin_tool_specs()`
    """

    return tuple(_BUILTIN_TOOL_SPECS.values())
