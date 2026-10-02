# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

"""Real owner-lifetime locks; PostgreSQL uses an isolated FRED_TEST_POSTGRES_URL."""

import asyncio
import os
import subprocess
import sys
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import pytest
import pytest_asyncio
from fred_runtime.runtime_support import graph_resume_lock as locks
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

Admission = tuple[locks.GraphResumeLock, locks.GraphResumeLock, str, str]


@pytest_asyncio.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=[pytest.mark.integration, pytest.mark.integration_postgres],
        ),
    ]
)
async def admission(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[Admission]:
    if request.param == "postgresql":
        url = os.environ.get("FRED_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("FRED_TEST_POSTGRES_URL is required")
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'checkpoint.sqlite'}"
    engine = create_async_engine(url)
    other_engine = create_async_engine(url)
    namespace = uuid4().hex
    try:
        yield (
            locks.GraphResumeLock(engine, namespace),
            locks.GraphResumeLock(other_engine, namespace),
            url,
            namespace,
        )
    finally:
        await engine.dispose()
        await other_engine.dispose()


@pytest.mark.asyncio
async def test_live_owner_excludes_only_its_thread_and_exit_releases(
    admission: Admission,
) -> None:
    owner, competitor, _, _ = admission
    async with owner.acquire("thread"):
        with pytest.raises(locks.GraphResumeAlreadyRunningError):
            async with competitor.acquire("thread"):
                pytest.fail("A live owner was superseded")
        async with competitor.acquire("another-thread"):
            pass
    async with competitor.acquire("thread"):
        pass


_OWNER_PROCESS = """
import asyncio, sys
from sqlalchemy.ext.asyncio import create_async_engine
from fred_runtime.runtime_support.graph_resume_lock import GraphResumeLock
async def main():
    engine = create_async_engine(sys.argv[1])
    async with GraphResumeLock(engine, sys.argv[2]).acquire("thread"):
        print("owned", flush=True)
        await asyncio.Event().wait()
asyncio.run(main())
"""


@pytest.mark.asyncio
async def test_process_death_releases_ownership_without_a_timeout(
    admission: Admission,
) -> None:
    _, competitor, url, namespace = admission
    process = subprocess.Popen(
        [sys.executable, "-c", _OWNER_PROCESS, url, namespace],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        ready = await asyncio.wait_for(
            asyncio.to_thread(process.stdout.readline), timeout=15
        )
        assert ready == "owned\n"
        with pytest.raises(locks.GraphResumeAlreadyRunningError):
            async with competitor.acquire("thread"):
                pytest.fail("A live owner was superseded")
        process.kill()
        await asyncio.to_thread(process.wait, timeout=10)
        # PostgreSQL releases when its backend observes the closed connection.
        for attempt in range(40):
            try:
                async with competitor.acquire("thread"):
                    break
            except locks.GraphResumeAlreadyRunningError:
                if attempt == 39:
                    raise
                await asyncio.sleep(0.05)
    finally:
        if process.poll() is None:
            process.kill()
        await asyncio.to_thread(process.wait, timeout=10)
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()


@pytest.mark.asyncio
async def test_cancelled_sqlite_acquisition_closes_a_late_worker_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired = threading.Event()
    finish = threading.Event()
    handles: list[BinaryIO] = []
    original = locks._acquire_file_lock

    def slow_acquire(path: Path) -> BinaryIO:
        handle = original(path)
        handles.append(handle)
        acquired.set()
        assert finish.wait(timeout=5)
        return handle

    monkeypatch.setattr(locks, "_acquire_file_lock", slow_acquire)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cp.sqlite'}")
    lock = locks.GraphResumeLock(engine, "test")

    async def hold() -> None:
        async with lock.acquire("thread"):
            pytest.fail("Cancelled acquisition must not enter")

    pending = asyncio.create_task(hold())
    try:
        assert await asyncio.to_thread(acquired.wait, timeout=5)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        finish.set()
        for _ in range(100):
            if handles[0].closed:
                break
            await asyncio.sleep(0.01)
        assert handles[0].closed
        monkeypatch.setattr(locks, "_acquire_file_lock", original)
        async with lock.acquire("thread"):
            pass
    finally:
        finish.set()
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.integration_postgres
@pytest.mark.asyncio
async def test_postgres_server_timers_do_not_steal_a_long_running_owner() -> None:
    url = os.environ.get("FRED_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FRED_TEST_POSTGRES_URL is required")
    probe = create_async_engine(url)
    try:
        async with probe.connect() as connection:
            version = connection.dialect.server_version_info or ()
    finally:
        await probe.dispose()
    settings = {"idle_in_transaction_session_timeout": "100ms"}
    if version >= (17,):
        settings["transaction_timeout"] = "100ms"
    engine = create_async_engine(url, connect_args={"server_settings": settings})
    namespace = uuid4().hex
    try:
        owner = locks.GraphResumeLock(engine, namespace)
        competitor = locks.GraphResumeLock(engine, namespace)
        async with owner.acquire("thread"):
            await asyncio.sleep(0.3)
            with pytest.raises(locks.GraphResumeAlreadyRunningError):
                async with competitor.acquire("thread"):
                    pytest.fail("A server timer stole a live owner's lock")
        # SET LOCAL must not disable server timers on later pooled work.
        async with engine.connect() as connection:
            for setting in settings:
                assert await connection.scalar(text(f"SHOW {setting}")) == "100ms"
    finally:
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.integration_postgres
@pytest.mark.asyncio
async def test_postgres_pool_reserves_checkpoint_capacity_across_checkpointers() -> (
    None
):
    url = os.environ.get("FRED_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FRED_TEST_POSTGRES_URL is required")
    engine = create_async_engine(url, pool_size=2, max_overflow=0, pool_timeout=1)
    namespace = uuid4().hex
    try:
        owner = locks.GraphResumeLock(engine, namespace)
        competitor = locks.GraphResumeLock(engine, namespace)
        async with owner.acquire("thread"):
            with pytest.raises(locks.UserFacingExecutionError, match="capacity"):
                async with competitor.acquire("another-thread"):
                    pytest.fail("All checkpoint connections were reserved by owners")
            async with engine.begin() as connection:
                assert await connection.scalar(text("SELECT 1")) == 1
        async with competitor.acquire("another-thread"):
            pass
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_memory_sqlite_explicitly_refuses_unguarded_continuation() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        with pytest.raises(RuntimeError, match="file-backed"):
            async with locks.GraphResumeLock(engine, "test").acquire("thread"):
                pytest.fail("An unsupported provider admitted continuation")
    finally:
        await engine.dispose()
