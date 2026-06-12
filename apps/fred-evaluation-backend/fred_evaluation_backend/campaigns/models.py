from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from fred_evaluation_backend.campaigns.base import Base, utcnow


class EvaluationCampaignRow(Base):
    __tablename__ = "evaluation_campaign"

    campaign_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_runtime_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    target_instance_id: Mapped[str | None] = mapped_column(String, nullable=True)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile: Mapped[str] = mapped_column(String(64), nullable=False)
    judge_profile_id: Mapped[str] = mapped_column(String(255), nullable=False)
    operational_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_error_cases: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    scoring_error_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationCaseRow(Base):
    __tablename__ = "evaluation_case"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_campaign.campaign_id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    structural_checks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoring_errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_trace_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    telemetry_trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationRunRow(Base):
    __tablename__ = "evaluation_run"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_campaign.campaign_id"),
        nullable=False,
        index=True,
    )
    operational_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_error_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scoring_error_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationExportDeliveryRow(Base):
    __tablename__ = "evaluation_export_delivery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_campaign.campaign_id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    exporter: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationEventRow(Base):
    __tablename__ = "evaluation_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_campaign.campaign_id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class EvaluationMetricResultRow(Base):
    __tablename__ = "evaluation_metric_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        String, ForeignKey("evaluation_case.case_id"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[str | None] = mapped_column(String(32), nullable=True)
    threshold: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
