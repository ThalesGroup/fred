# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Durable ownership and outstanding operations for conversation object files.

SQL content belongs to the Control Plane root through foreign keys. Object I/O
cannot join that transaction: its manifest prevents root deletion until erasure,
and an unacknowledged operation remains pending indefinitely, including crashes.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    MetaData,
    Table,
    Uuid,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

_metadata = MetaData()
# Reference-only metadata; migrations never own the Control Plane table.
Table(
    "session_metadata",
    _metadata,
    Column("session_id", Uuid, primary_key=True),
    schema="control_plane",
)
_fences = Table(
    "runtime_session_filesystem",
    _metadata,
    Column(
        "session_id",
        Uuid(as_uuid=False),
        ForeignKey(
            "control_plane.session_metadata.session_id",
            name="runtime_session_filesystem_root_fk",
            ondelete="CASCADE",
        ),
        primary_key=True,
    ),
    Column("closed", Boolean, nullable=False, server_default="false"),
)
_writes = Table(
    "runtime_session_file_write",
    _metadata,
    Column("token", Uuid(as_uuid=False), primary_key=True),
    Column(
        "session_id",
        Uuid(as_uuid=False),
        ForeignKey(
            "control_plane.session_metadata.session_id",
            name="runtime_session_file_write_root_fk",
            ondelete="RESTRICT",
        ),
        nullable=False,
    ),
    Column("pending", Boolean, nullable=False),
    CheckConstraint(
        "(NOT pending AND token = session_id) OR (pending AND token <> session_id)",
        name="runtime_session_file_write_kind_check",
    ),
)
Index("runtime_session_file_write_session_idx", _writes.c.session_id)
_ROOT_FK = "runtime_session_filesystem_root_fk"


class SessionPurgedError(RuntimeError):
    """This conversation permanently stopped accepting object writes."""


class SessionWritesPending(RuntimeError):
    """An external write has not been acknowledged; erasure cannot complete."""


class SessionFence:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def _lock(self, conn: AsyncConnection, session_id: str) -> bool:
        # The FK rejects creation after root deletion. ON CONFLICT plus the row
        # lock serializes the very first write with closure across all replicas.
        await conn.execute(
            pg_insert(_fences)
            .values(session_id=session_id, closed=False)
            .on_conflict_do_nothing(index_elements=["session_id"])
        )
        return bool(
            await conn.scalar(
                select(_fences.c.closed)
                .where(_fences.c.session_id == session_id)
                .with_for_update()
            )
        )

    async def _manifest(self, conn: AsyncConnection, session_id: str) -> None:
        # One durable content marker survives every completed write. Unlike an
        # operation token it is removed only after the whole prefix is erased.
        marker = await conn.scalar(
            pg_insert(_writes)
            .values(token=session_id, session_id=session_id, pending=False)
            .on_conflict_do_update(
                index_elements=["token"],
                set_={"pending": False},
                where=(_writes.c.session_id == session_id)
                & _writes.c.pending.is_(False),
            )
            .returning(_writes.c.token)
        )
        if marker is None:
            raise RuntimeError("session_filesystem_manifest_conflict")

    async def begin_filesystem_write(self, session_id: str) -> str:
        token = str(uuid4())
        async with self.engine.begin() as conn:
            if await self._lock(conn, session_id):
                raise SessionPurgedError("conversation_purged")
            await self._manifest(conn, session_id)
            await conn.execute(
                insert(_writes).values(token=token, session_id=session_id, pending=True)
            )
        return token

    async def end_filesystem_write(self, token: str) -> None:
        # No timeout or lease expiry proves that a remote PUT stopped taking
        # effect. Only the actual successful result acknowledges its operation.
        async with self.engine.begin() as conn:
            await conn.execute(
                delete(_writes).where(_writes.c.token == token, _writes.c.pending)
            )

    async def _pending(self, conn: AsyncConnection, session_id: str) -> bool:
        return (
            await conn.scalar(
                select(_writes.c.token)
                .where(_writes.c.session_id == session_id, _writes.c.pending)
                .limit(1)
            )
        ) is not None

    async def close(self, session_id: str) -> None:
        try:
            async with self.engine.begin() as conn:
                await self._lock(conn, session_id)
                await self._manifest(conn, session_id)
                await conn.execute(
                    update(_fences)
                    .where(_fences.c.session_id == session_id)
                    .values(closed=True)
                )
                pending = await self._pending(conn, session_id)
        except IntegrityError as exc:
            # A repeated purge after CP deleted the root is already closed by
            # the FK. Match only this named constraint, never a general failure.
            cause = getattr(exc.orig, "__cause__", None)
            if (
                getattr(exc.orig, "sqlstate", None) == "23503"
                and getattr(cause, "constraint_name", None) == _ROOT_FK
            ):
                return
            raise
        # Commit closure even when an uncertain external operation remains.
        if pending:
            raise SessionWritesPending("session_writes_pending")

    async def acknowledge_purge(self, session_id: str) -> None:
        """Release the root restriction only after successful object erasure."""
        async with self.engine.begin() as conn:
            closed = await conn.scalar(
                select(_fences.c.closed)
                .where(_fences.c.session_id == session_id)
                .with_for_update()
            )
            if closed is None:
                return  # The root has already cascaded this closure row.
            if not closed:
                raise RuntimeError("session_filesystem_not_closed")
            if await self._pending(conn, session_id):
                raise SessionWritesPending("session_writes_pending")
            await conn.execute(
                delete(_writes).where(
                    _writes.c.session_id == session_id, _writes.c.pending.is_(False)
                )
            )
            # Keep closed until CP cascades it. A late run cannot recreate the
            # content marker in the interval before the root's final deletion.
