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

from langgraph.graph import MessagesState
from typing import List, Optional
from pydantic.v1 import BaseModel
from langchain_core.messages import AIMessage
from fred_core import VectorSearchHit


class RagGraphState(MessagesState):
    """
    Represents the state of the RAG (Retrieval-Augmented Generation) graph during execution.

    This state object carries all relevant information between steps of the LangGraph agent flow.

    Attributes:
        question (Optional[str]): The user question to be answered.
        generation (Optional[AIMessage]): The latest AI-generated response.
        documents (Optional[List[VectorSearchHit]]): List of retrieved documents relevant to the question.
        sources (Optional[List[VectorSearchHit]]): Metadata or source references for retrieved documents.
        retry_count (Optional[int]): Number of retries attempted in the generation process.
        top_k (Optional[int]): Number of top documents to retrieve from the vector store.
        irrelevant_documents (Optional[List[VectorSearchHit]]): List of irrelevant documents.
    """

    question: Optional[str]
    generation: Optional[AIMessage]
    documents: Optional[List[VectorSearchHit]]
    sources: Optional[List[VectorSearchHit]]
    retry_count: Optional[int]
    top_k: Optional[int]
    irrelevant_documents: Optional[List[VectorSearchHit]]


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
