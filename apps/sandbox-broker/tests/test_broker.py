import asyncio
from dataclasses import replace
from time import monotonic

import pytest
from fastapi.testclient import TestClient
from fred_sdk.contracts.sandbox import SandboxError, SandboxResult
from sandbox_broker.api import create_app
from sandbox_broker.backend import SandboxLease, SandboxPrepareLeak
from sandbox_broker.config import BrokerSettings
from sandbox_broker.pool import WarmPool


def settings(**overrides):
    data = dict(
        backend="docker",
        isolation="kata",
        runtime_name="kata",
        image="python@sha256:" + "a" * 64,
        token="x" * 32,
        warm_pool_size=1,
        max_sandboxes=1,
        cold_start_on_miss=False,
        pid_limit_verified=True,
    )
    data.update(overrides)
    return BrokerSettings(**data)


class FakeBackend:
    def __init__(self):
        self.prepared = []
        self.disposed = []
        self.requests = []

    async def preflight(self):
        return None

    async def prepare(self):
        lease = SandboxLease(id=f"sandbox-{len(self.prepared)}", target="target")
        self.prepared.append(lease)
        return lease

    async def execute(self, lease, request):
        self.requests.append((lease, request))
        return SandboxResult(exit_code=0, stdout="ready", stderr="")

    async def dispose(self, lease):
        self.disposed.append(lease)


def test_broker_auth_and_execution_contract() -> None:
    fake = FakeBackend()
    with TestClient(create_app(settings(), fake)) as client:
        assert (
            client.post(
                "/v1/execute", json={"language": "bash", "code": "pwd"}
            ).status_code
            == 401
        )
        response = client.post(
            "/v1/execute",
            headers={"Authorization": "Bearer " + "x" * 32},
            json={"language": "python", "code": "print(1)"},
        )
        assert response.status_code == 200
        assert response.json()["stdout"] == "ready"
        assert fake.requests[0][1].language == "python"
    assert fake.prepared[0] in fake.disposed


def test_broker_rejects_large_input_before_backend() -> None:
    fake = FakeBackend()
    with TestClient(create_app(settings(), fake)) as client:
        response = client.post(
            "/v1/execute",
            headers={"Authorization": "Bearer " + "x" * 32},
            content=b"x" * 20_001,
        )
        assert response.status_code == 413
        assert fake.requests == []


@pytest.mark.asyncio
async def test_warm_lease_is_single_use_and_pool_is_bounded() -> None:
    fake = FakeBackend()
    pool = WarmPool(fake, settings())
    await pool.start()
    first = await pool.acquire()
    with pytest.raises(SandboxError, match="busy"):
        await pool.acquire()
    assert len(fake.prepared) == 1
    await pool.release(first)
    for _ in range(20):
        if pool.ready_count:
            break
        await asyncio.sleep(0.01)
    second = await pool.acquire()
    assert second != first
    await pool.release(second)
    await pool.close()
    assert len(fake.prepared) <= 3


@pytest.mark.asyncio
async def test_idle_lease_is_replaced_before_workload_deadline() -> None:
    fake = FakeBackend()
    pool = WarmPool(fake, settings())
    await pool.start()
    old = pool._ready.get_nowait()
    expired = replace(old, prepared_at=monotonic() - 3001)
    pool._ready.put_nowait(expired)
    pool._wake.set()
    for _ in range(100):
        if expired in fake.disposed and pool.ready_count:
            break
        await asyncio.sleep(0.01)
    assert expired in fake.disposed
    assert (await pool.acquire()).id != old.id
    await pool.close()


@pytest.mark.asyncio
async def test_zero_idle_pool_provisions_on_demand_and_caps_concurrency() -> None:
    fake = FakeBackend()
    pool = WarmPool(fake, settings(warm_pool_size=0, cold_start_on_miss=True))
    await pool.start()
    assert pool.ready_count == 0 and fake.prepared == []
    lease = await pool.acquire()
    with pytest.raises(SandboxError, match="busy"):
        await pool.acquire()
    await pool.release(lease)
    assert len(fake.prepared) == 1 and fake.disposed == [lease]
    await pool.close()


@pytest.mark.asyncio
async def test_uncertain_prepare_cleanup_keeps_capacity_reserved() -> None:
    class LeakingBackend(FakeBackend):
        async def prepare(self):
            lease = SandboxLease(id="uncertain", target="uncertain")
            self.prepared.append(lease)
            raise SandboxPrepareLeak(lease)

    fake = LeakingBackend()
    pool = WarmPool(fake, settings(warm_pool_size=0, cold_start_on_miss=True))
    await pool.start()
    with pytest.raises(SandboxPrepareLeak):
        await pool.acquire()
    assert pool.allocated_count == 1
    with pytest.raises(SandboxError, match="busy"):
        await pool.acquire()
    await pool._retry_leaked()
    assert pool.allocated_count == 0
    await pool.close()


@pytest.mark.asyncio
async def test_failed_disposal_retries_before_releasing_capacity() -> None:
    class FlakyBackend(FakeBackend):
        fail_once = True

        def __init__(self):
            super().__init__()
            self.retry_started = asyncio.Event()
            self.allow_retry = asyncio.Event()

        async def dispose(self, lease):
            if self.fail_once:
                self.fail_once = False
                raise RuntimeError("transient delete error")
            self.retry_started.set()
            await self.allow_retry.wait()
            await super().dispose(lease)

    fake = FlakyBackend()
    pool = WarmPool(fake, settings(warm_pool_size=0, cold_start_on_miss=True))
    await pool.start()
    lease = await pool.acquire()
    await pool.release(lease)
    await asyncio.wait_for(fake.retry_started.wait(), timeout=1)
    assert pool.allocated_count == 1
    with pytest.raises(SandboxError, match="busy"):
        await pool.acquire()
    fake.allow_retry.set()
    for _ in range(100):
        if pool.allocated_count == 0:
            break
        await asyncio.sleep(0.01)
    assert fake.disposed == [lease]
    assert pool.allocated_count == 0
    await pool.close()


@pytest.mark.asyncio
async def test_agent_sandbox_uses_external_ready_capacity() -> None:
    class ExternalPoolBackend(FakeBackend):
        ready = 0

        async def warm_state(self):
            return self.ready, 1

    fake = ExternalPoolBackend()
    pool = WarmPool(
        fake,
        settings(
            backend="agent_sandbox",
            warm_pool_size=0,
            cold_start_on_miss=False,
            network_policy_verified=True,
        ),
    )
    await pool.start()
    with pytest.raises(SandboxError, match="busy"):
        await pool.acquire()
    assert fake.prepared == []
    fake.ready = 1
    lease = await pool.acquire()
    assert len(fake.prepared) == 1
    await pool.release(lease)
    await pool.close()


@pytest.mark.asyncio
async def test_external_ready_probe_reserves_capacity_before_await() -> None:
    class SlowExternalPool(FakeBackend):
        def __init__(self):
            super().__init__()
            self.probing = asyncio.Event()
            self.continue_probe = asyncio.Event()

        async def warm_state(self):
            self.probing.set()
            await self.continue_probe.wait()
            return 1, 1

    fake = SlowExternalPool()
    pool = WarmPool(
        fake,
        settings(
            backend="agent_sandbox",
            warm_pool_size=0,
            cold_start_on_miss=False,
            network_policy_verified=True,
        ),
    )
    await pool.start()
    first = asyncio.create_task(pool.acquire())
    await fake.probing.wait()
    with pytest.raises(SandboxError, match="busy"):
        await pool.acquire()
    fake.continue_probe.set()
    await pool.release(await first)
    await pool.close()


def test_kubernetes_requires_operator_network_verification() -> None:
    with pytest.raises(ValueError, match="NetworkPolicy enforcement"):
        settings(backend="kubernetes", runtime_name="kata-qemu")


def test_kubernetes_requires_operator_pid_limit_verification() -> None:
    with pytest.raises(ValueError, match="pod PID limit"):
        settings(
            backend="kubernetes",
            runtime_name="kata-qemu",
            network_policy_verified=True,
            pid_limit_verified=False,
        )
