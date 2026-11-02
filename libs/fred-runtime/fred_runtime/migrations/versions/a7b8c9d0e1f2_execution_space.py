"""Name execution space explicitly without converting team ancestry into space."""

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"  # pragma: allowlist secret
down_revision = "f6a7b8c9d0e1"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Steering already stored an admitted space under the old name.
    op.alter_column("runtime_turn_steering", "team_id", new_column_name="space_id")
    # History stored ancestry. Never copy those values into execution scope.
    op.drop_index("ix_session_history_team_id", table_name="session_history")
    op.drop_column("session_history", "team_id")
    op.add_column("session_history", sa.Column("space_id", sa.String(), nullable=True))
    op.create_index("ix_session_history_space_id", "session_history", ["space_id"])


def downgrade() -> None:
    op.drop_index("ix_session_history_space_id", table_name="session_history")
    op.drop_column("session_history", "space_id")
    op.add_column("session_history", sa.Column("team_id", sa.String(), nullable=True))
    op.create_index("ix_session_history_team_id", "session_history", ["team_id"])
    op.alter_column("runtime_turn_steering", "space_id", new_column_name="team_id")
