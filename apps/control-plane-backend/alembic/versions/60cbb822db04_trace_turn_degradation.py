# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Persist trace publication degradation on the affected turn.

Revision ID: 60cbb822db04
Revises: 3fa0e47d652c
"""

import sqlalchemy as sa
from alembic import op

revision = "60cbb822db04"  # pragma: allowlist secret
down_revision = "3fa0e47d652c"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_TABLE = "conversation_trace_turn"
_INDEX = "ix_conversation_trace_turn_degraded_until"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("degraded_until", sa.DateTime(timezone=True)))
    op.add_column(_TABLE, sa.Column("degradation_reason", sa.String(32)))
    op.create_index(
        _INDEX,
        _TABLE,
        ["degraded_until"],
        postgresql_where=sa.text("degraded_until IS NOT NULL"),
        sqlite_where=sa.text("degraded_until IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "degradation_reason")
    op.drop_column(_TABLE, "degraded_until")
