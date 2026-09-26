"""Reserve active document ingestions and durably deliver scheduler batches.

Revision ID: a92e13f80c64
Revises: f7a1c4d20b93
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a92e13f80c64"  # pragma: allowlist secret
down_revision = "f7a1c4d20b93"  # pragma: allowlist secret
branch_labels = None
depends_on = None

PREDICATE = "kind = 'ingestion' AND target->>'type' = 'document' AND target->>'id' <> '' AND state NOT IN ('succeeded', 'failed', 'cancelled')"


def upgrade() -> None:
    duplicates = op.get_bind().execute(sa.text(f"SELECT target->>'id' FROM kf_task_run WHERE {PREDICATE} GROUP BY target->>'id' HAVING count(*) > 1 LIMIT 1")).first()
    if duplicates:
        raise RuntimeError(
            "Active duplicate document ingestions exist. Drain ingestion workflows and reconcile their task states before retrying this migration; do not mark running workflows failed."
        )
    op.create_index(
        "uq_kf_task_run_active_document_ingestion",
        "kf_task_run",
        [sa.text("(target->>'id')")],
        unique=True,
        postgresql_where=sa.text(PREDICATE),
        sqlite_where=sa.text(PREDICATE),
    )
    op.create_table(
        "kf_ingestion_submission",
        sa.Column("workflow_id", sa.String(255), primary_key=True),
        sa.Column("definition", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("kf_ingestion_submission")
    op.drop_index("uq_kf_task_run_active_document_ingestion", table_name="kf_task_run")
