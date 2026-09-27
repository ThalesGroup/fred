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

"""add category column to prompt table

Stores the functional category (doc-assist, summary, extraction…) for each
prompt-library record. Nullable so existing rows keep working until they are
re-saved with a category.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c5d6e7f8a9b0"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add category column to the prompt table."""
    op.add_column(
        "prompt",
        sa.Column("category", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Remove category column from the prompt table."""
    op.drop_column("prompt", "category")
