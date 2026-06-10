"""add evaluation tables

Adds evaluation_campaign, evaluation_case, and evaluation_metric_result tables
for EVAL-01 Phase 2.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f7a8b9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b4c5d6e7f8a9"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evaluation_campaign",
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("target_kind", sa.String(length=32), nullable=False),
        sa.Column("target_runtime_id", sa.String(), nullable=True),
        sa.Column("target_agent_id", sa.String(), nullable=True),
        sa.Column("target_instance_id", sa.String(), nullable=True),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("dataset_version", sa.String(length=100), nullable=True),
        sa.Column("profile", sa.String(length=64), nullable=False),
        sa.Column("judge_profile_id", sa.String(length=255), nullable=False),
        sa.Column("operational_state", sa.String(length=32), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("completed_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("execution_error_cases", sa.Integer(), nullable=False),
        sa.Column("scoring_error_cases", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("campaign_id"),
    )
    op.create_index(
        op.f("ix_evaluation_campaign_team_id"),
        "evaluation_campaign",
        ["team_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_campaign_task_id"),
        "evaluation_campaign",
        ["task_id"],
        unique=False,
    )

    op.create_table(
        "evaluation_case",
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column(
            "campaign_id",
            sa.String(),
            sa.ForeignKey("evaluation_campaign.campaign_id"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column("actual_output", sa.Text(), nullable=True),
        sa.Column("profile", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("execution_error", sa.Text(), nullable=True),
        sa.Column("scoring_errors_json", sa.Text(), nullable=True),
        sa.Column("raw_trace_ref", sa.String(), nullable=True),
        sa.Column("telemetry_trace_id", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("case_id"),
    )
    op.create_index(
        op.f("ix_evaluation_case_campaign_id"),
        "evaluation_case",
        ["campaign_id"],
        unique=False,
    )

    op.create_table(
        "evaluation_metric_result",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "case_id",
            sa.String(),
            sa.ForeignKey("evaluation_case.case_id"),
            nullable=False,
        ),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("score", sa.String(length=32), nullable=True),
        sa.Column("threshold", sa.String(length=32), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evaluation_metric_result_case_id"),
        "evaluation_metric_result",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_metric_result_campaign_id"),
        "evaluation_metric_result",
        ["campaign_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_evaluation_metric_result_campaign_id"),
        table_name="evaluation_metric_result",
    )
    op.drop_index(
        op.f("ix_evaluation_metric_result_case_id"),
        table_name="evaluation_metric_result",
    )
    op.drop_table("evaluation_metric_result")
    op.drop_index(op.f("ix_evaluation_case_campaign_id"), table_name="evaluation_case")
    op.drop_table("evaluation_case")
    op.drop_index(
        op.f("ix_evaluation_campaign_task_id"), table_name="evaluation_campaign"
    )
    op.drop_index(
        op.f("ix_evaluation_campaign_team_id"), table_name="evaluation_campaign"
    )
    op.drop_table("evaluation_campaign")
