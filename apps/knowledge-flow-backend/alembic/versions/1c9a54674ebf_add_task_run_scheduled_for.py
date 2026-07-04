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

"""add task_run.scheduled_for (shared fred-core task table)

Keeps Knowledge-Flow's copy of the shared fred-core ``task_run`` table in sync
with the ORM after CTRLP-12 added ``scheduled_for`` (a due timestamp for tasks
scheduled ahead of time). Knowledge-Flow does not schedule tasks, so the column
is always null here — but the schema must match the shared ORM.

Idempotent: skips the ADD COLUMN if the database already has it.

Revision ID: 1c9a54674ebf
Revises: 0b9a54674eba
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "1c9a54674ebf"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "0b9a54674eba"  # pragma: allowlist secret
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
    op.create_index(op.f("ix_task_run_scheduled_for"), "task_run", ["scheduled_for"], unique=False)


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
