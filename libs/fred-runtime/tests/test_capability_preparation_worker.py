"""Generic preparation activity survives a fresh worker instance."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from fred_sdk.contracts.capability.preparation import (
    PreparationAsset,
    PreparationResult,
    PreparationSpec,
    PreparationWork,
)
from temporalio.exceptions import ApplicationError

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.capabilities.preparation_worker import (
    CapabilityPreparationActivities,
    WorkerAssetReader,
)
from fred_runtime.capabilities.registry import CapabilityRegistry


class MemoryFilesystem:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def write(self, path: str, content: bytes) -> None:
        self.objects[path] = content

    async def exists(self, path: str) -> bool:
        return path in self.objects


class Capability:
    def __init__(self, *, fail: bool = False) -> None:
        self.manifest = SimpleNamespace(
            preparation=PreparationSpec(asset_slots=("source",), rules_version="v1")
        )
        self.fail = fail

    async def prepare(self, context: Any) -> PreparationResult:
        content = await context.assets.read(context.work.assets[0].asset_id)
        if self.fail:
            raise RuntimeError("transient")
        path = (
            f"capability-results/{context.work.preparation_id}/"
            f"{context.work.attempt}/result.bin"
        )
        await context.artifacts.write(path, content.upper())
        return PreparationResult(reference=path, summary="ready")


class Registry:
    def __init__(self, capability: Capability) -> None:
        self._capability = capability

    def ids(self) -> tuple[str, ...]:
        return ("example",)

    def __contains__(self, capability_id: str) -> bool:
        return capability_id == "example"

    def capability(self, capability_id: str) -> Capability:
        assert capability_id == "example"
        return self._capability


@pytest.mark.asyncio
async def test_new_worker_instance_resumes_without_serving_pod_state() -> None:
    asset_id = uuid4()
    preparation_id = uuid4()
    source = b"deck"
    attempts: list[int] = []
    results: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/attempts/1") or request.url.path.endswith(
            "/attempts/2"
        ):
            attempt = int(request.url.path.rsplit("/", 1)[1])
            attempts.append(attempt)
            work = PreparationWork(
                preparation_id=preparation_id,
                owner_kind="agent",
                owner_id="a1",
                runtime_id="fred-agents",
                capability_id="example",
                input_revision="revision-1",
                rules_version="v1",
                attempt=attempt,
                max_attempts=2,
                assets=(
                    PreparationAsset(
                        asset_id=asset_id,
                        slot_key="source",
                        filename="deck.pptx",
                        sha256=hashlib.sha256(source).hexdigest(),
                        size=len(source),
                    ),
                ),
            )
            return httpx.Response(200, json={"work": work.model_dump(mode="json")})
        if request.url.path.endswith(f"/assets/{asset_id}"):
            return httpx.Response(200, content=source)
        if request.url.path.endswith("/result"):
            import json

            results.append(json.loads(request.content))
            return httpx.Response(200, json={"accepted": True})
        return httpx.Response(404)

    config = cast(
        AgentPodConfig,
        SimpleNamespace(
            app=SimpleNamespace(runtime_id="fred-agents"),
            preparation=SimpleNamespace(per_capability_concurrency={}),
        ),
    )
    filesystem = MemoryFilesystem()
    async with httpx.AsyncClient(
        base_url="http://control-plane/control-plane/v1",
        transport=httpx.MockTransport(handler),
    ) as client:
        first = CapabilityPreparationActivities(
            cast(CapabilityRegistry, Registry(Capability(fail=True))),
            client,
            cast(Any, filesystem),
            config,
        )
        with pytest.raises(ApplicationError):
            await first.prepare_once(str(preparation_id), 1)
        second = CapabilityPreparationActivities(
            cast(CapabilityRegistry, Registry(Capability())),
            client,
            cast(Any, filesystem),
            config,
        )
        await second.prepare_once(str(preparation_id), 2)
    assert attempts == [1, 2]
    assert len(results) == 1
    assert results[0]["state"] == "succeeded"
    assert (
        filesystem.objects[f"capability-results/{preparation_id}/2/result.bin"]
        == b"DECK"
    )


@pytest.mark.asyncio
async def test_asset_reader_rejects_corrupt_bytes() -> None:
    asset_id = uuid4()
    work = PreparationWork(
        preparation_id=uuid4(),
        owner_kind="agent",
        owner_id="a1",
        runtime_id="fred-agents",
        capability_id="example",
        input_revision="r1",
        rules_version="v1",
        assets=(
            PreparationAsset(
                asset_id=asset_id,
                slot_key="source",
                filename="deck.pptx",
                sha256=hashlib.sha256(b"good").hexdigest(),
                size=4,
            ),
        ),
    )
    async with httpx.AsyncClient(
        base_url="http://control-plane",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"evil")),
    ) as client:
        with pytest.raises(ValueError, match="integrity"):
            await WorkerAssetReader(client, work).read(asset_id)
