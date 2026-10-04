# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

"""Owner-lifetime admission for technical Graph continuations, separate from HITL."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import BinaryIO
from weakref import WeakKeyDictionary

from fred_core.sql.base_sql import advisory_lock_key
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool, Pool, QueuePool

from fred_runtime.execution_errors import UserFacingExecutionError

# Pod-local pool reservations leave connections available for checkpoint writes.
# Shared by checkpointers using the same pool; they do not decide thread ownership.
_POOL_SLOTS: WeakKeyDictionary[Pool, asyncio.Semaphore] = WeakKeyDictionary()


class GraphResumeAlreadyRunningError(UserFacingExecutionError):
    def __init__(self) -> None:
        super().__init__(
            "This Graph execution is already being continued.",
            "Another continuation holds the Graph thread lock.",
        )


def _acquire_file_lock(path: Path) -> BinaryIO:
    """Acquire a local POSIX lock in a worker thread; close releases ownership."""
    import fcntl

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise GraphResumeAlreadyRunningError() from None
    except BaseException:
        handle.close()
        raise
    return handle


def _close_late_lock(task: asyncio.Task[BinaryIO]) -> None:
    """Cancellation must not leak a lock acquired by an unfinished worker."""
    if not task.cancelled() and task.exception() is None:
        task.result().close()


class GraphResumeLock:
    def __init__(self, engine: AsyncEngine, namespace: str) -> None:
        self._engine = engine
        self._namespace = namespace

    @asynccontextmanager
    async def acquire(self, thread_id: str) -> AsyncIterator[None]:
        """Hold admission around a continuation; never wait for another owner."""
        key = f"graph_continue\0{self._namespace}\0{thread_id}"
        if self._engine.dialect.name == "postgresql":
            pool = self._engine.pool
            if isinstance(pool, QueuePool) and pool.size() >= 2:
                slots = _POOL_SLOTS.setdefault(
                    pool, asyncio.Semaphore(pool.size() // 2)
                )
            elif isinstance(pool, NullPool):
                slots = asyncio.Semaphore(1)
            else:
                raise RuntimeError(
                    "Graph continuation requires a PostgreSQL pool of at least "
                    "two connections, or NullPool."
                )
            if slots.locked():
                raise UserFacingExecutionError(
                    "Graph continuation capacity is in use. Retry later.",
                    "Checkpoint connection capacity is reserved for active continuations.",
                )
            async with slots, self._engine.begin() as connection:
                # A long node must not lose admission to idle/transaction timers.
                await connection.execute(
                    text("SET LOCAL idle_in_transaction_session_timeout = 0")
                )
                if (connection.dialect.server_version_info or ()) >= (17,):
                    await connection.execute(text("SET LOCAL transaction_timeout = 0"))
                acquired = await connection.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": advisory_lock_key(key)},
                )
                if not acquired:
                    raise GraphResumeAlreadyRunningError()
                yield
        elif self._engine.dialect.name == "sqlite":
            database = self._engine.url.database
            if (
                not database
                or database == ":memory:"
                or self._engine.url.query.get("uri")
            ):
                raise RuntimeError("Graph continuation requires file-backed SQLite.")
            path = Path(database).resolve()
            lock_path = (
                path.with_name(f"{path.name}.graph-locks")
                / hashlib.sha256(key.encode()).hexdigest()
            )
            acquiring = asyncio.create_task(
                asyncio.to_thread(_acquire_file_lock, lock_path)
            )
            handle: BinaryIO | None = None
            try:
                handle = await asyncio.shield(acquiring)
                yield
            finally:
                if handle is None:
                    acquiring.add_done_callback(_close_late_lock)
                else:
                    handle.close()
            # Never unlink: replacing a locked inode would admit a second owner.
        else:
            raise RuntimeError(
                "Graph continuation admission requires PostgreSQL or file-backed SQLite."
            )
