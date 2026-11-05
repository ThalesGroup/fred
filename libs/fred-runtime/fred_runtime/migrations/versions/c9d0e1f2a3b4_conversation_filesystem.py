"""Persist filesystem ownership and uncertain writes until confirmed erasure."""

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


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError("Removing filesystem ownership would reopen writes after purge")
