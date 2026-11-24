"""Bind Word session content and prepared-analysis snapshots to the CP root."""

from alembic import op

revision = "w9b2c3d4e5f6"  # pragma: allowlist secret
down_revision = "w8a1b2c3d4e5"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for suffix in ("sessions", "batches", "snapshots", "images", "analyses"):
        table = f"cap_word_template_{suffix}"
        source = (
            "split_part(template_key, ':', 1)" if suffix == "analyses" else "session_id"
        )
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN conversation_id uuid GENERATED ALWAYS AS ({source}::uuid) STORED NOT NULL"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_conversation_fk FOREIGN KEY (conversation_id) REFERENCES control_plane.session_metadata(session_id) ON DELETE CASCADE"
        )
        op.execute(f"CREATE INDEX {table}_conversation_idx ON {table}(conversation_id)")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        raise RuntimeError(
            "Removing conversation ownership would reopen writes after purge"
        )
