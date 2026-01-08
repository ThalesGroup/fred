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
from typing import List, Optional

from fred_core import VectorSearchHit
from pydantic import BaseModel, Field


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
    """
    Request schema for vector search.
    Generated OpenAPI will expose enum for policy, making UI dropdown trivial.
    """

    question: str
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return.")
    document_library_tags_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional list of tag names to filter documents. Only chunks in a document with at least one of these tags will be returned.",
    )
    search_policy: Optional[SearchPolicyName] = Field(
        default=None,
        description="Optional search policy preset. If omitted, defaults to 'hybrid'.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional chat session id to include session-scoped attachments (user/session filtered).",
    )
    include_session_scope: bool = Field(
        default=True,
        description="If true and session_id is provided, also search session-scoped attachment vectors (filtered by user/session).",
    )


class RerankRequest(BaseModel):
    question: str
    documents: List[VectorSearchHit]
    top_r: int = Field(default=6, ge=1, description="Number of top-reranked chunks to consider")
