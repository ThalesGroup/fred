from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Optional, Sequence

import httpx
from langchain_core.tools import BaseTool, tool
from pydantic import Field

# from langgraph.prebuilt import ToolRuntime
from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.common.kf_document_client import KfDocumentClient
from agentic_backend.common.rags_utils import ensure_ranks, sort_hits
from agentic_backend.core.agents.v2.contracts.context import ToolInvocationResult

# from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

_KF_SERVICE = "Knowledge Flow"


def _kf_tool_failure(
    *,
    tool_ref: str,
    action: str,
    exc: Exception,
    elapsed_s: float,
    document_uid: Optional[str] = None,
) -> tuple[str, ToolInvocationResult]:
    """Turn any tool-call failure into a non-empty, actionable error message plus an
    ``is_error=True`` artifact.

    The v2 ReAct runtime surfaces ``ToolInvocationResult.is_error`` directly to the
    user (and suppresses LLM hallucination), so a failing tool MUST return such a
    result instead of raising — a raised exception is re-raised by the default
    ``ToolNode`` handler, which leaves the tool call pending in the trace and yields
    an empty error detail to the UI.

    The message intentionally carries the failed step, document uid, service,
    whether it timed out, how long it took, and the underlying error type so the
    detail is never blank.
    """
    err_type = type(exc).__name__
    raw = str(exc).strip()
    is_timeout = isinstance(exc, httpx.TimeoutException)
    status_code: Optional[int] = None
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code

    if is_timeout:
        cause = f"the {_KF_SERVICE} service timed out after {elapsed_s:.0f}s"
    elif status_code is not None:
        cause = f"the {_KF_SERVICE} service returned HTTP {status_code}"
    else:
        cause = f"the {_KF_SERVICE} service call failed after {elapsed_s:.0f}s"

    target = f" (document_uid={document_uid})" if document_uid else ""
    detail = f": {raw}" if raw else ""
    message = f"Could not {action}{target}: {cause} [{err_type}{detail}]."
    return message, ToolInvocationResult(tool_ref=tool_ref, is_error=True)


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
        started = time.monotonic()
        try:
            hits = await client.agent_search(
                # todo: retrieve agent settings and runtime_context from `runtime.context.context` (lanchain)
                agent_settings=agent.agent_settings,
                runtime_context=agent.runtime_context,
                question=question,
                top_k=top_k,
                document_library_tags_ids=document_library_tags_ids,
                document_uids=document_uids,
            )
        except Exception as exc:
            elapsed = time.monotonic() - started
            message, artifact = _kf_tool_failure(
                tool_ref="kf_vector_search",
                action="search the document library",
                exc=exc,
                elapsed_s=elapsed,
            )
            logger.exception(
                "[OBS][SEARCH][TOOL] FAILED question=%r after=%.1fs -> %s",
                question[:80],
                elapsed,
                message,
            )
            return message, artifact

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
        started = time.monotonic()
        try:
            result = await client.agent_tree(
                agent_settings=agent.agent_settings,
                runtime_context=agent.runtime_context,
                working_directory=working_directory,
                max_chars=max_chars,
            )
        except Exception as exc:
            elapsed = time.monotonic() - started
            message, artifact = _kf_tool_failure(
                tool_ref="list_document_tree",
                action="list the document tree",
                exc=exc,
                elapsed_s=elapsed,
            )
            logger.exception(
                "[OBS][TREE][TOOL] FAILED working_directory=%r after=%.1fs -> %s",
                working_directory,
                elapsed,
                message,
            )
            return message, artifact
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
        document_uid: Annotated[
            str,
            Field(
                description=(
                    "The opaque unique identifier (uid) of the document, NOT its "
                    "name, title, or filename. Take the exact uid string from a "
                    "prior search_documents_using_vectorization hit or from the "
                    "'[document_uid]' shown for each document by list_document_tree. "
                    "If you only know a document's name, call list_document_tree or "
                    "search first to resolve its uid — never pass the name here."
                )
            ),
        ],
        instruction: Optional[str] = None,
        max_chars: Optional[int] = None,
    ) -> tuple[str, ToolInvocationResult]:
        """Generate a fresh, on-demand summary of one document by its uid.

        Use this when you need to understand a document's content in depth —
        e.g. to decide whether it's relevant, or to extract specific information
        — without pulling its full text into your own context. A fresh model
        reads the whole document (using map-reduce for large documents) and
        returns just the summary.

        `document_uid` MUST be a document's opaque uid, not its name or title.
        Get it from a prior search_documents_using_vectorization hit or from
        list_document_tree (the value shown in '[document_uid]'). If you only
        have a name, resolve the uid with one of those tools first.

        Pass `instruction` to steer the summary: focus area, what to look for,
        audience, tone, desired length — e.g. "focus on financial risks and list
        every action item". Without it, you get a generic abstract.

        `max_chars` bounds the returned summary length; raise it for a more
        detailed summary, lower it for a terse one. Leave it unset to use the
        agent's configured default. The agent may also impose a hard maximum, in
        which case a larger request is clamped down to it.
        """
        rt = agent.runtime_context
        session_id = getattr(rt, "session_id", None)
        user_id = getattr(rt, "user_id", None)
        client = KfDocumentClient(agent=agent)
        read_timeout = getattr(client, "_summarize_read_timeout", None)
        logger.info(
            "[OBS][SUMMARIZE][TOOL] start session=%s user=%s document_uid=%s "
            "instruction=%r max_chars=%s read_timeout=%ss",
            session_id,
            user_id,
            document_uid,
            instruction,
            max_chars,
            read_timeout,
        )
        started = time.monotonic()
        try:
            result = await client.agent_summarize(
                agent_settings=agent.agent_settings,
                document_uid=document_uid,
                instruction=instruction,
                max_chars=max_chars,
            )
        except Exception as exc:
            elapsed = time.monotonic() - started
            message, artifact = _kf_tool_failure(
                tool_ref="summarize_document",
                action="summarize the document",
                exc=exc,
                elapsed_s=elapsed,
                document_uid=document_uid,
            )
            # Full stacktrace for operators; the returned message is the user detail.
            logger.exception(
                "[OBS][SUMMARIZE][TOOL] FAILED session=%s user=%s document_uid=%s "
                "step=knowledge_flow_summarize service=%s read_timeout=%ss "
                "after=%.1fs -> %s",
                session_id,
                user_id,
                document_uid,
                _KF_SERVICE,
                read_timeout,
                elapsed,
                message,
            )
            return message, artifact

        elapsed = time.monotonic() - started
        logger.info(
            "[OBS][SUMMARIZE][TOOL] ok session=%s document_uid=%s "
            "summary_chars=%d shrunk_for_budget=%s after=%.1fs",
            session_id,
            document_uid,
            len(result.summary or ""),
            result.shrunk_for_budget,
            elapsed,
        )
        artifact = ToolInvocationResult(tool_ref="summarize_document")
        return result.summary, artifact

    return [kf_vector_search, list_document_tree, summarize_document]
