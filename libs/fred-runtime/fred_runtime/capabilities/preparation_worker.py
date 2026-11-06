# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Generic Temporal worker for installed capability preparation hooks."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Mapping
from uuid import UUID

import httpx
from fred_core.filesystem.structures import BaseFilesystem
from fred_core.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
)
from fred_pod.security.oidc_endpoints import resolve_endpoints
from fred_sdk.contracts.capability.preparation import (
    PreparationAsset,
    PreparationContext,
    PreparationResult,
    PreparationWork,
)
from temporalio import activity
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.filesystem_factory import build_runtime_filesystem
from fred_runtime.capabilities.registry import (
    CapabilityRegistry,
    boot_capability_registry,
)
from fred_runtime.capabilities.preparation_workflow import CapabilityPreparationWorkflow
from fred_runtime.capabilities.vision_client import KnowledgeFlowVisionClient

logger = logging.getLogger(__name__)


class WorkerAssetReader:
    def __init__(self, client: httpx.AsyncClient, work: PreparationWork) -> None:
        self._client = client
        self._preparation_id = work.preparation_id
        self._assets = {asset.asset_id: asset for asset in work.assets}

    async def read(self, asset_id: UUID) -> bytes:
        asset: PreparationAsset | None = self._assets.get(asset_id)
        if asset is None:
            raise ValueError("Asset is outside the preparation")
        response = await self._client.get(
            f"/internal/capability-preparations/{self._preparation_id}/assets/{asset_id}"
        )
        response.raise_for_status()
        content = response.content
        if (
            len(content) != asset.size
            or hashlib.sha256(content).hexdigest() != asset.sha256
        ):
            raise ValueError("Preparation asset integrity check failed")
        return content


class WorkerArtifactStore:
    def __init__(
        self, filesystem: BaseFilesystem, preparation_id: UUID, attempt: int
    ) -> None:
        self._filesystem = filesystem
        self.prefix = f"capability-results/{preparation_id}/{attempt}/"
        self._writes = 0
        self._bytes = 0

    def _require_path(self, path: str) -> None:
        if not path.startswith(self.prefix) or ".." in path.split("/"):
            raise ValueError("Artifact path is outside the preparation attempt")

    async def write(self, path: str, content: bytes) -> None:
        self._require_path(path)
        if (
            len(content) > 64 * 1024 * 1024
            or self._writes >= 128
            or self._bytes + len(content) > 256 * 1024 * 1024
        ):
            raise ValueError("Preparation artifacts exceed the bounded output budget")
        self._writes += 1
        self._bytes += len(content)
        await self._filesystem.write(path, content)

    async def read(self, path: str) -> bytes:
        self._require_path(path)
        return await self._filesystem.read(path)

    async def delete(self, path: str) -> None:
        self._require_path(path)
        await self._filesystem.delete(path)

    async def exists(self, path: str) -> bool:
        self._require_path(path)
        return await self._filesystem.exists(path)


class CapabilityPreparationActivities:
    def __init__(
        self,
        registry: CapabilityRegistry,
        client: httpx.AsyncClient,
        filesystem: BaseFilesystem,
        config: AgentPodConfig,
        vision_client: KnowledgeFlowVisionClient | None = None,
    ) -> None:
        self._registry = registry
        self._client = client
        self._filesystem = filesystem
        self._runtime_id = config.app.runtime_id
        self._vision_client = vision_client
        self._semaphores = {
            capability_id: asyncio.Semaphore(
                config.preparation.per_capability_concurrency.get(capability_id, 1)
            )
            for capability_id in registry.ids()
        }

    async def prepare_once(self, preparation_id: str, attempt: int) -> None:
        response = await self._client.post(
            f"/internal/capability-preparations/{preparation_id}/attempts/{attempt}"
        )
        response.raise_for_status()
        work_data = response.json().get("work")
        if work_data is None:
            return
        work = PreparationWork.model_validate(work_data)
        if work.runtime_id != self._runtime_id:
            await self._report_unavailable(preparation_id, work, attempt)
            return
        if work.capability_id not in self._registry:
            await self._report_unavailable(preparation_id, work, attempt)
            return
        capability = self._registry.capability(work.capability_id)
        spec = capability.manifest.preparation
        if spec is None or spec.rules_version != work.rules_version:
            await self._report_unavailable(preparation_id, work, attempt)
            return
        artifacts = WorkerArtifactStore(self._filesystem, work.preparation_id, attempt)
        context = PreparationContext(
            work=work,
            assets=WorkerAssetReader(self._client, work),
            artifacts=artifacts,
            vision=self._vision_client,
        )
        try:
            async with self._semaphores[work.capability_id]:
                result: PreparationResult = await asyncio.wait_for(
                    capability.prepare(context), timeout=spec.timeout_seconds
                )
            if not await artifacts.exists(result.reference):
                raise ValueError("Preparation result artifact is missing")
            completion: Mapping[str, object] = {
                "input_revision": work.input_revision,
                "attempt": attempt,
                "state": "succeeded",
                "result": result.model_dump(mode="json"),
            }
        except Exception as exc:
            if attempt < work.max_attempts:
                raise ApplicationError("Preparation attempt failed") from exc
            logger.warning(
                "Preparation failed: capability=%s error_type=%s",
                work.capability_id,
                type(exc).__name__,
            )
            completion = {
                "input_revision": work.input_revision,
                "attempt": attempt,
                "state": "failed",
                "error_code": "preparation_failed",
                "error_detail": type(exc).__name__,
            }
        result_response = await self._client.post(
            f"/internal/capability-preparations/{preparation_id}/result",
            json=completion,
        )
        result_response.raise_for_status()

    async def _report_unavailable(
        self, preparation_id: str, work: PreparationWork, attempt: int
    ) -> None:
        response = await self._client.post(
            f"/internal/capability-preparations/{preparation_id}/result",
            json={
                "input_revision": work.input_revision,
                "attempt": attempt,
                "state": "failed",
                "error_code": "preparation_rules_unavailable",
            },
        )
        response.raise_for_status()

    @activity.defn(name="prepare_capability")
    async def prepare_capability(self, preparation_id: str) -> None:
        await self.prepare_once(preparation_id, activity.info().attempt)


async def run_preparation_worker(config: AgentPodConfig) -> None:
    if config.platform.control_plane_url is None:
        raise ValueError("Preparation worker needs platform.control_plane_url")
    registry = boot_capability_registry()
    filesystem = await build_runtime_filesystem(config.storage.object_store)
    auth = None
    m2m = config.security.m2m
    if m2m.enabled:
        token_endpoint = resolve_endpoints(
            provider=m2m.provider,
            realm_url=str(m2m.realm_url).rstrip("/"),
            token_url=str(m2m.token_url) if m2m.token_url else None,
        ).token_endpoint
        auth = M2MBearerAuth(
            M2MTokenProvider(
                M2MAuthConfig(
                    keycloak_realm_url=str(m2m.realm_url).rstrip("/"),
                    client_id=m2m.client_id,
                    secret_env=m2m.secret_env_var,
                    scope=m2m.scope,
                    token_url_override=token_endpoint,
                )
            )
        )
    temporal = config.scheduler.temporal
    temporal_client = await Client.connect(
        target_host=temporal.host,
        namespace=temporal.namespace,
        data_converter=pydantic_data_converter,
    )
    async with (
        httpx.AsyncClient(
            base_url=config.platform.control_plane_url.rstrip("/"),
            auth=auth,
            timeout=httpx.Timeout(60.0, connect=5.0),
        ) as http_client,
        httpx.AsyncClient(
            base_url=config.ai.knowledge_flow_url.rstrip("/"),
            auth=auth,
            timeout=httpx.Timeout(50.0, connect=5.0),
        ) as vision_http_client,
    ):
        activities = CapabilityPreparationActivities(
            registry,
            http_client,
            filesystem,
            config,
            KnowledgeFlowVisionClient(vision_http_client),
        )
        worker = Worker(
            client=temporal_client,
            task_queue=f"capability-preparation-{config.app.runtime_id}",
            workflows=[CapabilityPreparationWorkflow],
            activities=[activities.prepare_capability],
            max_concurrent_activities=config.preparation.max_concurrent_jobs,
        )
        logger.info(
            "Capability preparation worker ready: runtime=%s concurrency=%s",
            config.app.runtime_id,
            config.preparation.max_concurrent_jobs,
        )
        await worker.run()
