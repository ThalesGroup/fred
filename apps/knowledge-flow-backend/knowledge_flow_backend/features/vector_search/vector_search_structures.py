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
from uuid import UUID

from fred_core.store import VectorSearchHit
from pydantic import BaseModel, Field, model_validator


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
    """Corpus search in one Weaver space and its ancestors.

    The agent pod's delegation grant (person, run, agent) rides in the same body.
    """

    question: str
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return.")
    search_policy: Optional[SearchPolicyName] = Field(
        default=None,
        description="Optional search policy preset. If omitted, defaults to 'hybrid'.",
    )
    space_id: UUID = Field(description="The turn's space, from the agent pod's trusted binding.")


class RerankRequest(BaseModel):
    question: str
    documents: List[VectorSearchHit]
    top_r: int = Field(default=6, ge=1, description="Number of top-reranked chunks to consider")


class SimilaritySearchRequest(BaseModel):
    """Targeted similarity / comparison search (KF-SIMILARITY-SEARCH RFC).

    Find the passages most similar to ``anchor``, restricted to the named targets
    (documents and/or library folders), ranked best-first. Targeting is REQUIRED:
    at least one of ``document_uids`` / ``document_library_tags_ids`` must be given —
    this is a comparison primitive, not a corpus-wide question-answering search.
    """

    anchor: str = Field(..., min_length=1, description="Text/passage to find similar content for.")
    document_uids: list[str] = Field(default_factory=list, description="Target documents to search within.")
    document_library_tags_ids: list[str] = Field(default_factory=list, description="Target library folders to search within.")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of matches to return (best-first).")
    rerank: bool = Field(default=True, description="Re-rank matches best-first with the cross-encoder.")
    min_score: Optional[float] = Field(default=None, description="Drop matches below this relevance score.")

    @model_validator(mode="after")
    def _require_a_target(self) -> "SimilaritySearchRequest":
        if not self.document_uids and not self.document_library_tags_ids:
            raise ValueError("similarity search requires at least one target: document_uids or document_library_tags_ids")
        return self


class VisualEvidenceArtifactResponse(BaseModel):
    document_uid: str
    artifact_path: str
    file_name: str
    content_type: str
    artifact_url: str
