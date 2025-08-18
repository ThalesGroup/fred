# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from langchain.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from fred_core import VectorSearchHit
from app.agents.rags.structures import (
    GradeAnswerOutput,
    GradeDocumentsOutput,
    RagGraphState,
    RephraseQueryOutput,
)
from app.common.rags_client import VectorSearchClient
from app.common.rags_utils import attach_sources_to_llm_response
from app.core.agents.flow import AgentFlow
from app.core.agents.runtime_context import get_document_libraries_ids
from app.core.model.model_factory import get_model
from app.common.structures import AgentSettings

logger = logging.getLogger(__name__)


class RicoProExpert(AgentFlow):
    """
    A pragmatic RAG agent that:
      1) retrieves chunks (VectorSearchHit) via knowledge-flow REST,
      2) filters them with a simple relevance grader,
      3) generates a cited answer,
      4) retries with query rephrasing if needed.
    """

    TOP_K = 5

    name: str
    role: str
    nickname: str = "Rico Pro"
    description: str
    icon: str = "rags_agent"
    categories: List[str] = []
    tag: str = "Innovation"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.name = agent_settings.name
        self.nickname = agent_settings.nickname or agent_settings.name
        self.role = agent_settings.role
        self.description = agent_settings.description
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.categories = agent_settings.categories or ["General"]
        self.knowledge_flow_url = agent_settings.settings.get(
            "knowledge_flow_url", "http://localhost:8111/knowledge-flow/v1"
        )

        self.model = None
        self.base_prompt = ""
        self._graph = None

        # sane defaults
        self.categories = agent_settings.categories or ["Documentation"]
        self.tag = agent_settings.tag or "rags"

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
        self.search_client = VectorSearchClient(self.knowledge_flow_url, timeout_s=10)
        self.base_prompt = self._generate_prompt()
        self._graph = self._build_graph()

        super().__init__(
            name=self.name,
            role=self.role,
            nickname=self.nickname,
            description=self.description,
            icon=self.icon,
            graph=self._graph,
            base_prompt=self.base_prompt,
            categories=self.categories,
            tag=self.tag,
        )

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

        question: Optional[str] = state.get("question")
        if not question and state.get("messages"):
            question = state["messages"][-1].content

        top_k: int = int(state.get("top_k", self.TOP_K) or self.TOP_K)
        retry_count: int = int(state.get("retry_count", 0) or 0)
        if retry_count > 0:
            top_k = self.TOP_K + 3 * retry_count

        try:
            logger.info(f"📥 Retrieving with question={question!r} top_k={top_k}")

            tags = get_document_libraries_ids(self.get_runtime_context())
            if tags:
                logger.info(f"RicoPro filtering by libraries: {tags}")

            hits: List[VectorSearchHit] = self.search_client.search(
                query=question or "",
                top_k=top_k,
                tags=tags,
            )
            if not hits:
                warn = f"I couldn't find any relevant documents for “{question}”. Try rephrasing?"
                return {
                    "messages": [await self.model.ainvoke([HumanMessage(content=warn)])]
                }

            logger.info(f"✅ Retrieved {len(hits)} hits")

            serializable = [d.model_dump() for d in hits]
            message = SystemMessage(
                content=json.dumps(serializable),
                response_metadata={
                    "thought": True,
                    "fred": {"node": "retrieve", "task": "vector search retrieval"},
                    "sources": serializable,  # so your UI can show them in the step
                },
            )

            return {
                "messages": [message],
                "documents": hits,
                "sources": hits,  # keep for convenience
                "question": question,
                "top_k": top_k,
            }
        except Exception as e:
            logger.exception("Failed to retrieve documents: %s", e)
            return {
                "messages": [
                    SystemMessage(
                        content="An error occurred while retrieving documents. Please try again later."
                    )
                ]
            }

    async def _grade_documents(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question: str = state["question"]
        documents: Optional[List[VectorSearchHit]] = state.get("documents")

        system = (
            "You are a grader assessing the relevance of a retrieved document to a user question. "
            "It does not need to be stringent; goal is to filter out obviously wrong results. "
            "If the document contains keywords or semantic meaning related to the question, grade it 'yes'. "
            "Return a binary 'yes' or 'no'."
        )

        filtered_docs: List[VectorSearchHit] = []
        irrelevant_documents: List[VectorSearchHit] = (
            state.get("irrelevant_documents") or []
        )

        irrelevant_contents = {doc.content for doc in irrelevant_documents}
        grade_documents: List[VectorSearchHit] = [
            d for d in (documents or []) if d.content not in irrelevant_contents
        ]

        for document in grade_documents:
            grade_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system),
                    (
                        "human",
                        "Retrieved document:\n\n{document}\n\nUser question:\n\n{question}",
                    ),
                ]
            )

            if self.model is None:
                raise ValueError("model is None")

            chain = grade_prompt | self.model.with_structured_output(
                GradeDocumentsOutput
            )
            llm_response = await chain.ainvoke(
                {"question": question, "document": document.content}
            )
            score = cast(GradeDocumentsOutput, llm_response)

            if score.binary_score == "yes":
                filtered_docs.append(document)
            else:
                irrelevant_documents.append(document)

        serializable = [d.model_dump() for d in filtered_docs]
        message = SystemMessage(
            content=json.dumps(serializable),
            response_metadata={
                "thought": True,
                "fred": {
                    "node": "grade_documents",
                    "task": "filter relevant documents",
                },
                "sources": serializable,
            },
        )

        logger.info(f"✅ {len(filtered_docs)} documents are relevant")

        return {
            "messages": [message],
            "documents": filtered_docs,
            "irrelevant_documents": irrelevant_documents,
            "sources": filtered_docs,
        }

    async def _generate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question: str = state["question"]
        documents: List[VectorSearchHit] = state["documents"]

        # Simple context format with per-chunk provenance
        context = "\n".join(
            (
                f"Source file: {d.file_name or d.title}"
                f"\nPage: {d.page if d.page is not None else 'n/a'}"
                f"\nContent: {d.content}\n"
            )
            for d in documents
        )

        prompt = ChatPromptTemplate.from_template(
            "You are an assistant that answers questions based on retrieved documents.\n"
            "Use the documents to support your response with citations.\n\n"
            "{context}\n\nQuestion: {question}"
        )

        if self.model is None:
            raise ValueError("model is None")

        chain = prompt | self.model
        response = await chain.ainvoke(
            {"context": context, "question": question}
        )
        response = cast(AIMessage, response)

        # attach VectorSearchHit for UI (your helper already supports it)
        attach_sources_to_llm_response(response, documents)

        message = SystemMessage(
            content=response.content,
            response_metadata={
                "thought": True,
                "fred": {"node": "generate", "task": "compose final answer"},
                "sources": [d.model_dump() for d in documents],
            },
        )
        return {"messages": [message], "generation": response, "sources": documents}

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

        message = SystemMessage(
            content=better.rephrase_query,
            response_metadata={
                "thought": True,
                "fred": {"node": "rephrase_query", "task": "query rewriting"},
            },
        )

        return {
            "messages": [message],
            "question": better.rephrase_query,
            "retry_count": retry_count,
        }

    async def _finalize_success(self, state: Dict[str, Any]) -> Dict[str, Any]:
        generation: AIMessage = state["generation"]

        message = SystemMessage(
            content=generation.content,
            response_metadata={
                "thought": True,
                "fred": {"node": "finalize_success", "task": "deliver answer"},
            },
        )

        return {
            "messages": [message, generation],
            "question": "",
            "documents": [],
            "top_k": self.TOP_K,
            "sources": [],
            "retry_count": 0,
            "generation": None,
            "irrelevant_documents": [],
        }

    async def _finalize_failure(self, state: Dict[str, Any]) -> Dict[str, Any]:
        generation: Optional[AIMessage] = state.get("generation")
        content = generation.content if generation is not None else ""

        msg = (
            "The agent was unable to generate a satisfactory response to your question."
        )
        if generation:
            msg += " Here is the latest response:"

        message = SystemMessage(
            content=content,
            response_metadata={
                "thought": True,
                "fred": {"node": "finalize_failure", "task": "unsatisfactory answer"},
            },
        )

        messages = [message, SystemMessage(content=msg)]
        if generation is not None:
            messages.append(SystemMessage(content=generation.content, response_metadata=getattr(generation, "response_metadata", None)))

        return {
            "messages": messages,
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

        if grade.binary_score == "yes":
            return "useful"
        elif retry_count >= 2:
            return "abort"
        else:
            return "not useful"
