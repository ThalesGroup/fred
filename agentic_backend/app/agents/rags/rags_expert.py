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

from datetime import datetime
import logging
from typing import List
import requests

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import END, StateGraph

from app.core.model.model_factory import get_model
from app.core.agents.flow import AgentFlow
from app.core.chatbot.chat_schema import ChatSource
from app.common.document_source import DocumentSource
from app.common.structures import AgentSettings
from app.agents.rags.structures import RAGState

logger = logging.getLogger(__name__)

class RagsExpert(AgentFlow):
    name: str = "RagsExpert"
    role: str = "Rags Expert"
    nickname: str = "Rico"
    description: str = "Extracts and analyzes document content to answer questions."
    icon: str = "rags_agent"
    categories: List[str] = []
    tag: str = "Innovation"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.knowledge_flow_url = agent_settings.settings.get(
            "knowledge_flow_url", "http://localhost:8111/knowledge-flow/v1"
        )
        self.similarity_threshold = agent_settings.settings.get("similarity_threshold", 0) # By default if no similarity_threshold is present in the settings, we let everything pass
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.model = None
        self.base_prompt = ""
        self._graph = None
        self.categories = agent_settings.categories or ["Documentation"]
        self.tag = agent_settings.tag or "rags"

    async def async_init(self):
        self.model = get_model(self.agent_settings.model)
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

    def _generate_prompt(self) -> str:
        return (
            "You are responsible for analyzing document parts and answering questions based on them.\n"
            "Whenever you reference a document part, provide citations.\n"
            f"The current date is {self.current_date}.\n"
        )

    async def _question_rewrite(self, state: RAGState):
        question = state["messages"][-1].content
        prompt = (
            "Rewrite the following question for better document retrieval.\n"
            "Only return the rewritten question, nothing else.\n\n"
            f"{question}"
        )
        rewritten = await self.model.ainvoke([HumanMessage(content=prompt)])
        ai_msg = AIMessage(
            content=rewritten.content.strip(),
            response_metadata={
                "thought": True,
                "fred": {
                    "node": "question_rewrite",
                    "task": "Rewriting question for better retrieval"
                }
            }
        )
        state["rewritten_question"] = rewritten.content.strip()
        state["messages"].append(ai_msg)
        logger.info(f"Rewritten question: {state['rewritten_question']}")
        return state

    async def _retrieve_documents(self, state: RAGState):
        query = state["rewritten_question"] or state["messages"][-1].content
        try:
            response = requests.post(
                f"{self.knowledge_flow_url}/vector/search",
                json={"query": query, "top_k": 5},
                timeout=10,
            )
            response.raise_for_status()
            documents_data = response.json()

            all_scores = [doc.get("score", 0.0) for doc in documents_data]
            logger.info(f"similarity_threshold in agent settings: {self.similarity_threshold}")
            logger.info(f"Similarity scores of retrieved docs: {all_scores}")

            documents = []
            sources = []
            for doc in documents_data:
                if "uid" in doc and "document_uid" not in doc:
                    doc["document_uid"] = doc["uid"]
                doc_source = DocumentSource(**doc)
                logger.info(f"Document {doc_source.file_name} similarity score is {doc_source.score}")
                if doc_source.score is not None and doc_source.score >= self.similarity_threshold:
                    documents.append(doc_source)
                    sources.append(
                        ChatSource(
                            document_uid=doc_source.uid,
                            file_name=doc_source.file_name,
                            title=doc_source.title,
                            author=doc_source.author,
                            content=doc_source.content,
                            created=doc_source.created,
                            modified=doc_source.modified or "",
                            type=doc_source.type,
                            score=doc_source.score,
                        )
                    )

            if not documents:
                msg = f"No documents passed the similarity threshold (set to {self.similarity_threshold}) for: '{query}'. Try rephrasing?"
                response = await self.model.ainvoke("Print the message and emphasize the question asked via italic or bold characters and line breaks" + msg)
                state["messages"].append(response)
                logger.warning("All documents below similarity threshold.")
                state["retrieved_documents"] = []
                return state

            state["retrieved_documents"] = documents
            state["sources"] = sources
            logger.info(f"Retrieved {len(documents)} documents above threshold.")
            return state

        except Exception:
            logger.exception("Error retrieving documents.")
            ai_msg = AIMessage(
                content="An error occurred while retrieving documents. Please try again later.",
            )
            state["messages"].append(ai_msg)
            state["retrieved_documents"] = []
            return state

    async def _generate_answer(self, state: RAGState):
        if not state["retrieved_documents"]:
            logger.warning("No documents available for answer generation.")
            return state

        question = state["rewritten_question"] or state["messages"][-1].content
        documents_str = "\n".join(
            f"Source file: {d.file_name}\nPage: {d.page}\nContent: {d.content}\n"
            for d in state["retrieved_documents"]
        )
        prompt = (
            "You are an assistant that answers questions based on retrieved documents.\n"
            "Use the following documents to support your response.\n"
            "Do not display tags or any character irrelevant to the question.\n\n"
            f"{documents_str}\n"
            f"Question:\n{question}\n"
        )
        response = await self.model.ainvoke([HumanMessage(content=prompt)])
        ai_msg = AIMessage(
            content=response.content,
            response_metadata={
                "thought": True,
                "fred": {
                    "node": "answer_generator",
                    "task": "Generated raw answer from documents"
                }
            }
        )
        state["messages"].append(ai_msg)
        logger.info("Document based answer generated.")
        return state

    async def _refine_answer(self, state: RAGState):
        if not state["retrieved_documents"]:
            return state

        answer = state["messages"][-1].content
        prompt = (
            "Improve the following answer by adding explicit citations and proper formatting.\n"
            "Only return the improved answer. Do not add any explanations or introductions.\n\n"
            f"{answer}"
        )
        refined = await self.model.ainvoke([HumanMessage(content=prompt)])
        refined.response_metadata.update({
            "sources": [s.model_dump() for s in state["sources"]]
        })
        state["messages"][-1] = refined
        logger.info("Answer refined with metadata and formatting.")
        return state

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(RAGState)
        builder.add_node("question_rewrite", self._question_rewrite)
        builder.add_node("retriever", self._retrieve_documents)
        builder.add_node("answer_generator", self._generate_answer)
        builder.add_node("answer_refiner", self._refine_answer)

        builder.set_entry_point("question_rewrite")
        builder.add_edge("question_rewrite", "retriever")

        builder.add_conditional_edges(
            "retriever",
            lambda state: "answer_generator" if state.get("retrieved_documents") else END,
        )
        builder.add_edge("answer_generator", "answer_refiner")
        builder.add_edge("answer_refiner", END)
        return builder
