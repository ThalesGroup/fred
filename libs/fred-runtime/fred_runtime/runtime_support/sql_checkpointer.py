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

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_phase_metric import phase_timer
from fred_core.sql.base_sql import (
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
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
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
    case,
    delete,
    desc,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
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

    _FRED_MSGPACK_ALLOWLIST: tuple[tuple[str, str], ...] = (
        ("agentic_backend.core.agents.v2.contracts.context", "ToolContentKind"),
    )

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        prefix: str = "v2_",
        kpi: BaseKPIWriter | None = None,
    ) -> None:
        # Pass the allowlist directly to the constructor.
        # with_msgpack_allowlist() is a no-op when the default serde starts with
        # allowed_msgpack_modules=True, because it returns self unchanged.
        serde = JsonPlusSerializer(
            allowed_msgpack_modules=list(self._FRED_MSGPACK_ALLOWLIST)
        )
        super().__init__(serde=serde)
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
        # Side table giving each checkpoint thread an owner + age key.
        # Why it exists (CTRLP-12 / RFC §3.A): the checkpoint tables above are
        # keyed by thread_id only — no user, no age — so they can be neither
        # erased per-user nor swept by retention. This one row per thread makes
        # both possible (A6 idle sweep via last_activity_at; per-user erase via
        # user_id). It is a checkpoint-side table, so it self-inits with its
        # siblings via create_all — deliberately NOT alembic-tracked, exactly
        # like langgraph_checkpoint/_blob/_write (alembic env is scoped to
        # session_history only). Keyed by thread_id, so MEMORY-02's per-agent
        # checkpoint_ns split is orthogonal: many (thread_id, ns) checkpoints
        # simply refresh one owner row.
        self.thread_owner_table = Table(
            self.store.prefixed("checkpoint_thread_owner"),
            metadata,
            Column("thread_id", String, primary_key=True),
            Column("user_id", String, nullable=True),
            Column("team_id", String, nullable=True),
            Column(
                "created_at",
                DateTime(timezone=True),
                server_default=func.now(),
                nullable=False,
            ),
            Column(
                "last_activity_at",
                DateTime(timezone=True),
                server_default=func.now(),
                nullable=False,
            ),
            keep_existing=True,
        )
        Index(
            f"{self.checkpoints_table.name}_thread_created_idx",
            self.checkpoints_table.c.thread_id,
            self.checkpoints_table.c.checkpoint_ns,
            self.checkpoints_table.c.created_at.desc(),
        )
        Index(
            f"{self.thread_owner_table.name}_user_idx",
            self.thread_owner_table.c.user_id,
        )
        Index(
            f"{self.thread_owner_table.name}_activity_idx",
            self.thread_owner_table.c.last_activity_at,
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
            # Best-effort owner/age index write — see _record_thread_owner.
            # MUST run after the checkpoint transaction commits (its own tx) and
            # MUST NEVER raise: a failed owner write cannot fail a user's turn.
            await self._record_thread_owner(configurable)
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
                # Keep the owner index truthful: a thread that no longer has a
                # checkpoint must not linger as an owner row (would resurrect in
                # per-user purge / idle sweep).
                await conn.execute(
                    delete(self.thread_owner_table).where(
                        self.thread_owner_table.c.thread_id == thread_id
                    )
                )

    # ------------------------- owner / age index (CTRLP-12 A4) -------------------------

    async def _record_thread_owner(self, configurable: dict[str, Any]) -> None:
        """
        Best-effort upsert of this thread's owner/age row. Called from ``aput``.

        Identity note (A4 design decision): at ``aput`` time the RunnableConfig's
        ``configurable`` carries only ``thread_id``/``checkpoint_ns``/``checkpoint_id``
        — user/team identity is NOT threaded into the checkpointer today (verified
        by grep of the graph/react invocation sites). So this write always records
        the **age key** (``last_activity_at``), which is all ``aput`` can know and
        is what the A6 idle sweep needs, and picks up ``user_id``/``team_id`` only
        if a caller has injected them under the ``__fred_user_id``/``__fred_team_id``
        keys (``__``-prefixed → excluded from persisted checkpoint metadata by
        LangGraph's ``get_checkpoint_metadata``, so identity is not duplicated into
        checkpoint blobs). Nothing injects them yet; the authoritative owner comes
        from :meth:`backfill_thread_owners_from_history`. Injecting at the
        invocation sites is a documented, optional follow-up (out of A4 scope).

        This never raises: a failed owner write must not fail the user's turn.
        """
        try:
            thread_id = str(configurable["thread_id"])
            user_id = configurable.get("__fred_user_id")
            team_id = configurable.get("__fred_team_id")
            async with self.store.begin() as conn:
                await self._upsert_owner(
                    conn,
                    thread_id=thread_id,
                    user_id=str(user_id) if user_id is not None else None,
                    team_id=str(team_id) if team_id is not None else None,
                    last_activity_at=func.now(),
                )
        except Exception:
            self._logger.warning(
                "checkpoint_thread_owner write skipped (best-effort); owner "
                "index may lag until the next backfill",
                exc_info=True,
            )

    async def _upsert_owner(
        self,
        conn: AsyncConnection,
        *,
        thread_id: str,
        user_id: str | None,
        team_id: str | None,
        last_activity_at: Any,
        created_at: Any | None = None,
    ) -> None:
        """
        Upsert exactly one owner row per thread (PK = thread_id).

        Merge rules on conflict:
        - ``last_activity_at`` moves forward only (portable ``GREATEST`` via CASE);
        - ``user_id``/``team_id`` fill from the new value but never overwrite a
          known owner with NULL (``COALESCE(new, existing)``);
        - ``created_at`` is insert-only (first-seen), never updated.
        """
        dialect = conn.dialect.name
        if dialect == "postgresql":
            insert_stmt = pg_insert(self.thread_owner_table)
        elif dialect == "sqlite":
            insert_stmt = sqlite_insert(self.thread_owner_table)
        else:
            raise ValueError(f"Unsupported dialect for owner upsert: {dialect}")

        values: dict[str, Any] = {
            "thread_id": thread_id,
            "user_id": user_id,
            "team_id": team_id,
            "last_activity_at": last_activity_at,
        }
        if created_at is not None:
            values["created_at"] = created_at
        stmt = insert_stmt.values(**values)

        owner = self.thread_owner_table.c
        stmt = stmt.on_conflict_do_update(
            index_elements=[owner.thread_id],
            set_={
                "user_id": func.coalesce(stmt.excluded.user_id, owner.user_id),
                "team_id": func.coalesce(stmt.excluded.team_id, owner.team_id),
                "last_activity_at": case(
                    (
                        stmt.excluded.last_activity_at > owner.last_activity_at,
                        stmt.excluded.last_activity_at,
                    ),
                    else_=owner.last_activity_at,
                ),
            },
        )
        await conn.execute(stmt)

    async def backfill_thread_owners_from_history(
        self, *, history_table_name: str = "session_history"
    ) -> int:
        """
        One-shot reconciliation: seed the owner index from ``session_history``.

        ``session_history`` is where identity is definitively known (user_id is
        part of its PK; team_id/timestamp are recorded per turn). One owner row
        per distinct ``session_id`` (== checkpoint ``thread_id``) is written, with
        ``created_at``=min(timestamp), ``last_activity_at``=max(timestamp). Safe to
        re-run: it coalesces owner identity and only advances ``last_activity_at``.

        Returns the number of distinct threads processed.
        """
        await self._ensure_tables()
        # Lightweight, read-only projection of the runtime-owned history table.
        history = Table(
            history_table_name,
            MetaData(),
            Column("session_id", String),
            Column("user_id", String),
            Column("team_id", String),
            Column("timestamp", DateTime(timezone=True)),
            keep_existing=True,
        )
        async with self.store.begin() as conn:
            rows = (
                await conn.execute(
                    select(
                        history.c.session_id,
                        func.min(history.c.user_id),
                        func.min(history.c.team_id),
                        func.min(history.c.timestamp),
                        func.max(history.c.timestamp),
                    ).group_by(history.c.session_id)
                )
            ).fetchall()
            for row in rows:
                await self._upsert_owner(
                    conn,
                    thread_id=str(row[0]),
                    user_id=(str(row[1]) if row[1] is not None else None),
                    team_id=(str(row[2]) if row[2] is not None else None),
                    last_activity_at=row[4],
                    created_at=row[3],
                )
        return len(rows)

    async def purge_threads_for_user(self, user_id: str) -> list[str]:
        """
        Erase every checkpoint thread owned by ``user_id`` (per-user erase / A6).

        Enumerates thread_ids from the owner index and calls the existing
        :meth:`adelete_thread` for each (which also drops the owner row). Returns
        the thread_ids purged.
        """
        await self._ensure_tables()
        async with self.store.begin() as conn:
            rows = (
                await conn.execute(
                    select(self.thread_owner_table.c.thread_id).where(
                        self.thread_owner_table.c.user_id == user_id
                    )
                )
            ).fetchall()
        thread_ids = [str(row[0]) for row in rows]
        for thread_id in thread_ids:
            await self.adelete_thread(thread_id)
        return thread_ids

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
