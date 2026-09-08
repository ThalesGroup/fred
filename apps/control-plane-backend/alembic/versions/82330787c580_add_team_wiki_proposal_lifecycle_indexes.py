"""add team wiki proposal lifecycle indexes

Revision ID: 82330787c580
Revises: e4a71b9c6d38
Create Date: 2026-09-08

Backs two new lifecycle-sweep queries (WIKI-05): a cross-team scan for
abandoned proposals (`status='proposed' AND created_at < cutoff`) and a
per-session lookup used when a session is erased.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "82330787c580"  # pragma: allowlist secret
down_revision: Union[str, None] = "e4a71b9c6d38"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_team_wiki_revisions_status_created_at",
        "team_wiki_revisions",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_team_wiki_revisions_session_id",
        "team_wiki_revisions",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_team_wiki_revisions_session_id", table_name="team_wiki_revisions")
    op.drop_index(
        "ix_team_wiki_revisions_status_created_at", table_name="team_wiki_revisions"
    )
