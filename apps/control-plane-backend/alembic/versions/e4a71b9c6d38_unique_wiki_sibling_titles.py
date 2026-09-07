"""unique wiki sibling titles

Revision ID: e4a71b9c6d38
Revises: d9f6a3b47c12
Create Date: 2026-09-07

An agent addresses a wiki page by its path — its titles from the root — so two
pages sharing a title under one parent would give two pages the same address.
The service refuses one, and this index is what makes it hold under two
concurrent writes (WIKI-05).

Case-folded and whitespace-collapsed, because "Réunions" and "réunions " are
the same name to a reader. `COALESCE(parent_page_id, '')` is what extends the
rule to root pages, where `parent_page_id` is NULL and a plain unique index
would treat every row as distinct — no engine treats two NULLs as equal on
their own, and `''` can never collide with a real `page_id` (an 8-char alnum
slug, see `_unique_slug`).

Any existing collision is renamed rather than left to fail the migration: a
deployment that already has two namesakes must upgrade, not stop. The rename
pass runs in Python, against both engines identically, using the same fold as
`team_wiki.service.title_key` — the index itself has to be raw SQL per engine
(see `_folded_title_sql` below), but the one-off cleanup does not.
"""

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4a71b9c6d38"  # pragma: allowlist secret
down_revision: Union[str, None] = "d9f6a3b47c12"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_team_wiki_pages_sibling_title"
_PARENT_KEY = "COALESCE(parent_page_id, '')"

_TITLE_WHITESPACE = re.compile(r"[ \t\n\r\f\v]+")


def _title_key(title: str) -> str:
    """Mirrors `team_wiki.service.title_key` — kept as a literal copy, not an
    import, because a migration has to keep working after the function it
    borrowed from changes."""

    return _TITLE_WHITESPACE.sub(" ", title).strip(" \t\n\r\f\v").lower()


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
    close the race between two such checks. It does not change what the
    upgrade below dedupes: that runs the exact fold, in Python, against both
    engines identically, so the index can never fail to create either way.
    """

    if dialect_name == "postgresql":
        return "lower(btrim(regexp_replace(title, '[ \\t\\n\\r\\f\\v]+', ' ', 'g')))"
    return "lower(trim(title, ' ' || char(9, 10, 13, 12, 11)))"


def upgrade() -> None:
    bind = op.get_bind()

    # Suffix every duplicate but the oldest, so the index below can be
    # created. Repeated until nothing collides: one pass is not enough,
    # because a suffix can land on a title that already exists ("Foo", "Foo",
    # "Foo (2)" would rename the second Foo onto the third page) and the
    # index creation would then fail with the deployment stuck mid-migration.
    for _ in range(20):
        rows = bind.execute(
            sa.text(
                "SELECT page_id, team_id, parent_page_id, title "
                "FROM team_wiki_pages ORDER BY created_at, page_id"
            )
        ).fetchall()

        seen: dict[tuple[str, str | None, str], int] = {}
        renamed = 0
        for page_id, team_id, parent_page_id, title in rows:
            key = (team_id, parent_page_id, _title_key(title))
            seen[key] = seen.get(key, 0) + 1
            n = seen[key]
            if n > 1:
                bind.execute(
                    sa.text(
                        "UPDATE team_wiki_pages SET title = :title "
                        "WHERE page_id = :page_id"
                    ),
                    {"title": f"{title} ({n})", "page_id": page_id},
                )
                renamed += 1
        if not renamed:
            break
    else:
        raise RuntimeError(
            "team_wiki_pages still has sibling titles that collide after 20 "
            "de-duplication passes; resolve them by hand before upgrading."
        )

    fold = _folded_title_sql(bind.dialect.name)
    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX} ON team_wiki_pages "
        f"(team_id, {_PARENT_KEY}, {fold})"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
