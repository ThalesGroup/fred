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

"""add team wiki

Revision ID: b7d4c1a9e802
Revises: a1c3e5f70b21
Create Date: 2026-09-06

Two tables for the team wiki (WIKI-01): pages and their revisions. One table
holds every team's pages, keyed by `team_id`, rather than a table per team — a
table per team would mean DDL at team creation, outside Alembic and hard to
reconcile.

A proposal for a page that does not exist yet has nowhere to carry the page's
title and parent: the page row is only created when a human approves, so an
unapproved page never appears in the team's rail. Two nullable columns on the
revision hold them until then (WIKI-04).

Clearing a page's review mark left no trace in an earlier draft of this
feature: the page's `updated_by` was overwritten with the reviewer, which
erased who had actually written the page, and nothing recorded that a
validation had happened at all. Two more nullable columns on the revision
record it as its own event, so the history can show the agent's edit and the
human's validation separately (WIKI-05).

An agent addresses a wiki page by its path — its titles from the root — so two
pages sharing a title under one parent would give two pages the same address.
The service refuses one, and a case-folded, whitespace-collapsed unique index
is what makes it hold under two concurrent writes (WIKI-05). Case-folded
because "Réunions" and "réunions " are the same name to a reader.
`COALESCE(parent_page_id, '')` extends the rule to root pages, where
`parent_page_id` is NULL and a plain unique index would treat every row as
distinct — no engine treats two NULLs as equal on their own, and `''` can
never collide with a real `page_id` (an 8-char alnum slug, see
`_unique_slug`). The table is created fresh by this same migration, so no
existing-row dedup pass is needed before the index goes on.

Two indexes back the lifecycle-sweep queries added alongside the above
(WIKI-05): a cross-team scan for abandoned proposals
(`status='proposed' AND created_at < cutoff`) and a per-session lookup used
when a session is erased.
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

_SIBLING_TITLE_INDEX = "uq_team_wiki_pages_sibling_title"
_PARENT_KEY = "COALESCE(parent_page_id, '')"


def _folded_title_sql(dialect_name: str) -> str:
    """The DB-side mirror of `title_key`, for the index PostgreSQL and SQLite
    each enforce on every future insert.

    PostgreSQL gets the exact match: `regexp_replace` collapses the same
    whitespace class `title_key` strips. SQLite has no `regexp_replace`, so it
    only case-folds and trims the ends — a narrower backstop for the
    concurrent-write race than PostgreSQL gets (it will not catch two titles
    that differ solely by a run of internal whitespace). That gap is
    acceptable here because the service layer's `_require_free_title` already
    enforces the exact rule, with full whitespace collapsing, on every write
    before either engine's index is ever reached; this index only exists to
    close the race between two such checks.
    """

    if dialect_name == "postgresql":
        return "lower(btrim(regexp_replace(title, '[ \\t\\n\\r\\f\\v]+', ' ', 'g')))"
    return "lower(trim(title, ' ' || char(9, 10, 13, 12, 11)))"


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
        sa.Column("proposed_title", sa.String(length=300), nullable=True),
        sa.Column("proposed_parent_page_id", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(), nullable=True),
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

    bind = op.get_bind()
    fold = _folded_title_sql(bind.dialect.name)
    op.execute(
        f"CREATE UNIQUE INDEX {_SIBLING_TITLE_INDEX} ON team_wiki_pages "
        f"(team_id, {_PARENT_KEY}, {fold})"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"DROP INDEX IF EXISTS {_SIBLING_TITLE_INDEX}")
    op.drop_index("ix_team_wiki_revisions_session_id", table_name="team_wiki_revisions")
    op.drop_index(
        "ix_team_wiki_revisions_status_created_at", table_name="team_wiki_revisions"
    )
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
