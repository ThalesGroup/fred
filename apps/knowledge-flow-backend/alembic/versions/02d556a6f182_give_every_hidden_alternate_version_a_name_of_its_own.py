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

"""give every hidden alternate version a name of its own

Importing a document whose name a folder already held used to store it as a
hidden alternate: same name, `version = 1`. Nothing rendered the distinction and
no action promoted it, so the two were indistinguishable in the UI.

Each alternate becomes an ordinary document named `report (1).pdf`. Nothing is
deleted, no identifier and no folder membership changes. Full rationale:
openspec/changes/retire-document-versioning/design.md.

Revision ID: 02d556a6f182
Revises: c3a71f5e0d48
Create Date: 2026-09-30 21:23:00.415294

"""

from pathlib import PurePosixPath
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
# codeql[py/unused-global-variable]
revision: str = "02d556a6f182"  # pragma: allowlist secret
# codeql[py/unused-global-variable]
down_revision: Union[str, Sequence[str], None] = "c3a71f5e0d48"  # pragma: allowlist secret
# codeql[py/unused-global-variable]
branch_labels: Union[str, Sequence[str], None] = None
# codeql[py/unused-global-variable]
depends_on: Union[str, Sequence[str], None] = None

# `(doc->'identity'->>'version')::int` on its own would raise on a row whose
# value is not a number, and PostgreSQL does not promise to evaluate a guard in
# the same WHERE before the cast. CASE does promise it.
_IS_ALTERNATE = """
    CASE WHEN doc -> 'identity' ->> 'version' ~ '^[0-9]+$'
         THEN (doc -> 'identity' ->> 'version')::int
         ELSE 0
    END > 0
"""


def _suffixed(name: str, number: int) -> str:
    """`report.pdf` -> `report (1).pdf`, the convention every desktop uses.

    The extension is whatever follows the last dot, so a name that is all dots
    or has none keeps the suffix at the end where a user would expect it.
    """
    stem = PurePosixPath(name).stem
    extension = PurePosixPath(name).suffix
    return f"{stem} ({number}){extension}" if stem else f"{name} ({number})"


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        _rename_alternates_postgresql(bind)
        return

    _rename_alternates_portable(bind)


def _rename_alternates_postgresql(bind: sa.engine.Connection) -> None:
    """One indexed lookup per candidate name, never a scan of the corpus.

    The alternates are few — the old mechanism allowed at most one per name per
    folder — while the documents they might collide with are not, so the
    collision question is asked of the database (`idx_metadata_document_name`
    plus the GIN index on `tag_ids`) rather than answered by loading every name.
    """
    alternates = bind.execute(
        sa.text(
            f"""
            SELECT document_uid,
                   doc -> 'identity' ->> 'document_name' AS name,
                   COALESCE(tag_ids, ARRAY[]::varchar[]) AS tags
            FROM metadata
            WHERE {_IS_ALTERNATE}
            ORDER BY document_uid
            """
        )
    ).fetchall()

    held = sa.text(
        """
        SELECT 1 FROM metadata
        WHERE document_uid <> :uid
          AND doc -> 'identity' ->> 'document_name' = :name
          AND tag_ids && CAST(:tags AS varchar[])
        LIMIT 1
        """
    )

    for uid, name, tags in alternates:
        new_name = name
        if name and tags:
            # A document in no folder cannot collide with anything.
            def taken(candidate: str, uid: str = uid, tags: list = tags) -> bool:
                return bind.execute(held, {"uid": uid, "name": candidate, "tags": tags}).first() is not None

            if taken(name):
                number = 1
                while taken(_suffixed(name, number)):
                    number += 1
                new_name = _suffixed(name, number)

        # One statement per document: the rename and the two field removals
        # land together or not at all, which is what makes a resumed run safe.
        bind.execute(
            sa.text(
                """
                UPDATE metadata
                SET doc = jsonb_set(
                        doc #- '{identity,canonical_name}' #- '{identity,version}',
                        '{identity,document_name}',
                        to_jsonb(CAST(:name AS text))
                    )
                WHERE document_uid = :uid
                """
            ),
            {"uid": uid, "name": new_name},
        )


def _rename_alternates_portable(bind: sa.engine.Connection) -> None:
    """SQLite (tests only): no JSONB operators, so read, decide, write back.

    `tag_ids` is a JSON array here rather than a native one, so the overlap the
    PostgreSQL branch delegates to `&&` is computed in Python. A test corpus is
    exactly where that costs nothing.
    """
    metadata_table = sa.table(
        "metadata",
        sa.column("document_uid", sa.String()),
        sa.column("tag_ids", sa.JSON()),
        sa.column("doc", sa.JSON()),
    )
    rows = bind.execute(sa.select(metadata_table.c.document_uid, metadata_table.c.tag_ids, metadata_table.c.doc)).fetchall()

    def identity(doc: object) -> dict:
        return doc.get("identity", {}) if isinstance(doc, dict) else {}

    def tags_of(tag_ids: object) -> set:
        return set(tag_ids) if isinstance(tag_ids, list) else set()

    def is_alternate(doc: object) -> bool:
        version = identity(doc).get("version")
        return isinstance(version, int) and not isinstance(version, bool) and version > 0

    # Names held per folder, kept current as each alternate is renamed so two
    # alternates in one folder cannot both claim `(1)`.
    names_by_tag: dict[str, dict[str, str]] = {}
    for uid, tag_ids, doc in rows:
        name = identity(doc).get("document_name")
        if not name:
            continue
        for tag in tags_of(tag_ids):
            names_by_tag.setdefault(tag, {})[uid] = name

    for uid, tag_ids, doc in sorted(rows, key=lambda row: row[0]):
        if not is_alternate(doc):
            continue
        name = identity(doc).get("document_name")
        tags = tags_of(tag_ids)
        new_name = name

        if name and tags:

            def taken(candidate: str, uid: str = uid, tags: set = tags) -> bool:
                return any(held_uid != uid and held_name == candidate for tag in tags for held_uid, held_name in names_by_tag.get(tag, {}).items())

            if taken(name):
                number = 1
                while taken(_suffixed(name, number)):
                    number += 1
                new_name = _suffixed(name, number)

        updated = dict(doc)
        updated_identity = dict(identity(doc))
        updated_identity.pop("canonical_name", None)
        updated_identity.pop("version", None)
        if new_name:
            updated_identity["document_name"] = new_name
        updated["identity"] = updated_identity

        bind.execute(metadata_table.update().where(metadata_table.c.document_uid == uid).values(doc=updated))

        for tag in tags:
            names_by_tag.setdefault(tag, {})[uid] = new_name


def downgrade() -> None:
    """Downgrade schema.

    Deliberately empty. Once two documents have names of their own, nothing
    records which of them used to be the hidden one, so a downgrade that claimed
    to restore the distinction would be inventing it. The renamed documents stay
    valid ordinary documents on an older release.
    """
