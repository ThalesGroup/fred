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

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentSource(BaseModel):
    content: str
    file_path: str
    file_name: str
    page: Optional[int]
    uid: str
    modified: Optional[str] = None

    # Required for frontend
    title: str
    author: str
    created: str
    type: str

    # Metrics & evaluation
    score: float = Field(..., description="Similarity score returned by the vector store (e.g., cosine distance).")
    rank: Optional[int] = Field(None, description="Rank of the document among the retrieved results.")
    embedding_model: Optional[str] = Field(None, description="Identifier of the embedding model used.")
    vector_index: Optional[str] = Field(None, description="Name of the vector index used for retrieval.")
    token_count: Optional[int] = Field(None, description="Approximate token count of the content.")

    # Optional usage tracking or provenance
    retrieved_at: Optional[str] = Field(None, description="Timestamp when the document was retrieved.")
    retrieval_session_id: Optional[str] = Field(None, description="Session or trace ID for auditability.")


class SearchResponseDocument(BaseModel):
    content: str
    metadata: dict


class SearchPolicyName(str, Enum):
    hybrid = "hybrid"  # default
    strict = "strict"  # high precision
    semantic = "semantic"  # simple, not precise useful to debug


class SearchRequest(BaseModel):
    """Search arguments; document authority comes from the authenticated header."""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(description="Natural-language search query. This operation returns chunks, not a generated answer.")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return.")
    search_policy: Optional[SearchPolicyName] = Field(
        default=None,
        description="Optional search policy preset. If omitted, defaults to 'hybrid'.",
    )
    rerank: bool = Field(
        default=False,
        description="Retrieve up to min(top_k * 5, 100) candidates and rerank visible, in-scope hits with the organization's selected reranker or the local cross-encoder, keeping top_k. Retrieval scores are unchanged.",
    )
    min_score: float | None = Field(default=None, description="Keep hits whose original retrieval score (or 0.0 when absent) is at least this value, after optional reranking and its top_k limit.")


class VisualEvidenceArtifactResponse(BaseModel):
    document_uid: str
    artifact_path: str
    file_name: str
    content_type: str
    artifact_url: str
