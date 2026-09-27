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

"""add task_run.execution_id (OPS-04 reconciliation)

Revision ID: a7c1e9d2b4f6
Revises: f2b3c4d5e6f7
Create Date: 2026-06-17 13:00:00.000000

Forward migration adding the ``execution_id`` column used to reconcile a still-pending
task against the real status of the Temporal workflow that backs it. The column was
originally (incorrectly) added inline to the already-released create-table revision
``a3b4c5d6e7f8``; editing an applied revision never re-runs, so existing databases
would be missing the column. This is the proper additive migration instead.

Idempotent: skips the ADD COLUMN if a database already has ``execution_id`` (e.g. a dev
DB that applied the now-reverted inline edit, or a fresh DB created via create_all).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c1e9d2b4f6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f2b3c4d5e6f7"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _task_run_has_execution_id() -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_run" not in inspector.get_table_names():
        # Nothing to alter (table created later / managed elsewhere). The model's
        # create_all path will include execution_id on first create.
        return True
    columns = {col["name"] for col in inspector.get_columns("task_run")}
    return "execution_id" in columns


def upgrade() -> None:
    """Upgrade schema."""
    if _task_run_has_execution_id():
        return
    op.add_column(
        "task_run",
        sa.Column("execution_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_run" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("task_run")}
    if "execution_id" in columns:
        op.drop_column("task_run", "execution_id")
