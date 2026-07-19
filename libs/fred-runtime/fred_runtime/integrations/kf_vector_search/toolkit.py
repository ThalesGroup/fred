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
In-process Knowledge Flow vector-search toolkit for v2 ReAct agents (MIGR-03.03).

Why this module exists:
- restores the kea behaviour where the "search_documents" tool, selected from the
  Tools tab as an MCP server, returns typed `VectorSearchHit` sources so the chat
  UI renders the Sources panel (and clickable `[N]` citations)
- in kea that tool was an *inprocess* provider (`transport: inprocess`,
  `provider: kf_vector_search`) — NOT a real remote MCP endpoint. A remote MCP tool
  returns plain text with no typed artifact, so the panel cannot render. This
  toolkit re-establishes the inprocess path on swift.

Key design:
- exposes one LangChain tool (`search_documents_using_vectorization`) that returns a
  `ToolInvocationResult` directly (NOT a `content_and_artifact` tuple). The shared
  runtime-provider resolver invokes provider tools with a plain args dict, which
  collapses a `content_and_artifact` tuple to its content string and drops the
  artifact — so the sources must ride on a returned `ToolInvocationResult`, which the
  resolver extracts (see `react_tool_resolution._resolve_runtime_provider_tool`).
  `blocks` carry the hit JSON for the LLM; `sources` carry the typed hits the chat
  Sources panel renders. This mirrors the built-in `knowledge.search` tool ref.
- retrieval scoping (libraries, document uids, search policy, session/corpus scope,
  team) is read from the bound runtime context at call time — identical to the
  built-in `knowledge.search` tool ref used by Rico, so both paths behave the same

How to use it:
- built by `build_inprocess_toolkit` when a catalog server declares
  `provider: "kf_vector_search"`; the MCP runtime calls `.tools()` to collect the
  LangChain tools
"""

from __future__ import annotations

import logging
from typing import Sequence

from fred_core.common import OwnerFilter
from fred_core.common.team_id import is_personal_team_id
from fred_core.store.vector_search import VectorSearchHit, select_citable_sources
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from langchain_core.tools import BaseTool, tool

from fred_runtime.common.kf_base_client import KnowledgeFlowAgentContext
from fred_runtime.common.kf_vectorsearch_client import VectorSearchClient
from fred_runtime.runtime_support.request_context_helpers import (
    get_document_library_tags_ids,
    get_document_uids,
    get_rag_knowledge_scope,
    get_search_policy,
    get_vector_search_scopes,
)

logger = logging.getLogger(__name__)

KF_VECTOR_SEARCH_PROVIDER = "kf_vector_search"

# Only the fields the LLM needs for citation and reasoning are exposed. URL and
# operational fields are excluded so the model cannot reproduce broken or internal
# paths in its reply — this mirrors `_invoke_knowledge_search` (the tool-ref path).
_LLM_FIELDS = {"uid", "title", "content", "file_name", "page", "section", "score"}


def _llm_slice(hit: VectorSearchHit) -> dict[str, object]:
    return {k: v for k, v in hit.model_dump(mode="json").items() if k in _LLM_FIELDS}


class KfVectorSearchToolkit:
    """
    Inprocess toolkit that binds a Knowledge Flow vector search to one agent turn.

    Why this class exists:
    - the MCP runtime resolves inprocess providers to a toolkit object and calls its
      `tools()` method to collect LangChain tools
    - the toolkit is built per request from the agent shim (which carries the bound
      runtime context and agent settings), so each tool call reads the current
      session scope

    How to use it:
    - `KfVectorSearchToolkit(agent=shim).tools()`
    """

    def __init__(self, *, agent: KnowledgeFlowAgentContext) -> None:
        self._agent = agent
        self._client = VectorSearchClient(agent=agent)

    def tools(self) -> list[BaseTool]:
        agent = self._agent
        client = self._client

        @tool("search_documents_using_vectorization")
        async def search_documents_using_vectorization(
            question: str,
            top_k: int = 8,
        ) -> ToolInvocationResult:
            """Search the selected document libraries using semantic similarity (RAG).

            Call this tool BEFORE answering any factual, technical, or domain-specific
            question — the corpus may hold more specific or recent information than you
            already know. Skip it only for purely conversational exchanges (greetings,
            thanks, clarifying what was just said).

            Returns ranked hits with title and content. Cite each grounded claim with
            the bracketed rank of the hit it relies on: [1], [2]. Only use information
            actually present in the returned hits; never invent facts beyond them.
            """
            runtime_context = agent.runtime_context

            if get_rag_knowledge_scope(runtime_context) == "general_only":
                return ToolInvocationResult(
                    tool_ref=KF_VECTOR_SEARCH_PROVIDER,
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

            top_k = top_k if isinstance(top_k, int) and top_k > 0 else 8
            team_id = agent.agent_settings.team_id
            scoped_team = bool(team_id) and not is_personal_team_id(team_id)
            include_session_scope, include_corpus_scope = get_vector_search_scopes(
                runtime_context
            )

            hits: Sequence[VectorSearchHit] = await client.search(
                question=question,
                top_k=top_k,
                document_library_tags_ids=get_document_library_tags_ids(
                    runtime_context
                ),
                document_uids=get_document_uids(runtime_context),
                search_policy=get_search_policy(runtime_context),
                owner_filter=OwnerFilter.TEAM if scoped_team else OwnerFilter.PERSONAL,
                team_id=team_id if scoped_team else None,
                session_id=runtime_context.session_id,
                include_session_scope=include_session_scope,
                include_corpus_scope=include_corpus_scope,
            )

            logger.info(
                "[KFVS][TOOL] question=%r top_k=%d hits=%d",
                question[:80],
                top_k,
                len(hits),
            )
            # Return a ToolInvocationResult directly: the runtime-provider resolver
            # invokes this tool with a plain args dict, so a content_and_artifact
            # tuple would lose the artifact (and its sources). `blocks` feed the LLM
            # the full hit set; `sources` (the Sources panel) is narrowed separately —
            # never a dataset pointer chunk, never a hit that's noise relative to the
            # best match in this call (RAG-DATASET-DISCOVERY-RFC.md §7). Mirrors
            # `_invoke_knowledge_search`'s use of the same shared default ratio.
            return ToolInvocationResult(
                tool_ref=KF_VECTOR_SEARCH_PROVIDER,
                blocks=(
                    ToolContentBlock(
                        kind=ToolContentKind.JSON,
                        data={
                            "query": question,
                            "hits": [_llm_slice(h) for h in hits],
                        },
                    ),
                ),
                sources=select_citable_sources(hits),
            )

        return [search_documents_using_vectorization]
