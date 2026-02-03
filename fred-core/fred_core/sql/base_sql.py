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
import logging
import re
from typing import Any, Iterator, Literal, Mapping, Sequence, overload

from sqlalchemy import Table, create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.sql import ClauseElement

from fred_core.common.structures import PostgresStoreConfig

logger = logging.getLogger(__name__)


@overload
def _build_engine_from_config(
    config: PostgresStoreConfig,
    *,
    async_mode: Literal[False] = False,
) -> Engine: ...


@overload
def _build_engine_from_config(
    config: PostgresStoreConfig,
    *,
    async_mode: Literal[True],
) -> AsyncEngine: ...


def _build_engine_from_config(
    config: PostgresStoreConfig,
    *,
    async_mode: bool = False,
) -> Engine | AsyncEngine:
    """
    Internal helper to build a SQLAlchemy Engine (sync or async) from a PostgresStoreConfig.

    Args:
        config: PostgreSQL configuration
        async_mode: If True, creates an AsyncEngine with asyncpg driver. If False, creates a sync Engine.

    Returns:
        Engine or AsyncEngine instance
    """
    context = "AsyncEngine" if async_mode else "Engine"

    missing = [
        name
        for name in ("host", "database", "username")
        if not getattr(config, name, None)
    ]
    if missing:
        raise ValueError(
            f"[SQL][{context}] Missing required Postgres config fields: {', '.join(missing)}"
        )

    connect_args: dict[str, Any] = (
        dict(config.connect_args) if config.connect_args else {}
    )

    def _mask_dsn(dsn: str) -> str:
        return re.sub(r":([^:@]+)@", ":***@", dsn)

    # For async mode, convert postgresql:// to postgresql+asyncpg://
    dsn = config.dsn()
    if async_mode:
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://")

    masked_dsn = _mask_dsn(dsn)

    logger.info(
        "[SQL][%s] Creating %s: url=%s host=%s port=%s db=%s user=%s pwd_set=%s echo=%s pool_size=%s connect_args=%s",
        context,
        "async engine" if async_mode else "engine",
        masked_dsn,
        config.host,
        config.port,
        config.database,
        config.username,
        bool(config.password),
        config.echo,
        config.pool_size,
        connect_args,
    )

    try:
        if async_mode:
            engine = create_async_engine(
                dsn,
                echo=config.echo,
                pool_size=config.pool_size or 5,
                connect_args=connect_args,
            )
        else:
            engine = create_engine(
                dsn,
                echo=config.echo,
                pool_size=config.pool_size or 5,
                connect_args=connect_args,
            )
        logger.info("[SQL][%s] %s created successfully.", context, "Async engine" if async_mode else "Engine")
        return engine
    except Exception as exc:
        logger.exception("[SQL][%s] Failed to create %s: %s", context, "async engine" if async_mode else "engine", exc)
        logger.error(
            "[SQL][%s] Debug details: url=%s host=%s port=%s db=%s user=%s pwd_set=%s echo=%s pool_size=%s connect_args=%s",
            context,
            masked_dsn,
            config.host,
            config.port,
            config.database,
            config.username,
            bool(config.password),
            config.echo,
            config.pool_size,
            connect_args,
        )
        raise


def create_engine_from_config(config: PostgresStoreConfig) -> Engine:
    """
    Build a SQLAlchemy Engine for Postgres from a PostgresStoreConfig.
    Adds explicit logging and validation of required fields to ease debugging.
    """
    return _build_engine_from_config(config, async_mode=False)


def create_async_engine_from_config(config: PostgresStoreConfig) -> AsyncEngine:
    """
    Build an async SQLAlchemy Engine for Postgres from a PostgresStoreConfig.
    Uses asyncpg driver for async operations.
    """
    return _build_engine_from_config(config, async_mode=True)


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
