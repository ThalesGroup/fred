"""initial schema

Matches the production database as of 2026-04-01.
Only teammetadata — the state of prod at the time Alembic was introduced.

Idempotent: skips CREATE TABLE if a database already has ``teammetadata`` (e.g. a
pre-Alembic prod/staging clone that was never explicitly stamped, or a Job re-run
against a database left in a partial state). Without this guard, running against
such a database raises ``DuplicateTableError`` instead of proceeding to the rest
of head.

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


def _teammetadata_exists() -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return "teammetadata" in inspector.get_table_names()


def upgrade() -> None:
    """Upgrade schema."""
    if _teammetadata_exists():
        return
    op.create_table(
        "teammetadata",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("description", sa.String(length=180), nullable=True),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("banner_object_storage_key", sa.String(length=300), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    if not _teammetadata_exists():
        return
    op.drop_table("teammetadata")
