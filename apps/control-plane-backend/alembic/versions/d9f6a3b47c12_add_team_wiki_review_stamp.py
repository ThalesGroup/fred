"""add team wiki review stamp

Revision ID: d9f6a3b47c12
Revises: c8e5f2a13b47
Create Date: 2026-09-07

Clearing a page's review mark left no trace: the page's `updated_by` was
overwritten with the reviewer, which erased who had actually written the page,
and nothing recorded that a validation had happened at all. Two nullable
columns on the revision record it as its own event, so the history can show the
agent's edit and the human's validation separately (WIKI-05).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9f6a3b47c12"  # pragma: allowlist secret
down_revision: Union[str, None] = "c8e5f2a13b47"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "team_wiki_revisions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "team_wiki_revisions",
        sa.Column("reviewed_by", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("team_wiki_revisions", "reviewed_by")
    op.drop_column("team_wiki_revisions", "reviewed_at")
