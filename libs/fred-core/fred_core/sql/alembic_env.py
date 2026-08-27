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
from collections.abc import Callable, Collection, Sequence
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


def build_ownership_filters(
    owned_tables: frozenset[str],
) -> tuple[Callable[..., bool], Callable[..., bool]]:
    """Return ``(include_name, include_object)`` scoping Alembic to *owned_tables*.

    Both filters are needed, and they cover different directions (#2314):

    - ``include_name`` filters names reflected from the **database**, so
      autogenerate and ``alembic check`` ignore (never DROP, never report
      drift for) tables that belong to other backends sharing the database.
    - ``include_object`` filters objects on the **metadata** side, so
      autogenerate never proposes CREATE for a foreign table that happens to
      be registered on a shared declarative base but is absent from the
      database. With ``include_name`` alone that exact leak occurs: the
      shared-base table is not in the DB, is present in ``target_metadata``,
      and comes out of autogenerate as a ``create_table`` — a second writer
      for a table another backend's tree owns.
    """

    def include_name(name: str | None, type_: str, _parent_names: object) -> bool:
        if type_ == "table":
            return name in owned_tables
        return True

    def include_object(
        obj: object, name: str | None, type_: str, _reflected: bool, _compare_to: object
    ) -> bool:
        if type_ == "table":
            return name in owned_tables
        return True

    return include_name, include_object


def autogenerate_diffs(
    connection: Connection,
    target_metadata: MetaData | Sequence[MetaData],
    owned_tables: Collection[str],
) -> list[object]:
    """Run an autogenerate comparison scoped by ``build_ownership_filters``.

    Tests and CI checks only (same scoping rule as
    ``fred_core.history.create_history_schema``): this is how each backend's
    ownership tests assert the #2314 acceptance shape — "a database holding
    exactly the owned tables yields an empty migration" — without every app
    duplicating the MigrationContext/compare plumbing. Production migrations
    go through ``make_alembic_env`` alone.

    Merges *target_metadata* into one ``MetaData`` because Alembic accepts a
    sequence at runtime but ``compare_metadata``'s signature is typed for a
    single object.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    metas = (
        target_metadata if isinstance(target_metadata, Sequence) else [target_metadata]
    )
    union = MetaData()
    for meta in metas:
        for table in meta.tables.values():
            table.to_metadata(union)

    include_name, include_object = build_ownership_filters(frozenset(owned_tables))
    context = MigrationContext.configure(
        connection,
        opts={
            "target_metadata": union,
            "include_name": include_name,
            "include_object": include_object,
        },
    )
    return compare_metadata(context, union)


def make_alembic_env(
    target_metadata: MetaData | Sequence[MetaData],
    get_postgres_config: Callable[[], PostgresStoreConfig],
    version_table: str = "alembic_version",
    owned_tables: Collection[str] | None = None,
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
        owned_tables: Table names this backend's migration tree owns. REQUIRED
            whenever *target_metadata* includes a shared declarative base
            (fred-core's ``CoreBase``): deriving ownership from the metadata
            would claim every table on the shared base, including those other
            backends migrate — which is how control-plane's autogenerate once
            proposed creating knowledge-flow's ``tag``/``metadata`` (#2314).
            When ``None`` (the default, for backends whose metadata is fully
            their own), ownership is derived from *target_metadata* as before.
            Alembic-only tables with no ORM model (e.g. knowledge-flow's
            ``sched_workflow_tasks``) must stay OUT of the set: they are not
            in the metadata, so owning them would make autogenerate propose
            their DROP.
    """
    # Import here to keep alembic an optional dependency of fred_core
    # (only needed in migration contexts, not at application runtime).
    from alembic import context

    # The set of table names owned by this backend: declared by the caller, or
    # derived from the metadata when the metadata contains nothing shared.
    if owned_tables is not None:
        _owned_tables: frozenset[str] = frozenset(owned_tables) | {version_table}
    else:
        metas = (
            target_metadata
            if isinstance(target_metadata, Sequence)
            else [target_metadata]
        )
        _owned_tables = frozenset(t for m in metas for t in m.tables) | {version_table}

    _include_name, _include_object = build_ownership_filters(_owned_tables)

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
            include_object=_include_object,
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
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()

    def run_migrations_online() -> None:
        """Run migrations against a live database."""
        asyncio.run(_run_async_migrations())

    return run_migrations_offline, run_migrations_online
