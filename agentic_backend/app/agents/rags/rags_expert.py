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
from typing import List, Dict, Any, Optional

from app.common.structures import AgentSettings
from app.core.model.model_factory import get_model
import requests
from requests import Response
from langchain_core.messages import HumanMessage, SystemMessage
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
    
    TOP_K = 4
    
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

        return f"""
        You are responsible for analyzing document parts and answering questions based on them.
        Whenever you reference a document part, provide citations.
        The current date is {self.current_date}.
        """

    
    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MessagesState)
        return builder

    # Nodes
    async def _retrieve(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve documents from vector search API based on the question in the state.

        Args:
            state (Dict[str, Any]): Current graph state

        Returns:
            Dict[str, Any]: Updated state
        """
        question: Optional[str] = state.get("question")
        if not question and state.get("messages"):
            question = state["messages"][-1].content

        top_k: Optional[int] = state.get("top_k", self.TOP_K)
        retry_count: Optional[int] = state.get("retry_count", 0)
        if retry_count and retry_count > 0:
            top_k = self.TOP_K + 3 * retry_count

        try:
            logger.info(f"📥 Retrieving with question: {question} | top_k: {top_k}")

            response: Response = requests.post(
                f"{self.knowledge_flow_url}/vector/search",
                json={"query": question, "top_k": top_k},
                timeout=30,
            )
            response.raise_for_status()
            documents_data = response.json()

            documents: List = []
            for document in documents_data:
                if "uid" in document and "document_uid" not in document:
                    document["document_uid"] = document["uid"]
                doc_source = DocumentSource(**document)
                documents.append(doc_source)

            logger.info(f"✅ Retrieved {len(documents)} documents.")

            return {
                "messages": [],
                "documents": documents,
                "question": question,
                "top_k": top_k,
            }
        except Exception as e:
            logger.exception(f"Failed to retrieve documents: {e}")
            return {
                "messages": [
                    SystemMessage(
                        content="An error occurred while retrieving documents. Please try again later."
                    )
                ]
            }

