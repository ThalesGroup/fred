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


import logging
from typing import Any, Dict, List, Optional, cast

from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph

from fred_core import VectorSearchHit
from app.agents.rags.structures import (
    GradeAnswerOutput,
    GradeDocumentsOutput,
    RagGraphState,
    RephraseQueryOutput,
)
from app.common.vector_search_client import VectorSearchClient
from app.common.rags_utils import attach_sources_to_llm_response
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import get_document_libraries_ids
from app.core.model.model_factory import get_model
from app.common.structures import AgentSettings

logger = logging.getLogger(__name__)


def mk_thought(*, label: str, node: str, task: str, content: str) -> AIMessage:
    """
    Emits an assistant-side 'thought' trace.
    - UI shows this under the Thoughts accordion (channel=thought).
    - The actual text to show must be in response_metadata['thought'].
    - Any routing/context tags go under response_metadata['extras'].
    """
    return AIMessage(
        content="",  # content is unused for thought; we put text in metadata
        response_metadata={
            "thought": content,  # <-- text the UI will render in Thoughts
            "extras": {"task": task, "node": node, "label": label},
        },
    )


def mk_tool_call(*, call_id: str, name: str, args: Dict[str, Any]) -> AIMessage:
    """
    Emits an OpenAI-style tool_call on the assistant role.
    Your SessionManager will convert it to ChatMessage(role=assistant, channel=tool_call).
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
    ok: Optional[bool] = None,
    latency_ms: Optional[int] = None,
    extras: Optional[Dict[str, Any]] = None,
    sources: Optional[list] = None,
) -> ToolMessage:
    md: Dict[str, Any] = {}
    if extras:
        md["extras"] = extras
    if latency_ms is not None:
        md["latency_ms"] = latency_ms
    if ok is not None:
        md["ok"] = ok
    if sources:
        md["sources"] = [
            s.model_dump() if hasattr(s, "model_dump") else s for s in sources
        ]
    return ToolMessage(content=content, tool_call_id=call_id, response_metadata=md)


def _chunk_key(d: VectorSearchHit) -> str:
    """
    Build a stable, collision-resistant key for a chunk based on its document ID + locators.
    Works even if some fields are missing; keeps agent grading/dedup deterministic.
    """
    uid = getattr(d, "document_uid", None) or getattr(d, "uid", "") or ""
    page = getattr(d, "page", "")
    start = getattr(d, "char_start", "")
    end = getattr(d, "char_end", "")
    # Fallbacks to reduce accidental collisions for stores without char spans
    heading = getattr(d, "heading_slug", "") or getattr(d, "heading", "") or ""
    return f"{uid}|p={page}|cs={start}|ce={end}|h={heading}"


class AdvancedRagExpert(AgentFlow):
    """
    A pragmatic RAG agent that:
      1) retrieves chunks (VectorSearchHit) via knowledge-flow REST,
      2) filters them with a permissive relevance grader,
      3) generates a cited answer,
      4) retries with query rephrasing if needed.
    """

    TOP_K = 5
    MIN_DOCS = 3  # minimum number of docs we'll try to keep for generation

    name: str = "AdvancedRagExpert"
    nickname: str = "Remulus"
    role: str = "Advanced Rag Expert"
    description: str = """Answers user questions by retrieving relevant information from ingested document corpora.
        Uses a vector-based retrieval pipeline to ground responses in internal or uploaded knowledge.
    """
    icon: str = "rags_agent"
    categories: List[str] = ["Documentation"]
    tag: str = "rags"

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.search_client = VectorSearchClient()
        self.base_prompt = self._generate_prompt()
        self._graph = self._build_graph()

    # ---------- prompt ----------

    def _generate_prompt(self) -> str:
        return (
            "You analyze retrieved document parts and answer the user's question. "
            "Always include citations when you use documents. "
            f"Current date: {self.current_date}."
        )

    # ---------- graph ----------

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(RagGraphState)

        builder.add_node("retrieve", self._retrieve)
        builder.add_node("grade_documents", self._grade_documents)
        builder.add_node("generate", self._generate)
        builder.add_node("rephrase_query", self._rephrase_query)
        builder.add_node("finalize_success", self._finalize_success)
        builder.add_node("finalize_failure", self._finalize_failure)

        builder.set_entry_point("retrieve")
        builder.add_edge("retrieve", "grade_documents")
        builder.add_conditional_edges(
            "grade_documents",
            self._decide_to_generate,
            {
                "rephrase_query": "rephrase_query",
                "generate": "generate",
                "abort": "finalize_failure",
            },
        )
        builder.add_edge("rephrase_query", "retrieve")
        builder.add_conditional_edges(
            "generate",
            self._grade_generation,
            {
                "useful": "finalize_success",
                "not useful": "rephrase_query",
                "abort": "finalize_failure",
            },
        )
        builder.add_edge("finalize_success", END)
        builder.add_edge("finalize_failure", END)

        return builder

    # ---------- nodes ----------

    async def _retrieve(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if self.model is None:
            raise RuntimeError(
                "Model is not initialized. Did you forget to call async_init()?"
            )

        question: Optional[str] = state.get("question") or (
            state.get("messages") and state["messages"][-1].content
        )
        top_k: int = int(state.get("top_k", self.TOP_K) or self.TOP_K)
        retry_count: int = int(state.get("retry_count", 0) or 0)
        if retry_count > 0:
            top_k = self.TOP_K + 3 * retry_count

        try:
            tags = get_document_libraries_ids(self.get_runtime_context())
            hits: List[VectorSearchHit] = self.search_client.search(
                query=question or "", top_k=top_k, tags=tags
            )

            if not hits:
                warn = f"I couldn't find any relevant documents for “{question}”. Try rephrasing?"
                return {
                    "messages": [
                        mk_thought(
                            label="retrieve_none",
                            node="retrieve",
                            task="retrieval",
                            content=warn,
                        )
                    ],
                    "question": question,  # ✅ keep it
                    "documents": [],  # ✅ explicit
                    "sources": [],
                    "top_k": top_k,
                    "retry_count": retry_count,
                }
            call_id = "tc_retrieve_1"
            call_args = {
                "query": question,
                "top_k": top_k,
                **({"tags": tags} if tags else {}),
            }
            call_msg = mk_tool_call(call_id=call_id, name="retrieve", args=call_args)

            # 2) emit the tool result (tool/tool_result)
            summary = f"Retrieved {len(hits)} candidates."
            result_msg = mk_tool_result(
                call_id=call_id,
                content=summary,
                ok=True,
                extras={"task": "retrieval", "node": "retrieve"},
                sources=hits,  # will end up in metadata.sources for this step
            )
            # 3) add a small Thought so the accordion shows progress
            thought_msg = mk_thought(
                label="retrieve", node="retrieve", task="retrieval", content=summary
            )

            return {
                "messages": [call_msg, result_msg, thought_msg],
                "documents": hits,
                "sources": hits,
                "question": question,
                "top_k": top_k,
                "retry_count": retry_count,
            }
        except Exception as e:
            logger.exception("Failed to retrieve documents: %s", e)
            return {
                "messages": [
                    mk_thought(
                        label="retrieve_error",
                        node="retrieve",
                        task="retrieval",
                        content="Error during retrieval.",
                    )
                ]
            }

    async def _grade_documents(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question: str = state["question"]
        documents: Optional[List[VectorSearchHit]] = state.get("documents")

        # Permissive, generic grader. Keep candidates unless clearly off-topic.
        system = (
            "You are a permissive relevance grader for retrieval-augmented generation.\n"
            "- Return 'yes' unless the document is clearly off-topic for the question.\n"
            "- Consider shared keywords, entities, acronyms, or overlapping semantics as relevant.\n"
            "- Minor mismatches or partial overlaps should still be 'yes'.\n"
            'Return strictly as JSON matching the schema: {{"binary_score": "yes" | "no"}}.'
        )

        filtered_docs: List[VectorSearchHit] = []
        irrelevant_documents: List[VectorSearchHit] = (
            state.get("irrelevant_documents") or []
        )

        # Avoid false dedup across retries by using a stable chunk key.
        irrelevant_keys = {_chunk_key(doc) for doc in irrelevant_documents}
        grade_documents: List[VectorSearchHit] = [
            d for d in (documents or []) if _chunk_key(d) not in irrelevant_keys
        ]

        for document in grade_documents:
            grade_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system),
                    (
                        "human",
                        "Document to assess:\n\n{document}\n\nUser question:\n\n{question}",
                    ),
                ]
            )
            if self.model is None:
                raise ValueError("model is None")

            # Enrich the grader input with lightweight provenance.
            doc_for_grader = (
                f"Title: {document.title or document.file_name}\n"
                f"Page: {getattr(document, 'page', 'n/a')}\n"
                f"Content:\n{document.content}"
            )

            chain = grade_prompt | self.model.with_structured_output(
                GradeDocumentsOutput
            )
            llm_response = await chain.ainvoke(
                {"question": question, "document": doc_for_grader}
            )
            score = cast(GradeDocumentsOutput, llm_response)

            logger.debug(
                "Grade for %s (p=%s): %s",
                document.file_name or document.title,
                getattr(document, "page", None),
                getattr(score, "binary_score", None),
            )

            if str(score.binary_score).lower() == "yes":
                filtered_docs.append(document)
            else:
                irrelevant_documents.append(document)

        # Failsafe: ensure we keep at least MIN_DOCS (like standard RagExpert keeps 3).
        if (len(filtered_docs) == 0) and documents:
            filtered_docs = documents[: self.MIN_DOCS]
        elif 0 < len(filtered_docs) < self.MIN_DOCS and documents:
            # top-up with earliest originals not already kept
            seen = {_chunk_key(d) for d in filtered_docs}
            for d in documents:
                if len(filtered_docs) >= self.MIN_DOCS:
                    break
                if _chunk_key(d) not in seen:
                    filtered_docs.append(d)
                    seen.add(_chunk_key(d))

        kept = filtered_docs
        total = len(documents or [])
        logger.info("✅ %d documents are relevant (of %d)", len(kept), total)

        # short, human-readable thought (so Thoughts accordion is clean)
        message = mk_thought(
            label="grade_documents",
            node="grade_documents",
            task="retrieval",
            content=f"Kept {len(kept)} of {total} documents for answering.",
        )

        # attach only the KEPT docs for the UI's Sources panel on this step
        meta = getattr(message, "response_metadata", {}) or {}
        meta["sources"] = [d.model_dump() for d in kept]
        setattr(message, "response_metadata", meta)

        return {
            "messages": [message],
            "documents": kept,
            "irrelevant_documents": irrelevant_documents,
            "sources": kept,
        }

    async def _generate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question: str = state["question"]
        documents: List[VectorSearchHit] = state["documents"]

        context = "\n".join(
            f"Source file: {d.file_name or d.title}\nPage: {getattr(d, 'page', 'n/a')}\nContent: {d.content}\n"
            for d in documents
        )

        prompt = ChatPromptTemplate.from_template(
            "You are an assistant that answers questions based on retrieved documents.\n"
            "Use the documents to support your response with citations.\n\n"
            "{context}\n\nQuestion: {question}"
        )

        if self.model is None:
            raise ValueError("model is None")

        # Small progress thought (so UI can show a step)
        progress = mk_thought(
            label="generate",
            node="generate",
            task="answering",
            content="Drafting an answer from selected documents…",
        )

        response = await (prompt | self.model).ainvoke(
            {"context": context, "question": question}
        )
        response = cast(AIMessage, response)
        attach_sources_to_llm_response(
            response, documents
        )  # attaches metadata.sources to AIMessage

        return {"messages": [progress], "generation": response, "sources": documents}

    async def _rephrase_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question: str = state["question"]
        retry_count: int = int(state.get("retry_count", 0) or 0) + 1

        system = (
            "You are a question re-writer that converts an input question into a better "
            "version optimized for vector retrieval. Preserve the language of the input."
        )
        rewrite_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                (
                    "human",
                    "Initial question:\n\n{question}\n\nProduce an improved version.",
                ),
            ]
        )

        if self.model is None:
            raise ValueError("model is None")

        chain = rewrite_prompt | self.model.with_structured_output(RephraseQueryOutput)
        llm_response = await chain.ainvoke({"question": question})
        better = cast(RephraseQueryOutput, llm_response)

        logger.info(
            "Rephrased question: %r -> %r (retry=%d)",
            question,
            better.rephrase_query,
            retry_count,
        )

        message = mk_thought(
            label="rephrase_query",
            node="rephrase_query",
            task="query rewriting",
            content=better.rephrase_query,
        )

        return {
            "messages": [message],
            "question": better.rephrase_query,
            "retry_count": retry_count,
        }

    async def _finalize_success(self, state: Dict[str, Any]) -> Dict[str, Any]:
        generation: AIMessage = state["generation"]

        return {
            "messages": [generation],  # type:"ai", subtype:"final" set downstream
            "question": "",
            "documents": [],
            "top_k": self.TOP_K,
            "sources": [],
            "retry_count": 0,
            "generation": None,
            "irrelevant_documents": [],
        }

    async def _finalize_failure(self, state: Dict[str, Any]) -> Dict[str, Any]:
        explanation = "The agent was unable to generate a satisfactory response. I can rephrase the question and try again."
        msg = AIMessage(
            content=explanation,
            response_metadata={
                "extras": {"task": "answering", "node": "finalize_failure"},
                "sources": [],  # optional
            },
        )
        # IMPORTANT: downstream needs channel="final"
        # If your transport infers channel from where you put it,
        # ensure it is converted to role=assistant, channel=final.
        return {
            "messages": [msg],
            "question": "",
            "documents": [],
            "top_k": self.TOP_K,
            "sources": [],
            "retry_count": 0,
            "generation": None,
            "irrelevant_documents": [],
        }

    # ---------- edges ----------

    async def _decide_to_generate(self, state: Dict[str, Any]) -> str:
        documents: Optional[List[VectorSearchHit]] = state.get("documents")
        retry_count: int = int(state.get("retry_count", 0) or 0)

        if retry_count > 2:
            return "abort"
        elif not documents:
            return "rephrase_query"
        else:
            return "generate"

    async def _grade_generation(self, state: Dict[str, Any]) -> str:
        question: str = state["question"]
        generation: AIMessage = state["generation"]
        retry_count: int = int(state.get("retry_count", 0) or 0)

        system = (
            "You are a grader assessing whether an answer resolves a question. "
            "Return a binary 'yes' or 'no'."
        )
        answer_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                ("human", "Question:\n\n{question}\n\nAnswer:\n\n{generation}"),
            ]
        )

        if self.model is None:
            raise ValueError("model is None")

        grader = answer_prompt | self.model.with_structured_output(GradeAnswerOutput)
        llm_response = await grader.ainvoke(
            {"question": question, "generation": generation.content}
        )
        grade = cast(GradeAnswerOutput, llm_response)

        if str(grade.binary_score).lower() == "yes":
            return "useful"
        elif retry_count >= 2:
            return "abort"
        else:
            return "not useful"
