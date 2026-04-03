# Copyright Thales 2025
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
Shared Alembic env.py helpers used by every backend that runs migrations.

Typical usage in ``alembic/env.py``::

    import my_backend.models.foo  # noqa: F401  — registers tables with Base
    from my_backend.common.config_loader import load_configuration
    from my_backend.models.base import Base
    from alembic import context
    from fred_core.sql import make_alembic_env

    run_migrations_offline, run_migrations_online = make_alembic_env(
        target_metadata=Base.metadata,
        get_postgres_config=lambda: load_configuration().storage.postgres,
    )

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from sqlalchemy import MetaData, pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from fred_core.common.structures import PostgresStoreConfig


def _build_url(get_postgres_config: Callable[[], PostgresStoreConfig]) -> str:
    """Return an async-driver DB URL.

    Checks ``DATABASE_URL`` env var first (useful in CI to avoid config files).
    Falls back to building the URL from the ``PostgresStoreConfig`` returned by
    *get_postgres_config*.
    """
    url_override = os.environ.get("DATABASE_URL")
    if url_override:
        return url_override

    pg = get_postgres_config()
    if pg.sqlite_path:
        path = Path(pg.sqlite_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path}"

    return pg.async_dsn()


def make_alembic_env(
    target_metadata: MetaData | Sequence[MetaData],
    get_postgres_config: Callable[[], PostgresStoreConfig],
    version_table: str = "alembic_version",
) -> tuple[Callable[[], None], Callable[[], None]]:
    """Return ``(run_migrations_offline, run_migrations_online)`` for *env.py*.

    Args:
        target_metadata: The SQLAlchemy ``MetaData`` (or list of ``MetaData``)
            that Alembic should compare against when generating migrations.
        get_postgres_config: Zero-argument callable that returns the backend's
            ``PostgresStoreConfig``.  Called lazily so config loading only
            happens when migrations actually run.
        version_table: Name of the Alembic version table.  Set a unique name
            per backend when multiple backends share the same database so their
            migration histories don't collide.
    """
    # Import here to keep alembic an optional dependency of fred_core
    # (only needed in migration contexts, not at application runtime).
    from alembic import context

    # Build the set of table names owned by this backend so that autogenerate
    # and `alembic check` ignore tables that belong to other backends sharing
    # the same database.
    metas = (
        target_metadata if isinstance(target_metadata, Sequence) else [target_metadata]
    )
    _owned_tables: frozenset[str] = frozenset(t for m in metas for t in m.tables) | {
        version_table
    }

    def _include_name(name: str | None, type_: str, _parent_names: object) -> bool:
        if type_ == "table":
            return name in _owned_tables
        return True

    def _is_postgres(url: str) -> bool:
        return url.startswith("postgresql")

    def _do_run_migrations(connection: Connection, *, is_postgres: bool = True) -> None:
        if is_postgres:
            connection.execute(text("SET lock_timeout = '5s'"))
            connection.execute(text("SET statement_timeout = '30s'"))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=not is_postgres,
            version_table=version_table,
            include_name=_include_name,
        )
        with context.begin_transaction():
            context.run_migrations()

    async def _run_async_migrations() -> None:
        url = _build_url(get_postgres_config)
        is_postgres = _is_postgres(url)
        connectable = create_async_engine(url, poolclass=pool.NullPool)
        async with connectable.begin() as connection:
            await connection.run_sync(_do_run_migrations, is_postgres=is_postgres)
        await connectable.dispose()

    def run_migrations_offline() -> None:
        """Emit SQL to stdout without a live DB (used with ``--sql`` flag)."""
        url = _build_url(get_postgres_config)
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            version_table=version_table,
            include_name=_include_name,
        )
        with context.begin_transaction():
            context.run_migrations()

    def run_migrations_online() -> None:
        """Run migrations against a live database."""
        asyncio.run(_run_async_migrations())

    return run_migrations_offline, run_migrations_online
