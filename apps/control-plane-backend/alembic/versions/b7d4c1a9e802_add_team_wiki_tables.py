# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""add team wiki tables

Two tables for the team wiki (WIKI-01): pages and their revisions.

One table holds every team's pages, keyed by `team_id`, rather than a table per
team — a table per team would mean DDL at team creation, outside Alembic and
invisible to this history.

Revisions are append-only: an edit inserts a row here and moves the page's
`current_revision_id`. History, restore and conflict detection are consequences
of that shape rather than features built on top, which is why there is no
`content` column on the page itself.

`(team_id, slug)` is unique, and the rules page uses a reserved slug — so at
most one rules page per team follows from that constraint with no partial index.

Revision ID: b7d4c1a9e802
Revises: a1c3e5f70b21
Create Date: 2026-09-06 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d4c1a9e802"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a1c3e5f70b21"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

__all__ = [
    "branch_labels",
    "depends_on",
    "down_revision",
    "downgrade",
    "revision",
    "upgrade",
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "team_wiki_pages",
        sa.Column("page_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("parent_page_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("current_revision_id", sa.String(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("page_id"),
        sa.UniqueConstraint("team_id", "slug", name="uq_team_wiki_pages_team_slug"),
    )
    op.create_index(
        op.f("ix_team_wiki_pages_team_id"), "team_wiki_pages", ["team_id"], unique=False
    )
    op.create_index(
        op.f("ix_team_wiki_pages_parent_page_id"),
        "team_wiki_pages",
        ["parent_page_id"],
        unique=False,
    )

    op.create_table(
        "team_wiki_revisions",
        sa.Column("revision_id", sa.String(), nullable=False),
        sa.Column("page_id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("base_revision_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("author_user_id", sa.String(), nullable=False),
        sa.Column("author_kind", sa.String(length=16), nullable=False),
        sa.Column("agent_instance_id", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("revision_id"),
    )
    op.create_index(
        op.f("ix_team_wiki_revisions_page_id"),
        "team_wiki_revisions",
        ["page_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_wiki_revisions_team_id"),
        "team_wiki_revisions",
        ["team_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_team_wiki_revisions_team_id"), table_name="team_wiki_revisions"
    )
    op.drop_index(
        op.f("ix_team_wiki_revisions_page_id"), table_name="team_wiki_revisions"
    )
    op.drop_table("team_wiki_revisions")
    op.drop_index(
        op.f("ix_team_wiki_pages_parent_page_id"), table_name="team_wiki_pages"
    )
    op.drop_index(op.f("ix_team_wiki_pages_team_id"), table_name="team_wiki_pages")
    op.drop_table("team_wiki_pages")
