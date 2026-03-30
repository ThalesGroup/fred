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

"""State models for the DVA Risk Validator graph workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import PublishedArtifact


class DVARiskValidatorInput(BaseModel):
    """Input payload accepted by the graph agent."""

    message: str = Field(..., min_length=1)


class RiskEvidence(BaseModel):
    """Evidence and treatment snapshot captured for one risk item."""

    coverage_ref: str = "NO EVIDENCE FOUND"
    coverage_citation: int | None = None
    strategy_text: str = "NO EVIDENCE FOUND"
    strategy_citation: int | None = None
    actions: list[str] = Field(default_factory=list)
    action_citations: list[int] = Field(default_factory=list)
    owner_text: str = "NO EVIDENCE FOUND"
    owner_citation: int | None = None
    target_date_text: str = "NO EVIDENCE FOUND"
    target_date_citation: int | None = None
    mapping_text: str = "NO EVIDENCE FOUND"
    mapping_citation: int | None = None
    evidence_status: Literal["Sufficient", "Partial", "NO EVIDENCE FOUND"] = (
        "NO EVIDENCE FOUND"
    )
    notes: str = "No direct treatment evidence was detected in retrieved passages."


class RiskRecord(BaseModel):
    """Normalized risk row used by report rendering and machine index export."""

    risk_id: str
    title: str
    risk_type: Literal["Source", "Inferred"]
    source_order: int
    priority: Literal["P0", "P1", "P2", "P3"]
    treatment_status: Literal["Adequate", "Partial", "Missing"] = "Missing"
    blocker: bool = False
    blocker_reason: str = ""
    inferred_recommended_strategy: list[str] = Field(default_factory=list)
    inferred_recommended_actions: list[str] = Field(default_factory=list)
    evidence: RiskEvidence = Field(default_factory=RiskEvidence)


class CitationSource(BaseModel):
    """Single source row referenced by numeric in-report citations."""

    index: int
    title: str
    file_name: str
    section: str | None = None
    page: int | None = None
    document_uid: str | None = None


class DVARiskValidatorState(BaseModel):
    """Graph state tracked across all workflow steps."""

    latest_user_text: str
    requested_max_risks: int | None = None
    risk_section_hint: str | None = None
    risk_table_located: bool = False
    source_risks: list[RiskRecord] = Field(default_factory=list)
    all_risks: list[RiskRecord] = Field(default_factory=list)
    sources: list[CitationSource] = Field(default_factory=list)
    report_markdown: str = ""
    risk_index_json: str = "{}"
    result_artifact: PublishedArtifact | None = None
    risk_index_artifact: PublishedArtifact | None = None
    persisted_runtime_context: RuntimeContext | None = None
    final_text: str = ""
    done_reason: str | None = None
    generated_at: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat(timespec="seconds")
    )
