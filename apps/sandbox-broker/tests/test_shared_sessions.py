"""Integration checks for cross-replica admission on a local PostgreSQL database."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import asyncpg
import pytest
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult
from sandbox_broker.backend import SandboxLease
from sandbox_broker.command import CommandResult
from sandbox_broker.config import BrokerSettings
from sandbox_broker.shared_sessions import SharedConversationPool


@dataclass
class _Kubernetes:
    def _kubectl(self, *args: str) -> list[str]:
        return list(args)


class _Backend:
    def __init__(self) -> None:
        self.kubernetes = _Kubernetes()
        self.runner = self
        self.files: dict[str, str] = {}
        self.prepared = 0
        self.resumed = 0
        self.suspended = 0
        self.active = 0
        self.peak = 0
        self.gate = asyncio.Event()
        self.gate.set()

    async def run(self, *args, **kwargs) -> CommandResult:
        return CommandResult(0, "", "")

    async def preflight(self) -> None:
        return None

    async def prepare(self, view_key: str, *, name: str) -> SandboxLease:
        self.prepared += 1
        return SandboxLease(name, name, view_key)

    async def attach(self, name: str, view_key: str) -> SandboxLease:
        return SandboxLease(name, name, view_key)

    async def resume(self, name: str, view_key: str) -> SandboxLease:
        self.resumed += 1
        return SandboxLease(name, name, view_key)

    async def suspend(self, name: str) -> None:
        self.suspended += 1

    async def renew(self, lease: SandboxLease, seconds: int) -> None:
        return None

    async def execute(
        self, lease: SandboxLease, request: SandboxRequest
    ) -> SandboxResult:
        self.active += 1
        self.peak = max(self.active, self.peak)
        try:
            await self.gate.wait()
            self.files[lease.id] = request.code
            return SandboxResult(exit_code=0, stdout=request.code, stderr="")
        finally:
            self.active -= 1

    async def dispose(self, lease: SandboxLease) -> None:
        self.files.pop(lease.id, None)


@pytest.mark.asyncio
async def test_shared_admission_resume_and_restart() -> None:
    dsn = os.getenv("SANDBOX_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set SANDBOX_TEST_POSTGRES_DSN for PostgreSQL integration")
    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute("TRUNCATE sandbox_conversation_leases CASCADE")
    finally:
        await connection.close()
    config = BrokerSettings(
        backend="agent_sandbox",
        isolation="gvisor",
        runtime_name="gvisor",
        image="python@sha256:" + "a" * 64,
        token="x" * 32,
        network_policy_verified=True,
        pid_limit_verified=True,
        max_sandboxes=1,
        max_preparations=1,
        coordinator_dsn=dsn,
        workspace_storage_class="local-path",
        max_retained_sessions=3,
        queue_wait_seconds=3,
    )
    backend = _Backend()
    first = SharedConversationPool(backend, config)  # type: ignore[arg-type]
    second = SharedConversationPool(backend, config)  # type: ignore[arg-type]
    await first.start()
    await second.start()
    try:
        view = await first.view_key("a" * 64, "c" * 64)
        assert await second.view_key("a" * 64, "c" * 64) == view
        with pytest.raises(SandboxError, match="unauthorized"):
            await second.view_key("a" * 64, "d" * 64)
        backend.gate.clear()
        one = asyncio.create_task(
            first.execute("a" * 64, "c" * 64, SandboxRequest(code="first"))
        )
        await asyncio.sleep(0.1)
        two = asyncio.create_task(
            second.execute("a" * 64, "c" * 64, SandboxRequest(code="second"))
        )
        await asyncio.sleep(0.1)
        assert backend.peak == 1
        backend.gate.set()
        assert (await one).stdout == "first"
        assert (await two).stdout == "second"
        assert backend.peak == 1
        await first.close()
        assert (
            await second.execute("a" * 64, "c" * 64, SandboxRequest(code="third"))
        ).stdout == "third"
        assert backend.prepared == 1
        assert await second.view_key("a" * 64, "c" * 64) == view
        async with second._db().acquire() as db:
            await db.execute(
                "UPDATE sandbox_conversation_leases SET last_used_at=now()-interval '130 seconds' WHERE session_key=$1",
                "a" * 64,
            )
        await second.sweep()
        assert backend.suspended == 1
        assert (
            await second.execute("a" * 64, "c" * 64, SandboxRequest(code="resumed"))
        ).stdout == "resumed"
        assert backend.resumed == 1
        waiting = asyncio.create_task(
            second.execute("b" * 64, "d" * 64, SandboxRequest(code="other"))
        )
        await asyncio.sleep(0.2)
        assert not waiting.done()
        assert backend.prepared == 1
        async with second._db().acquire() as db:
            assert await db.fetchval("SELECT count(*) FROM sandbox_wait_tickets") == 1
            await db.execute(
                "UPDATE sandbox_conversation_leases SET last_used_at=now()-interval '130 seconds' WHERE session_key=$1",
                "a" * 64,
            )
        await second.sweep()
        assert (await waiting).stdout == "other"
        assert backend.prepared == 2
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_admin_cap_is_shared_before_next_admission() -> None:
    dsn = os.getenv("SANDBOX_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set SANDBOX_TEST_POSTGRES_DSN for PostgreSQL integration")
    database = await asyncpg.connect(dsn)
    previous = await database.fetchrow(
        "SELECT * FROM sandbox_settings WHERE id='default'"
    )
    await database.execute("TRUNCATE sandbox_conversation_leases CASCADE")
    await database.execute(
        """INSERT INTO sandbox_settings
           (id,idle_minutes,max_active_sessions,updated_at)
           VALUES ('default',20,2,now())
           ON CONFLICT (id) DO UPDATE SET max_active_sessions=2"""
    )
    config = BrokerSettings(
        backend="agent_sandbox",
        isolation="gvisor",
        runtime_name="gvisor",
        image="python@sha256:" + "a" * 64,
        token="x" * 32,
        network_policy_verified=True,
        pid_limit_verified=True,
        max_sandboxes=2,
        max_preparations=2,
        coordinator_dsn=dsn,
        workspace_storage_class="local-path",
        queue_wait_seconds=1,
    )
    backend = _Backend()
    first = SharedConversationPool(backend, config)  # type: ignore[arg-type]
    second = SharedConversationPool(backend, config)  # type: ignore[arg-type]
    try:
        await first.start()
        await second.start()
        assert (
            await first.execute("e" * 64, "a" * 64, SandboxRequest(code="first"))
        ).stdout == "first"
        await database.execute(
            "UPDATE sandbox_settings SET max_active_sessions=1 WHERE id='default'"
        )
        with pytest.raises(SandboxError, match="busy"):
            await second.execute("f" * 64, "b" * 64, SandboxRequest(code="second"))
        assert backend.prepared == 1
        assert (await second.statistics())["limit"] == 1
    finally:
        await first.close()
        await second.close()
        if previous is None:
            await database.execute("DELETE FROM sandbox_settings WHERE id='default'")
        else:
            await database.execute(
                """UPDATE sandbox_settings SET idle_minutes=$1,
                   max_active_sessions=$2, updated_by=$3, updated_at=$4
                   WHERE id='default'""",
                previous["idle_minutes"],
                previous["max_active_sessions"],
                previous["updated_by"],
                previous["updated_at"],
            )
        await database.close()


@pytest.mark.asyncio
async def test_stale_sweeper_cannot_delete_new_conversation_generation() -> None:
    dsn = os.getenv("SANDBOX_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set SANDBOX_TEST_POSTGRES_DSN for PostgreSQL integration")
    database = await asyncpg.connect(dsn)
    await database.execute("TRUNCATE sandbox_conversation_leases CASCADE")
    config = BrokerSettings(
        backend="agent_sandbox",
        isolation="gvisor",
        runtime_name="gvisor",
        image="python@sha256:" + "a" * 64,
        token="x" * 32,
        network_policy_verified=True,
        pid_limit_verified=True,
        coordinator_dsn=dsn,
        workspace_storage_class="local-path",
    )
    pool = SharedConversationPool(_Backend(), config)  # type: ignore[arg-type]
    await pool.start()
    try:
        old_view = await pool.view_key("a" * 64, "b" * 64)
        await database.execute(
            """UPDATE sandbox_conversation_leases SET state='deleting',
               last_used_at=now()-interval '21 minutes' WHERE session_key=$1""",
            "a" * 64,
        )
        old = await pool._ensure("a" * 64, "b" * 64)
        await pool._sweep_one(old, delete=True)
        new_view = await pool.view_key("a" * 64, "b" * 64)
        assert new_view != old_view
        await pool._sweep_one(old, delete=True)
        assert await pool.view_key("a" * 64, "b" * 64) == new_view
    finally:
        await pool.close()
        await database.close()
