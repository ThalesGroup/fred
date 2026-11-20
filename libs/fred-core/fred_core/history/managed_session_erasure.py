# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from hashlib import sha256

from sqlalchemy import false, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from fred_core.history.history_models import ManagedSessionWriteFenceRow as Fence

SESSION_ERASURE_HEADER = "X-Fred-Session-Erasure"


class ManagedSessionWriteBusy(ValueError):
    def __init__(self) -> None:
        super().__init__("session_write_busy")


async def _limit_lock_wait(session: AsyncSession) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SET LOCAL lock_timeout = '1s'"))


def managed_session_key(session_id: str) -> str:
    return sha256(session_id.encode()).hexdigest()


async def open_managed_session_write_fence(
    session: AsyncSession, session_id: str
) -> bool:
    """Register a managed session before its first execution if it can still write."""
    key = managed_session_key(session_id)
    erased = await _read_managed_session_fence(session, key)
    if erased is not None:
        return not erased
    insert = (
        pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    )
    await _limit_lock_wait(session)
    try:
        await session.execute(
            insert(Fence)
            .values(session_key=key, erased=False)
            .on_conflict_do_nothing(index_elements=[Fence.session_key])
        )
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            raise ManagedSessionWriteBusy() from exc
        raise
    return await managed_session_writes_allowed(session, key)


async def close_managed_session_write_fence(
    session: AsyncSession, session_id: str
) -> None:
    """Wait for earlier writers and permanently close this conversation's fence."""
    insert = (
        pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    )
    await _limit_lock_wait(session)
    await session.execute(
        insert(Fence)
        .values(session_key=managed_session_key(session_id), erased=True)
        .on_conflict_do_update(
            index_elements=[Fence.session_key], set_={"erased": True}
        )
    )


async def managed_session_writes_allowed(
    connection: AsyncSession | AsyncConnection,
    key: str,
) -> bool:
    """Hold a shared lock until the caller commits its content write."""
    return await _read_managed_session_fence(connection, key) is not True


async def _read_managed_session_fence(
    connection: AsyncSession | AsyncConnection, key: str
) -> bool | None:
    dialect = (
        connection.get_bind().dialect
        if isinstance(connection, AsyncSession)
        else connection.dialect
    )
    if dialect.name == "sqlite":
        # SQLite serializes writers instead of supporting SELECT FOR SHARE.
        await connection.execute(
            update(Fence).where(false()).values(erased=Fence.erased)
        )
    try:
        return await connection.scalar(
            select(Fence.erased)
            .where(Fence.session_key == key)
            .with_for_update(read=True, nowait=True)
        )
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            raise ManagedSessionWriteBusy() from exc
        raise
