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

"""add task_run acknowledgement columns (OBSERV-02 v3, rev. 3 §2.10)

Persisted "an admin has seen and handled this" acknowledgement, shared by
every admin viewing that task's scope — replaces the client-only
`failuresAcknowledged` Redux flag. Both columns start NULL for every existing
row; NULL/NULL means "not acknowledged", the only state a pre-migration task
can have. Shared fred-core table (`fred_core.tasks.orm_models.TaskRunRow`) —
this backend's own copy, mirrored by an equivalent migration in
knowledge-flow-backend.

Idempotent: skips the ADD COLUMN if the database already has it (fresh DB via
create_all, or re-run).

Revision ID: 9e5074103b67
Revises: a5b6c7d8e9f0
Create Date: 2026-07-25 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9e5074103b67"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a5b6c7d8e9f0"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ("acknowledged_at", "acknowledged_by")


def _task_run_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_run" not in inspector.get_table_names():
        return set(_COLUMNS)  # table absent (fresh create_all) → treat as present
    return {col["name"] for col in inspector.get_columns("task_run")}


def upgrade() -> None:
    """Upgrade schema."""
    existing = _task_run_columns()
    if "acknowledged_at" not in existing:
        op.add_column(
            "task_run",
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "acknowledged_by" not in existing:
        op.add_column(
            "task_run",
            sa.Column("acknowledged_by", sa.String(length=36), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_run" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("task_run")}
    if "acknowledged_by" in existing:
        op.drop_column("task_run", "acknowledged_by")
    if "acknowledged_at" in existing:
        op.drop_column("task_run", "acknowledged_at")
