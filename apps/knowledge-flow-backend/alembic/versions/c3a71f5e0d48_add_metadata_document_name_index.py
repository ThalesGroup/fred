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

"""index the document name so a folder can be asked whether it holds it

Every imported file asks "does this folder already hold a document with this
name?". The name lives inside the `doc` JSON, so without an index on it that
question costs a scan of the whole table, once per file.

Combined with the existing GIN index on `tag_ids`, this lets the question be
answered by index alone.

Revision ID: c3a71f5e0d48
Revises: a92e13f80c64
Create Date: 2026-09-29 19:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a71f5e0d48"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "a92e13f80c64"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "idx_metadata_document_name"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        INDEX_NAME,
        "metadata",
        [sa.text("(doc -> 'identity' ->> 'document_name')")],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(INDEX_NAME, table_name="metadata")
