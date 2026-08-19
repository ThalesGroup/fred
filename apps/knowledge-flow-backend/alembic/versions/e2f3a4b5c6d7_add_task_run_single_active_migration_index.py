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

"""add task_run partial unique index (shared fred-core task table)

Keeps Knowledge-Flow's copy of the shared fred-core ``task_run`` table in sync
with the ORM after control-plane-backend added a partial unique index
enforcing "at most one active kind='migration' task" (that kind is never
created here — Knowledge-Flow's own task kinds, e.g. "ingestion", are
unaffected by the predicate — this migration exists only to keep the shared
table's schema identical across both backends' own Postgres databases). Same
rationale as `d96d9ae21375_add_task_run_acknowledgement_columns.py`.

Idempotent: skips creating the index if the database already has it.

Revision ID: e2f3a4b5c6d7
Revises: d96d9ae21375
Create Date: 2026-07-27 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3a4b5c6d7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d96d9ae21375"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_task_run_single_active_migration"
_WHERE_CLAUSE = "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"


def _task_run_exists() -> bool:
    return "task_run" in sa.inspect(op.get_bind()).get_table_names()


def _task_run_indexes() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _task_run_exists():
        return {_INDEX_NAME}
    return {ix["name"] for ix in inspector.get_indexes("task_run") if ix["name"] is not None}


def upgrade() -> None:
    """Upgrade schema."""
    if _INDEX_NAME not in _task_run_indexes():
        op.create_index(
            _INDEX_NAME,
            "task_run",
            ["kind"],
            unique=True,
            postgresql_where=sa.text(_WHERE_CLAUSE),
        )


def downgrade() -> None:
    """Downgrade schema.

    `_task_run_indexes`'s "table absent → treat as present" sentinel is written
    for `upgrade` (skip the create). Downgrade needs the opposite reading: since
    #2170 split the task tables per backend, the shared `task_run` is genuinely
    gone by the time this unwinds, and DROP INDEX would fail on a missing table.
    """
    if _task_run_exists() and _INDEX_NAME in _task_run_indexes():
        op.drop_index(_INDEX_NAME, table_name="task_run")
