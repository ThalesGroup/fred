# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from hashlib import sha256

from sqlalchemy import false, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from fred_core.history.history_models import ManagedSessionWriteFenceRow as Fence

SESSION_ERASURE_HEADER = "X-Fred-Session-Erasure"


def managed_session_key(session_id: str) -> str:
    return sha256(session_id.encode()).hexdigest()


async def open_managed_session_write_fence(
    session: AsyncSession, session_id: str
) -> bool:
    """Register a managed session before its first execution if it can still write."""
    key = managed_session_key(session_id)
    if await managed_session_writes_allowed(session, key, allow_unregistered=False):
        return True
    insert = (
        pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    )
    await session.execute(
        insert(Fence)
        .values(session_key=key, erased=False)
        .on_conflict_do_nothing(index_elements=[Fence.session_key])
    )
    return await managed_session_writes_allowed(session, key)


async def close_managed_session_write_fence(
    session: AsyncSession, session_id: str
) -> None:
    """Wait for earlier writers and permanently close this conversation's fence."""
    insert = (
        pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    )
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
    *,
    allow_unregistered: bool = True,
) -> bool:
    """Hold a shared lock until the caller commits its content write."""
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
    erased = await connection.scalar(
        select(Fence.erased).where(Fence.session_key == key).with_for_update(read=True)
    )
    return erased is False or (erased is None and allow_unregistered)
