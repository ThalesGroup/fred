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

from typing import Annotated, List, Optional, TypedDict

from fred_core import VectorSearchHit
from langchain_core.messages import AIMessage
from langgraph.graph import add_messages
from pydantic.v1 import BaseModel


class RagGraphState(TypedDict):
    """
    Represents the state of the RAG (Retrieval-Augmented Generation) graph.

    This TypedDict defines the structure of the state that flows through the
    RAG graph, including messages, the user's question, generated responses,
    retrieved documents, sources, retry count, irrelevant documents, and response grade.
    """

    messages: Annotated[list, add_messages]
    question: Optional[str]
    generation: Optional[AIMessage]
    documents: Optional[List[VectorSearchHit]]
    sources: Optional[List[VectorSearchHit]]
    retry_count: Optional[int]
    irrelevant_documents: Optional[List[VectorSearchHit]]
    response_grade: Optional[str]
    context: Optional[str]


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
