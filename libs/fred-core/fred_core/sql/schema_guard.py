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

"""
Startup-time schema guard — fail fast when a deployment skipped its migrations.

Why this module exists:
- table DDL is owned by Alembic only (issue #2290); no store creates its own
  tables at runtime any more, so a deployment that never ran its migration job
  has no schema at all
- without a boot-time check that failure surfaces mid-request as
  ``UndefinedTableError`` — hours after a green health check — which is the
  failure class audited in issue #2137

How to use it:
- call ``require_tables`` once, from the startup path that builds the engine
  (never from a read/write path — it opens a connection and inspects the
  catalog, which is startup-only work)

Example:
    await require_tables(
        engine,
        ["session_history"],
        component="fred-runtime",
        migrate_command="python -m fred_runtime migrate",
        version_table="alembic_version_runtime",
    )
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import Column, MetaData, String, Table, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger(__name__)

MIGRATIONS_DOC = "docs/swift/ops/DATABASE_MIGRATIONS.md"


class SchemaNotMigratedError(RuntimeError):
    """
    Raised at startup when a table the component needs does not exist.

    Why a dedicated type:
    - callers (and tests) must be able to tell "migrations were never applied"
      apart from a generic connectivity or configuration failure
    """


def _table_names(sync_conn: Connection) -> set[str]:
    return set(sa_inspect(sync_conn).get_table_names())


async def require_tables(
    engine: AsyncEngine,
    tables: Sequence[str],
    *,
    component: str,
    migrate_command: str,
    version_table: str | None = None,
) -> None:
    """
    Verify that *tables* exist, raising ``SchemaNotMigratedError`` if not.

    Args:
        engine: an already-connectable engine (call after the connectivity ping).
        tables: table names the component cannot serve traffic without.
        component: name used in the log/error message, e.g. ``"fred-runtime"``.
        migrate_command: the exact command an operator must run to fix it.
        version_table: the component's Alembic version table. When given and the
            tables exist but the version table is missing or empty, the database
            is schema-correct but *unmanaged* — a warning naming the recovery
            path is logged (this is the pre-#2290 state, where a store created
            its own tables and Alembic was never stamped).

    Raises:
        SchemaNotMigratedError: at least one required table is missing.
    """
    async with engine.connect() as conn:
        existing = await conn.run_sync(_table_names)
        missing = [name for name in tables if name not in existing]
        if missing:
            message = (
                f"[SCHEMA] {component}: required table(s) missing — "
                f"{', '.join(missing)}. The database has not been migrated "
                f"(table DDL is owned by Alembic only). Run: {migrate_command} "
                f"— see {MIGRATIONS_DOC}."
            )
            logger.critical(message)
            raise SchemaNotMigratedError(message)

        if version_table is None:
            return

        stamped = version_table in existing and await _has_version_row(
            conn, version_table
        )

    if not stamped:
        logger.warning(
            "[SCHEMA] %s: tables exist but '%s' is not stamped — this database "
            "is not managed by Alembic and `%s` will fail on the first "
            "revision. Stamp it before the next upgrade — see %s.",
            component,
            version_table,
            migrate_command,
            MIGRATIONS_DOC,
        )


async def _has_version_row(conn: AsyncConnection, version_table: str) -> bool:
    """
    Return True iff *version_table* holds a revision (i.e. was stamped).

    Built through SQLAlchemy's ``Table`` rather than an f-string so the table
    name is quoted by the dialect instead of interpolated into raw SQL.
    """
    table = Table(version_table, MetaData(), Column("version_num", String))
    result = await conn.execute(select(func.count()).select_from(table))
    return (result.scalar() or 0) > 0
