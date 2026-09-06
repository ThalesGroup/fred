"""add team wiki proposal columns

Revision ID: c8e5f2a13b47
Revises: b7d4c1a9e802
Create Date: 2026-09-07

A proposal for a page that does not exist yet has nowhere to carry the page's
title and parent: the page row is only created when a human approves, so that
an unapproved page never appears in the team's rail. Two nullable columns on
the revision hold them until then (WIKI-04).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e5f2a13b47"  # pragma: allowlist secret
down_revision: Union[str, None] = "b7d4c1a9e802"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "team_wiki_revisions",
        sa.Column("proposed_title", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "team_wiki_revisions",
        sa.Column("proposed_parent_page_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("team_wiki_revisions", "proposed_parent_page_id")
    op.drop_column("team_wiki_revisions", "proposed_title")
