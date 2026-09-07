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

import sqlalchemy as sa
from alembic import op

revision: str = "e4a71b9c6d38"  # pragma: allowlist secret
down_revision: Union[str, None] = "d9f6a3b47c12"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_team_wiki_pages_sibling_title"
# Collapse BEFORE trimming, and spell the class out: `btrim(title)` alone strips
# spaces only, so a leading tab survived it and became a leading space; and
# Postgres `\s` under a UTF-8 ctype does not cover U+00A0. `control_plane_backend
# .team_wiki.service.title_key` folds a title exactly this way — the two must
# stay in step or the index stops backing the rule it exists for.
_FOLDED = "lower(btrim(regexp_replace(title, '[ \\t\\n\\r\\f\\v]+', ' ', 'g')))"
_KEY = f"team_id, parent_page_id, {_FOLDED}"


def upgrade() -> None:
    # Suffix every duplicate but the oldest, so the index below can be created.
    # Repeated until nothing collides: one pass is not enough, because a suffix
    # can land on a title that already exists ("Foo", "Foo", "Foo (2)" would
    # rename the second Foo onto the third page) and the index creation would
    # then fail with the deployment stuck mid-migration.
    for _ in range(20):
        renamed = (
            op.get_bind()
            .execute(
                sa.text(
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
            )
            .rowcount
        )
        if not renamed:
            break
    else:
        raise RuntimeError(
            "team_wiki_pages still has sibling titles that collide after 20 "
            "de-duplication passes; resolve them by hand before upgrading."
        )
    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX} ON team_wiki_pages ({_KEY}) NULLS NOT DISTINCT"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
