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
`DocumentAccessCapability` (RFC §3, §10) — the canonical real capability.

Why this module exists:
- it is the first REAL (non-tracer) capability: live document tools wired to
  platform services through typed SDK ports, plus static config-field scoping
  and one computed chat-turn narrowing control
- it doubles as the canonical in-tree reference a capability author copies

What this capability ships (and deliberately does NOT):
- `search_documents_using_vectorization`, the vector-search tool, wired live
  through `ctx.services.document_search`
- `list_document_tree` and `summarize_document`: wired live through
  `ctx.services.document_tree` / `ctx.services.document_summarize`, backed by
  Knowledge Flow's document tree and synchronous summarize endpoints. Their
  failures surface as `is_error` tool results with actionable detail
  (timeout/HTTP status), never raised exceptions.
- still deferred: the tree's trailing "Session attachments" section — a
  pod-reachable session-attachment enumeration does not exist yet
  (attachments are only a *search* scope today, `attachments_only=True`).
  The tree tool therefore lists the corpus only, and is not registered at all
  in attachments-only mode (`search_attachments_only`), where the corpus is
  out of the agent's scope by definition.

Identifier hygiene (hard rule): document uids and tag ids are internal working
identifiers for the agent's own tool calls (tree → summarize chaining, scope
filters). The agent uses them freely, but every LLM-facing docstring instructs
the model to NEVER repeat them to the end user — answers refer to documents by
display name only.

Doctrine (RFC §3.5, §3.8, §10):
- the capability reaches the platform ONLY through typed optional ports on
  `RuntimeServices`; the per-turn binding and the raw access token NEVER enter
  `CapabilityContext`
- the tool signature exposes ONLY LLM arguments (`question`, `top_k`); scope and
  identity reach the tool through the middleware closure, never the tool schema

Scoping precedence (`turn_option ⊆ capability_config ⊆ session_binding`):
- HERE the tool narrows its stored-config scope (`config.library_tag_ids` /
  `config.document_uids`) by the per-turn `document_scope` selection
  (`turn_options`), enforcing `turn_option ⊆ capability_config`;
- the runtime adapter then bounds the result by the session binding's own scope,
  enforcing `⊆ session_binding` (see `DocumentSearchAdapter`).

Duplicate-search-tool story (pilot decision, RFC §10):
- the builtin `knowledge.search` (`TOOL_REF_KNOWLEDGE_SEARCH`) and the inprocess
  `mcp:mcp-knowledge-flow-mcp-text` catalog server both still expose a
  vector-search tool that reads its scope from `RuntimeContext` only. An
  instance that BOTH wires one of those AND selects this capability would get
  two vector-search tools with different scoping. For the pilot this capability
  is the forward path (it adds per-capability config + turn scoping the builtin
  cannot express); the builtin/catalog path stays reachable for back-compat and
  its retirement is a follow-up. Do NOT wire both on one instance.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence

from fred_core.store.vector_search import (
    DEFAULT_MIN_SOURCE_SCORE_RATIO,
    select_citable_sources,
)
from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    ChatControlSpec,
    TeamScopePolicy,
)
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from fred_sdk.contracts.runtime import (
    DocumentSearchResult,
    DocumentSummaryResult,
    DocumentTreeResult,
)
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field, model_validator

from fred_runtime.capabilities.mcp import (
    RagScopeControlParams,
    SearchPolicyControlParams,
)

# The tool-result `tool_ref` this capability stamps on its artifact — distinct
# from the builtin `knowledge.search` ref so the two paths stay traceable apart.
DOCUMENT_ACCESS_TOOL_REF = "document_access"

# Vector-search policy values Knowledge Flow accepts (mirrors the MCP catalog's
# `chat_options.search_policy` enum). None on the config means "let the session
# binding decide".
_SEARCH_POLICIES = ("strict", "hybrid", "semantic")
_RAG_SCOPES = ("corpus_only", "hybrid", "general_only")

# Only the fields the LLM needs for citation, reasoning, and tool chaining are
# exposed to the model. URL and operational fields are excluded so the model
# cannot reproduce broken or internal paths. `uid` stays: it is the working
# identifier summarize_document takes — internal to the agent, never repeated
# to the end user (each tool docstring says so).
_LLM_FIELDS = frozenset(
    {"uid", "title", "content", "file_name", "page", "section", "score"}
)

_KF_SERVICE = "Knowledge Flow"

# Built-in default summary length when neither the caller (the LLM) nor the
# capability config specifies one.
DEFAULT_SUMMARIZE_MAX_CHARS = 5000
# Wire bounds of the Knowledge Flow endpoints' `max_chars` validation — clamp
# client-side so an out-of-range LLM value degrades gracefully instead of 422ing.
_SUMMARIZE_MAX_CHARS_BOUNDS = (200, 20_000)
_TREE_MAX_CHARS_BOUNDS = (500, 20_000)


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    low, high = bounds
    return max(low, min(value, high))


def resolve_summarize_max_chars(cap: int | None, requested: int | None) -> int:
    """
    Resolve the effective summary length from the configured cap and the
    caller's request.

    The per-agent cap (`summarize_max_chars` config) is both the default (when
    the caller asks for nothing) and a hard upper bound on whatever the caller
    requests; without one, the built-in default applies and the caller's
    request is honored verbatim (within wire bounds).
    """

    default = cap if cap is not None else DEFAULT_SUMMARIZE_MAX_CHARS
    effective = requested if requested is not None else default
    if cap is not None:
        effective = min(effective, cap)
    return _clamp(effective, _SUMMARIZE_MAX_CHARS_BOUNDS)


def _document_tool_failure(
    *,
    tool_ref: str,
    action: str,
    exc: Exception,
    elapsed_s: float,
    document_uid: str | None = None,
) -> tuple[str, ToolInvocationResult]:
    """Turn any document tool-call failure into a non-empty, actionable error
    message plus an ``is_error=True`` artifact.

    The v2 ReAct runtime surfaces ``ToolInvocationResult.is_error`` directly to
    the user (and suppresses LLM hallucination), so a failing tool MUST return
    such a result instead of raising — a raised exception is re-raised by the
    default ``ToolNode`` handler, which leaves the tool call pending in the
    trace and yields an empty error detail to the UI.

    Transport detail (timeout, HTTP status) arrives via the SDK-typed
    `DocumentPortCallError` attributes the adapters stamp — this module never
    imports the adapter's HTTP stack.
    """

    err_type = type(exc).__name__
    raw = str(exc).strip()
    timed_out = bool(getattr(exc, "timed_out", False))
    status_code = getattr(exc, "status_code", None)

    if timed_out:
        cause = f"the {_KF_SERVICE} service timed out after {elapsed_s:.0f}s"
    elif status_code is not None:
        cause = f"the {_KF_SERVICE} service returned HTTP {status_code}"
    else:
        cause = f"the {_KF_SERVICE} service call failed after {elapsed_s:.0f}s"

    target = f" (document_uid={document_uid})" if document_uid else ""
    detail = f": {raw}" if raw else ""
    message = f"Could not {action}{target}: {cause} [{err_type}{detail}]."
    # `blocks` carries the same diagnostic as `content` (CAPAB-02, same reason
    # as the success-path artifacts above): a Graph agent's plain-dict
    # invocation keeps only the artifact half of a `content_and_artifact`
    # return — an artifact with `is_error=True` but no message tells a Graph
    # node THAT the call failed but not WHY.
    return message, ToolInvocationResult(
        tool_ref=tool_ref,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def narrow_scope_ids(
    outer: Sequence[str] | None, inner: Sequence[str] | None
) -> list[str] | None:
    """
    Bound one scope level (`inner`) by a broader one (`outer`) — the capability
    half of the scoping precedence.

    Semantics (empty/None = "no bound at this level"):
    - `inner` empty → inherit `outer` unchanged;
    - `outer` empty → `outer` is unbounded, so keep `inner` as-is;
    - both present  → intersection, so the result is a subset of BOTH.

    Used here as `narrow_scope_ids(capability_config, turn_option)` to enforce
    `turn_option ⊆ capability_config`; the adapter applies the SAME primitive as
    `narrow_scope_ids(session_binding, params)` to complete
    `turn_option ⊆ capability_config ⊆ session_binding`.
    """

    if not inner:
        return list(outer) if outer else None
    if not outer:
        return list(inner)
    allowed = set(outer)
    return [value for value in inner if value in allowed]


class DocumentAccessConfig(BaseModel):
    """
    Agent-creation / stored config of the document-access capability (RFC §3.2),
    mirroring the legacy MCP search tool's configuration surface exactly.

    `bind_libraries` + `library_tag_ids` pin the agent to a fixed library set
    (the bound ids are IGNORED while `bind_libraries` is off, like the legacy
    tool); `document_uids` NARROWS to specific documents. An empty list means
    "no capability-side narrowing at this level" (the session binding still
    bounds it). `default_top_k` and `search_policy` set retrieval defaults;
    the `show_*` toggles pick which computed chat controls the composer shows
    (attach files, library/document scope, search policy, RAG scope). When
    the search-policy picker is shown, `search_policy` acts as the picker's
    DEFAULT and the per-turn choice (RuntimeContext) wins at search time;
    when hidden, it is enforced as-is. `min_source_score_ratio` bounds what's
    citable as a "source" in the chat UI (RAG-DATASET-DISCOVERY-RFC.md §7) —
    it never narrows what the model itself sees, only what a human is shown
    as evidence.
    """

    library_tag_ids: list[str] = []
    document_uids: list[str] = []
    default_top_k: int = 8
    search_policy: str | None = None
    bind_libraries: bool = False
    show_library_selection: bool = True
    show_document_selection: bool = True
    show_attach_files_control: bool = True
    # Restrict search to the conversation's attached files, never the corpus.
    # Enforced pod-side: the tool passes `attachments_only=True` to the
    # DocumentSearchPort, whose adapter searches the session scope only
    # (include_corpus_scope=False); the scope-picker chat control is dropped.
    # Only meaningful while attachments are enabled: the field is gated on
    # `show_attach_files_control` in the form AND inert without it (a stored
    # True must not strand an agent that can no longer receive attachments).
    search_attachments_only: bool = False
    # Per-agent default AND hard cap for summarize_document's summary length
    # (chars). None = built-in default, caller's request honored verbatim.
    summarize_max_chars: int | None = Field(default=None, ge=200, le=20_000)
    show_search_policy_control: bool = True
    show_rag_scope_control: bool = True
    default_rag_scope: str | None = None
    min_source_score_ratio: float = Field(
        default=DEFAULT_MIN_SOURCE_SCORE_RATIO,
        ge=0.0,
        le=1.0,
        description=(
            "A hit must score at least this fraction of the best hit in the "
            "same search call to be citable as a source. Does not affect what "
            "the model itself can read — only the human-facing Sources panel."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_slices(cls, data: object) -> object:
        """Slices stored before the split-toggle surface revalidate without
        behavior change: the single scope toggle maps onto the split
        library/document toggles, and a pre-`bind_libraries` library scope
        stays binding."""

        if isinstance(data, dict):
            if (
                "show_document_scope_control" in data
                and "show_library_selection" not in data
                and "show_document_selection" not in data
            ):
                shown = bool(data.get("show_document_scope_control"))
                data["show_library_selection"] = shown
                data["show_document_selection"] = shown
            if "bind_libraries" not in data and data.get("library_tag_ids"):
                data["bind_libraries"] = True
        return data


class DocumentAccessTurnOptions(BaseModel):
    """
    Per-turn narrowing carried by the `document_scope` chat control (RFC §3.5).

    Each field is `None` when the turn does not narrow that level; a present list
    is intersected with the capability config scope (never widening it).
    """

    library_tag_ids: list[str] | None = None
    document_uids: list[str] | None = None


class DocumentScopeControlParams(BaseModel):
    """
    Params for the `document_scope` composer widget (RFC §3.3).

    Mirrors the stock widget the MCP capability emits: the picker shows libraries
    and/or documents, and `bound_library_ids` (when set) pins the selection
    read-only to the capability's configured library scope.
    """

    libraries: bool = True
    documents: bool = True
    bound_library_ids: list[str] | None = None


class DocumentAccessCapability(
    AgentCapability[
        DocumentAccessConfig, DocumentAccessConfig, DocumentAccessTurnOptions
    ]
):
    """
    Document access over the platform corpus: vector search, tree listing, and
    on-demand summarization, wired through the `document_search` /
    `document_tree` / `document_summarize` ports. Config-field scoping + one
    computed chat-turn narrowing control. See the module docstring for the
    remaining deferral (session-attachment enumeration) and the
    duplicate-search-tool decision.
    """

    manifest = CapabilityManifest(
        id="document_access",
        # Pre-GA: the version stays 0.1.0 while the platform has not shipped —
        # config-surface changes land without bumps. Start bumping (it keys the
        # stored-slice schema_version and the control-plane chat-controls
        # cache) once real deployments hold stored configs.
        version="0.1.0",
        name="capability.document_access.name",
        description="capability.document_access.description",
        icon="find_in_page",
        config_fields=[
            FieldSpec(
                key="show_library_selection",
                type="boolean",
                title="Document library picker",
                description="Show a document library selector in the chat interface.",
                default=True,
                # `ui.group` drives the form's visual sections: the renderer
                # draws a thin divider whenever the group changes between two
                # consecutive visible fields.
                ui=UIHints(group="scope"),
            ),
            FieldSpec(
                key="bind_libraries",
                type="boolean",
                title="Bind to specific libraries",
                description=(
                    "Restrict this agent to a fixed set of document libraries "
                    "chosen at configuration time."
                ),
                default=False,
                ui=UIHints(group="scope"),
            ),
            FieldSpec(
                key="library_tag_ids",
                type="array",
                item_type="string",
                title="Bound document libraries",
                description=(
                    "Restrict the chat library picker to this preselected set "
                    "of document libraries."
                ),
                # Library/document tree picker, only shown while the binding
                # toggle above is on (the ids are ignored otherwise).
                ui=UIHints(
                    widget="document_libraries",
                    visible_when="bind_libraries",
                    group="scope",
                ),
            ),
            FieldSpec(
                key="show_document_selection",
                type="boolean",
                title="Document picker",
                description="Show a document selector in the chat interface.",
                default=True,
                ui=UIHints(group="scope"),
            ),
            FieldSpec(
                key="show_attach_files_control",
                type="boolean",
                title="File attachments",
                description=(
                    "Allow users to attach files (PDF, images, text) to their "
                    "messages in the chat interface."
                ),
                default=True,
                ui=UIHints(group="scope"),
            ),
            FieldSpec(
                key="search_attachments_only",
                type="boolean",
                title="Search in attachments only",
                description=(
                    "Restrict the agent's document search to the files "
                    "attached to the conversation — the corpus is never "
                    "searched."
                ),
                default=False,
                ui=UIHints(group="scope", visible_when="show_attach_files_control"),
            ),
            FieldSpec(
                key="default_top_k",
                type="integer",
                title="Default results",
                description="How many hits to retrieve when the model omits top_k.",
                default=8,
                min=1,
                ui=UIHints(group="retrieval", advanced=True),
            ),
            FieldSpec(
                key="min_source_score_ratio",
                type="number",
                title="Minimum source relevance ratio",
                description=(
                    "A hit must score at least this fraction of the best hit "
                    "in the same search to be shown as a cited source. Only "
                    "affects the human-facing Sources panel, never what the "
                    "model itself can read."
                ),
                default=DEFAULT_MIN_SOURCE_SCORE_RATIO,
                min=0.0,
                max=1.0,
                ui=UIHints(group="retrieval", advanced=True),
            ),
            FieldSpec(
                key="summarize_max_chars",
                type="integer",
                title="Summary length cap",
                description=(
                    "Default and hard maximum length (in characters) of "
                    "summaries produced by the summarize_document tool. Leave "
                    "empty to use the built-in default and honor the model's "
                    "requested length."
                ),
                min=200,
                max=20_000,
                ui=UIHints(group="retrieval", advanced=True),
            ),
            FieldSpec(
                key="show_search_policy_control",
                type="boolean",
                title="Search policy picker in chat",
                description=(
                    "Allow users to switch the search policy from the chat "
                    "interface. The configured search policy then acts as the "
                    "picker's default instead of being enforced."
                ),
                default=True,
                ui=UIHints(group="search_policy", advanced=True),
            ),
            FieldSpec(
                key="search_policy",
                type="select",
                enum=list(_SEARCH_POLICIES),
                title="Default search policy",
                description=(
                    "Search strategy used when the user has not overridden it "
                    "(enforced as-is when the picker is hidden)."
                ),
                ui=UIHints(group="search_policy", advanced=True),
            ),
            FieldSpec(
                key="show_rag_scope_control",
                type="boolean",
                title="RAG scope picker in chat",
                description=(
                    "Allow users to switch the RAG scope (corpus only / hybrid "
                    "/ general knowledge) from the chat interface."
                ),
                default=True,
                ui=UIHints(group="rag_scope", advanced=True),
            ),
            FieldSpec(
                key="default_rag_scope",
                type="select",
                enum=list(_RAG_SCOPES),
                title="Default RAG scope",
                description="Scope used when the user has not overridden it.",
                ui=UIHints(group="rag_scope", advanced=True),
            ),
        ],
        # No new chat part / side panel / router / owned table — the pilot's
        # smallest real surface (RFC §10). team_scope=default_on: baseline
        # document access should work without a per-team admin gate (RFC §8.3).
        team_scope=TeamScopePolicy.DEFAULT_ON,
    )
    ConfigModel = DocumentAccessConfig
    TurnOptionsModel = DocumentAccessTurnOptions

    def chat_controls(self, config: DocumentAccessConfig) -> list[ChatControlSpec]:
        """
        The stock composer controls (RFC §3.3), each behind its config toggle —
        the same widget set the legacy MCP search tool emits, so both paths
        offer the same chat surface. `bound_library_ids` pins the scope picker
        to the capability's configured library scope (read-only) when one is
        set. Search-policy/RAG-scope choices travel on `RuntimeContext`, which
        the document-search adapter already honors.
        """

        controls: list[ChatControlSpec] = []
        if config.show_attach_files_control:
            controls.append(ChatControlSpec(widget="attach_files"))
        # Same visibility algebra as the legacy MCP tool: binding replaces the
        # free library picker with a read-only pinned list; the document picker
        # is independent. Attachments-only pins the whole scope to the
        # conversation's attached files, so no scope picker at all.
        bound = (config.library_tag_ids or None) if config.bind_libraries else None
        show_libraries = (not config.bind_libraries) and config.show_library_selection
        show_documents = config.show_document_selection
        if config.search_attachments_only and config.show_attach_files_control:
            show_libraries = show_documents = False
            bound = None
        if show_libraries or show_documents or bound:
            controls.append(
                ChatControlSpec(
                    widget="document_scope",
                    params=DocumentScopeControlParams(
                        libraries=show_libraries or bool(bound),
                        documents=show_documents,
                        bound_library_ids=bound,
                    ),
                )
            )
        if config.show_search_policy_control:
            controls.append(
                ChatControlSpec(
                    widget="search_policy",
                    params=(
                        SearchPolicyControlParams(default=config.search_policy)  # type: ignore[arg-type]
                        if config.search_policy in _SEARCH_POLICIES
                        else SearchPolicyControlParams()
                    ),
                )
            )
        if config.show_rag_scope_control:
            controls.append(
                ChatControlSpec(
                    widget="rag_scope",
                    params=(
                        RagScopeControlParams(default=config.default_rag_scope)  # type: ignore[arg-type]
                        if config.default_rag_scope in _RAG_SCOPES
                        else RagScopeControlParams()
                    ),
                )
            )
        return controls

    def tools(
        self,
        ctx: CapabilityContext[DocumentAccessConfig, DocumentAccessTurnOptions],
    ) -> Sequence[BaseTool]:
        """
        Build the single vector-search tool, bound to the turn's typed
        context (RFC §3.2, §5). This is the ONLY runtime contribution of this
        capability — `AgentCapability.middleware()`'s default wraps this for
        `create_agent()`; no ReAct-loop-specific hook is needed.

        Return-convention note (Phase 1, NOTES-GRAPH-CAPABILITY-BRIDGE.md):
        kept as `@tool(..., response_format="content_and_artifact")` returning
        a `(content, ToolInvocationResult)` tuple. Verified empirically
        (`test_capability_tool_return_convention.py`) that this is correct for the only
        execution path this tool goes through today — `create_agent()`'s real
        ToolCall-based tool-calling loop, which builds a `ToolMessage` whose
        `.artifact` carries the `ToolInvocationResult` (and its `.sources`)
        intact. A plain-dict `.ainvoke()` call (the shape Graph's
        `invoke_runtime_tool` and the MCP runtime-provider resolver both use)
        does NOT preserve this: LangChain collapses a `content_and_artifact`
        response to the bare content string with NO tuple and NO artifact at
        all when there is no `ToolCall` to attach it to — worse than the
        tuple-collapse the original plan assumed. Switching to a bare
        `ToolInvocationResult` return (`KfVectorSearchToolkit`'s convention)
        would fix that path but breaks THIS one: without
        `response_format="content_and_artifact"`, `create_agent()`'s ToolCall
        loop stringifies the whole model into `ToolMessage.content` and never
        populates `.artifact`. Since Phase 1 does not wire this tool into any
        plain-dict invocation path (that's Phase 4), the existing convention
        is correct as-is; Phase 2+ must adapt at the tool-carrier/assembly
        seam rather than change this tool's return shape again.
        """

        config = ctx.config
        turn = ctx.turn_options
        services = ctx.services

        # Capability-config ∩ turn-option → the params handed to the port. This
        # enforces `turn_option ⊆ capability_config`; the adapter then bounds the
        # result by the session binding (`⊆ session_binding`).
        # Bound library ids only apply while the binding toggle is on — same
        # semantics as the legacy tool (the tree's value is kept but inert
        # when unbound).
        bound_library_ids = (
            (config.library_tag_ids or None) if config.bind_libraries else None
        )
        scoped_library_tag_ids = narrow_scope_ids(
            bound_library_ids, turn.library_tag_ids
        )
        scoped_document_uids = narrow_scope_ids(
            config.document_uids or None, turn.document_uids
        )
        default_top_k = config.default_top_k if config.default_top_k > 0 else 8
        # With the search-policy picker shown, the configured policy is only
        # the picker's DEFAULT: pass None so the adapter falls back to the
        # per-turn RuntimeContext value (which carries that default anyway).
        # With the picker hidden, the configured policy is enforced.
        search_policy = (
            None if config.show_search_policy_control else config.search_policy
        )
        min_source_score_ratio = config.min_source_score_ratio
        attachments_only = (
            config.search_attachments_only and config.show_attach_files_control
        )
        summarize_cap = config.summarize_max_chars

        @tool(
            "search_documents_using_vectorization",
            response_format="content_and_artifact",
        )
        async def search_documents_using_vectorization(
            question: str,
            top_k: int | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Search the selected document libraries using semantic similarity (RAG).

            Call this tool BEFORE answering any factual, technical, or
            domain-specific question — the corpus may hold more specific or more
            recent information than you already know. Skip it only for purely
            conversational exchanges (greetings, thanks, clarifying what was just
            said).

            Covers prose/text documents. If a hit describes a structured/tabular
            dataset (a "dataset pointer"), do not answer from it directly — pivot
            to the tabular/SQL tool it names instead.

            Returns ranked hits with title and content. Only use information
            actually present in the returned hits; never invent facts beyond
            them.
            """

            port = services.document_search
            if port is None:
                # No platform port injected (e.g. a bare test harness). Fail
                # LOUD in the tool result rather than silently returning nothing.
                raise RuntimeError(
                    "document_access: RuntimeServices.document_search is not "
                    "available on this execution path."
                )

            effective_top_k = top_k if isinstance(top_k, int) and top_k > 0 else None
            result: DocumentSearchResult = await port.search(
                question,
                top_k=effective_top_k or default_top_k,
                library_tag_ids=scoped_library_tag_ids,
                document_uids=scoped_document_uids,
                search_policy=search_policy,
                attachments_only=(
                    config.search_attachments_only and config.show_attach_files_control
                ),
            )
            hits = result.hits

            content = {
                "query": question,
                "hits": [
                    {
                        k: v
                        for k, v in hit.model_dump(mode="json").items()
                        if k in _LLM_FIELDS
                    }
                    for hit in hits
                ],
            }
            # `blocks` feed the LLM the full hit set (the model needs to see a
            # dataset pointer to know to pivot to the tabular tool, and every
            # hit to reason with) — `sources` (the chat Sources panel) is
            # narrowed separately: never a pointer chunk (no real content to
            # cite), and never a hit that's noise relative to the best match
            # in this call (found live citing near-zero-relevance paragraphs
            # from an unrelated document, RAG-DATASET-DISCOVERY-RFC.md §7).
            artifact = ToolInvocationResult(
                tool_ref=DOCUMENT_ACCESS_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data=content),),
                sources=select_citable_sources(
                    hits, min_score_ratio=min_source_score_ratio
                ),
            )
            return json.dumps(content), artifact

        @tool("list_document_tree", response_format="content_and_artifact")
        async def list_document_tree(
            working_directory: str | None = None,
            max_chars: int = 6000,
        ) -> tuple[str, ToolInvocationResult]:
            """List the folders and documents in the user's document scope as a tree.

            Call this first to orient on what's available before searching or
            summarizing — it shows folder structure and, for each document, its
            name, uid, and upload date, not its content.

            Documents are rendered as "name [document_uid] (uploaded date)" —
            use that uid as the `document_uid` argument to summarize_document.
            The bracketed identifiers are internal working ids for YOUR tool
            calls only: NEVER repeat them in your answer to the user — always
            refer to documents by their display name.

            `working_directory` narrows the listing to a specific folder (e.g.
            "Sales/HR"); omit it to start from the root. The tree is rendered as
            indented text, with documents appearing as leaves under every folder
            they belong to (a document can be in more than one folder).

            If the corpus is too large to show in full, the deepest branches are
            pruned and a note tells you how many items were omitted — when that
            happens, narrow `working_directory` or switch to
            search_documents_using_vectorization instead of trying to browse
            everything.
            """

            port = services.document_tree
            if port is None:
                raise RuntimeError(
                    "document_access: RuntimeServices.document_tree is not "
                    "available on this execution path."
                )

            effective_max_chars = _clamp(max_chars, _TREE_MAX_CHARS_BOUNDS)
            started = time.monotonic()
            try:
                result: DocumentTreeResult = await port.tree(
                    working_directory=working_directory,
                    library_tag_ids=scoped_library_tag_ids,
                    max_chars=effective_max_chars,
                )
            except Exception as exc:
                return _document_tool_failure(
                    tool_ref="list_document_tree",
                    action="list the document tree",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            # `blocks` carries the same tree text as `content` (CAPAB-02): a
            # Graph agent's plain-dict invocation keeps only the artifact half
            # of a `content_and_artifact` return (`_adapt_capability_tool_for_graph`,
            # `graph_runtime.py`) — an artifact with no payload silently loses
            # the tree for a Graph node, exactly the "never silently degrade"
            # failure RFC §3.9 forbids. ReAct is unaffected: `content` is
            # still what the model reads.
            artifact = ToolInvocationResult(
                tool_ref="list_document_tree",
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=result.tree),),
            )
            return result.tree, artifact

        @tool("summarize_document", response_format="content_and_artifact")
        async def summarize_document(
            document_uid: str,
            instruction: str | None = None,
            max_chars: int | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Generate a fresh, on-demand summary of one document by its uid.

            Use this when you need to understand a document's content in depth —
            e.g. to decide whether it's relevant, or to extract specific
            information — without pulling its full text into your own context. A
            fresh model reads the whole document (using map-reduce for large
            documents) and returns just the summary.

            `document_uid` MUST be the document's opaque uid, not its name or
            title. Get it from a prior search_documents_using_vectorization
            hit's 'uid' field, from list_document_tree (the value shown in
            '[...]' after each document name), or from the conversation's
            attached-files list (the bracketed value after the file name). If
            you only know a document's name, resolve its uid with one of those
            first — never pass the name here. The uid is an internal working
            identifier for YOUR tool calls only: NEVER repeat it in your answer
            to the user — always refer to the document by its display name.

            Pass `instruction` to steer the summary: focus area, what to look
            for, audience, tone, desired length — e.g. "focus on financial risks
            and list every action item". Without it, you get a generic abstract.

            `max_chars` bounds the returned summary length; raise it for a more
            detailed summary, lower it for a terse one. Leave it unset to use
            the agent's configured default. The agent may also impose a hard
            maximum, in which case a larger request is clamped down to it.
            """

            port = services.document_summarize
            if port is None:
                raise RuntimeError(
                    "document_access: RuntimeServices.document_summarize is not "
                    "available on this execution path."
                )

            effective_max_chars = resolve_summarize_max_chars(summarize_cap, max_chars)
            started = time.monotonic()
            try:
                result: DocumentSummaryResult = await port.summarize(
                    document_uid,
                    instruction=instruction,
                    max_chars=effective_max_chars,
                )
            except Exception as exc:
                message, artifact = _document_tool_failure(
                    tool_ref="summarize_document",
                    action="summarize the document",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                    document_uid=document_uid,
                )
                # 403/404 almost always means the model passed a file NAME (or
                # a stale/foreign uid) — the backend fails closed on unknown
                # resources. Tell the model how to recover instead of letting
                # it give up and echo the error.
                if getattr(exc, "status_code", None) in (403, 404):
                    message += (
                        " If you passed a file name, that is the likely cause: "
                        "document_uid must be the opaque uid. Find it in the "
                        "conversation's attached-files list (the bracketed "
                        "value after the file name), in a search hit's 'uid' "
                        "field, or via list_document_tree — then call "
                        "summarize_document again with that uid. Do not "
                        "repeat the uid to the user."
                    )
                    # CAPAB-02: `_document_tool_failure` already baked the
                    # (shorter) pre-hint message into `artifact.blocks`; the
                    # recovery hint appended above must reach `blocks` too, or
                    # a Graph agent — which keeps only the artifact half of
                    # this return — loses exactly the guidance a model needs
                    # to self-correct and retry.
                    artifact = artifact.model_copy(
                        update={
                            "blocks": (
                                ToolContentBlock(
                                    kind=ToolContentKind.TEXT, text=message
                                ),
                            )
                        }
                    )
                return message, artifact
            # `blocks` carries the same summary text as `content` — same
            # reason as `list_document_tree` above (CAPAB-02).
            artifact = ToolInvocationResult(
                tool_ref="summarize_document",
                blocks=(
                    ToolContentBlock(kind=ToolContentKind.TEXT, text=result.summary),
                ),
            )
            return result.summary, artifact

        tools: list[BaseTool] = [search_documents_using_vectorization]
        # The corpus tree is meaningless in attachments-only mode (the corpus
        # is out of the agent's scope by definition), and there is no
        # session-attachment enumeration yet (see module docstring) — so the
        # listing tool is dropped rather than registered-but-empty.
        if not attachments_only:
            tools.append(list_document_tree)
        tools.append(summarize_document)
        return tools
