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
from fred_sdk.contracts.models import FieldSpec
from fred_sdk.contracts.runtime import DocumentSearchResult
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

# The tool-result `tool_ref` this capability stamps on its artifact — distinct
# from the builtin `knowledge.search` ref so the two paths stay traceable apart.
DOCUMENT_ACCESS_TOOL_REF = "document_access"

# Vector-search policy values Knowledge Flow accepts (mirrors the MCP catalog's
# `chat_options.search_policy` enum). None on the config means "let the session
# binding decide".
_SEARCH_POLICIES = ("strict", "hybrid", "semantic")

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
    Agent-creation / stored config of the document-access capability (RFC §3.2).

    The scope fields NARROW the searchable set at agent-creation time: an empty
    list means "no capability-side narrowing at this level" (the session binding
    still bounds it). `default_top_k` and `search_policy` set retrieval
    defaults; `show_document_scope_control` toggles the computed chat control.
    """

    library_tag_ids: list[str] = []
    document_uids: list[str] = []
    default_top_k: int = 8
    search_policy: str | None = None
    show_document_scope_control: bool = True


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
        scoped_library_tag_ids = narrow_scope_ids(
            config.library_tag_ids or None, turn.library_tag_ids
        )
        scoped_document_uids = narrow_scope_ids(
            config.document_uids or None, turn.document_uids
        )
        default_top_k = config.default_top_k if config.default_top_k > 0 else 8
        search_policy = config.search_policy

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
            # `blocks` feed the LLM the hit JSON; `sources` carry the typed hits
            # the chat Sources panel renders (the runtime merges artifact
            # sources onto the tool_result/final events).
            artifact = ToolInvocationResult(
                tool_ref=DOCUMENT_ACCESS_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data=content),),
                sources=tuple(hits),
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
        version="0.1.0",
        name="capability.document_access.name",
        description="capability.document_access.description",
        icon="find_in_page",
        config_fields=[
            FieldSpec(
                key="library_tag_ids",
                type="array",
                item_type="string",
                title="Document libraries",
                description=(
                    "Restrict search to these document library tag ids. Empty = "
                    "no capability-side restriction (still bounded by the session)."
                ),
            ),
            FieldSpec(
                key="document_uids",
                type="array",
                item_type="string",
                title="Documents",
                description="Restrict search to these specific document uids.",
            ),
            FieldSpec(
                key="default_top_k",
                type="integer",
                title="Default results",
                description="How many hits to retrieve when the model omits top_k.",
                default=8,
                min=1,
            ),
            FieldSpec(
                key="search_policy",
                type="select",
                enum=list(_SEARCH_POLICIES),
                title="Search policy",
                description="Retrieval policy; empty lets the session decide.",
            ),
            FieldSpec(
                key="show_document_scope_control",
                type="boolean",
                title="Show scope picker in chat",
                description=(
                    "Show the per-turn document-scope narrowing control in the "
                    "chat composer."
                ),
                default=True,
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
        One computed `document_scope` narrowing control (RFC §3.3), shown only
        when the instance opts in. `bound_library_ids` pins the picker to the
        capability's configured library scope (read-only) when one is set.
        """

        if not config.show_document_scope_control:
            return []
        bound = config.library_tag_ids or None
        return [
            ChatControlSpec(
                widget="document_scope",
                params=DocumentScopeControlParams(
                    libraries=True,
                    documents=True,
                    bound_library_ids=bound,
                ),
            )
        ]

    def middleware(
        self,
        ctx: CapabilityContext[DocumentAccessConfig, DocumentAccessTurnOptions],
    ) -> list[AgentMiddleware]:
        return [_DocumentAccessMiddleware(ctx)]
