from langgraph.graph import MessagesState
from app.core.chatbot.chat_schema import ChatSource
from typing import List, Optional
from app.common.document_source import DocumentSource
from pydantic.v1 import BaseModel
from langchain_core.messages import AIMessage


class RagGraphState(MessagesState):
    """
    Represents the state of the RAG (Retrieval-Augmented Generation) graph during execution.

    This state object carries all relevant information between steps of the LangGraph agent flow.

    Attributes:
        question (Optional[str]): The user question to be answered.
        generation (Optional[AIMessage]): The latest AI-generated response.
        documents (Optional[List[DocumentSource]]): List of retrieved documents relevant to the question.
        sources (Optional[List[ChatSource]]): Metadata or source references for retrieved documents.
        retry_count (Optional[int]): Number of retries attempted in the generation process.
        top_k (Optional[int]): Number of top documents to retrieve from the vector store.
        irrelevant_documents (Optional[List[DocumentSource]]): List of irrelevant documents.
    """

    question: Optional[str]
    generation: Optional[AIMessage]
    documents: Optional[List[DocumentSource]]
    sources: Optional[List[ChatSource]]
    retry_count: Optional[int]
    top_k: Optional[int]
    irrelevant_documents: Optional[List[DocumentSource]]


class GradeDocumentsOutput(BaseModel):
    """
    Output schema representing the binary relevance score of retrieved documents.

    Attributes:
        binary_score (str): Binary score ("yes"/"no") indicating whether the retrieved documents
                            are relevant to the user's question.
    """

    binary_score: str


class GradeAnswerOutput(GradeDocumentsOutput):
    """
    Output schema representing the binary assessment of the generated answer.

    Inherits:
        binary_score (str): Whether the answer provided is relevant/correct ("yes"/"no").
    """

    pass


class RephraseQueryOutput(BaseModel):
    """
    Output model representing the result of a query rephrasing operation.

    Attributes:
        rephrase_query (str): The rephrased version of the original query.
    """

    rephrase_query: str
