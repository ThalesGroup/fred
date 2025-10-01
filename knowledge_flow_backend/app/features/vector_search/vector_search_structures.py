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

from dataclasses import dataclass
from enum import Enum
from typing import Optional

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


@dataclass(frozen=True)
class SearchPolicy:
    """
    Fred — Retrieval policy focused on precision.
    Why:
      - We prefer returning nothing over surfacing off-topic chunks.
      - Two signals must agree: vector similarity AND lexical evidence.
      - Toggle phrase requirement to slash near-topic false positives.
    """

    k_final: int = 5  # max docs to return
    fetch_k: int = 60  # ANN/BM25 candidate pool
    vector_min_cosine: float = 0.52  # gate for ANN (cosine after normalization)
    bm25_min_score: float = 3.0  # gate for BM25 (tune per index)
    require_phrase_hit: bool = True  # demand exact phrase in text/title/section
    use_mmr: bool = True  # de-dup many chunks from same doc


class SearchPolicyName(str, Enum):
    hybrid = "hybrid"  # default
    strict = "strict"  # high precision
    semantic = "semantic"  # simple, not precise useful to debug


@dataclass(frozen=True)
class HybridPolicy:
    """
    Hybrid (default) — BM25 + ANN with RRF fusion and soft lexical signals.
    Robust default: resists semantic drift while keeping recall.
    """

    # ---- Output & fetch sizes ----
    k_final: int = 8
    fetch_k_ann: int = 60
    fetch_k_bm25: int = 60

    # ---- Thresholds ----
    vector_min_cosine: float = 0.45
    bm25_min_score: float = 1.5

    # ---- RRF fusion ----
    rrf_k: int = 60
    w_ann: float = 1.0
    w_bm25: float = 0.9

    # ---- Diversity / MMR ----
    use_mmr: bool = True

    # ---- Soft signal bonuses (never hard filters) ----
    enable_soft_signals: bool = True
    who_query_boost: float = 0.02
    capitalized_terms_bonus: float = 0.08
    quoted_phrases_bonus: float = 0.12
    soft_bonus_cap: float = 0.25


@dataclass(frozen=True)
class StrictPolicy:
    """
    Strict — ANN ∩ BM25 ∩ (optional) exact phrase; returns [] if weak.
    Why: high-precision mode for dense/noisy libraries.
    """

    k_final: int = 5
    fetch_k: int = 60
    vector_min_cosine: float = 0.52
    bm25_min_score: float = 3.0
    require_phrase_hit: bool = True
    use_mmr: bool = True


POLICIES = {
    SearchPolicyName.hybrid: HybridPolicy(),
    SearchPolicyName.strict: StrictPolicy(),
    SearchPolicyName.semantic: HybridPolicy(k_final=10, fetch_k_ann=50, fetch_k_bm25=0),  # not used by retriever
}


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
