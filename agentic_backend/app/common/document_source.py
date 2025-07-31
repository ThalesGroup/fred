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

from pydantic import BaseModel, Field
from typing import Optional


class DocumentSource(BaseModel):
    content: str
    file_path: str
    file_name: str
    page: Optional[int]
    uid: str
    modified: Optional[str] = None

    # Required by frontend
    title: str
    author: str
    created: str
    type: str

    # Metrics
    score: float = Field(..., description="Similarity score from vector search")
    rank: Optional[int] = None
    embedding_model: Optional[str] = None
    vector_index: Optional[str] = None
    token_count: Optional[int] = None

    # Provenance
    retrieved_at: Optional[str] = None
    retrieval_session_id: Optional[str] = None
