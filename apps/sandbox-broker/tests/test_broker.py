import asyncio
from time import monotonic

import httpx
import pytest
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult
from sandbox_broker.api import create_app
from sandbox_broker.backend import SandboxLease, SandboxPrepareLeak
from sandbox_broker.config import BrokerSettings
from sandbox_broker.pool import OnDemandCapacity
from sandbox_broker.sessions import ConversationPool
from sandbox_broker.settings_sync import SettingsSync


def settings(**overrides):
    data = dict(
        backend="docker",
        isolation="kata",
        runtime_name="kata",
        image="python@sha256:" + "a" * 64,
        token="x" * 32,
        warm_pool_size=0,
        max_sandboxes=1,
        cold_start_on_miss=True,
        pid_limit_verified=True,
    )
    data.update(overrides)
    return BrokerSettings(**data)


class FakeBackend:
    def __init__(self):
        self.prepared = []
        self.disposed = []
        self.requests = []
        self.view_keys = []

    async def preflight(self):
        return None

    async def prepare(self, view_key=None):
        self.view_keys.append(view_key)
        lease = SandboxLease(id=f"sandbox-{len(self.prepared)}", target="target")
        self.prepared.append(lease)
        return lease

    async def execute(self, lease, request):
        self.requests.append((lease, request))
        return SandboxResult(exit_code=0, stdout="ready", stderr="")

    async def dispose(self, lease):
        self.disposed.append(lease)


@pytest.mark.asyncio
async def test_view_key_is_workload_generation_scoped() -> None:
    first = FakeBackend()
    second = FakeBackend()
    views = []
    for backend in (first, second):
        app = create_app(settings(), backend)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            headers = {
                "Authorization": "Bearer " + "x" * 32,
                "X-Fred-Sandbox-Session": "a" * 64,
            }
            response = await client.post("/v1/view-key", headers=headers)
            assert response.status_code == 200
            views.append(response.json()["view_key"])
            assert (
                await client.post(
                    "/v1/execute",
                    headers=headers,
                    json={"language": "bash", "code": "true"},
                )
            ).status_code == 200
            assert backend.view_keys == [views[-1]]
    assert views[0] != views[1]


@pytest.mark.asyncio
async def test_broker_auth_and_execution_contract() -> None:
    fake = FakeBackend()
    app = create_app(settings(), fake)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        assert (
            await client.post("/v1/execute", json={"language": "bash", "code": "pwd"})
        ).status_code == 401
        response = await client.post(
            "/v1/execute",
            headers={"Authorization": "Bearer " + "x" * 32},
            json={"language": "python", "code": "print(1)"},
        )
        assert response.status_code == 200
        assert response.json()["stdout"] == "ready"
        assert fake.requests[0][1].language == "python"
    assert fake.prepared[0] in fake.disposed


@pytest.mark.asyncio
async def test_broker_rejects_large_input_before_backend() -> None:
    fake = FakeBackend()
    app = create_app(settings(), fake)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        response = await client.post(
            "/v1/execute",
            headers={"Authorization": "Bearer " + "x" * 32},
            content=b"x" * 20_001,
        )
        assert response.status_code == 413
        assert fake.requests == []


@pytest.mark.asyncio
async def test_conversation_reuses_workload_and_never_shares_it() -> None:
    fake = FakeBackend()
    config = settings(warm_pool_size=0, cold_start_on_miss=True, max_sandboxes=2)
    app = create_app(config, fake)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        headers = {"Authorization": "Bearer " + "x" * 32}
        body = {"language": "bash", "code": "pwd"}
        for key in ("a" * 64, "a" * 64, "b" * 64):
            response = await client.post(
                "/v1/execute",
                headers={**headers, "X-Fred-Sandbox-Session": key},
                json=body,
            )
            assert response.status_code == 200
        assert fake.requests[0][0] == fake.requests[1][0]
        assert fake.requests[0][0] != fake.requests[2][0]
        assert fake.disposed == []
        assert (await client.get("/healthz")).json()["active_conversations"] == 2
        assert (
            await client.post(
                "/v1/execute",
                headers={**headers, "X-Fred-Sandbox-Session": "bad"},
                json=body,
            )
        ).status_code == 400
    assert len(fake.disposed) == 2


@pytest.mark.asyncio
async def test_conversation_idle_expiry_replaces_workload() -> None:
    fake = FakeBackend()
    pool = OnDemandCapacity(fake, settings(warm_pool_size=0, cold_start_on_miss=True))
    await pool.start()
    sessions = ConversationPool(pool, idle_seconds=1200, max_sessions=1)
    request = SandboxRequest(language="bash", code="pwd")
    await sessions.execute("a", request)
    first_view = fake.view_keys[0]
    sessions._sessions["a"].last_used = monotonic() - 1201
    await sessions.sweep()
    await asyncio.sleep(0)
    await sessions.execute("a", request)
    assert fake.view_keys[1] != first_view
    assert fake.requests[0][0] != fake.requests[1][0]
    assert fake.requests[0][0] in fake.disposed
    await sessions.close()
    await pool.close()


@pytest.mark.asyncio
async def test_failed_retained_workload_is_replaced_on_retry() -> None:
    class DeadBackend(FakeBackend):
        fail_once = True

        async def execute(self, lease, request):
            if self.fail_once:
                self.fail_once = False
                raise SandboxError("backend_failed")
            return await super().execute(lease, request)

    fake = DeadBackend()
    pool = OnDemandCapacity(fake, settings(warm_pool_size=0, cold_start_on_miss=True))
    await pool.start()
    sessions = ConversationPool(pool, max_sessions=1)
    request = SandboxRequest(language="python", code="print(1)")
    with pytest.raises(SandboxError, match="backend_failed"):
        await sessions.execute("same", request)
    for _ in range(100):
        if fake.disposed:
            break
        await asyncio.sleep(0.01)
    assert fake.disposed == [fake.prepared[0]]
    assert (await sessions.execute("same", request)).stdout == "ready"
    assert len(fake.prepared) == 2
    await sessions.close()
    await pool.close()


@pytest.mark.asyncio
async def test_admin_policy_applies_without_redeploy_with_operator_cap() -> None:
    fake = FakeBackend()
    config = settings(
        warm_pool_size=0,
        cold_start_on_miss=True,
        max_sandboxes=2,
        settings_url="https://control-plane.local/control-plane/v1/internal/sandbox-settings",
        settings_token="y" * 32,
    )
    pool = OnDemandCapacity(fake, config)
    await pool.start()
    sessions = ConversationPool(pool, max_sessions=2)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"idle_minutes": 30, "max_active_sessions": 20},
        )

    sync = SettingsSync(config, sessions, httpx.MockTransport(handler))
    await sync.refresh()
    assert seen[0].headers["Authorization"] == "Bearer " + "y" * 32
    assert sessions.idle_seconds == 1800
    assert sessions.max_sessions == 2
    await sync.close()
    await pool.close()


@pytest.mark.asyncio
async def test_admin_policy_does_not_prepare_idle_sandbox() -> None:
    fake = FakeBackend()
    config = settings(
        settings_url="https://control-plane.local/control-plane/v1/internal/sandbox-settings",
        settings_token="y" * 32,
    )
    pool = OnDemandCapacity(fake, config)
    await pool.start()
    sessions = ConversationPool(pool)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"idle_minutes": 30, "max_active_sessions": 1},
        )

    sync = SettingsSync(config, sessions, httpx.MockTransport(handler))
    await sync.refresh()
    assert fake.prepared == []
    assert sessions.idle_seconds == 1800
    await sync.close()
    await pool.close()


@pytest.mark.asyncio
async def test_reducing_active_limit_evicts_oldest_idle_conversation() -> None:
    fake = FakeBackend()
    pool = OnDemandCapacity(
        fake, settings(warm_pool_size=0, cold_start_on_miss=True, max_sandboxes=2)
    )
    await pool.start()
    sessions = ConversationPool(pool, max_sessions=2)
    request = SandboxRequest(language="bash", code="pwd")
    await sessions.execute("old", request)
    await sessions.execute("new", request)
    await sessions.configure(idle_seconds=1200, max_sessions=1)
    assert list(sessions._sessions) == ["new"]
    for _ in range(100):
        if fake.disposed:
            break
        await asyncio.sleep(0.01)
    assert fake.disposed == [fake.prepared[0]]
    await sessions.close()
    await pool.close()


@pytest.mark.asyncio
async def test_reducing_active_limit_retires_inflight_conversation() -> None:
    class SlowBackend(FakeBackend):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.finish = asyncio.Event()

        async def execute(self, lease, request):
            if request.code == "slow":
                self.started.set()
                await self.finish.wait()
            return await super().execute(lease, request)

    fake = SlowBackend()
    pool = OnDemandCapacity(
        fake, settings(warm_pool_size=0, cold_start_on_miss=True, max_sandboxes=2)
    )
    await pool.start()
    sessions = ConversationPool(pool, max_sessions=2)
    running = asyncio.create_task(
        sessions.execute("old", SandboxRequest(language="bash", code="slow"))
    )
    await fake.started.wait()
    await sessions.execute("new", SandboxRequest(language="bash", code="pwd"))
    await sessions.configure(idle_seconds=1200, max_sessions=1)
    assert sessions._sessions["old"].retire
    fake.finish.set()
    assert (await running).stdout == "ready"
    assert list(sessions._sessions) == ["new"]
    await sessions.close()
    await pool.close()


@pytest.mark.asyncio
async def test_on_demand_lease_is_single_use_and_pool_is_bounded() -> None:
    fake = FakeBackend()
    pool = OnDemandCapacity(fake, settings())
    await pool.start()
    first = await pool.acquire()
    with pytest.raises(SandboxError, match="busy"):
        await pool.acquire()
    assert len(fake.prepared) == 1
    await pool.release(first)
    second = await pool.acquire()
    assert second != first
    await pool.release(second)
    await pool.close()
    assert len(fake.prepared) == 2


@pytest.mark.asyncio
async def test_capacity_provisions_on_demand_and_caps_concurrency() -> None:
    fake = FakeBackend()
    pool = OnDemandCapacity(fake, settings(warm_pool_size=0, cold_start_on_miss=True))
    await pool.start()
    assert fake.prepared == []
    lease = await pool.acquire()
    with pytest.raises(SandboxError, match="busy"):
        await pool.acquire()
    await pool.release(lease)
    assert len(fake.prepared) == 1 and fake.disposed == [lease]
    await pool.close()


@pytest.mark.asyncio
async def test_uncertain_prepare_cleanup_keeps_capacity_reserved() -> None:
    class LeakingBackend(FakeBackend):
        async def prepare(self, view_key=None):
            lease = SandboxLease(id="uncertain", target="uncertain")
            self.prepared.append(lease)
            raise SandboxPrepareLeak(lease)

    fake = LeakingBackend()
    pool = OnDemandCapacity(fake, settings(warm_pool_size=0, cold_start_on_miss=True))
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
    pool = OnDemandCapacity(fake, settings(warm_pool_size=0, cold_start_on_miss=True))
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


def test_broker_rejects_preloaded_capacity() -> None:
    with pytest.raises(ValueError, match="provisioned on demand"):
        settings(warm_pool_size=1)
    with pytest.raises(ValueError, match="provisioned on demand"):
        settings(cold_start_on_miss=False)
