# Copyright Thales 2025
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


import json
import logging
import re
import time
from typing import Any, List, Tuple
from uuid import uuid4

import requests
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.graph_search_client import GraphSearchClient
from agentic_backend.common.llm_errors import (
    error_log_context,
    guardrail_fallback_message,
    normalize_llm_exception,
)
from agentic_backend.common.rags_utils import (
    format_rag_sources_for_prompt,
)
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    get_rag_knowledge_scope,
    is_corpus_only_mode,
)
from agentic_backend.core.runtime_source import expose_runtime_source

_EXPLICIT_ID_RE = re.compile(
    r"\b(?:CR-\d+|SYS-REQ-\d+|SAF-REQ-\d+|HAZ-\d+|TC-\d+|SW-COMP-\d+)\b"
)


def extract_explicit_ids(text: str) -> list[str]:
    if not isinstance(text, str) or not text:
        return []
    return _EXPLICIT_ID_RE.findall(text)


def extract_ids_from_hits(hits: List[Any]) -> list[str]:
    """
    Deterministically extract requirement/hazard/test identifiers from retrieved hits.
    This provides an "allowed IDs" set to reduce hallucinations and force explicit ID usage.
    """
    found: list[str] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        for key in ("fact", "text", "content", "name", "title"):
            v = h.get(key)
            if isinstance(v, str):
                found.extend(extract_explicit_ids(v))
    # preserve order while de-duping
    out: list[str] = []
    seen: set[str] = set()
    for x in found:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def mk_thought(*, label: str, node: str, task: str, content: str) -> AIMessage:
    """
    Emit an assistant-side 'thought' trace.
    The UI shows it under the Thoughts accordion (channel=thought).
    """
    return AIMessage(
        content="",  # keep content empty; StreamTranscoder will emit only the thought trace
        response_metadata={
            "thought": content,
            "extras": {"task": task, "node": node, "label": label},
        },
    )


def mk_tool_call(*, call_id: str, name: str, args: dict) -> AIMessage:
    """
    Emit a tool_call trace line without actually invoking an LLM tool.
    This makes internal actions (like retrieval) visible in the UI.
    """
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": call_id,
                "name": name,
                "args": args,
            }
        ],
        response_metadata={"extras": {"task": "retrieval", "node": name}},
    )


def mk_tool_result(
    *,
    call_id: str,
    content: str,
    ok: bool | None = None,
    latency_ms: int | None = None,
    extras: dict | None = None,
) -> ToolMessage:
    md: dict[str, Any] = {}
    if extras:
        md["extras"] = extras
    if latency_ms is not None:
        md["latency_ms"] = latency_ms
    if ok is not None:
        md["ok"] = ok
    return ToolMessage(content=content, tool_call_id=call_id, response_metadata=md)


def rag_hits_to_citations(hits: List[Any]) -> List[dict]:
    """
    Version ultra-simple :
    - hits = list de dicts
    - citation = { "index": n, "fact": "...", "valid_at": "..." }
    """
    citations = []
    for idx, h in enumerate(hits, start=1):
        fact = h.get("fact")
        if not fact:
            continue

        citations.append({"index": idx, "fact": fact, "valid_at": h.get("valid_at")})

    return citations


def attach_rag_sources_to_llm_response(answer, hits: List[Any]):
    """
    Ajoute :
    - sources : faits bruts et dates
    - citations : liste indexée pour l’UI
    """

    answer.additional_kwargs = getattr(answer, "additional_kwargs", {}) or {}

    # The frontend Sources panel expects VectorSearchHit-like objects with `uid` and `rank`.
    # We map GraphRAG hits (dicts) into a minimal compatible shape.
    sources = []
    for idx, h in enumerate(hits, start=1):
        if not isinstance(h, dict):
            continue
        uid = h.get("uuid") or h.get("uid") or h.get("id") or f"graph-hit-{idx}"
        fact = h.get("fact") or h.get("text") or h.get("content") or ""
        score = h.get("score")
        title = h.get("title") or h.get("name") or "GraphRAG"
        valid_at = h.get("valid_at")

        sources.append(
            {
                "uid": str(uid),
                "rank": idx,
                # fred_core.VectorSearchHit requires a numeric score; Graphiti hits may omit it.
                "score": float(score) if isinstance(score, (int, float)) else 0.0,
                "title": str(title) if title else None,
                "content": str(fact) if fact else "",
                "file_name": None,
                "mime_type": None,
                "created": valid_at,
                "retrieved_at": None,
                "type": "graph_rag",
            }
        )

    answer.additional_kwargs["sources"] = sources
    answer.additional_kwargs["citations"] = rag_hits_to_citations(hits)

    return answer


logger = logging.getLogger(__name__)

# -----------------------------
# Spec-only tuning (class-level)
# -----------------------------
# Dev note:
# - These are *UI schema fields* (spec). Live values come from AgentSettings.tuning
#   and are applied by AgentFlow at runtime.
RAG_TUNING = AgentTuning(
    # High-level role as seen by UI / other tools
    role="Document Retrieval Agent",
    description=(
        "A general-purpose RAG agent that answers questions using retrieved document snippets. "
        "It grounds all claims in the provided sources, cites them inline, and explicitly acknowledges "
        "when the evidence is weak, conflicting, or missing."
    ),
    tags=["document"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="RAG System Prompt",
            description=(
                "Defines the assistant’s behavior for evidence-based answers, source usage, and citation style."
            ),
            required=True,
            default=(
                "You are a GraphRAG traceability analyst for engineering artifacts (requirements, hazards, tests).\n"
                "You answer questions by extracting *explicit identifiers* and *explicit relationships* from the provided sources.\n"
                "\n"
                "Non-negotiable rules:\n"
                "- Treat sources as ground truth. Do NOT invent IDs, requirements, hazards, tests, components, or links.\n"
                "- Only assert a relationship (A -> B) if a source explicitly states or clearly implies it.\n"
                "- Every row you output must include evidence markers like [1], [2] that reference the provided sources.\n"
                "- If information is missing, write 'NOT_EVIDENCED' (do not guess).\n"
                "\n"
                "Identifier patterns (examples): CR-123, SYS-REQ-12, SAF-REQ-03, HAZ-07, TC-04, SW-COMP-01.\n"
                "\n"
                "Output format:\n"
                "- Prefer structured outputs (Markdown tables / impact matrix), not free-form prose.\n"
                "- Keep explanations short and evidence-driven.\n"
                "- Always respond in {response_language}.\n"
                "\n"
                "Today is {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.response_language",
            type="text",
            title="Response Language",
            description="Language to use for all answers (e.g., 'English', 'Spanish').",
            required=False,
            default="English",
            ui=UIHints(group="Prompts"),
        ),
        FieldSpec(
            key="prompts.with_sources",
            type="prompt",
            title="Answer With Sources",
            description=(
                "User-facing instructions when sources are available. "
                "Include placeholders for {question} and {sources}."
            ),
            required=True,
            default=(
                "You are given:\n"
                "- Question\n"
                "- Sources (each line is labeled [n], e.g. [1])\n"
                "- Allowed IDs: {allowed_ids}\n"
                "\n"
                "Task:\n"
                "1) Extract all explicit entity IDs present in the sources (e.g. requirements, risks, functions, components, tests, changes, issues, etc.).\n"
                "2) Extract explicit relationships between IDs only when they are clearly evidenced in the sources (e.g. 'X implemented by Y', 'A mitigates B', 'C verified by D').\n"
                "3) Build relationship paths using only evidenced links (multi-hop paths are allowed).\n"
                "\n"
                "Hard constraints:\n"
                "- Do NOT output any ID that is not present in the sources. If Allowed IDs is NONE_FOUND, say NOT_EVIDENCED.\n"
                "- For every relationship/path, cite the supporting source line(s) [S#].\n"
                "- When evidence is missing, write NOT_EVIDENCED.\n"
                "\n"
                "Return exactly these sections (Markdown):\n"
                "## Impact Matrix\n"
                "| ID | Type | Summary | Linked IDs (direct) | Evidence |\n"
                "|---|---|---|---|---|\n"
                "| ... |\n"
                "\n"
                "## Trace Paths\n"
                "| Path | Hop Evidence | Notes |\n"
                "|---|---|---|\n"
                "| Entity-A → Entity-B → Entity-C | [S1],[S4],... | ... |\n"
                "\n"
                "## Gaps / Not Evidenced\n"
                "- Bullet list of entities, relationships, or paths that could not be evidenced from the provided sources.\n"
                "\n"
                "Question:\n"
                "{question}\n"
                "\n"
                "Sources:\n"
                "{sources}\n"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.no_sources",
            type="prompt",
            title="Answer Without Sources",
            description=(
                "Instructions when no usable sources remain after filtering. Include a {question} placeholder."
            ),
            required=True,
            default=(
                "No relevant sources were retrieved.\n"
                "Do NOT guess or invent requirement/hazard/test IDs.\n"
                "Reply with 'NOT_EVIDENCED' and suggest how to ingest/index the missing documents.\n"
                "\n"
                "Question:\n"
                "{question}"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.no_results",
            type="prompt",
            title="No Results Message",
            description=(
                "Message sent to the model when the search returns no documents at all. Include a {question} placeholder if needed."
            ),
            required=True,
            default=(
                "I couldn't find any relevant documents. Try rephrasing or expanding your query?"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.keyword_expansion",
            type="prompt",
            title="Keyword Expansion Prompt",
            description=(
                "Prompt used to extract keywords before retrieval. Include the {question} placeholder."
            ),
            required=True,
            default=(
                "Here is a user question:\n"
                "{question}\n\n"
                "List at most 6 important keywords or keyphrases for a focused document search.\n"
                "- Reply only with a comma-separated list.\n"
                "- No sentences, no numbering."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="rag.top_k",
            type="integer",
            title="Top-K Documents",
            description="How many chunks to retrieve per question.",
            required=False,
            default=8,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="rag.keyword_expansion",
            type="boolean",
            title="Enable Keyword Expansion",
            description=(
                "If enabled, the model first extracts keywords and augments the query before vector search to widen recall."
            ),
            required=False,
            default=True,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="rag.history_max_messages",
            type="integer",
            title="Conversation Memory",
            description="How many recent messages to include before the current question.",
            required=False,
            default=10,
            ui=UIHints(group="Prompts"),
        ),
        FieldSpec(
            key="rag.min_score",
            type="number",
            title="Minimum Score (filter)",
            description=(
                "Filter out retrieved chunks with a score below this value. "
                "Use 0 to disable score-based filtering."
            ),
            required=False,
            default=0.6,
            ui=UIHints(group="Retrieval"),
        ),
    ],
)


@expose_runtime_source("agent.Richard")
class Richard(AgentFlow):
    """
    Retrieval-Augmented Generation expert.

    Key principles (aligned with AgentFlow):
    - No hidden prompt composition. This node explicitly chooses which tuned fields to use.
    - Graph is built in async_init() and compiled lazily via AgentFlow.get_compiled_graph().
    - Chat context text is *opt-in* (governed by a tuning boolean).
    """

    tuning = RAG_TUNING  # UI schema only; live values are in AgentSettings.tuning

    async def async_init(self, runtime_context: RuntimeContext):
        """Bind the model, create the vector search client, and build the graph."""
        self.model = get_default_chat_model()
        self.search_client = GraphSearchClient(
            base_url="http://localhost:9666/graph-rag"
        )
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    # -----------------------------
    # Small helpers (local policy)
    # -----------------------------
    def _render_tuned_prompt(self, key: str, **tokens) -> str:
        prompt = self.get_tuned_text(key)
        if not prompt:
            logger.warning("Richard: no tuned prompt found for %s", key)
            raise RuntimeError(f"Richard: no tuned prompt found for '{key}'.")
        return self.render(prompt, **tokens)

    def _system_prompt(self) -> str:
        """
        Resolve the RAG system prompt from tuning; optionally append chat context text if enabled.
        """
        response_language = (
            self.get_tuned_text("prompts.response_language") or "English"
        )
        sys_text = self._render_tuned_prompt(
            "prompts.system", response_language=response_language
        )  # token-safe rendering (e.g. {today})

        logger.debug(
            "Richard: resolved system prompt (len=%d, language=%s)",
            len(sys_text),
            response_language or "default",
        )
        return sys_text

    async def _expand_with_keywords(self, question: str) -> Tuple[str, List[str]]:
        """
        Ask the model for a short list of keywords and append them to the query for retrieval.
        """
        prompt = self._render_tuned_prompt(
            "prompts.keyword_expansion", question=question
        )
        try:
            resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            raw = resp.content if isinstance(resp.content, str) else ""
            keywords = [kw.strip() for kw in raw.split(",") if kw.strip()]
            if not keywords:
                return question, []
            augmented = f"{question} {' '.join(keywords)}"
            return augmented, keywords
        except Exception as e:
            logger.warning(
                "Richard: keyword expansion failed, using raw question. err=%s", e
            )
            return question, []

    # -----------------------------
    # Node: reasoner
    # -----------------------------
    async def _run_reasoning_step(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError(
                "Model is not initialized. Did you forget to call async_init()?"
            )

        # Last user question (MessagesState ensures 'messages' is AnyMessage[])
        last = state["messages"][-1]
        if not isinstance(last.content, str):
            raise TypeError(
                f"Expected string content for the last message, got: {type(last.content).__name__}"
            )
        question = last.content

        trace_msgs: list[Any] = []
        try:
            runtime_context = self.get_runtime_context()
            rag_scope = get_rag_knowledge_scope(runtime_context)

            if rag_scope == "general_only":
                logger.info("Richard: general-only mode; bypassing retrieval.")
                sys_msg = SystemMessage(content=self._system_prompt())
                history_max = self.get_tuned_int(
                    "rag.history_max_messages", default=6, min_value=0
                )
                history = self.get_recent_history(
                    state["messages"],
                    max_messages=history_max,
                    include_system=False,
                    include_tool=False,
                    drop_last=True,
                )
                human_msg = HumanMessage(
                    content=self._render_tuned_prompt(
                        "prompts.no_sources", question=question
                    )
                )
                messages = [sys_msg, *history, human_msg]
                messages = self.with_chat_context_text(messages)
                answer = await self.model.ainvoke(messages)
                return {"messages": [answer]}

            # 0) Optional keyword expansion to widen recall
            augmented_question = question
            keywords: List[str] = []
            if bool(self.get_tuned_any("rag.keyword_expansion")):
                augmented_question, keywords = await self._expand_with_keywords(
                    question
                )
                logger.debug(
                    "[AGENT] keyword expansion enabled; raw_question=%r keywords=%s augmented=%r",
                    question,
                    keywords,
                    augmented_question,
                )
            else:
                logger.debug(
                    "[AGENT] keyword expansion disabled; using raw_question=%r",
                    question,
                )

            # 1) Build retrieval scope from runtime context
            top_k = self.get_tuned_int("rag.top_k", default=5)
            min_score = float(self.get_tuned_any("rag.min_score") or 0.0)
            logger.debug(
                "[AGENT] reasoning start question=%r top_k=%s rag_scope=%s",
                question,
                top_k,
                rag_scope,
            )

            # 2) Graph search (instrumented so UI can show it)
            call_id = f"tc_graph_search_{uuid4().hex[:8]}"
            trace_msgs.append(
                mk_tool_call(
                    call_id=call_id,
                    name="graph.search",
                    args={
                        "base_url": self.search_client.base_url,
                        "query": augmented_question,
                        "top_k": top_k,
                        "min_score": min_score,
                    },
                )
            )
            t0 = time.perf_counter()
            hits: List[Any] = self.search_client.search(
                question=augmented_question, top_k=top_k
            )
            # Best-effort score filtering if backend provides `score`.
            if min_score > 0:
                hits = [
                    h
                    for h in hits
                    if not isinstance(h, dict)
                    or not isinstance(h.get("score"), (int, float))
                    or float(h["score"]) >= min_score
                ]

            # 2b) Optional "graph-ish" expansion passes:
            # - Centered search around the top hit (if the backend returns a stable uid/uuid).
            # - Re-query by extracted IDs to pull relationship facts and improve traceability.
            center_uid = None
            if hits and isinstance(hits[0], dict):
                center_uid = hits[0].get("uuid") or hits[0].get("uid")
            extra: list[Any] = []
            if isinstance(center_uid, str) and center_uid.strip():
                try:
                    extra.extend(
                        self.search_client.search(
                            question=augmented_question,
                            top_k=max(1, min(5, top_k)),
                            center_uid=center_uid,
                        )
                    )
                except Exception:
                    logger.debug(
                        "[AGENT] centered graph search failed for center_uid=%s",
                        center_uid,
                    )

            allowed_ids = extract_ids_from_hits(hits)
            if allowed_ids:
                per_id_k = max(1, min(3, top_k))
                for rid in allowed_ids[:25]:  # safety cap
                    try:
                        extra.extend(
                            self.search_client.search(question=rid, top_k=per_id_k)
                        )
                    except Exception:
                        logger.debug("[AGENT] ID expansion search failed for %s", rid)

            if extra:

                def _hit_key(h: Any) -> tuple[str, str]:
                    if not isinstance(h, dict):
                        return ("", str(h))
                    uid = str(h.get("uuid") or h.get("uid") or "")
                    fact = str(h.get("fact") or h.get("text") or h.get("content") or "")
                    return (uid, fact)

                merged: list[Any] = []
                seen: set[tuple[str, str]] = set()
                for h in [*hits, *extra]:
                    k = _hit_key(h)
                    if k in seen:
                        continue
                    seen.add(k)
                    merged.append(h)
                hits = merged
            logger.debug("[AGENT] graph search returned %d hit(s)", len(hits))
            dt_ms = int((time.perf_counter() - t0) * 1000)
            trace_summary = {
                "hits": len(hits),
                "ids_found": len(extract_ids_from_hits(hits)),
                "center_uid_used": center_uid if isinstance(center_uid, str) else None,
                "expansion_calls": len(extra),
            }
            trace_msgs.append(
                mk_tool_result(
                    call_id=call_id,
                    content=json.dumps(trace_summary, ensure_ascii=False),
                    ok=True,
                    latency_ms=dt_ms,
                    extras={"task": "retrieval", "node": "graph.search"},
                )
            )
            trace_msgs.append(
                mk_thought(
                    label="graph_search",
                    node="graph.search",
                    task="retrieval",
                    content=f"Graph search completed: hits={len(hits)} ids={len(extract_ids_from_hits(hits))} latency_ms={dt_ms}",
                )
            )

            # 3) Build messages explicitly (no magic)
            #    - One SystemMessage with policy/tone (from tuning)
            #    - One HumanMessage with task + formatted sources
            sys_msg = SystemMessage(content=self._system_prompt())
            sources_block = format_rag_sources_for_prompt(hits)
            allowed_ids = extract_ids_from_hits(hits)
            allowed_ids_csv = ", ".join(allowed_ids) if allowed_ids else "NONE_FOUND"
            logger.debug(
                "[AGENT] prepared %d source(s) for prompt (chars=%s)",
                len(hits),
                len(sources_block),
            )
            history_max = self.get_tuned_int(
                "rag.history_max_messages", default=6, min_value=0
            )
            history = self.get_recent_history(
                state["messages"],
                max_messages=history_max,
                include_system=False,
                include_tool=False,
                drop_last=True,
            )
            guardrails = ""
            if is_corpus_only_mode(runtime_context):
                guardrails = (
                    "\n\nIMPORTANT: Answer strictly using the provided documents. "
                    "If they are insufficient, state that you cannot answer without evidence from the corpus. "
                    "Do not rely on your general knowledge."
                )
            human_msg = HumanMessage(
                content=self._render_tuned_prompt(
                    "prompts.with_sources",
                    question=question,
                    sources=sources_block,
                    allowed_ids=allowed_ids_csv,
                )
                + guardrails
            )
            logger.debug(
                "[AGENT] prompt lengths sys=%d human=%d sources_chars=%d",
                len(sys_msg.content),
                len(human_msg.content),
                len(sources_block),
            )

            # 4) Ask the model
            messages = [sys_msg, *history, human_msg]
            messages = self.with_chat_context_text(messages)

            logger.debug(
                "[AGENT] invoking model with %d messages (sys_len=%d human_len=%d)",
                len(messages),
                len(sys_msg.content),
                len(human_msg.content),
            )
            answer = await self.model.ainvoke(messages)

            # 5) Attach rich sources metadata for the UI
            attach_rag_sources_to_llm_response(answer, hits)

            return {"messages": [*trace_msgs, answer]}

        except requests.exceptions.RequestException as e:
            # Retrieval service failure (GraphRAG FastAPI / MCP server not running, wrong port, wrong base path, etc.)
            resp = getattr(e, "response", None)
            status = getattr(resp, "status_code", None)
            url = (
                getattr(resp, "url", None)
                or f"{self.search_client.base_url}/graph/search"
            )

            if status == 404:
                fallback_text = (
                    "GraphRAG retrieval service endpoint was not found.\n\n"
                    f"- URL: {url}\n"
                    "- Likely cause: the `contrib/graphrag_mcp_server` is not running, "
                    "or it is running on a different port/base path.\n"
                    "- Fix: start it with `cd contrib/graphrag_mcp_server && make run` "
                    "(default: `http://localhost:8080/graph-rag`).\n"
                    "- If port 8080 is already used by another service, change `APP_PORT` "
                    "in `contrib/graphrag_mcp_server/.env` and update this agent's `base_url`."
                )
            elif status is not None:
                fallback_text = (
                    "GraphRAG retrieval service request failed.\n\n"
                    f"- HTTP {status} at: {url}\n"
                    f"- Error: {e}"
                )
            else:
                fallback_text = (
                    "Cannot reach the GraphRAG retrieval service.\n\n"
                    f"- Base URL: {self.search_client.base_url}\n"
                    f"- Error: {type(e).__name__}: {e}\n"
                    "- Fix: start `contrib/graphrag_mcp_server` (see `contrib/graphrag_mcp_server/README.md`)."
                )

            logger.error(
                "[AGENT] graph retrieval failed (status=%s url=%s err=%s)",
                status,
                url,
                e,
            )
            # Make the failure visible in the trace accordion as well.
            trace_msgs.append(
                mk_thought(
                    label="graph_search_error",
                    node="graph.search",
                    task="retrieval",
                    content=f"Graph search request failed: {type(e).__name__}: {e}",
                )
            )
            return {"messages": [*trace_msgs, AIMessage(content=fallback_text)]}

        except Exception as e:
            info = normalize_llm_exception(e)
            hits_count = (
                len(locals().get("hits", []))
                if isinstance(locals().get("hits", None), list)
                else 0
            )
            log_ctx = error_log_context(
                info,
                extra={
                    "question": question,
                    "doc_tag_ids": locals().get("doc_tag_ids"),
                    "search_policy": locals().get("search_policy"),
                    "top_k": locals().get("top_k"),
                    "hits_count": hits_count,
                },
            )
            logger.error("[AGENT] error in reasoning step.", extra={"err_ctx": log_ctx})

            fallback_text = guardrail_fallback_message(
                info,
                language=self.get_tuned_text("prompts.response_language"),
                default_message="An unexpected error occurred while searching documents. Please try again.",
            )
            return {"messages": [AIMessage(content=fallback_text)]}
