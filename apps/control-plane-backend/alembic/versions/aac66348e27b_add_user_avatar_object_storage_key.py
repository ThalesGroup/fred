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
"""Add the user profile picture object key.

Nullable: everyone starts without a picture, so there is no backfill.

Revision ID: aac66348e27b
Revises: ba2c3c7fd0c1
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aac66348e27b"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "ba2c3c7fd0c1"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_object_storage_key", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_object_storage_key")
