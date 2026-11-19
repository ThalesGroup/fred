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


"""Index model HTTP trace attempts and fence ordinary erasure.

Revision ID: 5ed9514a7602
Revises: 07e91c5a42d8
"""

import sqlalchemy as sa
from alembic import op

revision = "5ed9514a7602"
down_revision = "07e91c5a42d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_trace_turn", sa.Column("http_attempts", sa.JSON(), nullable=True)
    )
    op.add_column(
        "conversation_trace_turn",
        sa.Column("http_availability", sa.String(32), nullable=True),
    )
    op.add_column(
        "session_metadata",
        sa.Column(
            "trace_erasing", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("session_metadata", "trace_erasing")
    op.drop_column("conversation_trace_turn", "http_availability")
    op.drop_column("conversation_trace_turn", "http_attempts")
