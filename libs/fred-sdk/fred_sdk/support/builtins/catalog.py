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
- `knowledge.similarity_search`: targeted comparison search. Ranks the passages
  most similar to an anchor text, restricted to an explicit set of document
  uids — a comparison primitive (document-to-document), not a corpus-wide
  question-answering search like `knowledge.search`.
- `traces.summarize_conversation`: observability tool that summarizes the recent
  execution trace of one Fred conversation.
- `geo.render_points`: UI helper that turns latitude/longitude points into a map
  payload Fred can render.
- `chart.render`: UI helper that turns returned tabular rows into a chart.


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

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field, ValidationError, model_validator

from fred_sdk.contracts.context import (
    GeoPart,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)

from .chart import ChartPart, ChartRenderToolArgs, render_chart

TOOL_REF_KNOWLEDGE_SEARCH = "knowledge.search"
TOOL_REF_SIMILARITY_SEARCH = "knowledge.similarity_search"
TOOL_REF_TRACES_SUMMARIZE_CONVERSATION = "traces.summarize_conversation"
TOOL_REF_GEO_RENDER_POINTS = "geo.render_points"
TOOL_REF_CHART_RENDER = "chart.render"


class BuiltinToolBackend(str, Enum):
    """
    Execution backend used by one built-in Fred tool.

    Why this exists:
    - built-in tools are few, but they do not all execute through the same port
    - the runtime resolver needs one explicit backend choice instead of hidden
      conditionals spread across the codebase

    Current mapping:
    - `TOOL_INVOKER`: `knowledge.search`, `knowledge.similarity_search`,
      `traces.summarize_conversation`
    - `LOCAL`: SDK-owned pure rendering tools
    """

    TOOL_INVOKER = "tool_invoker"
    LOCAL = "local"


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


class SimilaritySearchToolArgs(BaseModel):
    anchor: str = Field(
        ...,
        min_length=1,
        description="Passage to find similar content for (a chunk of text, not a question).",
    )
    document_uids: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Explicit document uids to search within. Required — this is a "
            "targeted comparison primitive, not a corpus-wide search."
        ),
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of matches to return, best-first.",
    )
    rerank: bool = Field(
        default=True,
        description="Re-rank the best-first results with the cross-encoder.",
    )
    min_score: float | None = Field(
        default=None,
        description="Drop matches scoring below this relevance threshold.",
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
        description="Human-readable point label shown directly on the map when space permits; overrides properties.name.",
    )
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    properties: dict[str, object] = Field(
        default_factory=dict,
        description="Optional scalar details (strings, numbers, booleans) shown as a short hover preview and in full on click, for example {'description': 'Home port'}. Styling keys color and fillOpacity are not shown as details.",
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
    connect_as_zone: bool = Field(
        default=False,
        description="Set true only when the user asks to connect the supplied points into a closed zone. Provide at least three distinct coordinates in boundary order; the tool closes the zone automatically and keeps the point markers.",
    )
    popup_property: str | None = Field(
        default="name",
        description="Feature property to show in popups when present.",
    )
    fit_bounds: bool = Field(
        default=True,
        description="Whether the UI should fit the map viewport to the returned features.",
    )

    @model_validator(mode="after")
    def validate_zone_points(self) -> GeoRenderPointsToolArgs:
        if (
            self.connect_as_zone
            and len({(point.latitude, point.longitude) for point in self.points}) < 3
        ):
            raise ValueError("A zone requires at least three distinct GPS coordinates.")
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
    - `knowledge.similarity_search`: targeted document-to-document comparison
    - `traces.summarize_conversation`: conversation trace summary tool
    - `geo.render_points`: map-rendering helper
    - `chart.render`: chart-rendering helper

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
    local_handler: Callable[[dict[str, object]], ToolInvocationResult] | None = None
    output_part: type[BaseModel] | None = None

    def invoke_local(self, payload: dict[str, object]) -> ToolInvocationResult:
        if self.backend != BuiltinToolBackend.LOCAL or self.local_handler is None:
            raise RuntimeError(f"Built-in {self.tool_ref} has no local handler.")
        try:
            return self.local_handler(payload)
        except ValidationError as exc:
            return ToolInvocationResult(
                tool_ref=self.tool_ref,
                blocks=(
                    ToolContentBlock(
                        kind=ToolContentKind.TEXT,
                        text=self.validation_error_text(exc),
                    ),
                ),
                is_error=True,
            )

    def validation_error_text(self, exc: ValidationError) -> str:
        first_error = exc.errors(include_input=False)[0]
        location = ".".join(str(part) for part in first_error["loc"])
        detail = f"{location}: {first_error['msg']}" if location else first_error["msg"]
        return f"Invalid arguments for {self.tool_ref}: {detail[:300]}"


def _render_geo_points(payload: dict[str, object]) -> ToolInvocationResult:
    from .geo import render_geo_points

    return render_geo_points(payload)


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
    TOOL_REF_SIMILARITY_SEARCH: BuiltinToolSpec(
        tool_ref=TOOL_REF_SIMILARITY_SEARCH,
        args_schema=SimilaritySearchToolArgs,
        backend=BuiltinToolBackend.TOOL_INVOKER,
        default_description=(
            "Find the passages most similar to an anchor text, restricted to an "
            "explicit set of target documents (document-to-document comparison, "
            "not corpus-wide search)."
        ),
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
        backend=BuiltinToolBackend.LOCAL,
        local_handler=_render_geo_points,
        output_part=GeoPart,
        default_description=(
            "Display locations on an interactive map in the chat. Call this tool "
            "with points=[{latitude: number, longitude: number, name?: string, "
            "properties?: {description?: string, ...}}, ...] and an optional title. "
            "By default, display only point markers. Set connect_as_zone=true only if the user asks for a zone; "
            "supply at least three distinct points in boundary order. The tool closes the polygon and keeps the markers. "
            "For GPS points in Fred documents, use knowledge.search when available to retrieve coordinates; do not guess them. "
            "Names appear beside points where space permits; scalar properties have a short hover preview and full details on click. "
            "Use numeric coordinates in degrees and keep the "
            "user-facing reply concise. The tool returns the renderable map, so do not "
            "copy its GeoJSON into the reply."
        ),
    ),
    TOOL_REF_CHART_RENDER: BuiltinToolSpec(
        tool_ref=TOOL_REF_CHART_RENDER,
        args_schema=ChartRenderToolArgs,
        backend=BuiltinToolBackend.LOCAL,
        local_handler=render_chart,
        output_part=ChartPart,
        default_description=(
            "Render actual returned tabular rows in chat. Views: bar or bar_horizontal "
            "for comparisons and histogram bins; bar_stacked for parts of totals; "
            "line, area, or area_stacked for ordered trends; pie or donut for a few "
            "shares; scatter for numeric correlation; radar for category profiles; "
            "radial_bar for ranked values; funnel for ordered stages; treemap for "
            "relative sizes; composed for bars plus lines; table for details. "
            "Pass chart_type, title, rows, x_key, and y_keys for plotted views; "
            "for long-form grouped bars, pass group_key with one y_key to give each "
            "group its own color within the chart (at most eight groups); "
            "table needs only chart_type, title, and rows. Scatter needs one numeric "
            "x and y; pie, donut, radial_bar, funnel, and treemap need one nonnegative "
            "y; composed needs at least two y keys (first bar, rest lines). At most 50 rows and "
            "50,000 serialized characters are accepted. Keep the answer concise and "
            "disclose any query truncation."
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
