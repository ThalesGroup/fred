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

"""add task_run.scheduled_for (CTRLP-12 erasure schedule)

When a task is due to act ahead of time — a conversation erasure at retention
expiry — the task carries a ``scheduled_for`` timestamp so a platform/team admin
can see the pipeline of upcoming erasures with their dates, not just what is
running. Set once at creation, stable across state transitions. Nullable +
indexed so the schedule view can order/filter by date. Shared fred-core table.

Idempotent: skips the ADD COLUMN if the database already has it (fresh DB via
create_all, or re-run).

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "e3f4a5b6c7d8"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _task_run_has_scheduled_for() -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_run" not in inspector.get_table_names():
        return True
    columns = {col["name"] for col in inspector.get_columns("task_run")}
    return "scheduled_for" in columns


def upgrade() -> None:
    """Upgrade schema."""
    if _task_run_has_scheduled_for():
        return
    op.add_column(
        "task_run",
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_task_run_scheduled_for"), "task_run", ["scheduled_for"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_run" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("task_run")}
    if "scheduled_for" in columns:
        op.drop_index(op.f("ix_task_run_scheduled_for"), table_name="task_run")
        op.drop_column("task_run", "scheduled_for")
