"""Bind deck plans to their Control Plane conversation root."""

from alembic import op

revision = "r9e4a5b6c7d8"  # pragma: allowlist secret
down_revision = "r9d3f4a5b6c7"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE cap_ppt_builder_deck_plan ADD COLUMN conversation_id uuid GENERATED ALWAYS AS (session_id::uuid) STORED NOT NULL"
    )
    op.execute(
        "ALTER TABLE cap_ppt_builder_deck_plan ADD CONSTRAINT cap_ppt_builder_deck_plan_conversation_fk FOREIGN KEY (conversation_id) REFERENCES control_plane.session_metadata(session_id) ON DELETE CASCADE"
    )
    op.execute(
        "CREATE INDEX cap_ppt_builder_deck_plan_conversation_idx ON cap_ppt_builder_deck_plan (conversation_id)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Removing conversation ownership would reopen writes after purge"
    )
