# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""create cap_ppt_builder_analysis table

The ppt_builder capability's initial schema: one background template analysis
per agent instance. No foreign keys.

Revision ID: p7b1d2a3c4e5
Revises:
Create Date: 2026-10-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p7b1d2a3c4e5"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cap_ppt_builder_analysis",
        sa.Column("agent_instance_id", sa.String(length=128), nullable=False),
        sa.Column("team_id", sa.String(length=128), nullable=False),
        sa.Column("saved_by", sa.String(length=128), nullable=False),
        sa.Column("template_sha256", sa.String(length=64), nullable=False),
        sa.Column("labelling_key", sa.String(length=160), nullable=False),
        sa.Column("analysis_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("template_pptx", sa.LargeBinary(), nullable=False),
        sa.Column("inventory_json", sa.Text(), nullable=True),
        sa.Column("patterns_pdf", sa.LargeBinary(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("agent_instance_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cap_ppt_builder_analysis")
