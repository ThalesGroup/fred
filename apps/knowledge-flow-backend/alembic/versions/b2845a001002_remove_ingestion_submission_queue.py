"""Remove the ingestion submission fallback queue.

Revision ID: b2845a001002
Revises: a92e13f80c64
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b2845a001002"
down_revision = "a92e13f80c64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM kf_ingestion_submission LIMIT 1")).first():
        raise RuntimeError("Resolve pending ingestion submissions with the previous deployment before removing the submission queue.")
    op.drop_table("kf_ingestion_submission")


def downgrade() -> None:
    op.create_table(
        "kf_ingestion_submission",
        sa.Column("workflow_id", sa.String(255), primary_key=True),
        sa.Column("definition", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
