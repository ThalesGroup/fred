"""
Durable LangGraph-compatible checkpointer backed by Fred's shared SQL engine.

Why this exists:
- v2 runtimes should not depend on in-memory checkpoint state once they are used
  through real conversations, HITL, or future Temporal adapters.
- Fred already has a shared SQL engine lifecycle through `storage.postgres`.
- The runtime needs one durable checkpoint contract that works in local dev
  (SQLite fallback) and in production (Postgres) without changing agent code.

This class is intentionally infrastructure-focused. Business agents should never
care where checkpoints live. They only rely on the fact that pause/resume and
conversation continuity survive executor rebuilds and process boundaries.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fred_core.kpi import BaseKPIWriter, phase_timer
from fred_core.sql import (
    AsyncBaseSqlStore,
    advisory_lock_key,
    json_for_engine,
    run_ddl_with_advisory_lock,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    and_,
    delete,
    desc,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import func


def _sync_checkpointer_error(method_name: str) -> RuntimeError:
    return RuntimeError(
        "FredSqlCheckpointer is async-only for Fred v2. "
        f"Synchronous method '{method_name}' was called unexpectedly."
    )


def _configurable(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        raise RuntimeError("RunnableConfig must contain a configurable mapping.")
    return cast(dict[str, Any], configurable)


def _make_config(
    *, thread_id: str, checkpoint_ns: str = "", checkpoint_id: str | None = None
) -> RunnableConfig:
    configurable: dict[str, Any] = {
        "thread_id": thread_id,
        "checkpoint_ns": checkpoint_ns,
    }
    if checkpoint_id is not None:
        configurable["checkpoint_id"] = checkpoint_id
    return cast(RunnableConfig, {"configurable": configurable})


class FredSqlCheckpointer(BaseCheckpointSaver[str]):
    """
    Durable checkpoint backend for Fred v2 runtimes.

    Why this is the right level:
    - the runtime wants durable pause/resume and final state continuity
    - business agents should not open databases or serialize checkpoints
    - using Fred's shared SQL engine keeps local and production semantics close
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        prefix: str = "v2_",
        kpi: BaseKPIWriter | None = None,
    ) -> None:
        super().__init__()
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        metadata = MetaData()
        json_type = json_for_engine(engine)

        self.checkpoints_table = Table(
            self.store.prefixed("langgraph_checkpoint"),
            metadata,
            Column("thread_id", String, primary_key=True),
            Column("checkpoint_ns", String, primary_key=True, default=""),
            Column("checkpoint_id", String, primary_key=True),
            Column("parent_checkpoint_id", String, nullable=True),
            Column("checkpoint_type", String, nullable=False),
            Column("checkpoint_blob", LargeBinary, nullable=False),
            Column("metadata_json", json_type, nullable=False),
            Column(
                "created_at",
                DateTime(timezone=True),
                server_default=func.now(),
                nullable=False,
            ),
            keep_existing=True,
        )
        self.blobs_table = Table(
            self.store.prefixed("langgraph_checkpoint_blob"),
            metadata,
            Column("thread_id", String, primary_key=True),
            Column("checkpoint_ns", String, primary_key=True, default=""),
            Column("channel", String, primary_key=True),
            Column("version", String, primary_key=True),
            Column("value_type", String, nullable=False),
            Column("value_blob", LargeBinary, nullable=False),
            keep_existing=True,
        )
        self.writes_table = Table(
            self.store.prefixed("langgraph_checkpoint_write"),
            metadata,
            Column("thread_id", String, primary_key=True),
            Column("checkpoint_ns", String, primary_key=True, default=""),
            Column("checkpoint_id", String, primary_key=True),
            Column("task_id", String, primary_key=True),
            Column("idx", Integer, primary_key=True),
            Column("channel", String, nullable=False),
            Column("value_type", String, nullable=False),
            Column("value_blob", LargeBinary, nullable=False),
            Column("task_path", String, nullable=False, default=""),
            keep_existing=True,
        )
        Index(
            f"{self.checkpoints_table.name}_thread_created_idx",
            self.checkpoints_table.c.thread_id,
            self.checkpoints_table.c.checkpoint_ns,
            self.checkpoints_table.c.created_at.desc(),
        )
        self._metadata = metadata
        self._ddl_lock_id = advisory_lock_key(self.checkpoints_table.name)
        self._tables_ready = False
        self._logger = logging.getLogger(__name__)
        self._kpi = kpi

    @asynccontextmanager
    async def phase(self, phase_name: str):
        if self._kpi is None:
            yield
            return
        async with phase_timer(self._kpi, phase_name):
            yield

    async def _ensure_tables(self) -> None:
        if self._tables_ready:
            return
        async with self.phase("v2_checkpoint_ensure_tables"):
            await run_ddl_with_advisory_lock(
                engine=self.store.engine,
                lock_key=self._ddl_lock_id,
                ddl_sync_fn=self._metadata.create_all,
                logger=self._logger,
            )
        self._tables_ready = True

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:  # type: ignore[override]
        raise _sync_checkpointer_error("get_tuple")

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:  # type: ignore[override]
        async with self.phase("v2_checkpoint_get_tuple"):
            await self._ensure_tables()
            configurable = _configurable(config)
            thread_id = str(configurable["thread_id"])
            checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
            explicit_checkpoint_id = get_checkpoint_id(config)

            async with self.store.begin() as conn:
                row = None
                if explicit_checkpoint_id:
                    result = await conn.execute(
                        select(self.checkpoints_table).where(
                            and_(
                                self.checkpoints_table.c.thread_id == thread_id,
                                self.checkpoints_table.c.checkpoint_ns == checkpoint_ns,
                                self.checkpoints_table.c.checkpoint_id
                                == str(explicit_checkpoint_id),
                            )
                        )
                    )
                    row = result.fetchone()
                else:
                    result = await conn.execute(
                        select(self.checkpoints_table)
                        .where(
                            and_(
                                self.checkpoints_table.c.thread_id == thread_id,
                                self.checkpoints_table.c.checkpoint_ns == checkpoint_ns,
                            )
                        )
                        .order_by(
                            desc(self.checkpoints_table.c.created_at),
                            desc(self.checkpoints_table.c.checkpoint_id),
                        )
                        .limit(1)
                    )
                    row = result.fetchone()

                if row is None:
                    return None

                checkpoint_id = str(row.checkpoint_id)
                checkpoint = cast(
                    Checkpoint,
                    self.serde.loads_typed(
                        (row.checkpoint_type, bytes(row.checkpoint_blob))
                    ),
                )
                channel_values = await self._load_channel_values(
                    conn,
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    channel_versions=checkpoint.get("channel_versions", {}),
                )
                writes_result = await conn.execute(
                    select(self.writes_table)
                    .where(
                        and_(
                            self.writes_table.c.thread_id == thread_id,
                            self.writes_table.c.checkpoint_ns == checkpoint_ns,
                            self.writes_table.c.checkpoint_id == checkpoint_id,
                        )
                    )
                    .order_by(self.writes_table.c.task_id, self.writes_table.c.idx)
                )
                writes_rows = writes_result.fetchall()

            resolved_config = (
                config
                if explicit_checkpoint_id
                else _make_config(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=checkpoint_id,
                )
            )
            parent_config: RunnableConfig | None = None
            if row.parent_checkpoint_id:
                parent_config = _make_config(
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    checkpoint_id=str(row.parent_checkpoint_id),
                )
            pending_writes = [
                (
                    str(write_row.task_id),
                    str(write_row.channel),
                    self.serde.loads_typed(
                        (str(write_row.value_type), bytes(write_row.value_blob))
                    ),
                )
                for write_row in writes_rows
            ]
            return CheckpointTuple(
                config=resolved_config,
                checkpoint={**checkpoint, "channel_values": channel_values},
                metadata=cast(CheckpointMetadata, dict(row.metadata_json or {})),
                parent_config=parent_config,
                pending_writes=pending_writes,
            )

    def list(
        self,
        config: RunnableConfig | None = None,
        *,
        filter=None,
        before: RunnableConfig | None = None,
        limit=None,
    ) -> Iterator[CheckpointTuple]:  # type: ignore[override]
        raise _sync_checkpointer_error("list")

    async def alist(
        self,
        config: RunnableConfig | None = None,
        *,
        filter=None,
        before: RunnableConfig | None = None,
        limit=None,
    ) -> AsyncIterator[CheckpointTuple]:  # type: ignore[override]
        items = await self._collect_list(
            config, filter=filter, before=before, limit=limit
        )
        for item in items:
            yield item

    async def _collect_list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> list[CheckpointTuple]:
        async with self.phase("v2_checkpoint_list"):
            await self._ensure_tables()
            conditions: list[Any] = []
            if config is not None:
                cfg = _configurable(config)
                conditions.append(
                    self.checkpoints_table.c.thread_id == str(cfg["thread_id"])
                )
                checkpoint_ns = cfg.get("checkpoint_ns")
                if checkpoint_ns is not None:
                    conditions.append(
                        self.checkpoints_table.c.checkpoint_ns == str(checkpoint_ns)
                    )
            before_checkpoint_id = (
                get_checkpoint_id(before) if before is not None else None
            )
            before_created_at = None
            if before is not None and before_checkpoint_id and config is not None:
                before_tuple = await self.aget_tuple(before)
                if before_tuple is not None:
                    # Re-read the exact row timestamp for ordering.
                    async with self.store.begin() as conn:
                        res = await conn.execute(
                            select(self.checkpoints_table.c.created_at).where(
                                and_(
                                    self.checkpoints_table.c.thread_id
                                    == str(_configurable(before)["thread_id"]),
                                    self.checkpoints_table.c.checkpoint_ns
                                    == str(
                                        _configurable(before).get("checkpoint_ns", "")
                                    ),
                                    self.checkpoints_table.c.checkpoint_id
                                    == str(before_checkpoint_id),
                                )
                            )
                        )
                        ts_row = res.fetchone()
                        before_created_at = ts_row[0] if ts_row else None

            async with self.store.begin() as conn:
                stmt = select(self.checkpoints_table)
                if conditions:
                    stmt = stmt.where(and_(*conditions))
                if before_created_at is not None:
                    stmt = stmt.where(
                        self.checkpoints_table.c.created_at < before_created_at
                    )
                stmt = stmt.order_by(
                    desc(self.checkpoints_table.c.created_at),
                    desc(self.checkpoints_table.c.checkpoint_id),
                )
                if limit is not None:
                    stmt = stmt.limit(limit)
                rows = (await conn.execute(stmt)).fetchall()

            tuples: list[CheckpointTuple] = []
            for row in rows:
                candidate_config = _make_config(
                    thread_id=str(row.thread_id),
                    checkpoint_ns=str(row.checkpoint_ns),
                    checkpoint_id=str(row.checkpoint_id),
                )
                checkpoint_tuple = await self.aget_tuple(candidate_config)
                if checkpoint_tuple is None:
                    continue
                if filter and not all(
                    checkpoint_tuple.metadata.get(key) == value
                    for key, value in filter.items()
                ):
                    continue
                tuples.append(checkpoint_tuple)
            return tuples

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ):  # type: ignore[override]
        raise _sync_checkpointer_error("put")

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ):  # type: ignore[override]
        async with self.phase("v2_checkpoint_put"):
            await self._ensure_tables()
            c = checkpoint.copy()
            configurable = _configurable(config)
            thread_id = str(configurable["thread_id"])
            checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
            checkpoint_id = str(checkpoint["id"])
            values = cast(dict[str, Any], c.pop("channel_values", {}))
            metadata_json = get_checkpoint_metadata(config, metadata)
            async with self.store.begin() as conn:
                for channel, version in new_versions.items():
                    stored_type, stored_blob = (
                        self.serde.dumps_typed(values[channel])
                        if channel in values
                        else ("empty", b"")
                    )
                    await self.store.upsert(
                        conn,
                        self.blobs_table,
                        values={
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "channel": str(channel),
                            "version": str(version),
                            "value_type": str(stored_type),
                            "value_blob": stored_blob,
                        },
                        pk_cols=["thread_id", "checkpoint_ns", "channel", "version"],
                    )
                checkpoint_type, checkpoint_blob = self.serde.dumps_typed(c)
                await self.store.upsert(
                    conn,
                    self.checkpoints_table,
                    values={
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                        "parent_checkpoint_id": configurable.get("checkpoint_id"),
                        "checkpoint_type": str(checkpoint_type),
                        "checkpoint_blob": checkpoint_blob,
                        "metadata_json": metadata_json,
                    },
                    pk_cols=["thread_id", "checkpoint_ns", "checkpoint_id"],
                )
            return _make_config(
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
            )

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ):  # type: ignore[override]
        raise _sync_checkpointer_error("put_writes")

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ):  # type: ignore[override]
        async with self.phase("v2_checkpoint_put_writes"):
            await self._ensure_tables()
            configurable = _configurable(config)
            thread_id = str(configurable["thread_id"])
            checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
            checkpoint_id = str(configurable["checkpoint_id"])
            async with self.store.begin() as conn:
                for idx, (channel, value) in enumerate(writes):
                    write_idx = WRITES_IDX_MAP.get(channel, idx)
                    value_type, value_blob = self.serde.dumps_typed(value)
                    await self.store.upsert(
                        conn,
                        self.writes_table,
                        values={
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": checkpoint_id,
                            "task_id": task_id,
                            "idx": int(write_idx),
                            "channel": str(channel),
                            "value_type": str(value_type),
                            "value_blob": value_blob,
                            "task_path": task_path,
                        },
                        pk_cols=[
                            "thread_id",
                            "checkpoint_ns",
                            "checkpoint_id",
                            "task_id",
                            "idx",
                        ],
                    )

    def delete_thread(self, thread_id: str) -> None:  # type: ignore[override]
        raise _sync_checkpointer_error("delete_thread")

    async def adelete_thread(self, thread_id: str) -> None:
        async with self.phase("v2_checkpoint_delete_thread"):
            await self._ensure_tables()
            async with self.store.begin() as conn:
                await conn.execute(
                    delete(self.writes_table).where(
                        self.writes_table.c.thread_id == thread_id
                    )
                )
                await conn.execute(
                    delete(self.checkpoints_table).where(
                        self.checkpoints_table.c.thread_id == thread_id
                    )
                )
                await conn.execute(
                    delete(self.blobs_table).where(
                        self.blobs_table.c.thread_id == thread_id
                    )
                )

    def get_next_version(self, current: str | None, channel: None) -> str:  # type: ignore[override]
        """
        Return a monotonic string channel version compatible with LangGraph 1.x.

        Why this override is required:
        - LangGraph now calls `checkpointer.get_next_version(...)` during write
          application.
        - Base implementation raises `NotImplementedError` when `current` is a
          string.
        - Fred stores checkpoint channel versions durably and can receive
          string-typed versions on resumed streams.
        """

        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            try:
                current_v = int(str(current).split(".", 1)[0])
            except ValueError:
                current_v = 0
        next_v = current_v + 1
        # Keep lexical ordering stable while avoiding accidental collisions.
        return f"{next_v:032}.{secrets.token_hex(8)}"

    async def _load_channel_values(
        self,
        conn,
        *,
        thread_id: str,
        checkpoint_ns: str,
        channel_versions: dict[str, Any],
    ) -> dict[str, Any]:
        if not channel_versions:
            return {}
        conditions = [
            and_(
                self.blobs_table.c.channel == str(channel),
                self.blobs_table.c.version == str(version),
            )
            for channel, version in channel_versions.items()
        ]
        result = await conn.execute(
            select(self.blobs_table).where(
                and_(
                    self.blobs_table.c.thread_id == thread_id,
                    self.blobs_table.c.checkpoint_ns == checkpoint_ns,
                    or_(*conditions),
                )
            )
        )
        rows = result.fetchall()
        loaded: dict[tuple[str, str], tuple[bool, Any]] = {}
        for row in rows:
            if str(row.value_type) == "empty":
                continue
            loaded[(str(row.channel), str(row.version))] = (
                True,
                self.serde.loads_typed((str(row.value_type), bytes(row.value_blob))),
            )
        return {
            str(channel): loaded[(str(channel), str(version))][1]
            for channel, version in channel_versions.items()
            if (str(channel), str(version)) in loaded
        }
