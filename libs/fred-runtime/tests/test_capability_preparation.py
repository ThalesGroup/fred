# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Preparation transport, persistence-before-callback, and replica restart."""

import asyncio
import hashlib
import os
import subprocess
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from _tracer_capability import TracerEchoCapability
from conftest import StaticWorkloadTokens
from fred_runtime.app.preparation_worker import WORKFLOW_RUNNER, PreparationWorker
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.capabilities.preparation_workflow import PrepareCapability
from fred_runtime.common.outbound_credentials import DelegationRuntime
from fred_sdk.contracts.capability.preparation import (
    PreparationContext,
    PreparationResult,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment
from temporalio.worker import Worker


class PreparedTracer(TracerEchoCapability):
    def __init__(self):
        self.calculations = 0

    async def prepare(self, ctx: PreparationContext) -> PreparationResult:
        async with ctx.database.begin() as conn:
            existing = await conn.scalar(
                text("select reference from prepared where id=:id"),
                {"id": str(ctx.work.preparation_id)},
            )
            if existing:
                return PreparationResult(reference=existing)
            self.calculations += 1
            reference = f"result:{ctx.work.preparation_id}"
            await conn.execute(
                text("insert into prepared(id,reference) values(:id,:reference)"),
                {"id": str(ctx.work.preparation_id), "reference": reference},
            )
        return PreparationResult(reference=reference)


@pytest_asyncio.fixture
async def preparation(tmp_path, minimal_config):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'preparation.db'}")
    async with engine.begin() as conn:
        await conn.execute(
            text("create table prepared(id text primary key, reference text not null)")
        )
    minimal_config.platform.control_plane_url = "http://cp.invalid/v1"
    identity = str(uuid4())
    installation = uuid4()
    content = b"private-template-bytes"
    work = dict(
        preparation_id=identity,
        installation_id=str(installation),
        runtime_id="test-pod",
        capability_id="tracer_echo",
        space_id=str(uuid4()),
        agent_instance_id=str(uuid4()),
        configuration_revision=1,
        file_id=str(uuid4()),
        sha256=hashlib.sha256(content).hexdigest(),
        filename="model.pptx",
        size=len(content),
        config={},
        state="pending",
    )
    confirmations = []
    interrupted = asyncio.Event()

    async def cp(request):
        assert request.headers["authorization"] == "Bearer workload-token"
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=content)
        if request.url.path.endswith("/confirm"):
            async with engine.connect() as conn:
                assert await conn.scalar(text("select count(*) from prepared")) == 1
            confirmations.append(request.content)
            if len(confirmations) == 1:
                interrupted.set()
                raise httpx.ReadError(
                    "DO-NOT-RETAIN-secret-token-or-template", request=request
                )
            work["state"] = "ready"
            return httpx.Response(204)
        return httpx.Response(200, json=work)

    client = httpx.AsyncClient(transport=httpx.MockTransport(cp))

    def replica():
        registry = CapabilityRegistry()
        capability = PreparedTracer()
        registry.register(capability)
        worker = PreparationWorker(
            minimal_config,
            registry,
            client,
            DelegationRuntime(token_provider=StaticWorkloadTokens()),
            engine,
        )
        worker.installation_id = installation
        return worker, capability

    yield replica, identity, work, confirmations, interrupted
    await client.aclose()
    await engine.dispose()


@pytest.mark.asyncio
async def test_lost_confirmation_reuses_sql_result_on_another_replica(preparation):
    replica, identity, _, confirmations, _ = preparation
    first, capability = replica()
    with pytest.raises(
        ApplicationError, match="Capability preparation interrupted"
    ) as error:
        await ActivityEnvironment().run(first.prepare, identity)
    assert "secret" not in str(error.value)
    second, restarted = replica()
    await ActivityEnvironment().run(second.prepare, identity)
    assert capability.calculations == 1 and restarted.calculations == 0
    assert len(confirmations) == 2 and confirmations[0] == confirmations[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["runtime_id", "installation_id", "preparation_id"])
async def test_other_pod_or_installation_never_reads_the_file(preparation, field):
    replica, identity, work, confirmations, _ = preparation
    worker, capability = replica()
    work[field] = str(uuid4())
    with pytest.raises(ApplicationError, match="target mismatch"):
        await ActivityEnvironment().run(worker.prepare, identity)
    assert capability.calculations == 0 and confirmations == []


@pytest.mark.asyncio
async def test_obsolete_work_never_starts_calculation(preparation):
    replica, identity, work, confirmations, _ = preparation
    work["state"] = "obsolete"
    worker, capability = replica()
    await ActivityEnvironment().run(worker.prepare, identity)
    assert capability.calculations == 0 and confirmations == []


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("FRED_PREPARATION_TEMPORAL_TEST") != "1",
    reason="explicit disposable Docker Temporal test",
)
@pytest.mark.asyncio
async def test_temporal_survives_worker_restart_without_recalculating(preparation):
    replica, identity, _, confirmations, interrupted = preparation
    name = f"fred-preparation-test-{uuid4().hex}"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-p",
            "127.0.0.1::7233",
            "--entrypoint",
            "temporal",
            "mirror.gcr.io/temporalio/admin-tools:1.28",
            "server",
            "start-dev",
            "--ip",
            "0.0.0.0",
            "--headless",
        ],
        check=True,
        capture_output=True,
    )
    try:
        host = subprocess.check_output(
            ["docker", "port", name, "7233/tcp"], text=True
        ).strip()
        client = None
        for _ in range(40):
            try:
                client = await Client.connect(host)
                break
            except RuntimeError:
                await asyncio.sleep(0.5)
        assert client is not None
        queue = f"capability-test-{uuid4()}"
        first, calculated = replica()
        async with Worker(
            client,
            task_queue=queue,
            workflows=[PrepareCapability],
            workflow_runner=WORKFLOW_RUNNER,
            activities=[first.prepare],
        ):
            handle = await client.start_workflow(
                PrepareCapability.run,
                identity,
                id=f"preparation-{identity}",
                task_queue=queue,
            )
            await asyncio.wait_for(interrupted.wait(), 30)
        second, restarted = replica()
        async with Worker(
            client,
            task_queue=queue,
            workflows=[PrepareCapability],
            workflow_runner=WORKFLOW_RUNNER,
            activities=[second.prepare],
        ):
            await asyncio.wait_for(handle.result(), 150)
        assert calculated.calculations == 1 and restarted.calculations == 0
        assert len(confirmations) == 2 and confirmations[0] == confirmations[1]
        serialized = (await handle.fetch_history()).to_json()
        assert "private-template-bytes" not in serialized
        assert "workload-token" not in serialized and "DO-NOT-RETAIN" not in serialized
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)


@pytest.mark.asyncio
async def test_lost_acknowledgement_after_cp_commit_needs_no_recalculation(preparation):
    replica, identity, work, confirmations, _ = preparation
    first, calculated = replica()
    with pytest.raises(ApplicationError):
        await ActivityEnvironment().run(first.prepare, identity)
    # The CP transaction committed, but its acknowledgement was lost in transport.
    work["state"] = "ready"
    second, restarted = replica()
    await ActivityEnvironment().run(second.prepare, identity)
    assert calculated.calculations == 1 and restarted.calculations == 0
    assert len(confirmations) == 1
