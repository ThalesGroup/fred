"""add document_labels table

Revision ID: bcd7cbdbedca
Revises: e2f3a4b5c6d7
Create Date: 2026-08-11 15:26:35.808070

Backfills every existing `metadata.doc->'labels'` entry into the new
`document_labels` assignment table using the same normalization contract as
`metadata_utils.normalize_labels` (trim, drop empty, dedupe), then strips
`labels` out of the JSONB blob so there is exactly one persisted source of
truth going forward — see `docs/swift/design/FILESYSTEM.md` "Business
labels". `DocumentMetadata.labels` (the public Pydantic/API field) is
unaffected: it is hydrated from `document_labels` on read
(`PostgresDocumentMetadataStore._hydrate_labels`), not stored verbatim.

On PostgreSQL, backfill and the downgrade's reconstruction are both plain
set-based SQL (`INSERT ... SELECT` over `jsonb_array_elements_text`, and
`UPDATE ... FROM` over a `jsonb_agg`) — the whole `metadata` table's rows and
JSONB blobs are never pulled into Python memory, however large the corpus.
SQLite (tests only) keeps a straightforward per-row Python loop, since a
small test corpus is exactly where that simplicity costs nothing.

Downgrade reconstructs `doc.labels` from `document_labels` for every
document (defaulting to `[]`, matching the Pydantic model's own default)
before dropping the table — no data loss on rollback.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bcd7cbdbedca"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOC_JSON_TYPE = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _normalize(raw_labels: list) -> list[str]:
    """Same contract as `knowledge_flow_backend.features.metadata.metadata_utils.normalize_labels`,
    reimplemented here (not imported) because migrations must not depend on
    application code that can change shape independently of the schema."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_labels or []:
        label = (raw or "").strip()
        if label and label not in seen:
            seen.add(label)
            out.append(label)
    return out


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "document_labels",
        sa.Column("document_uid", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["document_uid"], ["metadata.document_uid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_uid", "label"),
    )
    op.create_index("idx_document_labels_label_document_uid", "document_labels", ["label", "document_uid"], unique=False)

    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Set-based backfill: expand each document's `doc->'labels'` JSONB
        # array server-side (`jsonb_array_elements_text`), trim/drop-empty
        # each value (`regexp_replace` matches Python `str.strip()`'s
        # whitespace class, not just the space character `trim()` alone
        # would), and let `SELECT DISTINCT` dedupe -- the normalization
        # contract `metadata_utils.normalize_labels` also applies, minus its
        # first-seen-order guarantee, which `document_labels` (a set, no
        # order column) does not need. No row of `metadata` or its JSONB
        # blob is ever pulled into Python memory, however large the corpus.
        bind.execute(
            sa.text(
                r"""
                INSERT INTO document_labels (document_uid, label)
                SELECT DISTINCT document_uid, label FROM (
                    SELECT
                        m.document_uid AS document_uid,
                        regexp_replace(elem.value, '^\s+|\s+$', '', 'g') AS label
                    FROM metadata m,
                         LATERAL jsonb_array_elements_text(COALESCE(m.doc->'labels', '[]'::jsonb)) AS elem(value)
                ) normalized
                WHERE label <> ''
                ON CONFLICT DO NOTHING
                """
            )
        )

        # Strip `labels` from the JSONB blob -- `document_labels` is now the
        # only source of truth, and a stray key here could silently start
        # diverging from it the moment any future code reintroduces it.
        # Guarded to `doc ? 'labels'` so a document that never had the key
        # is not rewritten for nothing.
        bind.execute(sa.text("UPDATE metadata SET doc = doc - 'labels' WHERE doc ? 'labels'"))
        return

    # SQLite (tests only): no JSONB functions available -- read/normalize/
    # write in Python. A small test corpus is exactly where this simplicity
    # costs nothing; the PostgreSQL branch above is what a real corpus needs.
    metadata_table = sa.table(
        "metadata",
        sa.column("document_uid", sa.String()),
        sa.column("doc", _DOC_JSON_TYPE),
    )
    document_labels_table = sa.table(
        "document_labels",
        sa.column("document_uid", sa.String()),
        sa.column("label", sa.String()),
    )
    rows = bind.execute(sa.select(metadata_table.c.document_uid, metadata_table.c.doc)).fetchall()

    # Backfill: one row per (document_uid, normalized label), deduped across
    # the whole table (normalization can make two previously-distinct raw
    # values collide, e.g. " DAT" and "DAT").
    seen_assignments: set[tuple[str, str]] = set()
    to_insert: list[dict] = []
    for document_uid, doc in rows:
        if not doc:
            continue
        for label in _normalize(doc.get("labels")):
            key = (document_uid, label)
            if key not in seen_assignments:
                seen_assignments.add(key)
                to_insert.append({"document_uid": document_uid, "label": label})
    if to_insert:
        bind.execute(sa.insert(document_labels_table), to_insert)

    for document_uid, doc in rows:
        if not doc or "labels" not in doc:
            continue
        stripped = {k: v for k, v in doc.items() if k != "labels"}
        bind.execute(sa.update(metadata_table).where(metadata_table.c.document_uid == document_uid).values(doc=stripped))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Set-based reconstruction: one UPDATE aggregates each document's
        # labels back into a sorted JSONB array via `jsonb_agg`, a second
        # covers documents with zero labels (absent from the aggregate join
        # entirely) -- neither pulls `metadata` into Python memory.
        bind.execute(
            sa.text(
                """
                UPDATE metadata m
                SET doc = doc || jsonb_build_object('labels', agg.labels)
                FROM (
                    SELECT document_uid, jsonb_agg(label ORDER BY label) AS labels
                    FROM document_labels
                    GROUP BY document_uid
                ) agg
                WHERE m.document_uid = agg.document_uid
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE metadata
                SET doc = doc || '{"labels": []}'::jsonb
                WHERE NOT EXISTS (
                    SELECT 1 FROM document_labels dl WHERE dl.document_uid = metadata.document_uid
                )
                """
            )
        )
        op.drop_index("idx_document_labels_label_document_uid", table_name="document_labels")
        op.drop_table("document_labels")
        return

    # SQLite (tests only): same per-row Python reasoning as upgrade()'s
    # fallback above.
    metadata_table = sa.table(
        "metadata",
        sa.column("document_uid", sa.String()),
        sa.column("doc", _DOC_JSON_TYPE),
    )
    document_labels_table = sa.table(
        "document_labels",
        sa.column("document_uid", sa.String()),
        sa.column("label", sa.String()),
    )

    label_rows = bind.execute(sa.select(document_labels_table.c.document_uid, document_labels_table.c.label)).fetchall()
    labels_by_uid: dict[str, list[str]] = {}
    for document_uid, label in label_rows:
        labels_by_uid.setdefault(document_uid, []).append(label)

    doc_rows = bind.execute(sa.select(metadata_table.c.document_uid, metadata_table.c.doc)).fetchall()
    for document_uid, doc in doc_rows:
        restored = dict(doc or {})
        restored["labels"] = sorted(labels_by_uid.get(document_uid, []))
        bind.execute(sa.update(metadata_table).where(metadata_table.c.document_uid == document_uid).values(doc=restored))

    op.drop_index("idx_document_labels_label_document_uid", table_name="document_labels")
    op.drop_table("document_labels")
