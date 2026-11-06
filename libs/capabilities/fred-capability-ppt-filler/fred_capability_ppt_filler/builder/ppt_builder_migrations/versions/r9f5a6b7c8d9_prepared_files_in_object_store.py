"""Move prepared files to the pod's object store; SQL keeps what proves them.

Weaver installs fresh, so the dropped binaries have no data to carry over.

Revision ID: r9f5a6b7c8d9
Revises: r9e4a5b6c7d8
"""

import sqlalchemy as sa
from alembic import op

revision = "r9f5a6b7c8d9"  # pragma: allowlist secret
down_revision = "r9e4a5b6c7d8"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cap_ppt_builder_analysis") as table:
        table.drop_column("template_pptx")
        table.drop_column("patterns_pdf")
        table.add_column(sa.Column("template_digest", sa.String(64), nullable=True))
        table.add_column(sa.Column("patterns_digest", sa.String(64), nullable=True))
        table.add_column(
            sa.Column(
                "pending_writes", sa.Integer(), nullable=False, server_default="0"
            )
        )
        table.create_check_constraint(
            "cap_ppt_builder_analysis_published_check",
            "status <> 'succeeded' OR template_digest IS NOT NULL",
        )
        table.create_check_constraint(
            "cap_ppt_builder_analysis_pending_writes_check", "pending_writes >= 0"
        )


def downgrade() -> None:
    raise RuntimeError("Prepared files cannot return to SQL: recreate the database")
