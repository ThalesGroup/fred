"""add agent_instance.suspension_reason (capability suspension lifecycle)

#1975 (CAPAB-01, RFC AGENT-CAPABILITY §3.9). A managed agent instance whose
capability slice is config-invalid, unavailable, or access-revoked enters a
platform-forced ``suspended`` state — distinct from the editor's ``enabled``
toggle — carrying a typed reason. The reason is stored as a nullable string
column on ``agent_instance``: NULL means "not suspended"; a non-NULL value is
one of ``capability_unavailable`` / ``capability_access_revoked`` /
``capability_config_invalid`` (``SuspensionReason``).

Revision ID: a6b7c8d9e0f1
Revises: f5b6c7d8e9a0
Create Date: 2026-07-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f5b6c7d8e9a0"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_instance",
        sa.Column("suspension_reason", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_instance", "suspension_reason")
