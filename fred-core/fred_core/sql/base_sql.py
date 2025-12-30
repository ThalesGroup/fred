from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

from sqlalchemy import Table, create_engine
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql import ClauseElement


@dataclass
class EngineConfig:
    """
    Minimal engine configuration used by the stores.
    """

    url: str
    echo: bool = False
    pool_size: int | None = None
    connect_args: Mapping[str, Any] | None = None


def create_engine_from_config(config: EngineConfig) -> Engine:
    """
    Build a SQLAlchemy Engine for Postgres from a simple config.
    """
    kwargs: dict[str, Any] = {"echo": config.echo}
    if config.pool_size is not None:
        kwargs["pool_size"] = config.pool_size
    if config.connect_args:
        kwargs["connect_args"] = dict(config.connect_args)
    return create_engine(config.url, **kwargs)


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
