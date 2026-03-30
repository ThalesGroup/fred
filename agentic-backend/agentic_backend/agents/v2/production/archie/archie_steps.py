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
Business steps for the Archie v2 RAG agent.

Step sequence:
  retrieve → score_filter → answer

Key design notes:
- All prompt text is read from state (injected at workflow start from the
  definition's tunable fields). Changing a prompt in the UI settings takes
  effect on the next run without any code change.
- Vector search is done via context.invoke_tool("knowledge.search", ...).
  The runtime adapter automatically injects all session-level parameters
  (library tags, document uids, search policy, owner filter, scopes) from
  RuntimeContext — the step only needs query + top_k.
- Sources collected via invoke_tool are automatically forwarded to the UI
  by the runtime executor; no manual attachment is needed.
"""

from __future__ import annotations

import logging

from fred_core.store import VectorSearchHit
from langchain_core.messages import HumanMessage, SystemMessage

from agentic_backend.common.rags_utils import (
    ensure_ranks,
    format_sources_for_prompt,
    sort_hits,
)
from agentic_backend.core.agents.v2.graph.authoring import (
    StepResult,
    typed_node,
)
from agentic_backend.core.agents.v2.graph.runtime import GraphNodeContext

from .archie_state import ArchieState

logger = logging.getLogger(__name__)

_CORPUS_ONLY_GUARDRAIL = (
    "\n\nIMPORTANT: Answer strictly using the provided documents. "
    "If they are insufficient, state that you cannot answer without evidence from the corpus and avoid using general knowledge."
)


# ── Step: retrieve ─────────────────────────────────────────────────────────────


@typed_node(ArchieState)
async def retrieve_step(
    state: ArchieState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Call the knowledge.search built-in tool.

    The runtime adapter (adapters.py._invoke_knowledge_search) automatically enriches
    the payload with all session-level parameters:
      - document_library_tags_ids   (user-selected libraries)
      - document_uids               (session-attached files)
      - search_policy               (semantic / hybrid / strict)
      - owner_filter / team_id      (scoping)
      - session_id                  (for session-scope retrieval)
      - include_session_scope / include_corpus_scope

    This step only passes what the LLM would choose: query + top_k.
    Sources collected here are automatically forwarded to the UI by the runtime.
    """
    context.emit_status("retrieve", f"Searching documents for: {state.question[:80]}")
    logger.debug(
        "[ARCHIE][RETRIEVE] invoking knowledge.search query=%r top_k=%d",
        state.question[:120],
        state.top_k,
    )

    result = await context.invoke_tool(
        "knowledge.search",
        {"query": state.question, "top_k": state.top_k},
    )

    hits: list[VectorSearchHit] = list(result.sources)
    logger.debug("[ARCHIE][RETRIEVE] knowledge.search returned hits=%d", len(hits))
    return StepResult(state_update={"hits": hits})


# ── Step: score_filter ─────────────────────────────────────────────────────────


@typed_node(ArchieState)
async def score_filter_step(
    state: ArchieState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Apply min_score filter and deterministic ordering.

    Score filtering is applied unconditionally on the score threshold,
    which is a no-op when min_score == 0.
    """
    hits = sort_hits(list(state.hits))
    ensure_ranks(hits)

    if state.min_score > 0:
        before = len(hits)
        hits = [
            h
            for h in hits
            if isinstance(h.score, (int, float)) and h.score >= state.min_score
        ]
        logger.debug(
            "[ARCHIE][SCORE_FILTER] min_score=%.2f kept=%d/%d",
            state.min_score,
            len(hits),
            before,
        )

    return StepResult(state_update={"filtered_hits": hits})


# ── Step: answer ───────────────────────────────────────────────────────────────


@typed_node(ArchieState)
async def answer_step(
    state: ArchieState,
    context: GraphNodeContext,
) -> StepResult:
    """
    Synthesise the final answer from retrieved hits.

    Prompts are read from state (injected from the definition's tunable fields).
    Branches:
    - No hits after filter → answer from general knowledge.
    - Hits available → answer grounded in sources.
    """
    context.emit_status("answer", "Synthesising answer.")
    system_msg = SystemMessage(content=state.system_prompt)

    filtered_hits: list[VectorSearchHit] = list(state.filtered_hits)

    if not filtered_hits:
        logger.debug(
            "[ARCHIE][ANSWER] no hits after score filter — answering without sources"
        )
        answer = await context.invoke_model(
            [
                system_msg,
                HumanMessage(
                    content=state.no_sources_prompt.format(question=state.question)
                ),
            ],
            operation="answer_no_sources",
        )
        return StepResult(state_update={"final_text": str(answer.content)})

    sources_block = format_sources_for_prompt(filtered_hits, snippet_chars=500)
    logger.debug(
        "[ARCHIE][ANSWER] answering with sources hits=%d sources_chars=%d",
        len(filtered_hits),
        len(sources_block),
    )

    answer = await context.invoke_model(
        [
            system_msg,
            HumanMessage(
                content=state.with_sources_prompt.format(
                    question=state.question,
                    sources=sources_block,
                )
            ),
        ],
        operation="answer_with_sources",
    )
    return StepResult(state_update={"final_text": str(answer.content)})
