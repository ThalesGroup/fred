"""Persist filesystem ownership and uncertain writes until confirmed erasure.

Deploy with old runtime writers drained. Existing SQL conversations seed a
conservative content manifest; the purge endpoint also creates it before touching
storage, covering pre-existing prefixes without runtime SQL content.
"""

from alembic import op

revision = "c9d0e1f2a3b4"  # pragma: allowlist secret
down_revision = "b8c9d0e1f2a3"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        CREATE TABLE runtime_session_filesystem (
            session_id uuid PRIMARY KEY,
            closed boolean NOT NULL DEFAULT false,
            CONSTRAINT runtime_session_filesystem_root_fk
                FOREIGN KEY (session_id) REFERENCES control_plane.session_metadata(session_id)
                ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE TABLE runtime_session_file_write (
            token uuid PRIMARY KEY,
            session_id uuid NOT NULL,
            pending boolean NOT NULL,
            CONSTRAINT runtime_session_file_write_root_fk
                FOREIGN KEY (session_id) REFERENCES control_plane.session_metadata(session_id)
                ON DELETE RESTRICT,
            CONSTRAINT runtime_session_file_write_kind_check
                CHECK ((NOT pending AND token = session_id) OR (pending AND token <> session_id))
        )
    """)
    op.execute(
        "CREATE INDEX runtime_session_file_write_session_idx ON runtime_session_file_write (session_id)"
    )
    # These are every runtime content table, including interrupted checkpoints
    # which have no history or thread-owner row. No permissions to read CP data
    # are needed to adopt the already FK-validated conversation identities.
    op.execute("""
        INSERT INTO runtime_session_filesystem(session_id)
        SELECT conversation_id FROM session_history
        UNION SELECT conversation_id FROM runtime_turn_steering
        UNION SELECT conversation_id FROM v2_langgraph_checkpoint
        UNION SELECT conversation_id FROM v2_langgraph_checkpoint_blob
        UNION SELECT conversation_id FROM v2_langgraph_checkpoint_write
        UNION SELECT conversation_id FROM v2_checkpoint_thread_owner
        UNION SELECT conversation_id FROM v2_checkpoint_hitl_claim
    """)
    op.execute("""
        INSERT INTO runtime_session_file_write(token, session_id, pending)
        SELECT session_id, session_id, false FROM runtime_session_filesystem
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError("Removing filesystem ownership would reopen writes after purge")
