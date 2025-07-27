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

from app.common.structures import AgentSettings
from app.core.monitoring.node_monitoring import monitor_node
from app.model_factory import get_model
import requests
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from app.core.agents.flow import AgentFlow
from app.common.document_source import DocumentSource
from app.core.chatbot.chat_schema import ChatSource

logger = logging.getLogger(__name__)

class RagsExpert(AgentFlow):
    """
    An expert agent that searches and analyzes documents to answer user questions.
    This agent uses a vector search service using the knowledge-flow search REST API to find relevant documents and generates
    responses based on the document content. This design is simple and straightworward.
    """
    name: str = "RagsExpert"
    role: str = "Rags Expert"
    nickname: str = "Rico"
    description: str = "Extracts and analyzes document content to answer questions."
    icon: str = "rags_agent"
    categories: List[str] = []
    tag: str = "Innovation"

    def __init__(self, agent_settings: AgentSettings):
        self.agent_settings = agent_settings
        self.knowledge_flow_url = agent_settings.settings.get("knowledge_flow_url", "http://localhost:8111/knowledge-flow/v1")
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
        """
        Generate the base prompt for the rags expert agent.

        Returns:
            str: The base prompt for the agent.
        """
        return (
            "You are responsible for analyzing document parts and answering questions based on them.\n"
            "Whenever you reference a document part, provide citations.\n"
            f"The current date is {self.current_date}.\n"
        )
    
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    async def _run_reasoning_step(self, state: MessagesState):
        question: str = state["messages"][-1].content
        try:
            response = requests.post(
                f"{self.knowledge_flow_url}/vector/search",
                json={"query": question, "top_k": 3},
                timeout=10
            )
            response.raise_for_status()
            documents_data = response.json()

            if not documents_data:
                msg = f"I couldn't find any relevant documents for '{question}'. Try rephrasing?"
                return {"messages": [await self.model.ainvoke([HumanMessage(content=msg)])]}

            documents = []
            sources: List[ChatSource] = []
            for doc in documents_data:
                if "uid" in doc and "document_uid" not in doc:
                    doc["document_uid"] = doc["uid"]
                doc_source = DocumentSource(**doc)
                documents.append(doc_source)
                sources.append(ChatSource(
                    document_uid=getattr(doc_source, "document_uid", getattr(doc_source, "uid", "unknown")),
                    file_name=doc_source.file_name,
                    title=doc_source.title,
                    author=doc_source.author,
                    content=doc_source.content,
                    created=doc_source.created,
                    modified=doc_source.modified or "",
                    type=doc_source.type,
                    score=doc_source.score,
                ))

            documents_str = "\n".join(
                f"Source file: {d.file_name}\nPage: {d.page}\nContent: {d.content}\n"
                for d in documents
            )

            prompt = (
                "You are an assistant that answers questions based on retrieved documents.\n"
                "Use the following documents to support your response with citations.\n\n"
                f"{documents_str}\n"
                f"Question:\n{question}\n"
            )

            response = await self.model.ainvoke([HumanMessage(content=prompt)])
            response.response_metadata.update({"sources": [s.model_dump() for s in sources]})
            return {"messages": [response]}

        except Exception as e:
            logger.exception("Error in RagsExpert reasoning.")
            fallback = await self.model.ainvoke([HumanMessage(content="An error occurred. Please try again later.")])
            return {"messages": [fallback]}

