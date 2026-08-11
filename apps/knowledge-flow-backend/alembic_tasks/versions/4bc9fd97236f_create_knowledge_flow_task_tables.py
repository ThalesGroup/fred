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

"""create knowledge-flow task tables (dedicated task database)

First revision of Knowledge Flow's dedicated task database (OPS-04, issue #2170).

Creates `task_run` and `task_event_log` at their current schema in one statement. Knowledge
Flow's main chain never created these tables — it only carried idempotent ALTERs that skip
when the table is absent, because it had always ridden on control-plane's copy in the shared
`fred` database. This chain owns them in a database of Knowledge Flow's own; the main chain
keeps owning tag/metadata/resource in the shared database.

The column set is the accumulated result of control-plane's four task revisions
(`a3b4c5d6e7f8` create, `a7c1e9d2b4f6` execution_id, `f4a5b6c7d8e9` scheduled_for,
`9e5074103b67` acknowledgement columns) plus its `c1d2e3f4a5b6` partial unique index. It was
produced by `alembic revision --autogenerate` against `fred_core.tasks.orm_models`, so it is
schema-identical to the ORM by construction rather than by hand-transcription.

Idempotent: skips a table that already exists. Knowledge Flow's API also runs
`create_all` for these two tables against the same engine at boot, and in Kubernetes the
pods start before the post-install migration Job, so this migration can legitimately find
the tables already present. Without the guard, `op.create_table` raises DuplicateTable and
the migration Job fails the release.

Revision ID: 4bc9fd97236f
Revises:
Create Date: 2026-08-01 17:20:08.725910
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
# codeql[py/unused-global-variable]
revision: str = "4bc9fd97236f"  # pragma: allowlist secret
# codeql[py/unused-global-variable]
down_revision: Union[str, Sequence[str], None] = None
# codeql[py/unused-global-variable]
branch_labels: Union[str, Sequence[str], None] = None
# codeql[py/unused-global-variable]
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")

# Partial unique index enforcing "at most one non-terminal migration-kind task".
# Must be passed for BOTH dialects. Omitting `sqlite_where` does not fail — it silently
# produces a unique index over EVERY row on `kind`, so a second `ingestion` task is then
# rejected on SQLite. Both predicates are therefore spelled out and must stay identical.
# (The equivalent index in the other chains was created with `postgresql_where` only and
# needed a follow-up repair revision; creating it correctly here avoids repeating that.)
_ACTIVE_MIGRATION_PREDICATE = "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Upgrade schema."""
    existing = _existing_tables()

    if "task_event_log" not in existing:
        op.create_table(
            "task_event_log",
            sa.Column("id", sa.BigInteger().with_variant(sa.INTEGER(), "sqlite"), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(length=32), nullable=False),
            sa.Column("progress", sa.Float(), nullable=True),
            sa.Column("step", sa.Text(), nullable=True),
            sa.Column("detail", _JSONB, nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("target", _JSONB, nullable=True),
            sa.Column("owner", sa.String(length=255), nullable=True),
            sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_id", "seq", name="uq_task_event_log_task_seq"),
        )
        with op.batch_alter_table("task_event_log", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_task_event_log_task_id"), ["task_id"], unique=False)

    if "task_run" not in existing:
        op.create_table(
            "task_run",
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("state", sa.String(length=32), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("progress", sa.Float(), nullable=True),
            sa.Column("step", sa.Text(), nullable=True),
            sa.Column("detail", _JSONB, nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("target", _JSONB, nullable=True),
            sa.Column("execution_id", sa.String(length=255), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("team_id", sa.String(length=255), nullable=True),
            sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("acknowledged_by", sa.String(length=36), nullable=True),
            sa.PrimaryKeyConstraint("task_id"),
        )
        with op.batch_alter_table("task_run", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_task_run_created_by"), ["created_by"], unique=False)
            batch_op.create_index(batch_op.f("ix_task_run_kind"), ["kind"], unique=False)
            batch_op.create_index(batch_op.f("ix_task_run_scheduled_for"), ["scheduled_for"], unique=False)
            batch_op.create_index(batch_op.f("ix_task_run_state"), ["state"], unique=False)
            batch_op.create_index("ix_task_run_state_updated", ["state", "updated_at"], unique=False)
            batch_op.create_index(batch_op.f("ix_task_run_team_id"), ["team_id"], unique=False)
            batch_op.create_index(
                "uq_task_run_single_active_migration",
                ["kind"],
                unique=True,
                sqlite_where=sa.text(_ACTIVE_MIGRATION_PREDICATE),
                postgresql_where=sa.text(_ACTIVE_MIGRATION_PREDICATE),
            )


def downgrade() -> None:
    """Downgrade schema."""
    existing = _existing_tables()

    if "task_run" in existing:
        with op.batch_alter_table("task_run", schema=None) as batch_op:
            batch_op.drop_index(
                "uq_task_run_single_active_migration",
                sqlite_where=sa.text(_ACTIVE_MIGRATION_PREDICATE),
                postgresql_where=sa.text(_ACTIVE_MIGRATION_PREDICATE),
            )
            batch_op.drop_index(batch_op.f("ix_task_run_team_id"))
            batch_op.drop_index("ix_task_run_state_updated")
            batch_op.drop_index(batch_op.f("ix_task_run_state"))
            batch_op.drop_index(batch_op.f("ix_task_run_scheduled_for"))
            batch_op.drop_index(batch_op.f("ix_task_run_kind"))
            batch_op.drop_index(batch_op.f("ix_task_run_created_by"))
        op.drop_table("task_run")

    if "task_event_log" in existing:
        with op.batch_alter_table("task_event_log", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_task_event_log_task_id"))
        op.drop_table("task_event_log")
