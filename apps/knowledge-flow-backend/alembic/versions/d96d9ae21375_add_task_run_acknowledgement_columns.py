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

"""add task_run acknowledgement columns (shared fred-core task table)

Keeps Knowledge-Flow's copy of the shared fred-core ``task_run`` table in sync
with the ORM after OBSERV-02 v3 (rev. 3 §2.10) added persisted
acknowledgement. Same rationale as `1c9a54674ebf_add_task_run_scheduled_for.py`
— Knowledge-Flow's ingestion tasks can need attention (a stuck/failed
ingestion) just like control-plane's, so this is not a dead column here.

Idempotent: skips the ADD COLUMN if the database already has it.

Revision ID: d96d9ae21375
Revises: 1c9a54674ebf
Create Date: 2026-07-25 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d96d9ae21375"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "1c9a54674ebf"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _task_run_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_run" not in inspector.get_table_names():
        return {"acknowledged_at", "acknowledged_by"}
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
