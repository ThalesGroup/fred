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

"""add task_run partial unique index for single active migration task

Atomic exclusion for concurrent migration-task launches (import / reset /
reset-full, `import_export/api.py`, all created with kind="migration"):
replaces a check-then-act race (list active tasks, then insert) with a real
DB-level guarantee. Every row this partial index covers already has
kind='migration' (the predicate says so), so a unique index on `kind` among
only those rows enforces "at most one non-terminal migration-kind row can
exist at any time", without constraining any other task kind.

Idempotent: skips creating the index if the database already has it (fresh DB
via create_all, or re-run).

Revision ID: c1d2e3f4a5b6
Revises: 8b8e6a86022a
Create Date: 2026-07-27 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "8b8e6a86022a"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_task_run_single_active_migration"
_WHERE_CLAUSE = (
    "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"
)


def _task_run_indexes() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_run" not in inspector.get_table_names():
        return {_INDEX_NAME}  # table absent (fresh create_all) → treat as present
    return {
        ix["name"] for ix in inspector.get_indexes("task_run") if ix["name"] is not None
    }


def upgrade() -> None:
    """Upgrade schema."""
    if _INDEX_NAME not in _task_run_indexes():
        op.create_index(
            _INDEX_NAME,
            "task_run",
            ["kind"],
            unique=True,
            sqlite_where=sa.text(_WHERE_CLAUSE),
            postgresql_where=sa.text(_WHERE_CLAUSE),
        )


def downgrade() -> None:
    """Downgrade schema."""
    if _INDEX_NAME in _task_run_indexes():
        op.drop_index(_INDEX_NAME, table_name="task_run")
