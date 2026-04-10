"""update_data_session_migrate_team_scoping

Revision ID: e89ab9e7ca5f
Revises: 5c9bc83efbfb
Create Date: 2026-04-01 16:03:41.693141

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e89ab9e7ca5f"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "5c9bc83efbfb"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
               UPDATE session
               SET team_id = COALESCE(
                       (agent.payload_json ->>'team_id'),
                       'personal'
                             ) FROM agent
               WHERE session.agent_id = agent.id;
               """)


def downgrade() -> None:
    """Downgrade schema."""
