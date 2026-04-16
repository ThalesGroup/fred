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

from typing import List, Optional

from pydantic import BaseModel, Field


class VectorSearchHit(BaseModel):
    # Content (chunk)
    content: str
    page: Optional[int] = None
    section: Optional[str] = None
    viewer_fragment: Optional[str] = None  # e.g., "p=12&sel=340-520"

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
    type: Optional[str] = Field(None, description="File type/category")

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
