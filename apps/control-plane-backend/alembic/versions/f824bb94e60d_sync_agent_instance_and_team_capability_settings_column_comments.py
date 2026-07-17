"""sync agent_instance and team_capability_settings column comments

Revision ID: f824bb94e60d
Revises: 37f6de4ac781
Create Date: 2026-07-17 15:01:46.891662

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f824bb94e60d"
down_revision: Union[str, Sequence[str], None] = "37f6de4ac781"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("agent_instance") as batch_op:
        batch_op.alter_column(
            "suspension_reason",
            existing_type=sa.VARCHAR(length=64),
            existing_nullable=True,
            comment="Platform-forced suspension reason (#1975, RFC §3.9). NULL = not suspended; else one of capability_unavailable / capability_access_revoked / capability_config_invalid. Distinct from the editor's `enabled` toggle.",
        )
    with op.batch_alter_table("team_capability_settings") as batch_op:
        batch_op.alter_column(
            "settings_json",
            existing_type=sa.TEXT(),
            existing_nullable=False,
            existing_server_default=sa.text("'{}'::text"),
            comment="JSON-serialized per-team enablement settings validated against the capability's TeamSettingsModel / team_settings_fields.",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("team_capability_settings") as batch_op:
        batch_op.alter_column(
            "settings_json",
            existing_type=sa.TEXT(),
            existing_nullable=False,
            existing_server_default=sa.text("'{}'::text"),
            comment=None,
        )
    with op.batch_alter_table("agent_instance") as batch_op:
        batch_op.alter_column(
            "suspension_reason",
            existing_type=sa.VARCHAR(length=64),
            existing_nullable=True,
            comment=None,
        )
