# Copyright Thales 2026
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

from __future__ import annotations

from pydantic import BaseModel, Field


class MindmapInput(BaseModel):
    message: str = Field(..., min_length=1)


class DocumentPage(BaseModel):
    document_uid: str
    path: str
    page_index: int
    start_line: int | None = None
    end_line: int | None = None
    total_lines: int | None = None
    has_more: bool = False
    next_offset: int | None = None
    truncated: bool = False
    content: str = ""


class DocumentSegmentSummary(BaseModel):
    document_uid: str
    page_index: int
    line_range: str
    title: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    notable_terms: list[str] = Field(default_factory=list)


class MindmapState(BaseModel):
    latest_user_text: str

    detected_language: str | None = None
    output_language: str = "auto"
    selected_document_uids: list[str] = Field(default_factory=list)
    needs_document_selection: bool = False
    use_search_fallback: bool = False

    retrieval_queries: list[str] = Field(default_factory=list)
    coverage_warnings: list[str] = Field(default_factory=list)
    document_segment_summaries: list[dict[str, object]] = Field(default_factory=list)

    # Stored as VectorSearchHit.model_dump() dicts so the state stays JSON-friendly.
    transcript_hits: list[dict[str, object]] = Field(default_factory=list)
    source_refs: list[dict[str, object]] = Field(default_factory=list)

    document_digest: str | None = None
    mindmap_payload: dict[str, object] | None = None
    final_text: str | None = None
    done_reason: str | None = None

    # Set by the runtime when a node raises and on_error routing fires.
    node_error: str = ""
