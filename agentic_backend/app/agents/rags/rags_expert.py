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
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.graph import END, MessagesState, StateGraph
from langchain.prompts import ChatPromptTemplate

from app.core.agents.flow import AgentFlow
from app.common.document_source import DocumentSource
from app.core.chatbot.chat_schema import ChatSource
from app.agents.rags.structures import (
    GradeDocumentsOutput,
    GradeAnswerOutput,
    RephraseQueryOutput
)


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

    async def _grade_documents(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Grades the relevance of retrieved documents against the user question,
        filtering out irrelevant documents based on a binary 'yes' or 'no' score
        from a grader model.

        Args:
            state (Dict[str, Any]): Current graph state

        Returns:
            Dict[str, Any]: Updated state
        """
        question: str = state["question"]
        documents: Optional[List[DocumentSource]] = state["documents"]

        system = """
        You are a grader assessing relevance of a retrieved document to a user question.
        It does not need to be a stringent test. The goal is to filter out erroneous retrievals.
        If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant.
        Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question.
        """

        filtered_docs: List[DocumentSource] = []

        for document in documents or []:
            grade_prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages(
                [
                    ("system", system),
                    (
                        "human",
                        "Retrieved document: \n\n {document} \n\n User question: {question}",
                    ),
                ]
            )
            chain = grade_prompt | self.model.with_structured_output(
                GradeDocumentsOutput
            )

            score = await chain.ainvoke(
                {"question": question, "document": document.content}
            )

            if score.binary_score == "yes":
                filtered_docs.append(document)

        logger.info(f"✅ {len(filtered_docs)} documents are relevant.")

        return {"messages": [], "documents": filtered_docs}

    async def _generate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate an answer to the question using retrieved documents.

        Args:
            state (Dict[str, Any]): Current graph state

        Returns:
            Dict[str, Any]: Updated state
        """
        question: str = state["question"]
        documents: List[DocumentSource] = state["documents"]

        documents_str: str = "\n".join(
            f"Source file: {document.file_name}\nPage: {document.page}\nContent: {document.content}\n"
            for document in documents
        )

        prompt: ChatPromptTemplate = ChatPromptTemplate.from_template(
            """
            You are an assistant that answers questions based on retrieved documents. 
            Use the following documents to support your response with citations :
             
            {context}
            
            Question: {question}
            """
        )
        chain = prompt | self.model

        response = await chain.ainvoke({"context": documents_str, "question": question})

        sources: List[ChatSource] = []
        for document in documents:
            sources.append(
                ChatSource(
                    document_uid=getattr(
                        document,
                        "document_uid",
                        getattr(document, "uid", "unknown"),
                    ),
                    file_name=document.file_name,
                    title=document.title,
                    author=document.author,
                    content=document.content,
                    created=document.created,
                    modified=document.modified or "",
                    type=document.type,
                    score=document.score,
                )
            )

        response.response_metadata.update(
            {"sources": [s.model_dump() for s in sources]}
        )

        return {"messages": [], "generation": response}
    
    async def _rephrase_query(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rephrase the input question to improve retrieval effectiveness.

        Args:
            state (Dict[str, Any]): Current graph state

        Returns:
            Dict[str, Any]: Updated state
        """
        question: str = state["question"]
        retry_count: int = state.get("retry_count", 0) + 1

        system = """
        You are a question re-writer that converts an input question to a better version that is optimized for vectorstore retrieval. 
        Look at the input and try to reason about the underlying semantic intent / meaning.
        """
        rewrite_prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                (
                    "human",
                    "Here is the initial question: \n\n {question} \n\n Formulate an improved question. Use the same language as the question to answer.",
                ),
            ]
        )
        chain = rewrite_prompt | self.model.with_structured_output(RephraseQueryOutput)

        response = await chain.ainvoke({"question": question})
        better_question = response.rephrase_query

        logger.info(f"The question has been rephrased : {question}")
        logger.info(f"The new question : {better_question}")
        logger.info(f"Retry count : {retry_count}")

        return {
            "messages": [],
            "question": better_question,
            "retry_count": retry_count,
        }


    async def _finalize_success(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reset state after successful completion.

        Args:
            state (Dict[str, Any]): Current graph state

        Returns:
            Dict[str, Any]: Updated state
        """
        return {
            "messages": [state["generation"]],
            "question": "",
            "documents": [],
            "top_k": self.TOP_K,
            "sources": [],
            "retry_count": 0,
            "generation": None,
        }

    async def _finalize_failure(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reset state after failure with an error message.

        Args:
            state (Dict[str, Any]): Current graph state

        Returns:
            Dict[str, Any]: Updated state
        """
        return {
            "messages": [
                SystemMessage(
                    content="The agent was unable to generate a satisfactory response to your question."
                )
            ],
            "question": "",
            "documents": [],
            "top_k": self.TOP_K,
            "sources": [],
            "retry_count": 0,
            "generation": None,
        }

    # Edges
    async def _decide_to_generate(self, state: Dict[str, Any]) -> str:
        """
        Decide next step based on document availability and retry count

        Args:
            state (Dict[str, Any]): Current graph state

        Returns:
            - "rephrase_query" if no documents were retrieved.
            - "abort" if retry_count exceeds 2.
            - "generate" otherwise.
        """
        documents: Optional[List[DocumentSource]] = state["documents"]
        retry_count: int = state.get("retry_count", 0)

        if not documents:
            return "rephrase_query"
        elif retry_count > 2:
            return "abort"
        else:
            return "generate"

    async def _grade_generation(self, state: Dict[str, Any]) -> str:
        """
        Assess whether the generated answer satisfactorily addresses the user's question.

        Uses a grading prompt to classify the answer as either 'yes' (resolves the question)
        or 'no' (does not resolve). Based on the grade and retry count, returns a decision
        string for the graph flow.

        Args:
            state (Dict[str, Any]): Current graph state

        Returns:
            - "useful" if the answer resolves the question,
            - "not useful" if it doesn't but retry limit not reached,
            - "abort" if it doesn't and retry limit (>= 2) is reached.
        """
        question: str = state["question"]
        generation: AIMessage = state["generation"]
        retry_count: int = state.get("retry_count", 0)

        system = """
        You are a grader assessing whether an answer addresses / resolves a question.
        Give a binary score 'yes' or 'no'. 'yes' means that the answer resolves the question.
        """
        answer_prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages(
            [
                ("system", system),
                (
                    "human",
                    "User question: \n\n {question} \n\n LLM generation: {generation}",
                ),
            ]
        )

        answer_grader = answer_prompt | self.model.with_structured_output(
            GradeAnswerOutput
        )
        grader_response = await answer_grader.ainvoke(
            {"question": question, "generation": generation.content}
        )
        grade = grader_response.binary_score
        if grade == "yes":
            return "useful"
        elif retry_count >= 2:
            return "abort"
        else:
            return "not useful"
