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

"""Index bounded LangChain snapshots for captured turns.

Revision ID: 9a6e2c14b7d0
Revises: 8f3b1a40d682
"""

import sqlalchemy as sa
from alembic import op

revision = "9a6e2c14b7d0"  # pragma: allowlist secret
down_revision = "8f3b1a40d682"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_trace_turn", sa.Column("model_calls", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("conversation_trace_turn", "model_calls")
