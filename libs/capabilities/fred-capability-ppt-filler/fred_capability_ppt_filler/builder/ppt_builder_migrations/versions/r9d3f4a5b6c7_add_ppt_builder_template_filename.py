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

"""add template_filename to cap_ppt_builder_analysis

The uploaded file's name, shown for the platform default template. Nullable:
existing rows keep none.

Revision ID: r9d3f4a5b6c7
Revises: q8c2e3b4d5f6
Create Date: 2026-10-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r9d3f4a5b6c7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "q8c2e3b4d5f6"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cap_ppt_builder_analysis",
        sa.Column("template_filename", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("cap_ppt_builder_analysis") as batch:
        batch.drop_column("template_filename")
