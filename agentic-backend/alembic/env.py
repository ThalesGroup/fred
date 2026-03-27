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

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

import fred_core.session.stores.session_models  # noqa: F401

# fred-core ORM models (session table) — included so Alembic manages them here.
from fred_core.models.base import Base as FredCoreBase
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import agentic_backend.core.agents.store.agent_models  # noqa: F401
import agentic_backend.core.feedback.store.feedback_models  # noqa: F401
import agentic_backend.core.mcp.store.mcp_server_models  # noqa: F401
import agentic_backend.core.monitoring.history_models  # noqa: F401
import agentic_backend.core.session.stores.session_attachment_models  # noqa: F401
import agentic_backend.scheduler.store.task_models  # noqa: F401
from agentic_backend.common.config_loader import load_configuration

# Import Base and every ORM model so they all register with Base.metadata
# before autogenerate inspects it.  These imports must stay here (not in
# agentic_backend/models/__init__.py) to avoid circular imports at runtime.
from agentic_backend.models.base import Base
from alembic import context

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# All agentic-backend tables (+ fred-core session table) are captured here.
target_metadata = [Base.metadata, FredCoreBase.metadata]


def _build_url() -> str:
    """Build a database URL from the active configuration.

    Returns an asyncpg URL for PostgreSQL or an aiosqlite URL when the
    configuration specifies ``sqlite_path`` instead of a PostgreSQL host.

    If the ``DATABASE_URL`` environment variable is set it is used directly,
    bypassing configuration file loading (useful for CI).
    """
    url_override = os.environ.get("DATABASE_URL")
    if url_override:
        return url_override
    cfg = load_configuration()
    pg = cfg.storage.postgres
    if pg.sqlite_path:
        path = Path(pg.sqlite_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path}"
    return (
        f"postgresql+asyncpg://{pg.username}:{pg.password}"
        f"@{pg.host}:{pg.port}/{pg.database}"
    )


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout, no live DB needed)."""
    url = _build_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection, *, is_postgres: bool = True) -> None:
    """Execute migrations on a live synchronous connection.

    On PostgreSQL, sets ``lock_timeout`` and ``statement_timeout`` so that
    a migration waiting on a table lock fails fast rather than blocking
    production traffic.  The Kubernetes init container will retry on failure.
    """
    if is_postgres:
        connection.execute(text("SET lock_timeout = '5s'"))
        connection.execute(text("SET statement_timeout = '30s'"))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=not is_postgres,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create a transient async engine and run migrations."""
    url = _build_url()
    postgres = _is_postgres(url)
    connectable = create_async_engine(url, poolclass=pool.NullPool)
    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations, is_postgres=postgres)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online (live-DB) migration mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
