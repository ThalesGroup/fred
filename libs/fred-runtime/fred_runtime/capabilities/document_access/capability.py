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
`DocumentAccessCapability` — the #1906 pilot (CAPAB-01, RFC §3, §10).

Why this module exists:
- it is the first REAL (non-tracer) capability: one live vector-search tool
  wired to a platform service through the SDK `DocumentSearchPort`, plus
  static config-field scoping and one computed chat-turn narrowing control
  (RFC §10 "#1906 document-access" row)
- it doubles as the canonical in-tree reference a capability author copies

What this pilot ships (and deliberately does NOT):
- ships: `search_documents_using_vectorization`, the vector-search tool, wired
  live through `ctx.services.document_search`
- deferred: `list_document_tree` and `summarize_document` — their Knowledge Flow
  backend endpoints (`POST /documents/tree`, a synchronous
  `POST /documents/{uid}/summarize`) and pod-reachable session-attachment
  enumeration do not exist on Swift yet. They are intentionally NOT registered
  (a registered tool the LLM can call but that returns "not implemented" erodes
  trust) — see RFC §10.

Doctrine (RFC §3.5, §3.8, §10):
- the capability reaches the platform ONLY through a typed optional port on
  `RuntimeServices` (`services.document_search`); the per-turn binding and the
  raw access token NEVER enter `CapabilityContext`
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
from fred_sdk.contracts.runtime import DocumentSearchResult
from langchain.agents.middleware import AgentMiddleware
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

# Only the fields the LLM needs for citation and reasoning are exposed to the
# model. URL and operational fields are excluded so the model cannot reproduce
# broken or internal paths — mirrors the builtin `knowledge.search` pruning.
_LLM_FIELDS = frozenset(
    {"uid", "title", "content", "file_name", "page", "section", "score"}
)


def narrow_scope_ids(
    outer: Sequence[str] | None, inner: Sequence[str] | None
) -> list[str] | None:
    """
    Bound one scope level (`inner`) by a broader one (`outer`) — the capability
    half of the pilot's scoping precedence (CAPAB-01 #1906).

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


class _DocumentAccessMiddleware(AgentMiddleware):
    """Carries the single vector-search tool, bound to the turn's typed context."""

    def __init__(
        self,
        ctx: CapabilityContext[DocumentAccessConfig, DocumentAccessTurnOptions],
    ) -> None:
        super().__init__()
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

        tools: Sequence[BaseTool] = [search_documents_using_vectorization]
        self.tools = tools


class DocumentAccessCapability(
    AgentCapability[
        DocumentAccessConfig, DocumentAccessConfig, DocumentAccessTurnOptions
    ]
):
    """
    Vector-search over the document corpus, wired through `DocumentSearchPort`
    (CAPAB-01 #1906 pilot). ONE live tool; config-field scoping + one computed
    chat-turn narrowing control. See the module docstring for the deferred
    tools and the duplicate-search-tool decision.
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
        # is independent.
        bound = (config.library_tag_ids or None) if config.bind_libraries else None
        show_libraries = (not config.bind_libraries) and config.show_library_selection
        show_documents = config.show_document_selection
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

    def middleware(
        self,
        ctx: CapabilityContext[DocumentAccessConfig, DocumentAccessTurnOptions],
    ) -> list[AgentMiddleware]:
        return [_DocumentAccessMiddleware(ctx)]
