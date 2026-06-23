"""add writable_documents table

Revision ID: a1c4f7e92b30
Revises: b5393ea7a65d
Create Date: 2026-06-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c4f7e92b30"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b5393ea7a65d"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirror the timestamp column type convention used across agentic-backend migrations.
ts_type = postgresql.TIMESTAMP(timezone=True).with_variant(
    sa.DateTime(timezone=True), "sqlite"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "writable_documents",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            ts_type,
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("session_id", "document_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("writable_documents")
