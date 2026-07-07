"""add agent_instance column comments

Adds column-level comments to agent_instance.tuning_json and
agent_instance.prompt_refs_json to match the ORM model definition.

Revision ID: a2b3c4d5e6f7
Revises: 655ea83030fa
Create Date: 2026-06-03 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "655ea83030fa"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("agent_instance") as batch_op:
        batch_op.alter_column(
            "tuning_json",
            existing_type=sa.Text(),
            existing_nullable=True,
            comment="JSON-serialized ManagedAgentTuning payload",
        )
        batch_op.alter_column(
            "prompt_refs_json",
            existing_type=sa.Text(),
            existing_nullable=True,
            comment="JSON-serialized prompt_refs: {field_key: {prompt_id, version}}",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_instance") as batch_op:
        batch_op.alter_column(
            "prompt_refs_json",
            existing_type=sa.Text(),
            existing_nullable=True,
            comment=None,
        )
        batch_op.alter_column(
            "tuning_json",
            existing_type=sa.Text(),
            existing_nullable=True,
            comment=None,
        )
