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

# fred_core/vector_search.py

from typing import List, Optional, Sequence

from pydantic import BaseModel, Field

# A pointer chunk (RAG-DATASET-DISCOVERY-RFC.md) describes a structured dataset
# for discovery — it carries no real content, so it must never be presented as
# a citable "source" the way a real content chunk is. `chunk_kind` distinguishes
# the two; this constant is the single place both writers (TabularProcessor)
# and readers (document_access, knowledge.search) agree on the pointer value.
DATASET_POINTER_CHUNK_KIND = "dataset_pointer"

# Default for `select_citable_sources`'s `min_score_ratio` — a hit scoring
# below half the best hit's score in the same search call is treated as noise
# relative to the strongest match, not a citable basis for an answer. Callers
# that expose this as a tunable field (e.g. DocumentAccessConfig) should use
# this as their own field default, so the two stay in sync.
DEFAULT_MIN_SOURCE_SCORE_RATIO = 0.5


class VectorSearchHit(BaseModel):
    # Content (chunk)
    content: str
    page: Optional[int] = None
    section: Optional[str] = None
    viewer_fragment: Optional[str] = None  # e.g., "p=12&sel=340-520"
    slide_id: Optional[int] = None
    has_visual_evidence: Optional[bool] = None
    slide_image_uri: Optional[str] = None
    chunk_kind: Optional[str] = Field(
        default=None,
        description=(
            "content (default, real ingested prose/data) or "
            f"'{DATASET_POINTER_CHUNK_KIND}' (a discovery pointer to a structured "
            "dataset, never citable as a source)."
        ),
    )

    # Identity
    uid: str = Field(..., description="Document UID")
    title: str
    author: Optional[str] = None
    created: Optional[str] = None
    modified: Optional[str] = None

    # File/source
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    repository: Optional[str] = None
    pull_location: Optional[str] = None
    language: Optional[str] = None
    mime_type: Optional[str] = None
    type: Optional[str] = Field(default=None, description="File type/category")

    # Tags (UI wants *names*; keep ids too for filters)
    tag_ids: List[str] = []
    tag_names: List[str] = []
    tag_full_paths: List[str] = []

    # Link fields (internal viewers / external)
    preview_url: Optional[str] = None  # e.g., "/documents/{uid}"
    preview_at_url: Optional[str] = None  # e.g., "/documents/{uid}#{viewer_fragment}"
    repo_url: Optional[str] = None  # e.g., "https://git/.../blob/ref/path#Lx-Ly"
    citation_url: Optional[str] = None  # e.g., "/documents/{uid}#chunk={chunk_id}"

    # Access (optional, forward-looking)
    license: Optional[str] = None
    confidential: Optional[bool] = None

    # Metrics
    score: float = Field(..., description="Similarity score from vector search")
    rank: Optional[int] = None
    embedding_model: Optional[str] = None
    vector_index: Optional[str] = None
    token_count: Optional[int] = None

    # Provenance
    retrieved_at: Optional[str] = None
    retrieval_session_id: Optional[str] = None


def select_citable_sources(
    hits: Sequence[VectorSearchHit],
    *,
    min_score_ratio: float = DEFAULT_MIN_SOURCE_SCORE_RATIO,
) -> tuple[VectorSearchHit, ...]:
    """
    Narrow a raw search-tool hit set down to what a chat "Sources" panel may
    cite — the full, unfiltered hit set must still reach the model's tool
    content (it needs every hit, including a dataset pointer, to decide how
    to answer); this filter is for the human-facing citation list only.

    Excludes two kinds of hit:
    - dataset pointer chunks (RAG-DATASET-DISCOVERY-RFC.md) — descriptive
      metadata about a structured dataset, never real content a human should
      be pointed to as "the source" of a factual claim.
    - hits scoring below `min_score_ratio` of the best score in this same
      hit set — noise relative to the strongest match in the batch, found
      live citing near-zero-relevance paragraphs from an unrelated document
      alongside a SQL-derived answer (RAG-DATASET-DISCOVERY-RFC.md §7).

    `min_score_ratio` is relative, not absolute, so it stays meaningful
    across embedding models with different score scales/distributions.
    """
    if not hits:
        return ()
    top_score = max(hit.score for hit in hits)
    threshold = top_score * min_score_ratio
    return tuple(
        hit
        for hit in hits
        if hit.chunk_kind != DATASET_POINTER_CHUNK_KIND and hit.score >= threshold
    )
