# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Conversation turn ownership, without a connection held during execution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TypeVar
from uuid import uuid4

from fred_core.history.postgres_history_store import dialect_insert
from fred_core.sql import make_session_factory, use_session
from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Uuid,
    delete,
    func,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from fred_runtime.execution_errors import UserFacingExecutionError

logger = logging.getLogger(__name__)
RENEW_INTERVAL_SECONDS = 20
T = TypeVar("T")
ACTIVE_TURN = Table(
    "session_active_turn",
    MetaData(),
    Column(
        "session_id",
        Uuid(as_uuid=False).with_variant(String(), "sqlite"),
        primary_key=True,
    ),
    Column("owner_token", String(32), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)


class ActiveTurnLost(UserFacingExecutionError):
    def __init__(self) -> None:
        super().__init__(
            "This response stopped because its conversation turn expired or was lost. "
            "Wait for any other response to finish, then send your message again."
        )


class ActiveTurnStore:
    """Atomic take/renew/release, using only the database clock."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions = make_session_factory(engine)

    def _now(self):
        return (
            func.clock_timestamp()
            if self.engine.dialect.name == "postgresql"
            else func.datetime("now")
        )

    def _expires(self):
        return (
            self._now() + text("INTERVAL '60 seconds'")
            if self.engine.dialect.name == "postgresql"
            else func.datetime("now", "+60 seconds")
        )

    async def take(self, session_id: str) -> ActiveTurn | None:
        token = uuid4().hex
        stmt = dialect_insert(self.engine)(ACTIVE_TURN).values(
            session_id=session_id, owner_token=token, expires_at=self._expires()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["session_id"],
            set_={"owner_token": token, "expires_at": self._expires()},
            where=ACTIVE_TURN.c.expires_at <= self._now(),
        ).returning(ACTIVE_TURN.c.owner_token)
        async with use_session(self.sessions) as session:
            acquired = await session.scalar(stmt)
        return ActiveTurn(self, session_id, token) if acquired else None

    async def renew(
        self,
        session_id: str,
        token: str,
        session: AsyncSession | AsyncConnection | None = None,
    ) -> bool:
        if session is None:
            async with use_session(self.sessions) as sql:
                return await self.renew(session_id, token, sql)
        return bool(
            await session.scalar(
                update(ACTIVE_TURN)
                .where(
                    ACTIVE_TURN.c.session_id == session_id,
                    ACTIVE_TURN.c.owner_token == token,
                    ACTIVE_TURN.c.expires_at > self._now(),
                )
                .values(expires_at=self._expires())
                .returning(ACTIVE_TURN.c.owner_token)
            )
        )

    async def release(self, session_id: str, token: str) -> None:
        async with use_session(self.sessions) as session:
            await session.execute(
                delete(ACTIVE_TURN).where(
                    ACTIVE_TURN.c.session_id == session_id,
                    ACTIVE_TURN.c.owner_token == token,
                )
            )


class ActiveTurn:
    def __init__(self, store: ActiveTurnStore, session_id: str, token: str) -> None:
        self.store, self.session_id, self.token = store, session_id, token
        self.lost = False
        self._heartbeat: asyncio.Task[None] | None = None
        self.on_lost: Callable[[], None] | None = None
        self._waiting_task: asyncio.Task[object] | None = None
        self._cancelled_task: asyncio.Task[object] | None = None

    def start(self) -> None:
        self._heartbeat = asyncio.create_task(self._keep_alive())

    def check(self) -> None:
        if self.lost:
            raise ActiveTurnLost()

    def _mark_lost(self) -> None:
        self.lost = True
        if self.on_lost is not None:
            self.on_lost()
        task = self._waiting_task
        if (
            task is not None
            and task is not asyncio.current_task()
            and not task.cancelling()
        ):
            self._cancelled_task = task
            task.cancel()

    async def next_event(self, iterator: AsyncIterator[T]) -> T:
        """Wake a blocked engine on lease loss, without cancelling SSE delivery."""
        self.check()
        task = asyncio.current_task()
        self._waiting_task = task
        try:
            event = await anext(iterator)
            self.check()
            return event
        except asyncio.CancelledError:
            if task is not None and self._cancelled_task is task:
                self._cancelled_task = None
                task.uncancel()
                if not task.cancelling():
                    self.check()
            raise
        finally:
            self._waiting_task = None

    async def fence(self, sql: AsyncSession | AsyncConnection) -> None:
        """Serialize a short write transaction with takeover of this exact lease."""
        self.check()
        if not await self.store.renew(self.session_id, self.token, sql):
            self._mark_lost()
            raise ActiveTurnLost()

    async def _keep_alive(self) -> None:
        try:
            while True:
                await asyncio.sleep(RENEW_INTERVAL_SECONDS)
                if not await self.store.renew(self.session_id, self.token):
                    break
        except Exception:
            # Fail closed on an unavailable database too; never log content.
            logger.error("event=active_turn outcome=failed reason=renewal_failed")
        self._mark_lost()
        logger.error("event=active_turn outcome=lost")

    @asynccontextmanager
    async def writing(self) -> AsyncIterator[AsyncSession]:
        self.check()
        async with use_session(self.store.sessions) as session:
            await self.fence(session)
            yield session

    async def release(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            await asyncio.gather(self._heartbeat, return_exceptions=True)
            self._heartbeat = None
        await self.store.release(self.session_id, self.token)
