# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Track trace capacity, publication leases, and diagnostic expiry.

Revision ID: 78961f25bd30
Revises: 2f0ac7d34e61
"""

from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "78961f25bd30"  # pragma: allowlist secret
down_revision = "2f0ac7d34e61"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, kind, default in (
        ("sampling_percent", sa.Integer(), "100"),
        ("retention_days", sa.Integer(), "30"),
        ("storage_cap_bytes", sa.BigInteger(), "20000000000"),
        ("used_bytes", sa.BigInteger(), "0"),
        ("reserved_bytes", sa.BigInteger(), "0"),
        ("reclaim_target", sa.BigInteger(), "0"),
    ):
        op.add_column(
            "conversation_trace_settings",
            sa.Column(name, kind, server_default=default, nullable=False),
        )
    op.add_column(
        "conversation_trace_settings",
        sa.Column("degraded_until", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "conversation_trace_settings", sa.Column("degradation_reason", sa.String(32))
    )
    op.add_column(
        "session_metadata",
        sa.Column("trace_last_captured_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_session_metadata_trace_last_captured_at",
        "session_metadata",
        ["trace_last_captured_at"],
    )
    op.execute(
        sa.text(
            "UPDATE session_metadata SET trace_last_captured_at = "
            "(SELECT max(t.started_at) FROM conversation_trace_turn t "
            "WHERE t.session_id = session_metadata.session_id) "
            "WHERE EXISTS (SELECT 1 FROM conversation_trace_turn t "
            "WHERE t.session_id = session_metadata.session_id)"
        )
    )
    op.add_column(
        "conversation_trace_consent",
        sa.Column("diagnostic_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        sa.text("UPDATE conversation_trace_consent SET diagnostic_at = started_at")
    )
    op.create_index(
        "ix_trace_consent_diagnostic_expiry",
        "conversation_trace_consent",
        ["diagnostic_at", "grant_id"],
    )
    storage = op.create_table(
        "conversation_trace_storage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("runtime_id", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("capture_id", sa.String(36), nullable=False),
        sa.Column("objects", sa.JSON(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("lease", sa.String(36)),
    )
    op.create_index(
        "ix_conversation_trace_storage_session_id",
        "conversation_trace_storage",
        ["session_id"],
    )
    op.create_index(
        "ix_conversation_trace_storage_capture_id",
        "conversation_trace_storage",
        ["capture_id"],
    )
    op.create_index(
        "ix_trace_storage_due",
        "conversation_trace_storage",
        ["runtime_id", "due_at", "id"],
    )
    op.create_index(
        "ix_trace_storage_state", "conversation_trace_storage", ["state", "session_id"]
    )

    if not op.get_context().as_sql:
        _backfill(op.get_bind(), storage)


def _backfill(connection: sa.Connection, storage: sa.Table) -> None:
    """Preserve older evidence. A runtime reconciles real object sizes before more writes."""
    consent = sa.table(
        "conversation_trace_consent",
        sa.column("grant_id", sa.String()),
        sa.column("incident", sa.JSON()),
        sa.column("diagnostic_at", sa.DateTime(timezone=True)),
    )
    for batch in connection.execute(
        sa.select(consent.c.grant_id, consent.c.incident).where(
            consent.c.incident.is_not(None)
        )
    ).partitions(100):
        for grant_id, incident in batch:
            if incident:
                connection.execute(
                    consent.update()
                    .where(consent.c.grant_id == grant_id)
                    .values(
                        diagnostic_at=datetime.fromisoformat(
                            incident["cutoff"]["started_at"]
                        )
                    )
                )

    turns = sa.table(
        "conversation_trace_turn",
        sa.column("capture_id", sa.String()),
        sa.column("session_id", sa.String()),
        sa.column("runtime_id", sa.String()),
        sa.column("started_at", sa.DateTime(timezone=True)),
        sa.column("http_attempts", sa.JSON()),
        sa.column("sse_segments", sa.JSON()),
        sa.column("model_calls", sa.JSON()),
        sa.column("tool_calls", sa.JSON()),
    )
    for batch in connection.execute(sa.select(turns)).mappings().partitions(100):
        rows = []
        for turn in batch:
            refs = {
                item["ref"]
                for field in ("http_attempts", "model_calls", "tool_calls")
                for item in turn[field] or []
            }
            for segment in turn["sse_segments"] or []:
                refs.update(
                    lane["ref"] for lane in (segment["outgoing"], *segment["provider"])
                )
            if refs:
                rows.append(
                    {
                        "id": str(uuid4()),
                        "capture_id": turn["capture_id"],
                        "session_id": turn["session_id"],
                        "runtime_id": turn["runtime_id"],
                        "objects": dict.fromkeys(refs, 0),
                        "size_bytes": 0,
                        "state": "measure",
                        "due_at": turn["started_at"],
                    }
                )
        if rows:
            connection.execute(storage.insert(), rows)


def downgrade() -> None:
    op.drop_table("conversation_trace_storage")
    op.drop_index(
        "ix_trace_consent_diagnostic_expiry", table_name="conversation_trace_consent"
    )
    op.drop_column("conversation_trace_consent", "diagnostic_at")
    op.drop_index(
        "ix_session_metadata_trace_last_captured_at", table_name="session_metadata"
    )
    op.drop_column("session_metadata", "trace_last_captured_at")
    for column in (
        "degradation_reason",
        "degraded_until",
        "reclaim_target",
        "reserved_bytes",
        "used_bytes",
        "storage_cap_bytes",
        "retention_days",
        "sampling_percent",
    ):
        op.drop_column("conversation_trace_settings", column)
