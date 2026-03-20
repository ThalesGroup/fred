from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class CitationRecord(StrictModel):
    index: int
    uid: str | None = None
    title: str | None = None
    section: str | None = None
    page: int | None = None
    file_name: str | None = None
    snippet: str | None = None


class RiskCoverage(StrictModel):
    section: str | None = None
    citations: list[int] = Field(default_factory=list)


class RiskTreatment(StrictModel):
    strategy: str | None = None
    actions: list[str] = Field(default_factory=list)
    owner: str | None = None
    target_date: str | None = None
    mapping: str | None = None


class RiskEvidence(StrictModel):
    status: Literal["Sufficient", "Partial", "NO EVIDENCE FOUND"] = "NO EVIDENCE FOUND"
    notes: str | None = None


class RiskRecommendation(StrictModel):
    strategy: str | None = None
    actions: list[str] = Field(default_factory=list)


class RiskAssessment(StrictModel):
    risk_id: str
    title: str
    source: Literal["source", "inferred"]
    order: int
    inferred_priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    coverage: RiskCoverage = Field(default_factory=RiskCoverage)
    treatment: RiskTreatment = Field(default_factory=RiskTreatment)
    evidence: RiskEvidence = Field(default_factory=RiskEvidence)
    treatment_status: Literal["Adequate", "Partial", "Missing"] = "Missing"
    blocker: bool = False
    blocker_reason: str | None = None
    recommendation: RiskRecommendation = Field(default_factory=RiskRecommendation)


class RiskIndex(StrictModel):
    generated_at: str
    source_document_uids: list[str] = Field(default_factory=list)
    source_document_library_ids: list[str] = Field(default_factory=list)
    include_session_scope: bool = True
    search_policy: str | None = None
    risks: list[RiskAssessment] = Field(default_factory=list)
    citations: list[CitationRecord] = Field(default_factory=list)

    @classmethod
    def build_timestamp(cls) -> str:
        return (
            datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def as_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
