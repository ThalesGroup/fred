"""unique wiki sibling titles

Revision ID: e4a71b9c6d38
Revises: d9f6a3b47c12
Create Date: 2026-09-07

An agent addresses a wiki page by its path — its titles from the root — so two
pages sharing a title under one parent would give two pages the same address.
The service refuses one, and this index is what makes it hold under two
concurrent writes (WIKI-05).

Case-folded and whitespace-collapsed, because "Réunions" and "réunions " are
the same name to a reader. `NULLS NOT DISTINCT` (PostgreSQL 15+) is what
extends the rule to root pages, where `parent_page_id` is NULL and a plain
unique index would treat every row as distinct.

Any existing collision is renamed rather than left to fail the migration: a
deployment that already has two namesakes must upgrade, not stop.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e4a71b9c6d38"  # pragma: allowlist secret
down_revision: Union[str, None] = "d9f6a3b47c12"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_team_wiki_pages_sibling_title"
_KEY = "team_id, parent_page_id, lower(regexp_replace(btrim(title), '\\s+', ' ', 'g'))"


def upgrade() -> None:
    # Suffix every duplicate but the oldest, so the index below can be created.
    op.execute(
        f"""
        WITH ranked AS (
            SELECT page_id,
                   row_number() OVER (
                       PARTITION BY {_KEY} ORDER BY created_at, page_id
                   ) AS n
            FROM team_wiki_pages
        )
        UPDATE team_wiki_pages p
           SET title = p.title || ' (' || ranked.n || ')'
          FROM ranked
         WHERE ranked.page_id = p.page_id AND ranked.n > 1
        """
    )
    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX} ON team_wiki_pages ({_KEY}) NULLS NOT DISTINCT"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
