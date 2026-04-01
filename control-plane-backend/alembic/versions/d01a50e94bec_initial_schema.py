"""initial schema

Matches the production database as of 2026-04-01.
Only teammetadata — the state of prod at the time Alembic was introduced.
Stamp production with: alembic stamp d01a50e94bec

Revision ID: d01a50e94bec
Revises:
Create Date: 2026-04-01 16:10:05.383171

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d01a50e94bec"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "teammetadata",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("description", sa.String(length=180), nullable=True),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("banner_object_storage_key", sa.String(length=300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("teammetadata")
