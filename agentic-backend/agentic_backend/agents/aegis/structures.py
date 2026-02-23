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
from pydantic import BaseModel, Field


class AegisGraphState(TypedDict):
    """
    Graph state for Aegis (Self-RAG + Corrective-RAG).

    This state is intentionally explicit so each node can make deterministic
    routing decisions without hidden side effects.
    """

    messages: Annotated[list, add_messages]
    question: Optional[str]
    documents: Optional[List[VectorSearchHit]]
    sources: Optional[List[VectorSearchHit]]
    iteration: Optional[int]
    draft_answer: Optional[AIMessage]
    self_check: Optional["SelfCheckOutput"]
    followup_queries: Optional[List[str]]
    decision: Optional[str]
    irrelevant_documents: Optional[List[VectorSearchHit]]


class SelfCheckOutput(BaseModel):
    """
    Structured output for the Self-RAG critic.
    """

    grounded: str = Field(..., description="yes/no: answer is grounded in sources")
    answers_question: str = Field(
        ..., description="yes/no: answer addresses the question"
    )
    citation_coverage: str = Field(
        ..., description="good/weak: are citations covering factual claims"
    )
    unsupported_claims: List[str] = Field(
        default_factory=list, description="claims not supported by sources"
    )
    missing_aspects: List[str] = Field(
        default_factory=list, description="important aspects missing from answer"
    )
    suggested_queries: List[str] = Field(
        default_factory=list,
        description="follow-up queries to improve grounding (max 3)",
    )
    confidence: str = Field(..., description="low/medium/high")


class GapQueriesOutput(BaseModel):
    """
    Structured output for generating corrective follow-up queries.
    """

    queries: List[str] = Field(
        default_factory=list, description="list of search queries"
    )
