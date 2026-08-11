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

"""repair task_run single-active-migration index (missing SQLite predicate)

`c1d2e3f4a5b6` created `uq_task_run_single_active_migration` passing only
`postgresql_where`. SQLAlchemy silently drops dialect-prefixed kwargs on other
dialects, so on SQLite the predicate vanished and the index landed as an
unconditional `UNIQUE (kind)` — "at most one task_run row per kind, ever"
instead of "at most one non-terminal kind='migration' row". Consequences on an
affected DB: the second task of any already-present kind fails to insert, and
the second migration task is refused permanently rather than once the first
reaches a terminal state (its IntegrityError still names this index, so
`import_export/api.py::_is_concurrent_migration_violation` mistranslates it
into a misleading 409 "another migration is already running").

Postgres was never affected — the predicate applies there.

Drop-then-recreate unconditionally rather than reusing the name-presence guard
of `c1d2e3f4a5b6`: the broken index carries the *same name* as the correct one,
so a presence check cannot tell them apart and would skip the repair on exactly
the databases that need it. On Postgres this replaces a correct index with an
identical one; the constraint is briefly absent mid-migration, which is safe
under the deploy-time migration lock.

Recreating fails with an IntegrityError only if the table genuinely holds two
non-terminal kind='migration' rows — real corruption that must surface rather
than be papered over.

Revision ID: a9b0c1d2e3f4
Revises: f3790013f637
Create Date: 2026-07-29 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f3790013f637"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_task_run_single_active_migration"
_WHERE_CLAUSE = (
    "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"
)


def _task_run_indexes() -> set[str]:
    # No missing-table branch here: both callers return before reaching this helper when
    # `task_run` is absent. upgrade() must return *before* op.create_index, which a helper
    # returning a set cannot express, so the check belongs in the callers.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {
        ix["name"] for ix in inspector.get_indexes("task_run") if ix["name"] is not None
    }


def upgrade() -> None:
    """Upgrade schema."""
    if "task_run" not in sa.inspect(op.get_bind()).get_table_names():
        return

    if _INDEX_NAME in _task_run_indexes():
        op.drop_index(_INDEX_NAME, table_name="task_run")

    op.create_index(
        _INDEX_NAME,
        "task_run",
        ["kind"],
        unique=True,
        sqlite_where=sa.text(_WHERE_CLAUSE),
        postgresql_where=sa.text(_WHERE_CLAUSE),
    )


def downgrade() -> None:
    """Downgrade schema: drop the index this revision created.

    Deliberately does NOT reinstate the broken unconditional `UNIQUE (kind)` the previous
    revision left on SQLite — recreating it would fail on any table already holding two rows
    of the same kind, which is precisely the state this repair exists to make reachable.

    Dropping is still the right revert: it leaves the database in a state the previous
    revision's own downgrade can complete, and an empty body did not. An empty downgrade
    stamped the earlier revision while leaving the partial index in place, so the schema
    matched neither revision and a later `alembic check` or re-upgrade saw state nothing
    expected.
    """
    if "task_run" not in sa.inspect(op.get_bind()).get_table_names():
        return

    if _INDEX_NAME in _task_run_indexes():
        op.drop_index(_INDEX_NAME, table_name="task_run")
