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

"""Index the bounded provider and outgoing SSE timeline for captured turns.

Revision ID: 8f3b1a40d682
Revises: 5ed9514a7602
"""

import sqlalchemy as sa
from alembic import op

revision = "8f3b1a40d682"  # pragma: allowlist secret
down_revision = "5ed9514a7602"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_trace_turn", sa.Column("sse_segments", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("conversation_trace_turn", "sse_segments")
