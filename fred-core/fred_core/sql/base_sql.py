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

import contextlib
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from sqlalchemy import JSON, Table, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)
from sqlalchemy.sql import ClauseElement

from fred_core.common.structures import PostgresStoreConfig

logger = logging.getLogger(__name__)


def json_for_engine(engine: Engine | AsyncEngine):
    """
    Return a JSON-capable column type appropriate for the given engine.

    - Postgres: JSONB
    - Others (e.g., SQLite): JSON (maps to JSON1 where available)
    """
    dialect = engine.dialect.name if engine is not None else ""
    return JSONB if dialect == "postgresql" else JSON


def create_engine_from_config(config: PostgresStoreConfig) -> Engine:
    """
    Build a SQLAlchemy Engine for Postgres from a PostgresStoreConfig.
    Adds explicit logging and validation of required fields to ease debugging.
    """
    missing = [
        name
        for name in ("host", "database", "username")
        if not getattr(config, name, None)
    ]
    if missing:
        raise ValueError(
            f"[SQL][Engine] Missing required Postgres config fields: {', '.join(missing)}"
        )

    connect_args: dict[str, Any] = (
        dict(config.connect_args) if config.connect_args else {}
    )

    def _mask_dsn(dsn: str) -> str:
        return re.sub(r":([^:@]+)@", ":***@", dsn)

    masked_dsn = _mask_dsn(config.dsn())
    effective_pool_size = config.pool_size or 5
    effective_max_overflow = (
        config.max_overflow if config.max_overflow is not None else 10
    )
    effective_pool_timeout = (
        config.pool_timeout if config.pool_timeout is not None else 30
    )
    # SQLAlchemy expects an int; None would later be compared with ints and crash
    effective_pool_recycle = (
        config.pool_recycle if config.pool_recycle is not None else -1
    )
    effective_pool_pre_ping = (
        config.pool_pre_ping if config.pool_pre_ping is not None else False
    )
    logger.warning(
        "[SQL][Engine] Creating engine (single PG config assumed): "
        "dsn=%s host=%s port=%s db=%s user=%s password_set=%s "
        "echo=%s pool_size=%s max_overflow=%s pool_timeout=%s pool_recycle=%s pool_pre_ping=%s "
        "connect_args=%s raw_config=%s",
        masked_dsn,
        config.host,
        config.port,
        config.database,
        config.username,
        bool(config.password),
        config.echo,
        effective_pool_size,
        effective_max_overflow,
        effective_pool_timeout,
        effective_pool_recycle,
        effective_pool_pre_ping,
        connect_args,
        {
            "host": config.host,
            "port": config.port,
            "database": config.database,
            "username": config.username,
            "password_set": bool(config.password),
            "echo": config.echo,
            "pool_size": config.pool_size,
            "max_overflow": config.max_overflow,
            "pool_timeout": config.pool_timeout,
            "pool_recycle": config.pool_recycle,
            "pool_pre_ping": config.pool_pre_ping,
            "connect_args": connect_args,
        },
    )

    try:
        engine = create_engine(
            config.dsn(),
            echo=config.echo,
            pool_size=effective_pool_size,
            max_overflow=effective_max_overflow,
            pool_timeout=effective_pool_timeout,
            pool_recycle=effective_pool_recycle,
            pool_pre_ping=effective_pool_pre_ping,
            connect_args=connect_args,
        )
        logger.warning(
            "[SQL][Engine] Engine created successfully with pool_size=%s max_overflow=%s "
            "pool_timeout=%s pool_recycle=%s pool_pre_ping=%s connect_args=%s",
            effective_pool_size,
            effective_max_overflow,
            effective_pool_timeout,
            effective_pool_recycle,
            effective_pool_pre_ping,
            connect_args,
        )
        return engine
    except Exception as exc:
        logger.exception("[SQL][Engine] Failed to create engine: %s", exc)
        logger.error(
            "[SQL][Engine] Debug details: url=%s host=%s port=%s db=%s user=%s pwd_set=%s "
            "echo=%s pool_size=%s max_overflow=%s pool_timeout=%s pool_recycle=%s pool_pre_ping=%s connect_args=%s",
            masked_dsn,
            config.host,
            config.port,
            config.database,
            config.username,
            bool(config.password),
            config.echo,
            config.pool_size,
            config.max_overflow,
            config.pool_timeout,
            config.pool_recycle,
            config.pool_pre_ping,
            connect_args,
        )
        raise


def create_async_engine_from_config(config: PostgresStoreConfig):
    """
    Build an async SQLAlchemy Engine (asyncpg) from PostgresStoreConfig.
    Mirrors the sync factory but returns an AsyncEngine to avoid thread-pool hops.
    """
    # Lightweight laptop-only escape hatch: if sqlite_path is set, prefer aiosqlite
    # over real Postgres. This keeps existing Postgres-backed stores reusable without
    # requiring a running database container.
    if config.sqlite_path is not None:
        sqlite_path_obj = Path(config.sqlite_path).expanduser()
        sqlite_path_obj.parent.mkdir(parents=True, exist_ok=True)
        sqlite_path = str(sqlite_path_obj)
        async_dsn = f"sqlite+aiosqlite:///{sqlite_path}"
        logger.info(
            "[SQL][AsyncEngine] sqlite_path provided; using SQLite fallback at %s",
            sqlite_path,
        )
        try:
            engine = create_async_engine(
                async_dsn,
                echo=config.echo,
                connect_args={"check_same_thread": False},
            )
            logger.info(
                "[SQL][AsyncEngine] SQLite async engine created path=%s", sqlite_path
            )
            return engine
        except Exception as exc:
            logger.exception(
                "[SQL][AsyncEngine] Failed to create SQLite engine at %s: %s",
                sqlite_path,
                exc,
            )
            raise

    if not os.getenv("FRED_POSTGRES_PASSWORD"):
        logger.error(
            "[TASKS][STORE] Missing FRED_POSTGRES_PASSWORD environment variable (required for Postgres task store)"
        )
        raise RuntimeError("FRED_POSTGRES_PASSWORD is required for Postgres task store")
    missing = [
        name
        for name in ("host", "database", "username")
        if not getattr(config, name, None)
    ]
    if missing:
        raise ValueError(
            f"[SQL][AsyncEngine] Missing required Postgres config fields: {', '.join(missing)}"
        )

    connect_args: dict[str, Any] = (
        dict(config.connect_args) if config.connect_args else {}
    )

    def _mask_dsn(dsn: str) -> str:
        return re.sub(r":([^:@]+)@", ":***@", dsn)

    async_dsn = (
        f"postgresql+asyncpg://{config.username}:{config.password}"
        f"@{config.host}:{config.port}/{config.database}"
    )
    masked_dsn = _mask_dsn(async_dsn)
    effective_pool_size = config.pool_size or 5
    effective_max_overflow = (
        config.max_overflow if config.max_overflow is not None else 10
    )
    effective_pool_timeout = (
        config.pool_timeout if config.pool_timeout is not None else 30
    )
    effective_pool_recycle = (
        config.pool_recycle if config.pool_recycle is not None else -1
    )
    effective_pool_pre_ping = (
        config.pool_pre_ping if config.pool_pre_ping is not None else False
    )

    logger.warning(
        "[SQL][AsyncEngine] Creating async engine (single PG config assumed): "
        "dsn=%s host=%s port=%s db=%s user=%s password_set=%s "
        "echo=%s pool_size=%s max_overflow=%s pool_timeout=%s pool_recycle=%s pool_pre_ping=%s "
        "connect_args=%s raw_config=%s",
        masked_dsn,
        config.host,
        config.port,
        config.database,
        config.username,
        bool(config.password),
        config.echo,
        effective_pool_size,
        effective_max_overflow,
        effective_pool_timeout,
        effective_pool_recycle,
        effective_pool_pre_ping,
        connect_args,
        {
            "host": config.host,
            "port": config.port,
            "database": config.database,
            "username": config.username,
            "password_set": bool(config.password),
            "echo": config.echo,
            "pool_size": config.pool_size,
            "max_overflow": config.max_overflow,
            "pool_timeout": config.pool_timeout,
            "pool_recycle": config.pool_recycle,
            "pool_pre_ping": config.pool_pre_ping,
            "connect_args": connect_args,
        },
    )

    try:
        engine = create_async_engine(
            async_dsn,
            echo=config.echo,
            pool_size=effective_pool_size,
            max_overflow=effective_max_overflow,
            pool_timeout=effective_pool_timeout,
            pool_recycle=effective_pool_recycle,
            pool_pre_ping=effective_pool_pre_ping,
            connect_args=connect_args,
        )
        logger.warning(
            "[SQL][AsyncEngine] Engine created successfully with pool_size=%s max_overflow=%s "
            "pool_timeout=%s pool_recycle=%s pool_pre_ping=%s connect_args=%s",
            effective_pool_size,
            effective_max_overflow,
            effective_pool_timeout,
            effective_pool_recycle,
            effective_pool_pre_ping,
            connect_args,
        )
        return engine
    except Exception as exc:
        logger.exception("[SQL][AsyncEngine] Failed to create engine: %s", exc)
        logger.error(
            "[SQL][AsyncEngine] Debug details: url=%s host=%s port=%s db=%s user=%s pwd_set=%s "
            "echo=%s pool_size=%s max_overflow=%s pool_timeout=%s pool_recycle=%s pool_pre_ping=%s connect_args=%s",
            masked_dsn,
            config.host,
            config.port,
            config.database,
            config.username,
            bool(config.password),
            config.echo,
            config.pool_size,
            config.max_overflow,
            config.pool_timeout,
            config.pool_recycle,
            config.pool_pre_ping,
            connect_args,
        )
        raise


class BaseSqlStore:
    """
    Lightweight SQL helper for Postgres-backed stores.
    """

    def __init__(self, engine: Engine, prefix: str = ""):
        self.engine = engine
        self.prefix = prefix

    def prefixed(self, name: str) -> str:
        """
        Apply the configured prefix if not already present.
        """
        return name if name.startswith(self.prefix) else f"{self.prefix}{name}"

    @contextlib.contextmanager
    def begin(self) -> Iterator[Connection]:
        """
        Provide a transactional connection.
        """
        with self.engine.begin() as conn:  # type: ignore[misc]
            yield conn

    def array_contains(self, column, value: Any) -> ClauseElement:
        """
        Array containment (tag filters, etc.) for Postgres arrays.
        """
        dialect = self.engine.dialect.name
        if dialect != "postgresql":
            raise ValueError(f"Unsupported dialect for array_contains: {dialect}")
        return column.any(value)

    def upsert(
        self,
        conn: Connection,
        table: Table,
        values: Mapping[str, Any],
        pk_cols: Sequence[str],
        update_cols: Sequence[str] | None = None,
    ) -> None:
        """
        Postgres-only upsert using ON CONFLICT.
        """
        dialect = conn.dialect.name
        if update_cols is None:
            update_cols = [c for c in values.keys() if c not in pk_cols]

        if dialect != "postgresql":
            raise ValueError(f"Unsupported dialect for upsert: {dialect}")

        stmt = pg_insert(table).values(**values)
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=[table.c[col] for col in pk_cols],
                set_={col: stmt.excluded[col] for col in update_cols},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[table.c[col] for col in pk_cols]
            )
        conn.execute(stmt)


class AsyncBaseSqlStore:
    """
    Async SQL helper for Postgres-backed stores (asyncpg).
    Mirrors BaseSqlStore but uses AsyncEngine/AsyncConnection to avoid thread hops.
    """

    def __init__(self, engine: AsyncEngine, prefix: str = ""):
        self.engine = engine
        self.prefix = prefix

    def prefixed(self, name: str) -> str:
        return name if name.startswith(self.prefix) else f"{self.prefix}{name}"

    @contextlib.asynccontextmanager
    async def begin(self):
        async with self.engine.begin() as conn:  # type: ignore[misc]
            yield conn

    def array_contains(self, column, value: Any) -> ClauseElement:
        dialect = self.engine.dialect.name
        if dialect != "postgresql":
            raise ValueError(f"Unsupported dialect for array_contains: {dialect}")
        return column.any(value)

    async def upsert(
        self,
        conn: AsyncConnection,
        table: Table,
        values: Mapping[str, Any],
        pk_cols: Sequence[str],
        update_cols: Sequence[str] | None = None,
    ) -> None:
        dialect = conn.dialect.name
        if update_cols is None:
            update_cols = [c for c in values.keys() if c not in pk_cols]

        # Select the correct insert function based on dialect
        if dialect == "postgresql":
            insert_stmt = pg_insert(table)
        elif dialect == "sqlite":
            insert_stmt = sqlite_insert(table)
        else:
            raise ValueError(f"Unsupported dialect for upsert: {dialect}")

        stmt = insert_stmt.values(**values)

        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=[table.c[col] for col in pk_cols],
                set_={col: stmt.excluded[col] for col in update_cols},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[table.c[col] for col in pk_cols]
            )

        await conn.execute(stmt)


# ------------------------- shared DDL helpers -------------------------


def advisory_lock_key(name: str) -> int:
    """Derive a deterministic signed 64-bit advisory lock key from a string."""

    # pg_advisory_xact_lock expects a signed bigint.
    # This hash is only used for deterministic lock-key derivation (non-cryptographic).
    return int.from_bytes(
        hashlib.sha1(name.encode("utf-8"), usedforsecurity=False).digest()[:8],
        "big",
        signed=True,
    )


async def run_ddl_with_advisory_lock(
    engine: AsyncEngine,
    lock_key: int,
    ddl_sync_fn: Callable[[Connection], None],
    logger: logging.Logger,
    tolerate_exists: bool = True,
) -> None:
    """
    Serialize DDL across uvicorn workers using a Postgres advisory lock.
    If you start fred on a fresh new platforms, tables are created by the first worker to receive traffic.
    Without this lock, multiple workers could attempt to create the same tables simultaneously, causing "already exists" errors and failed requests

    - Uses pg_advisory_xact_lock on Postgres (no-op on other dialects).
    - Runs the provided sync DDL callable via run_sync.
    - Optionally tolerates "already exists" races (pg_type_typname_nsp_index, duplicate key/table).
    """

    async with engine.begin() as conn:  # type: ignore[misc]
        if conn.dialect.name == "postgresql":
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": lock_key},
            )

        try:
            await conn.run_sync(ddl_sync_fn)
        except (IntegrityError, OperationalError, ProgrammingError) as exc:
            if not tolerate_exists:
                raise
            msg = str(exc).lower()
            race_markers = (
                "pg_type_typname_nsp_index",
                "already exists",
                "duplicate key value",
                "duplicate table",
            )
            if any(m in msg for m in race_markers):
                logger.warning(
                    "[SQL][DDL] DDL raced; assuming objects already exist (lock_id=%s)",
                    lock_key,
                )
            else:
                raise
