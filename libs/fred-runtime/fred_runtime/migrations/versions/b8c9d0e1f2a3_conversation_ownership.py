"""Make the Control Plane conversation the root of runtime content.

PostgreSQL is the Weaver lifecycle boundary. SQLite remains a standalone SDK
store and does not implement cross-service conversation deletion. Existing
content must have a valid Control Plane root: invalid IDs and orphans fail this
transaction, without silently deleting or adopting any data.
"""

from alembic import op

revision = "b8c9d0e1f2a3"  # pragma: allowlist secret
down_revision = "a7b8c9d0e1f2"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # Adopt the existing v2_ checkpoint tables, previously self-initialized.
    # Immutable DDL here also initializes a fresh database before pod startup.
    definitions = {
        "v2_langgraph_checkpoint": """
            thread_id varchar NOT NULL, checkpoint_ns varchar NOT NULL,
            checkpoint_id varchar NOT NULL, parent_checkpoint_id varchar,
            checkpoint_type varchar NOT NULL, checkpoint_blob bytea NOT NULL,
            metadata_json jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)""",
        "v2_langgraph_checkpoint_blob": """
            thread_id varchar NOT NULL, checkpoint_ns varchar NOT NULL,
            channel varchar NOT NULL, version varchar NOT NULL,
            value_type varchar NOT NULL, value_blob bytea NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)""",
        "v2_langgraph_checkpoint_write": """
            thread_id varchar NOT NULL, checkpoint_ns varchar NOT NULL,
            checkpoint_id varchar NOT NULL, task_id varchar NOT NULL, idx integer NOT NULL,
            channel varchar NOT NULL, value_type varchar NOT NULL, value_blob bytea NOT NULL,
            task_path varchar NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)""",
        "v2_checkpoint_thread_owner": """
            thread_id varchar PRIMARY KEY, user_id varchar, space_id varchar,
            binding_json jsonb, created_at timestamptz NOT NULL DEFAULT now(),
            last_activity_at timestamptz NOT NULL DEFAULT now()""",
        "v2_checkpoint_hitl_claim": """
            thread_id varchar NOT NULL, checkpoint_ns varchar NOT NULL,
            interrupt_id varchar NOT NULL, claim_token varchar NOT NULL,
            status varchar NOT NULL, claimed_at timestamptz NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, interrupt_id)""",
    }
    for table, definition in definitions.items():
        op.execute(f"CREATE TABLE IF NOT EXISTS {table} ({definition})")
    # Supported existing tables already carry space_id. Do not reinterpret a
    # retired team_id or derive missing ownership from persisted message data.
    op.execute("SELECT space_id FROM v2_checkpoint_thread_owner LIMIT 0")
    op.execute(
        "ALTER TABLE v2_checkpoint_thread_owner ADD COLUMN IF NOT EXISTS binding_json jsonb"
    )
    for table in ("session_history", "runtime_turn_steering", *definitions):
        source = (
            "split_part(thread_id, ':', 1)" if table in definitions else "session_id"
        )
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN conversation_id uuid GENERATED ALWAYS AS ({source}::uuid) STORED NOT NULL"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_conversation_fk FOREIGN KEY (conversation_id) REFERENCES control_plane.session_metadata(session_id) ON DELETE CASCADE"
        )
        op.execute(
            f"CREATE INDEX {table}_conversation_idx ON {table} (conversation_id)"
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS v2_langgraph_checkpoint_thread_created_idx ON v2_langgraph_checkpoint (thread_id, checkpoint_ns, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS v2_checkpoint_thread_owner_user_idx ON v2_checkpoint_thread_owner (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS v2_checkpoint_thread_owner_activity_idx ON v2_checkpoint_thread_owner (last_activity_at)"
    )
    for table in ("v2_langgraph_checkpoint", "v2_langgraph_checkpoint_write"):
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {table}_session_idx ON {table} (split_part(thread_id, ':', 1))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Removing conversation ownership would reopen writes after purge"
    )
