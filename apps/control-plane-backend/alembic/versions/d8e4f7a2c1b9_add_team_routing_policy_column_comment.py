"""add missing column comment on team_routing_policy.operation_rules_json

``TeamRoutingPolicy.operation_rules_json`` declares a ``comment=`` that its
creating migration (bc06439e4cf9, #2123) never emitted, so the live column had
no COMMENT while the model said it did. The mismatch stayed invisible because
``routing_policy_models`` was not imported in ``alembic/env.py`` — the table was
absent from the autogenerate metadata, so nothing compared the two. REASON-01
added that import (the table has a migration; it belongs under drift detection),
which surfaced the drift as a pending ``modify_comment`` in ``alembic check``.

Pure metadata change: COMMENT ON COLUMN touches no rows and takes no heavy lock.

Revision ID: d8e4f7a2c1b9
Revises: a7c3d91f2b40
Create Date: 2026-07-31 17:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8e4f7a2c1b9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a7c3d91f2b40"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMMENT = "JSON-serialized list of TeamOperationRouteRule (fred_sdk.contracts.context)."


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "team_routing_policy",
        "operation_rules_json",
        existing_type=sa.Text(),
        existing_nullable=False,
        existing_server_default=sa.text("'[]'"),
        comment=COMMENT,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "team_routing_policy",
        "operation_rules_json",
        existing_type=sa.Text(),
        existing_nullable=False,
        existing_server_default=sa.text("'[]'"),
        comment=None,
    )
