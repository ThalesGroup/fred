# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Add the bounded content notice work queue to existing history rows."""

import sqlalchemy as sa
from alembic import op
from fred_core.models.base import JsonColumn

revision = "b131ce5af248"  # pragma: allowlist secret
down_revision = "d37ac41af81b"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session_history", sa.Column("content_policy_job", JsonColumn))
    op.add_column(
        "session_history", sa.Column("content_policy_due", sa.DateTime(timezone=True))
    )
    op.add_column("session_history", sa.Column("content_policy_runtime", sa.String()))
    op.create_index(
        "ix_session_history_content_policy_due",
        "session_history",
        ["content_policy_runtime", "content_policy_due"],
        postgresql_where=sa.text("content_policy_due IS NOT NULL"),
        sqlite_where=sa.text("content_policy_due IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_session_history_content_policy_due", table_name="session_history")
    op.drop_column("session_history", "content_policy_runtime")
    op.drop_column("session_history", "content_policy_due")
    op.drop_column("session_history", "content_policy_job")
