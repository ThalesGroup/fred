# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Shared worker for installed capabilities; no HTTP server or agent loop."""

import asyncio
import hashlib
import logging
import signal
from contextlib import suppress
from datetime import timedelta
from uuid import UUID

import httpx
from fred_core.logs.context import operation_log_scope
from fred_core.logs.log_setup import log_setup
from fred_core.scheduler.temporal_client_provider import TemporalClientProvider
from fred_sdk.contracts.capability.preparation import (
    PreparationContext,
    PreparationWork,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.container import build_pod_container
from fred_runtime.app.security import prepare_authorization
from fred_runtime.capabilities import CapabilityRegistry, boot_capability_registry
from fred_runtime.capabilities.objects import bind_capability_objects
from fred_runtime.capabilities.preparation_workflow import PrepareCapability
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    build_workload_token_provider,
)
from fred_runtime.runtime_support import aclose_token_refresh_client

logger = logging.getLogger(__name__)
# Fred's package entrypoint imports its HTTP client. Keep that import outside
# Temporal's replay sandbox; the workflow itself only schedules one activity.
WORKFLOW_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules("fred_runtime")
)


def failure_summary(error: Exception) -> str:
    """Name a failure without its message: bodies, tokens and files stay out of logs."""
    summary = type(error).__name__
    if isinstance(error, httpx.HTTPStatusError):
        request = error.request
        summary += (
            f" status={error.response.status_code} {request.method} {request.url.path}"
        )
    return summary


class PreparationWorker:
    def __init__(
        self,
        config: AgentPodConfig,
        registry: CapabilityRegistry,
        client: httpx.AsyncClient,
        credentials: DelegationRuntime,
        database: AsyncEngine,
    ) -> None:
        self.config = config
        self.registry = registry
        self.client = client
        self.credentials = credentials
        self.database = database
        self.installation_id: UUID | None = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: object = None,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> httpx.Response:
        base = self.config.platform.control_plane_url
        if not base:
            raise ValueError("Preparation requires a Control Plane URL")
        lease = await self.credentials.workload_token_lease()
        if lease is None:
            raise ValueError("Preparation requires a workload identity")
        async with self.client.stream(
            method,
            f"{base.rstrip('/')}/capability-preparations{path}",
            headers={"Authorization": f"Bearer {lease.token}"},
            follow_redirects=False,
            params=params,
            json=json,
        ) as response:
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes():
                if len(content) + len(chunk) > max_bytes:
                    raise ValueError("Preparation response exceeds its bound")
                content.extend(chunk)
            return httpx.Response(
                response.status_code, content=bytes(content), headers=response.headers
            )

    async def context(self, preparation_id: str) -> PreparationContext:
        identity = str(UUID(preparation_id))
        response = await self.request("GET", f"/{identity}")
        work = PreparationWork.model_validate(response.json())
        if (
            work.installation_id != self.installation_id
            or work.runtime_id != self.config.app.runtime_id
            or str(work.preparation_id) != identity
        ):
            raise ApplicationError("Preparation target mismatch", non_retryable=True)
        if work.capability_id not in self.registry:
            raise ApplicationError("Capability is not installed", non_retryable=True)
        return PreparationContext(work=work, database=self.database, content=b"")

    @activity.defn(name="prepare_capability")
    async def prepare(self, preparation_id: str) -> None:
        with operation_log_scope(operation_id=preparation_id):
            await self._prepare(preparation_id)

    async def _prepare(self, preparation_id: str) -> None:
        # Exceptions entering history never contain HTTP bodies, tokens, configs or files.
        try:
            ctx = await self.context(preparation_id)
            if ctx.work.state != "pending":
                logger.info(
                    "Capability preparation skipped", extra={"state": ctx.work.state}
                )
                return
            logger.info(
                "Capability preparation started",
                extra={"attempt": activity.info().attempt},
            )
            capability = self.registry.capability(ctx.work.capability_id)
            content = await self.request(
                "GET", f"/{ctx.work.preparation_id}/content", max_bytes=ctx.work.size
            )
            if (
                len(content.content) != ctx.work.size
                or hashlib.sha256(content.content).hexdigest() != ctx.work.sha256
            ):
                raise ApplicationError("Preparation file mismatch", non_retryable=True)
            ctx = PreparationContext(
                work=ctx.work, database=ctx.database, content=content.content
            )
            task = asyncio.create_task(capability.prepare(ctx))
            try:
                while not task.done():
                    activity.heartbeat()
                    await asyncio.wait({task}, timeout=20)
                result = task.result()
                # SQL result precedes confirmation. A retry reuses it, then reconfirms.
                await self.request(
                    "POST",
                    f"/{ctx.work.preparation_id}/confirm",
                    json=result.model_dump(),
                )
                logger.info(
                    "Capability preparation confirmed",
                    extra={"outcome": "failed" if result.error else "ready"},
                )
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        except ApplicationError as error:
            logger.warning(
                "Capability preparation refused",
                extra={
                    "error_code": "capability_preparation_refused",
                    "reason": str(error),
                },
            )
            raise
        except Exception as error:
            logger.warning(
                "Capability preparation will be reconciled",
                extra={
                    "error_code": "capability_preparation_interrupted",
                    "reason": failure_summary(error),
                },
            )
            raise ApplicationError("Capability preparation interrupted") from None

    async def _retire(self, identity: str) -> None:
        ctx = await self.context(identity)
        if ctx.work.state != "obsolete":
            return
        await self.registry.capability(ctx.work.capability_id).retire_preparation(ctx)
        await self.request("POST", f"/{ctx.work.preparation_id}/cleaned")

    async def cleanup_once(self) -> None:
        def retrying(identity: str | None, error: Exception) -> None:
            logger.warning(
                "Capability cleanup will retry",
                extra={
                    "operation_id": identity,
                    "error_code": "capability_cleanup_retry",
                    "reason": failure_summary(error),
                },
            )

        try:
            reply = await self.request(
                "GET", "/cleanup", params={"runtime_id": self.config.app.runtime_id}
            )
            identities = reply.json()
        except Exception as error:
            retrying(None, error)
            return
        # A preparation whose erasure stays blocked must not hold back the others.
        for identity in identities:
            try:
                await self._retire(identity)
            except Exception as error:
                retrying(identity, error)

    async def cleanup(self) -> None:
        while True:
            await self.cleanup_once()
            await asyncio.sleep(10)


async def run_preparation_worker(config: AgentPodConfig) -> None:
    # The API's lifespan does not run here.
    log_setup(
        service_name=config.app.runtime_id,
        service_role="worker",
        log_level=config.app.log_level,
        log_format=config.app.log_format,
        use_rich=False,
    )
    if not config.scheduler.enabled:
        raise ValueError("Capability worker requires scheduler.enabled")
    registry = boot_capability_registry()
    container = build_pod_container(config)
    credentials = DelegationRuntime(
        token_provider=build_workload_token_provider(config.security)
    )
    cleanup: asyncio.Task[None] | None = None
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        container.initialize_control_plane_client()
        await prepare_authorization(container, conversations=False)
        engine = container.get_sql_engine()
        if engine is None:
            raise ValueError("Capability worker requires SQL storage")
        await container.initialize_filesystem()
        bind_capability_objects(registry, container.get_filesystem())
        runner = PreparationWorker(
            config,
            registry,
            container.get_control_plane_http_client(),
            credentials,
            engine,
        )
        # The CP binds queue and installation to the authenticated logical pod.
        reply = await runner.request(
            "GET", "/worker", params={"runtime_id": config.app.runtime_id}
        )
        queue = reply.json()["task_queue"]
        runner.installation_id = UUID(reply.json()["installation_id"])
        temporal = await TemporalClientProvider(config.scheduler.temporal).get_client()
        cleanup = asyncio.create_task(runner.cleanup())
        async with Worker(
            temporal,
            task_queue=queue,
            workflows=[PrepareCapability],
            workflow_runner=WORKFLOW_RUNNER,
            activities=[runner.prepare],
            max_concurrent_activities=2,
            graceful_shutdown_timeout=timedelta(seconds=30),
        ):
            logger.info("Preparation worker polling", extra={"task_queue": queue})
            await stop.wait()
    finally:
        if cleanup is not None:
            cleanup.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup
        try:
            await container.shutdown()
        finally:
            await aclose_token_refresh_client()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)
