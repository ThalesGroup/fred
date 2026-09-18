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

"""address a document by the source key its caller chose

A system that synchronizes a source names each document itself, and writing the
same name twice must update one document rather than add another. The pair is
unique so the database, not the caller, holds that rule.

Both columns stay NULL for every document uploaded by a person: NULLs never
collide, so nothing that exists today is affected by the unique index.

Revision ID: f7a1c4d20b93
Revises: c8f2d5b13ea6
Create Date: 2026-09-13 10:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a1c4d20b93"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c8f2d5b13ea6"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("metadata", sa.Column("source_library_id", sa.String(), nullable=True))
    op.add_column("metadata", sa.Column("source_key", sa.String(), nullable=True))
    op.create_index(
        "uq_metadata_source_library_key",
        "metadata",
        ["source_library_id", "source_key"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_metadata_source_library_key", table_name="metadata")
    op.drop_column("metadata", "source_key")
    op.drop_column("metadata", "source_library_id")
