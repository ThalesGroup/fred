# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Keep each explicitly reported failure for the lifetime of an active share.

Revision ID: 4eea63270bc1
Revises: 83adb40b71f5
"""

import sqlalchemy as sa
from alembic import op

revision = "4eea63270bc1"  # pragma: allowlist secret
down_revision = "83adb40b71f5"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the report index and preserve incidents from active legacy grants."""
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
    if op.get_context().dialect.name == "sqlite":
        # Match SQLAlchemy's SQLite timestamp format. Convert whole seconds to UTC
        # separately so SQLite's date functions cannot round the legacy microseconds.
        legacy_incidents = """
            SELECT session_id, json_extract(incident, '$.support_error_ref'),
                json_extract(incident, '$.cutoff.exchange_id'),
                json_extract(incident, '$.cutoff.first_rank'),
                json_extract(incident, '$.cutoff.last_rank'),
                json_extract(incident, '$.cutoff.turn_number'),
                datetime(substr(started_at, 1, 19) ||
                    CASE WHEN substr(started_at, -6, 1) IN ('+', '-')
                        THEN substr(started_at, -6) ELSE '' END) ||
                    CASE WHEN substr(started_at, 20, 1) = '.'
                        THEN substr(started_at, 20, 7) ELSE '.000000' END,
                json_extract(incident, '$.failure_category')
            FROM (
                SELECT session_id, incident,
                    json_extract(incident, '$.cutoff.started_at') AS started_at
                FROM conversation_trace_consent
                WHERE revoked_at IS NULL AND json_type(incident) = 'object'
            ) AS active_incidents
        """
    else:
        legacy_incidents = """
            SELECT session_id, incident->>'support_error_ref', incident->'cutoff'->>'exchange_id',
                (incident->'cutoff'->>'first_rank')::integer,
                (incident->'cutoff'->>'last_rank')::integer,
                (incident->'cutoff'->>'turn_number')::integer,
                (incident->'cutoff'->>'started_at')::timestamptz, incident->>'failure_category'
            FROM conversation_trace_consent
            WHERE revoked_at IS NULL AND json_typeof(incident) = 'object'
        """
    op.execute(
        f"""
        INSERT INTO conversation_trace_incident (
            session_id, support_error_ref, exchange_id, first_rank,
            last_rank, turn_number, started_at, failure_category
        )
        {legacy_incidents}
        """
    )


def downgrade() -> None:
    op.drop_table("conversation_trace_incident")
