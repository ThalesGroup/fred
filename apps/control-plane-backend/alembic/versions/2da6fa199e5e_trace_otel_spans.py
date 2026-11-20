"""Retain the OpenTelemetry span tree in the existing turn index.

Revision ID: 2da6fa199e5e
Revises: 60cbb822db04
"""

import sqlalchemy as sa
from alembic import op

revision = "2da6fa199e5e"  # pragma: allowlist secret
down_revision = "60cbb822db04"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversation_trace_turn", sa.Column("otel_spans", sa.JSON()))


def downgrade() -> None:
    op.drop_column("conversation_trace_turn", "otel_spans")
