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

`e2f3a4b5c6d7` created `uq_task_run_single_active_migration` passing only
`postgresql_where`. SQLAlchemy silently drops dialect-prefixed kwargs on other
dialects, so on SQLite the predicate vanished and the index landed as an
unconditional `UNIQUE (kind)` — "at most one task_run row per kind, ever"
instead of "at most one non-terminal kind='migration' row". Knowledge-Flow's
own kinds (e.g. "ingestion") are unaffected by the *intended* predicate but
very much affected by the degraded one: a second ingestion task cannot be
inserted at all.

On a DB that already held several same-kind rows the upgrade aborted outright
(`UNIQUE constraint failed: task_run.kind`), leaving the revision unapplied;
on an empty or single-kind DB it silently succeeded with the wrong index. This
migration handles the second case — the first is fixed by the corrected
`e2f3a4b5c6d7`, which such a database has yet to run.

Postgres was never affected — the predicate applies there — so `upgrade()` runs
on SQLite only. Since OPS-04 (#2170) this chain no longer owns `task_run`, and
on a deployment still sharing the `fred` database its DDL would land on
control-plane's live table for a repair Postgres never needed.

Drop-then-recreate unconditionally rather than reusing the name-presence guard
of `e2f3a4b5c6d7`: the broken index carries the *same name* as the correct one,
so a presence check cannot tell them apart and would skip the repair on exactly
the databases that need it.

Revision ID: f7a8b9c0d1e2
Revises: e2f3a4b5c6d7
Create Date: 2026-07-29 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f7a8b9c0d1e2"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_task_run_single_active_migration"
_WHERE_CLAUSE = "kind = 'migration' AND state NOT IN ('succeeded', 'failed', 'cancelled')"


def _task_run_indexes() -> set[str]:
    # No missing-table branch here: both callers return before reaching this helper when
    # `task_run` is absent. Same reasoning as the downgrade() comment in the sibling
    # `e2f3a4b5c6d7` — upgrade() must return *before* op.create_index, which a helper
    # returning a set cannot express, so the check belongs in the callers.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {ix["name"] for ix in inspector.get_indexes("task_run") if ix["name"] is not None}


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite-only: Postgres never had the defect (the predicate applies there), and since
    # OPS-04 (#2170) this chain no longer owns `task_run` — on a Postgres deployment still
    # sharing the `fred` database the DROP INDEX below would take ACCESS EXCLUSIVE on
    # control-plane's live table, blocking behind any open transaction until the deploy
    # Job's lock_timeout cancels it.
    if op.get_bind().dialect.name != "sqlite":
        return

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

    Gated on SQLite for the same reason as upgrade(), and it must stay symmetric with it:
    on Postgres upgrade() is a no-op, so a downgrade that still dropped the index would
    revert something this revision never did. Worse, the index it would drop is the one
    `e2f3a4b5c6d7` owns, and re-upgrading cannot restore it — upgrade() returns early
    here — so a `make db-downgrade` + re-upgrade round trip would destroy the
    single-active-migration constraint permanently, on a shared `fred` database where
    that constraint is control-plane's.
    """
    if op.get_bind().dialect.name != "sqlite":
        return

    if "task_run" not in sa.inspect(op.get_bind()).get_table_names():
        return

    if _INDEX_NAME in _task_run_indexes():
        op.drop_index(_INDEX_NAME, table_name="task_run")
