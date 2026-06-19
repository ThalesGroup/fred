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


class ComparisonInput(BaseModel):
    message: str = Field(..., min_length=1)


class ComparisonState(BaseModel):
    latest_user_text: str

    # Output language (fr/en), resolved once from tuning / UI / the question.
    language: str = "en"

    # Documents to compare, resolved from the Documents picker selection.
    doc_a_uid: str | None = None
    doc_b_uid: str | None = None
    # Human-readable document names (file name), resolved from search hits.
    doc_a_name: str | None = None
    doc_b_name: str | None = None
    extra_document_uids: list[str] = Field(default_factory=list)
    needs_document_selection: bool = False

    # Salient passages of A (anchors) and their closest B counterpart.
    # Stored as plain dicts (content/uid/score/...) so state stays JSON-friendly.
    anchors: list[dict[str, object]] = Field(default_factory=list)
    pairs: list[dict[str, object]] = Field(default_factory=list)
    verdicts: list[dict[str, object]] = Field(default_factory=list)

    # VectorSearchHit.model_dump() dicts kept for the final grounded sources.
    source_refs: list[dict[str, object]] = Field(default_factory=list)

    final_text: str | None = None
    done_reason: str | None = None

    # Set by the runtime when a node raises and on_error routing fires.
    node_error: str = ""
