"""Bind editable conversation content to its Control Plane lifecycle root."""

from alembic import op

revision = "w2r3i4t5a6b7"  # pragma: allowlist secret
down_revision = "w1r2i3t4a5b6"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # The cast and immediate FK validation reject inconsistent old rows. No
    # backfill creates roots, loses content or infers authority from user IDs.
    op.execute(
        "ALTER TABLE cap_writable_document_docs ADD COLUMN conversation_id uuid GENERATED ALWAYS AS (session_id::uuid) STORED NOT NULL"
    )
    op.execute(
        "ALTER TABLE cap_writable_document_docs ADD CONSTRAINT cap_writable_document_docs_conversation_fk FOREIGN KEY (conversation_id) REFERENCES control_plane.session_metadata(session_id) ON DELETE CASCADE"
    )
    op.execute(
        "CREATE INDEX cap_writable_document_docs_conversation_idx ON cap_writable_document_docs (conversation_id)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Removing conversation ownership would reopen writes after purge"
    )
