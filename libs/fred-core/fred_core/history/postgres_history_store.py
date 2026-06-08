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
Postgres-backed conversation history store.

Why this module exists:
- agent pods (``fred-runtime``) need to persist conversation history without
  importing from ``agentic-backend``
- this implementation uses the same ``session_history`` table and upsert
  strategy as ``agentic-backend``'s ``PostgresHistoryStore``, ensuring both
  backends write to a compatible schema

How to use it:
- instantiate with an ``AsyncEngine`` from ``fred_core.sql.base_sql``
- call ``save`` after each agent turn; call ``get`` to retrieve messages

Example:
    from fred_core.sql.base_sql import create_async_engine_from_config
    from fred_core.history.postgres_history_store import PostgresHistoryStore

    engine = create_async_engine_from_config(config.storage.postgres)
    store = PostgresHistoryStore(engine)

    await store.save(session_id="s1", messages=[...], user_id="u1")
    messages = await store.get("s1")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import MetaData, delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fred_core.history.base_history_store import BaseHistoryStore
from fred_core.history.history_models import SessionHistoryRow
from fred_core.history.history_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    MessagePart,
    Role,
)
from fred_core.sql.async_session import make_session_factory, use_session
from fred_core.sql.base_sql import advisory_lock_key, run_ddl_with_advisory_lock

logger = logging.getLogger(__name__)

_MESSAGE_PARTS_ADAPTER: TypeAdapter[List[MessagePart]] = TypeAdapter(List[MessagePart])


def _dialect_insert(engine: AsyncEngine):
    """
    Return the dialect-appropriate ``insert`` constructor.

    Why this exists:
    - ``sqlalchemy.dialects.postgresql.insert`` is required for
      ``on_conflict_do_update`` on PostgreSQL
    - ``sqlalchemy.dialects.sqlite.insert`` provides the same API for SQLite
      (SQLite 3.24+ supports ``ON CONFLICT DO UPDATE``)
    - the standard ``sqlalchemy.insert`` does not expose ``on_conflict_do_update``
    """
    if engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    return pg_insert


def _normalize_ts(ts: datetime | str) -> datetime:
    """Return a timezone-aware UTC datetime from a datetime or ISO string."""
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            logger.warning("[history][pg] Failed to parse timestamp %r — using now", ts)
            dt = datetime.now(timezone.utc)
    else:
        dt = ts
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _serialize_part(part: Any) -> dict:
    """
    Serialize one message part to a JSON-safe dict.

    Why this helper exists:
    - parts may be Pydantic models (call ``.model_dump()``) or already plain dicts
      (pass through unchanged) — a single helper handles both cases safely
    """
    if hasattr(part, "model_dump"):
        return part.model_dump(mode="json", exclude_none=True)
    if isinstance(part, dict):
        return part
    return {"_raw": str(part)}


def _serialize_metadata(metadata: Any) -> dict:
    """
    Serialize message metadata to a JSON-safe dict.

    How to use it:
    - ``metadata`` may be a ``ChatMetadata`` Pydantic model or a plain dict;
      both are handled without raising
    """
    if metadata is None:
        return {}
    if hasattr(metadata, "model_dump"):
        return metadata.model_dump(mode="json", exclude_none=True)
    if isinstance(metadata, dict):
        return metadata
    return {}


class PostgresHistoryStore(BaseHistoryStore):
    """
    Postgres-backed implementation of ``BaseHistoryStore``.

    Storage:
    - one row per message in ``session_history``
    - upsert on ``(session_id, user_id, rank)`` — retried writes are idempotent

    DDL:
    - the canonical schema is still tracked by fred-runtime Alembic migrations
    - the store also self-initializes the runtime-owned table on first use so a
      fresh local SQLite database does not fail before the first write

    Why upsert rather than insert:
    - a turn can be retried (HITL resume, network retry) and the same messages
      must not be duplicated; upsert collapses retries cleanly
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)
        self._metadata = MetaData()
        SessionHistoryRow.__table__.to_metadata(self._metadata)
        self._ddl_lock_id = advisory_lock_key(SessionHistoryRow.__tablename__)
        self._tables_ready = False

    async def _ensure_tables(self) -> None:
        """
        Ensure the runtime-owned history table exists before querying it.

        Why this helper exists:
        - fresh local SQLite runs create the database file before Alembic has
          necessarily been applied
        - the first history call is often ``next_rank()``, so table creation
          must happen before both reads and writes

        How to use it:
        - call at the start of every public store operation
        """
        if self._tables_ready:
            return
        await run_ddl_with_advisory_lock(
            engine=self._engine,
            lock_key=self._ddl_lock_id,
            ddl_sync_fn=self._metadata.create_all,
            logger=logger,
        )
        self._tables_ready = True

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save(
        self,
        session_id: str,
        messages: List[ChatMessage],
        user_id: str,
        team_id: str | None = None,
        agent_instance_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Persist a batch of messages for one turn.

        How to use it:
        - call after the agent executor generator is fully exhausted
        - ``messages`` must have ``rank`` set in ascending order (use
          ``_assign_ranks`` in the calling code to compute ranks from MAX(rank)+1)
        - ``team_id`` and ``agent_instance_id`` should always be passed for
          managed execution so admin and retention queries can filter by them

        Example:
            await store.save(
                session_id="s1", messages=[user_msg, assistant_msg],
                user_id="u1", team_id="personal", agent_instance_id="inst-abc"
            )
        """
        if not messages:
            return
        await self._ensure_tables()
        rows = [
            {
                "session_id": session_id,
                "user_id": user_id,
                "rank": msg.rank,
                "timestamp": _normalize_ts(msg.timestamp),
                "role": msg.role.value if isinstance(msg.role, Role) else msg.role,
                "channel": msg.channel.value
                if isinstance(msg.channel, Channel)
                else msg.channel,
                "exchange_id": msg.exchange_id,
                "team_id": team_id,
                "agent_instance_id": agent_instance_id,
                "parts_json": [_serialize_part(p) for p in (msg.parts or [])],
                "metadata_json": _serialize_metadata(msg.metadata),
            }
            for msg in messages
        ]
        stmt = _dialect_insert(self._engine)(SessionHistoryRow).values(rows)
        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["session_id", "user_id", "rank"],
            set_={
                k: stmt.excluded[k]
                for k in [
                    "parts_json",
                    "metadata_json",
                    "timestamp",
                    "team_id",
                    "agent_instance_id",
                ]
            },
        )
        async with use_session(self._sessions, session) as s:
            await s.execute(upsert_stmt)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(
        self,
        session_id: str,
        user_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> List[ChatMessage]:
        """
        Retrieve messages for a session, ordered by rank ascending.

        When user_id is provided, only rows belonging to that user are returned.
        Returns [] when no rows match — callers cannot distinguish "wrong owner"
        from "empty session" by design (avoids session-ID enumeration).
        """
        await self._ensure_tables()
        async with use_session(self._sessions, session) as s:
            q = select(SessionHistoryRow).where(
                SessionHistoryRow.session_id == session_id
            )
            if user_id is not None:
                q = q.where(SessionHistoryRow.user_id == user_id)
            rows = (
                (await s.execute(q.order_by(SessionHistoryRow.rank.asc())))
                .scalars()
                .all()
            )

        out: List[ChatMessage] = []
        for row in rows:
            try:
                parts = _MESSAGE_PARTS_ADAPTER.validate_python(row.parts_json or [])
                md_raw = row.metadata_json or {}
                # Reconstruct ChatMetadata, stripping keys that may belong to
                # richer subclasses (e.g. agentic-backend's runtime_context).
                try:
                    metadata = ChatMetadata.model_validate(md_raw)
                except ValidationError:
                    metadata = ChatMetadata()
                out.append(
                    ChatMessage(
                        session_id=session_id,
                        rank=row.rank,
                        timestamp=row.timestamp,
                        role=Role(row.role),
                        channel=Channel(row.channel),
                        exchange_id=row.exchange_id or "",
                        parts=parts,
                        metadata=metadata,
                    )
                )
            except (ValidationError, ValueError) as exc:
                logger.error(
                    "[history][pg] Skipping malformed row rank=%s: %s", row.rank, exc
                )
        return out

    async def list_sessions(
        self,
        user_id: str,
        session: AsyncSession | None = None,
    ) -> List[str]:
        """
        Return distinct session IDs for a user, ordered by most recent activity first.

        Why this exists:
        - the UI must list past conversations; the checkpointer has no ``user_id``
          index so the history store is the only correct source

        How to use it:
        - call from ``GET /sessions?user_id=<user_id>``

        Example:
            sessions = await store.list_sessions(user_id="alice")
            # returns ["session-3", "session-1", ...]  most recent first
        """
        await self._ensure_tables()
        async with use_session(self._sessions, session) as s:
            result = await s.execute(
                select(SessionHistoryRow.session_id)
                .where(SessionHistoryRow.user_id == user_id)
                .group_by(SessionHistoryRow.session_id)
                .order_by(func.max(SessionHistoryRow.timestamp).desc())
            )
            return [row[0] for row in result.all()]

    async def delete_session(
        self,
        session_id: str,
        user_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> int:
        """
        Permanently remove history rows for a session.

        When user_id is provided, only rows belonging to that user are deleted.
        Returns the number of rows removed (0 when session not found or not owned).
        """
        await self._ensure_tables()
        async with use_session(self._sessions, session) as s:
            where = [SessionHistoryRow.session_id == session_id]
            if user_id is not None:
                where.append(SessionHistoryRow.user_id == user_id)
            count_row = await s.execute(select(func.count()).where(*where))
            count: int = count_row.scalar() or 0
            await s.execute(delete(SessionHistoryRow).where(*where))
            await s.commit()
            return count

    async def session_belongs_to_user(
        self,
        session_id: str,
        user_id: str,
        session: AsyncSession | None = None,
    ) -> bool:
        """Return True iff at least one history row exists for (session_id, user_id)."""
        await self._ensure_tables()
        async with use_session(self._sessions, session) as s:
            result = await s.execute(
                select(func.count()).where(
                    SessionHistoryRow.session_id == session_id,
                    SessionHistoryRow.user_id == user_id,
                )
            )
            return (result.scalar() or 0) > 0

    # ------------------------------------------------------------------
    # Rank helper
    # ------------------------------------------------------------------

    async def next_rank(
        self,
        session_id: str,
        session: AsyncSession | None = None,
    ) -> int:
        """
        Return the next available rank for a session (``MAX(rank) + 1``).

        Why this exists:
        - callers must assign consecutive ranks before calling ``save``; querying
          ``MAX(rank)`` here is the authoritative way to avoid gaps or conflicts

        How to use it:
        - call once per turn, before constructing the messages to save
        - if the session has no rows yet, returns 0

        Example:
            base = await store.next_rank(session_id="s1")
            # base = 0 for a new session, or MAX+1 for an existing one
        """
        await self._ensure_tables()
        async with use_session(self._sessions, session) as s:
            result = await s.execute(
                select(func.max(SessionHistoryRow.rank)).where(
                    SessionHistoryRow.session_id == session_id
                )
            )
            max_rank = result.scalar()
        return 0 if max_rank is None else max_rank + 1
