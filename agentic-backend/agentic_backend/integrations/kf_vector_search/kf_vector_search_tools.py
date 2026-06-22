from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

from langchain_core.tools import BaseTool, tool

# from langgraph.prebuilt import ToolRuntime
from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.common.kf_document_client import KfDocumentClient
from agentic_backend.common.rags_utils import ensure_ranks, sort_hits
from agentic_backend.core.agents.v2.contracts.context import ToolInvocationResult

# from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


def build_kf_vector_search_tools(agent: KnowledgeFlowAgentContext) -> list[BaseTool]:
    """Return in-process LangChain tools for Knowledge Flow vector search."""

    @tool(
        "search_documents_using_vectorization", response_format="content_and_artifact"
    )
    async def kf_vector_search(
        # todo: set back when gitlab agents do not call this tool directly with ainvoke (and use KfDocumentClient directly instead)
        # runtime: ToolRuntime[RuntimeContext],
        question: str,
        top_k: int = 10,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        document_uids: Optional[Sequence[str]] = None,
    ) -> tuple[str, ToolInvocationResult]:
        """Search the user's document library using semantic similarity (RAG).

        Call this tool for ANY factual, technical, or domain-specific question BEFORE
        answering from training knowledge. The library may contain more specific,
        recent, or context-specific information than you already know — always search
        first, even when you believe you can answer without it.

        IMPORTANT: call this tool on EVERY new user message that is not purely conversational,
        even if you searched for the same topic in a previous turn. The document scope (selected
        libraries) may have changed between messages and a fresh search is required.

        Skip this tool only for purely conversational exchanges (greetings, thanks,
        clarifying what was just said) where no document lookup could add value.

        By default, use a top_k of 10. Increase to 15-20 when the question targets a specific topic across a large corpus.

        Returns ranked hits with title, content, and rank. For each answer:
        - Cite sources with bracketed numbers matching hit rank: [1], [2], etc.
        - Combine multiple sources when relevant: [1][3].
        - Only use information actually present in the returned hits. Do not invent or infer facts beyond what the hits contain.
        """
        client = KfDocumentClient(agent=agent)
        hits = await client.agent_search(
            # todo: retrieve agent settings and runtime_context from `runtime.context.context` (lanchain)
            agent_settings=agent.agent_settings,
            runtime_context=agent.runtime_context,
            question=question,
            top_k=top_k,
            document_library_tags_ids=document_library_tags_ids,
            document_uids=document_uids,
        )

        hits = sort_hits(hits)
        ensure_ranks(hits)

        logger.info(
            "[OBS][SEARCH][TOOL] question=%r top_k=%d llm_scoped_libs=%s llm_scoped_uids=%s -> hits_to_llm=%d titles=%s",
            question[:80],
            top_k,
            list(document_library_tags_ids) if document_library_tags_ids else None,
            list(document_uids) if document_uids else None,
            len(hits),
            [h.title for h in hits],
        )
        serialized = [h.model_dump() if hasattr(h, "model_dump") else h for h in hits]
        artifact = ToolInvocationResult(
            tool_ref="kf_vector_search",
            sources=tuple(hits),
        )
        return json.dumps(serialized, ensure_ascii=False), artifact

    @tool("list_document_tree", response_format="content_and_artifact")
    async def list_document_tree(
        working_directory: Optional[str] = None,
        max_chars: int = 6000,
    ) -> tuple[str, ToolInvocationResult]:
        """List the folders and documents in the user's document scope as a tree.

        Call this first to orient on what's available before searching or
        summarizing — it shows folder structure and, for each document, its
        name, uid, and upload date, not its content. Each document is rendered
        as "name [document_uid] (uploaded date)" — use that uid as the
        `document_uid` argument to summarize_document, or in search's
        `document_uids` filter.

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
        client = KfDocumentClient(agent=agent)
        result = await client.agent_tree(
            agent_settings=agent.agent_settings,
            runtime_context=agent.runtime_context,
            working_directory=working_directory,
            max_chars=max_chars,
        )
        logger.info(
            "[OBS][TREE][TOOL] working_directory=%r max_chars=%d truncated=%s",
            working_directory,
            max_chars,
            result.truncated,
        )
        artifact = ToolInvocationResult(tool_ref="list_document_tree")
        return result.tree, artifact

    @tool("summarize_document", response_format="content_and_artifact")
    async def summarize_document(
        document_uid: str,
        instruction: Optional[str] = None,
        max_chars: int = 5000,
    ) -> tuple[str, ToolInvocationResult]:
        """Generate a fresh, on-demand summary of one document by its uid.

        Use this when you need to understand a document's content in depth —
        e.g. to decide whether it's relevant, or to extract specific information
        — without pulling its full text into your own context. A fresh model
        reads the whole document (using map-reduce for large documents) and
        returns just the summary.

        Get `document_uid` from a prior search_documents_using_vectorization hit
        or from list_document_tree.

        Pass `instruction` to steer the summary: focus area, what to look for,
        audience, tone, desired length — e.g. "focus on financial risks and list
        every action item". Without it, you get a generic abstract.

        `max_chars` bounds the returned summary length; raise it for a more
        detailed summary, lower it for a terse one.
        """
        client = KfDocumentClient(agent=agent)
        result = await client.agent_summarize(
            document_uid=document_uid,
            instruction=instruction,
            max_chars=max_chars,
        )
        logger.info(
            "[OBS][SUMMARIZE][TOOL] document_uid=%s instruction=%r max_chars=%d shrunk_for_budget=%s",
            document_uid,
            instruction,
            max_chars,
            result.shrunk_for_budget,
        )
        artifact = ToolInvocationResult(tool_ref="summarize_document")
        return result.summary, artifact

    return [kf_vector_search, list_document_tree, summarize_document]
