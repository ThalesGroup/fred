"""Join trace receipts to Weaver's canonical conversation lifecycle."""

from alembic import op

revision = "f2b3c4d5e6a7"  # pragma: allowlist secret
down_revision = ("b34a0d59ef71", "e1f2a3b4c5d6")  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    # d0e1f2a3b4c5 already owns the exchange/rank index on the merged branch.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE session_trace_incidents ADD COLUMN conversation_id uuid GENERATED ALWAYS AS (session_id::uuid) STORED NOT NULL"
    )
    op.execute(
        "ALTER TABLE session_trace_incidents ADD CONSTRAINT session_trace_incidents_conversation_fk FOREIGN KEY (conversation_id) REFERENCES control_plane.session_metadata(session_id) ON DELETE CASCADE"
    )
    op.execute(
        "CREATE INDEX session_trace_incidents_conversation_idx ON session_trace_incidents (conversation_id)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        raise RuntimeError(
            "Removing conversation ownership would reopen writes after purge"
        )
