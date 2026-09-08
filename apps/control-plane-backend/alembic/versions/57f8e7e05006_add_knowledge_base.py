"""add knowledge_base table

DB-backed knowledge base instance records — a team's instantiation of an
enabled KnowledgeBaseType (docs/swift/rfc/KNOWLEDGE-BASE-RFC.md §2/§4/§6).
Same shape as agent_instance: operational data, never populated from
deployment YAML.

Revision ID: 57f8e7e05006
Revises: a1c3e5f70b21
Create Date: 2026-09-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "57f8e7e05006"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a1c3e5f70b21"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "knowledge_base",
        sa.Column("knowledge_base_id", sa.String(), nullable=False),
        sa.Column("knowledge_base_type_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tag_ids_json", sa.Text(), nullable=False),
        sa.Column("connector_ref", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("knowledge_base_id"),
    )
    op.create_index(
        op.f("ix_knowledge_base_team_id"),
        "knowledge_base",
        ["team_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_knowledge_base_team_id"), table_name="knowledge_base")
    op.drop_table("knowledge_base")
