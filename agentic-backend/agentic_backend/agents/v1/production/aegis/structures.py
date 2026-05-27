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

from typing import Annotated, List

from fred_core.store import VectorSearchHit
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class AegisGraphState(TypedDict, total=False):
    """
    Purpose:
        Define the partial LangGraph state updates exchanged by Aegis nodes.

    How to use:
        Nodes should read from this state but return only the keys they update,
        especially `messages`, so the runtime can persist LangGraph events.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    documents: List[VectorSearchHit]
    sources: List[VectorSearchHit]
    iteration: int
    draft_answer: AIMessage | None
    self_check: "SelfCheckOutput | None"
    followup_queries: List[str]
    decision: str | None
    irrelevant_documents: List[VectorSearchHit]


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
