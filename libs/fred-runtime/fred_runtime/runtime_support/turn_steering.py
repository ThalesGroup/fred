"""Bounded SQL queue and turn leases shared by managed chat replicas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fred_core.models.base import JsonColumn
from fred_sdk.contracts.runtime import SteeredUserMessageRuntimeEvent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    case,
    delete,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

_ACTIVE_LEASE = timedelta(seconds=90)
_PAUSED_RETENTION = timedelta(days=30)
_MAX_PENDING = 32
_NO_LEASE = datetime.max.replace(tzinfo=UTC)
_CLEANUP_BATCH = 256
_metadata = MetaData()
_turns = Table(
    "runtime_turn_steering",
    _metadata,
    Column("session_id", String, primary_key=True),
    Column("turn_id", String(128), nullable=False),
    Column("agent_instance_id", String, nullable=False),
    Column("user_id", String, nullable=False),
    Column("team_id", String, nullable=False),
    Column("state", String(16), nullable=False),
    Column("pending", JsonColumn, nullable=False),
    Column("seen", JsonColumn, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
Index("ix_runtime_turn_steering_expires_at", _turns.c.expires_at)


class PendingMessage(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)
    status: Literal["waiting", "offered", "uncertain"] = "offered"
    claim_id: str | None = None


class PendingMessageUpdate(BaseModel):
    request: Literal["enqueue", "edit", "remove", "retry"]
    agent_instance_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    text: str = ""


def _expired(value: datetime, now: datetime) -> bool:
    return value.replace(tzinfo=value.tzinfo or UTC) <= now


def _pending(row: RowMapping) -> list[PendingMessage]:
    return [PendingMessage.model_validate(item) for item in row["pending"]]


def _owned(row: RowMapping, agent: str, user: str, team: str) -> bool:
    return (row["agent_instance_id"], row["user_id"], row["team_id"]) == (
        agent,
        user,
        team,
    )


def _live(row: RowMapping) -> bool:
    return row["state"] in ("active", "resumed", "paused", "graph") and not _expired(
        row["expires_at"], datetime.now(UTC)
    )


class TurnSteeringMailbox:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine

    def configure(self, engine: AsyncEngine | None) -> None:
        self._engine = engine

    def _require_engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Turn steering SQL engine is not configured")
        return self._engine

    async def _row(self, conn: AsyncConnection, session_id: str) -> RowMapping | None:
        return (
            (
                await conn.execute(
                    select(_turns)
                    .where(_turns.c.session_id == session_id)
                    .with_for_update()
                )
            )
            .mappings()
            .first()
        )

    async def _ensure(
        self, conn: AsyncConnection, session: str, agent: str, user: str, team: str
    ) -> RowMapping:
        # Both supported dialects arbitrate first writers through the primary key.
        insert = sqlite_insert if conn.dialect.name == "sqlite" else pg_insert
        await conn.execute(
            insert(_turns)
            .values(
                session_id=session,
                turn_id="",
                agent_instance_id=agent,
                user_id=user,
                team_id=team,
                state="idle",
                pending=[],
                seen=[],
                expires_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=[_turns.c.session_id])
        )
        row = await self._row(conn, session)
        assert row is not None
        return row

    async def _save(
        self, conn: AsyncConnection, session: str, messages: list[PendingMessage]
    ) -> None:
        await conn.execute(
            update(_turns)
            .where(_turns.c.session_id == session)
            .values(
                pending=[message.model_dump() for message in messages],
                expires_at=case(
                    (
                        _turns.c.state == "idle",
                        _NO_LEASE if messages else datetime.now(UTC),
                    ),
                    else_=_turns.c.expires_at,
                ),
            )
        )

    async def messages(
        self, session: str, agent: str, user: str, team: str
    ) -> list[PendingMessage]:
        """Read a queue through any replica; expired offers become waiting again."""
        async with self._require_engine().begin() as conn:
            row = await self._row(conn, session)
            if row is None:
                return []
            if not _owned(row, agent, user, team):
                raise ValueError("queue_owner_mismatch")
            messages = _pending(row)
            if not _live(row):
                for message in messages:
                    if message.status == "offered":
                        message.status = "waiting"
                await self._save(conn, session, messages)
            return messages

    async def modify(
        self,
        session: str,
        agent: str,
        user: str,
        team: str,
        message_id: str,
        text: str,
        action: Literal["enqueue", "edit", "remove", "retry"],
    ) -> list[PendingMessage]:
        """Mutate one entry under its session lock, without replacing other tabs' edits."""
        async with self._require_engine().begin() as conn:
            row = await self._ensure(conn, session, agent, user, team)
            if not _owned(row, agent, user, team):
                raise ValueError("queue_owner_mismatch")
            messages = _pending(row)
            message = next((item for item in messages if item.id == message_id), None)
            if action == "enqueue":
                if message is not None:
                    if message.text != text:
                        raise ValueError("message_identity_conflict")
                elif len(messages) >= _MAX_PENDING:
                    raise ValueError("pending_queue_full")
                else:
                    messages.append(
                        PendingMessage(id=message_id, text=text, status="waiting")
                    )
            elif message is not None:
                if message.status == "offered" and _live(row):
                    raise ValueError("message_is_offered")
                if action == "edit":
                    if message.status != "waiting":
                        raise ValueError("message_is_not_waiting")
                    message.text = text
                elif action == "remove":
                    messages.remove(message)
                elif message.status == "uncertain":
                    if _live(row):
                        raise ValueError("turn_is_active")
                    message.status, message.claim_id = "waiting", None
            await self._save(conn, session, messages)
            return messages

    async def start(
        self,
        session_id: str,
        agent_instance_id: str,
        user_id: str,
        team_id: str,
        turn_id: str,
        *,
        resume: bool = False,
        queued_message_id: str | None = None,
        text: str | None = None,
        steering_enabled: bool = True,
    ) -> str | None:
        if self._engine is None:
            return None
        async with self._require_engine().begin() as conn:
            row = await self._ensure(
                conn, session_id, agent_instance_id, user_id, team_id
            )
            if not _owned(row, agent_instance_id, user_id, team_id):
                return None
            if _live(row) and (
                row["state"] != "paused" or queued_message_id is not None
            ):
                return None
            messages = _pending(row)
            preserve_offers = resume and row["state"] == "paused" and _live(row)
            for message in messages:
                if message.status == "offered":
                    if preserve_offers:
                        message.claim_id = turn_id
                    else:
                        message.status = "waiting"
            if queued_message_id is not None:
                message = next(
                    (item for item in messages if item.id == queued_message_id), None
                )
                if (
                    message is None
                    or messages[0] is not message
                    or message.status != "waiting"
                    or message.text != text
                ):
                    return None
                # Claim before invoking anything. A crash leaves recoverable uncertainty.
                message.status, message.claim_id = "uncertain", turn_id
            await self._save(conn, session_id, messages)
            await conn.execute(
                update(_turns)
                .where(_turns.c.session_id == session_id)
                .values(
                    turn_id=turn_id,
                    state=("resumed" if resume else "active")
                    if steering_enabled
                    else "graph",
                    seen=[],
                    expires_at=datetime.now(UTC) + _ACTIVE_LEASE,
                )
            )
            return turn_id

    async def pause(self, session_id: str, turn_id: str) -> None:
        async with self._require_engine().begin() as conn:
            await conn.execute(
                update(_turns)
                .where(
                    _turns.c.session_id == session_id,
                    _turns.c.turn_id == turn_id,
                    _turns.c.state.in_(("active", "resumed", "graph")),
                )
                .values(
                    state="paused", expires_at=datetime.now(UTC) + _PAUSED_RETENTION
                )
            )

    async def renew(self, session_id: str, turn_id: str) -> None:
        async with self._require_engine().begin() as conn:
            await conn.execute(
                update(_turns)
                .where(
                    _turns.c.session_id == session_id,
                    _turns.c.turn_id == turn_id,
                    _turns.c.state.in_(("active", "resumed", "graph")),
                    _turns.c.expires_at > datetime.now(UTC),
                )
                .values(expires_at=datetime.now(UTC) + _ACTIVE_LEASE)
            )

    async def end(self, session_id: str, turn_id: str, *, paused: bool = False) -> None:
        async with self._require_engine().begin() as conn:
            row = await self._row(conn, session_id)
            if row is None or row["turn_id"] != turn_id:
                return
            if paused:
                await conn.execute(
                    update(_turns)
                    .where(_turns.c.session_id == session_id)
                    .values(
                        state="paused",
                        expires_at=datetime.now(UTC) + _PAUSED_RETENTION,
                    )
                )
            else:
                messages = _pending(row)
                for message in messages:
                    if message.status == "offered":
                        message.status = "waiting"
                if not messages:
                    await conn.execute(
                        delete(_turns).where(_turns.c.session_id == session_id)
                    )
                else:
                    await self._save(conn, session_id, messages)
                    await conn.execute(
                        update(_turns)
                        .where(_turns.c.session_id == session_id)
                        .values(
                            state="idle",
                            expires_at=_NO_LEASE,
                            seen=[],
                        )
                    )

    async def offer(
        self,
        session_id: str,
        agent_instance_id: str,
        user_id: str,
        team_id: str,
        turn_id: str,
        message_id: str,
        text: str,
    ) -> bool:
        if self._engine is None:
            return False
        async with self._require_engine().begin() as conn:
            row = await self._row(conn, session_id)
            if (
                row is None
                or not _owned(row, agent_instance_id, user_id, team_id)
                or row["state"] not in ("active", "resumed")
                or not _live(row)
                or row["turn_id"] != turn_id
            ):
                return False
            messages = _pending(row)
            message = next((item for item in messages if item.id == message_id), None)
            if message is None:
                # Preserve the existing steering endpoint for older clients.
                if len(messages) >= _MAX_PENDING:
                    return False
                message = PendingMessage(id=message_id, text=text, status="waiting")
                messages.append(message)
            if message.status != "waiting":
                return message.claim_id == turn_id
            message.status, message.claim_id = "offered", turn_id
            await self._save(conn, session_id, messages)
            return True

    async def take(self, session_id: str, turn_id: str) -> list[tuple[str, str]]:
        async with self._require_engine().begin() as conn:
            row = await self._row(conn, session_id)
            if (
                row is None
                or row["turn_id"] != turn_id
                or row["state"] not in ("active", "resumed")
                or not _live(row)
            ):
                return []
            messages = _pending(row)
            offered = [item for item in messages if item.status == "offered"]
            for message in offered:
                message.status, message.claim_id = "uncertain", turn_id
            if offered:
                await self._save(conn, session_id, messages)
            return [(item.id, item.text) for item in offered]

    async def delivered(
        self, session_id: str, user_id: str, turn_id: str, ids: set[str]
    ) -> None:
        """Acknowledge only after history persistence, matching the dispatch attempt."""
        if not ids or self._engine is None:
            return
        async with self._require_engine().begin() as conn:
            row = await self._row(conn, session_id)
            if row is None or row["user_id"] != user_id:
                return
            messages = [
                item
                for item in _pending(row)
                if not (
                    item.id in ids
                    and item.status == "uncertain"
                    and item.claim_id == turn_id
                )
            ]
            await self._save(conn, session_id, messages)

    async def purge(self, session_id: str, user_id: str | None = None) -> None:
        if self._engine is None:
            return
        criteria = [_turns.c.session_id == session_id]
        if user_id is not None:
            criteria.append(_turns.c.user_id == user_id)
        async with self._require_engine().begin() as conn:
            await conn.execute(delete(_turns).where(*criteria))

    async def cleanup_expired(self) -> None:
        if self._engine is None:
            return
        async with self._require_engine().begin() as conn:
            rows = (
                (
                    await conn.execute(
                        select(_turns)
                        .where(
                            _turns.c.expires_at <= datetime.now(UTC),
                        )
                        .order_by(_turns.c.expires_at)
                        .limit(_CLEANUP_BATCH)
                        .with_for_update(skip_locked=True)
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                messages = _pending(row)
                if not messages:
                    await conn.execute(
                        delete(_turns).where(_turns.c.session_id == row["session_id"])
                    )
                else:
                    for message in messages:
                        if message.status == "offered":
                            message.status = "waiting"
                    # Park retained messages outside the expiry scan until a new turn.
                    await conn.execute(
                        update(_turns)
                        .where(_turns.c.session_id == row["session_id"])
                        .values(
                            state="idle",
                            expires_at=_NO_LEASE,
                            pending=[message.model_dump() for message in messages],
                            seen=[],
                        )
                    )


turn_steering_mailbox = TurnSteeringMailbox()


class TurnSteeringMiddleware(AgentMiddleware):
    def __init__(self, session_id: str | None, turn_id: str | None = None) -> None:
        super().__init__()
        self._session_id, self._turn_id = session_id, turn_id

    async def abefore_model(self, state, runtime) -> dict | None:
        if not self._session_id or not self._turn_id:
            return None
        messages = await turn_steering_mailbox.take(self._session_id, self._turn_id)
        if not messages:
            return None
        writer = get_stream_writer()
        for message_id, text in messages:
            writer(SteeredUserMessageRuntimeEvent(message_id=message_id, content=text))
        return {"messages": [HumanMessage(content=text) for _, text in messages]}
