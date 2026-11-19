# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Keep each explicitly reported failure for the lifetime of an active share.

Revision ID: 4eea63270bc1
Revises: 83adb40b71f5
"""

import sqlalchemy as sa
from alembic import op

revision = "4eea63270bc1"
down_revision = "83adb40b71f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_trace_incident",
        sa.Column("session_id", sa.String(255), primary_key=True),
        sa.Column("support_error_ref", sa.String(32), primary_key=True),
        sa.Column("exchange_id", sa.String(255), nullable=False),
        sa.Column("first_rank", sa.Integer(), nullable=False),
        sa.Column("last_rank", sa.Integer(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_category", sa.String(32)),
        sa.ForeignKeyConstraint(
            ["session_id"], ["session_metadata.session_id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_trace_incident_ref",
        "conversation_trace_incident",
        ["support_error_ref", "session_id"],
    )
    op.create_index(
        "ix_trace_incident_order",
        "conversation_trace_incident",
        ["session_id", "first_rank", "exchange_id"],
    )
    op.create_index(
        "ix_trace_incident_latest",
        "conversation_trace_incident",
        ["session_id", "started_at"],
    )
    op.execute(
        """
        INSERT INTO conversation_trace_incident (
            session_id, support_error_ref, exchange_id, first_rank,
            last_rank, turn_number, started_at, failure_category
        )
        SELECT session_id, incident->>'support_error_ref', incident->'cutoff'->>'exchange_id',
            (incident->'cutoff'->>'first_rank')::integer,
            (incident->'cutoff'->>'last_rank')::integer,
            (incident->'cutoff'->>'turn_number')::integer,
            (incident->'cutoff'->>'started_at')::timestamptz, incident->>'failure_category'
        FROM conversation_trace_consent
        WHERE revoked_at IS NULL AND json_typeof(incident) = 'object'
        """
    )


def downgrade() -> None:
    op.drop_table("conversation_trace_incident")
