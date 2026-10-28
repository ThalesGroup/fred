"""Shared SQL mailbox for managed chat messages offered during a turn."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fred_core.models.base import JsonColumn
from fred_sdk.contracts.runtime import SteeredUserMessageRuntimeEvent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    MetaData,
    String,
    Table,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

_ACTIVE_LEASE = timedelta(seconds=90)
_PAUSED_RETENTION = timedelta(days=30)
_MAX_PENDING = 32
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


def _expired(value: datetime, now: datetime) -> bool:
    return value.replace(tzinfo=value.tzinfo or UTC) <= now


class TurnSteeringMailbox:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine

    def configure(self, engine: AsyncEngine | None) -> None:
        self._engine = engine

    def _require_engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Turn steering SQL engine is not configured")
        return self._engine

    async def start(
        self,
        session_id: str,
        agent_instance_id: str,
        user_id: str,
        team_id: str,
        turn_id: str,
        *,
        resume: bool = False,
    ) -> str | None:
        if self._engine is None:
            return None
        now = datetime.now(UTC)
        try:
            async with self._require_engine().begin() as conn:
                row = (
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
                if row is None:
                    await conn.execute(
                        insert(_turns).values(
                            session_id=session_id,
                            turn_id=turn_id,
                            agent_instance_id=agent_instance_id,
                            user_id=user_id,
                            team_id=team_id,
                            state="resumed" if resume else "active",
                            pending=[],
                            seen=[],
                            expires_at=now + _ACTIVE_LEASE,
                        )
                    )
                    return turn_id
                if row["state"] in ("active", "resumed") and not _expired(
                    row["expires_at"], now
                ):
                    return None
                if (
                    resume
                    and row["state"] == "paused"
                    and not _expired(row["expires_at"], now)
                ):
                    if (
                        row["agent_instance_id"] != agent_instance_id
                        or row["user_id"] != user_id
                        or row["team_id"] != team_id
                    ):
                        return None
                    pending, seen = row["pending"], row["seen"]
                else:
                    pending, seen = [], []
                await conn.execute(
                    update(_turns)
                    .where(_turns.c.session_id == session_id)
                    .values(
                        turn_id=turn_id,
                        agent_instance_id=agent_instance_id,
                        user_id=user_id,
                        team_id=team_id,
                        state="resumed" if resume else "active",
                        pending=pending,
                        seen=seen,
                        expires_at=now + _ACTIVE_LEASE,
                    )
                )
                return turn_id
        except IntegrityError:
            # A concurrent first turn won the session's primary key.
            return None

    async def pause(self, session_id: str, turn_id: str) -> None:
        async with self._require_engine().begin() as conn:
            await conn.execute(
                update(_turns)
                .where(
                    _turns.c.session_id == session_id,
                    _turns.c.turn_id == turn_id,
                    _turns.c.state.in_(("active", "resumed")),
                )
                .values(
                    state="paused",
                    expires_at=datetime.now(UTC) + _PAUSED_RETENTION,
                )
            )

    async def renew(self, session_id: str, turn_id: str) -> None:
        async with self._require_engine().begin() as conn:
            await conn.execute(
                update(_turns)
                .where(
                    _turns.c.session_id == session_id,
                    _turns.c.turn_id == turn_id,
                    _turns.c.state.in_(("active", "resumed")),
                )
                .values(expires_at=datetime.now(UTC) + _ACTIVE_LEASE)
            )

    async def end(self, session_id: str, turn_id: str, *, paused: bool = False) -> None:
        async with self._require_engine().begin() as conn:
            row = (
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
            if row is None or row["turn_id"] != turn_id:
                return
            if paused:
                await conn.execute(
                    update(_turns)
                    .where(_turns.c.session_id == session_id)
                    .values(
                        state="paused", expires_at=datetime.now(UTC) + _PAUSED_RETENTION
                    )
                )
            else:
                await conn.execute(
                    delete(_turns).where(_turns.c.session_id == session_id)
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
            row = (
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
            if (
                row is None
                or row["state"] not in ("active", "resumed")
                or _expired(row["expires_at"], datetime.now(UTC))
                or row["turn_id"] != turn_id
                or row["agent_instance_id"] != agent_instance_id
                or row["user_id"] != user_id
                or row["team_id"] != team_id
            ):
                return False
            if message_id in row["seen"]:
                return True
            if len(row["pending"]) >= _MAX_PENDING:
                return False
            await conn.execute(
                update(_turns)
                .where(_turns.c.session_id == session_id)
                .values(
                    pending=[*row["pending"], {"id": message_id, "text": text}],
                    seen=[*row["seen"], message_id],
                )
            )
            return True

    async def take(self, session_id: str, turn_id: str) -> list[tuple[str, str]]:
        async with self._require_engine().begin() as conn:
            row = (
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
            if (
                row is None
                or row["turn_id"] != turn_id
                or row["state"] not in ("active", "resumed")
                or _expired(row["expires_at"], datetime.now(UTC))
            ):
                return []
            messages = [(item["id"], item["text"]) for item in row["pending"]]
            if messages:
                await conn.execute(
                    update(_turns)
                    .where(_turns.c.session_id == session_id)
                    .values(pending=[])
                )
            return messages

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
            await conn.execute(
                delete(_turns).where(_turns.c.expires_at <= datetime.now(UTC))
            )


turn_steering_mailbox = TurnSteeringMailbox()


class TurnSteeringMiddleware(AgentMiddleware):
    def __init__(self, session_id: str | None, turn_id: str | None = None) -> None:
        super().__init__()
        self._session_id = session_id
        self._turn_id = turn_id

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
