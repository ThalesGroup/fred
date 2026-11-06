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

    async def delete(self, path: str) -> None:
        self.objects.pop(path, None)


class Capability:
    def __init__(self, *, fail: bool = False, fail_after_write: bool = False) -> None:
        self.manifest = SimpleNamespace(
            preparation=PreparationSpec(asset_slots=("source",), rules_version="v1")
        )
        self.fail = fail
        self.fail_after_write = fail_after_write

    async def prepare(self, context: Any) -> PreparationResult:
        content = await context.assets.read(context.work.assets[0].asset_id)
        if self.fail:
            raise RuntimeError("transient")
        path = (
            f"capability-results/{context.work.preparation_id}/"
            f"{context.work.attempt}/result.bin"
        )
        await context.artifacts.write(path, content.upper())
        if self.fail_after_write:
            raise RuntimeError("after-write")
        return PreparationResult(reference=path, summary="ready")


class Registry:
    def __init__(self, capability: Capability, **others: Capability) -> None:
        self._capabilities = {"example": capability, **others}

    def ids(self) -> tuple[str, ...]:
        return tuple(self._capabilities)

    def __contains__(self, capability_id: str) -> bool:
        return capability_id in self._capabilities

    def capability(self, capability_id: str) -> Capability:
        return self._capabilities[capability_id]


class ReverseCapability(Capability):
    def __init__(self) -> None:
        super().__init__()
        self.manifest = SimpleNamespace(
            preparation=PreparationSpec(asset_slots=("source",), rules_version="v2")
        )

    async def prepare(self, context: Any) -> PreparationResult:
        content = await context.assets.read(context.work.assets[0].asset_id)
        path = f"capability-results/{context.work.preparation_id}/{context.work.attempt}/result.bin"
        await context.artifacts.write(path, content[::-1])
        return PreparationResult(reference=path, summary="reversed")


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


@pytest.mark.asyncio
async def test_failed_attempt_removes_unpublished_artifacts() -> None:
    asset_id = uuid4()
    preparation_id = uuid4()
    source = b"deck"
    results: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/attempts/1"):
            work = PreparationWork(
                preparation_id=preparation_id,
                owner_kind="agent",
                owner_id="a1",
                runtime_id="fred-agents",
                capability_id="example",
                input_revision="r1",
                rules_version="v1",
                attempt=1,
                max_attempts=1,
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
        worker = CapabilityPreparationActivities(
            cast(CapabilityRegistry, Registry(Capability(fail_after_write=True))),
            client,
            cast(Any, filesystem),
            config,
        )
        await worker.prepare_once(str(preparation_id), 1)
    assert filesystem.objects == {}
    assert results[0]["state"] == "failed"


@pytest.mark.asyncio
async def test_two_installed_capabilities_use_the_same_worker_path() -> None:
    preparation_ids = {"example": uuid4(), "reverse": uuid4()}
    assets = {"example": uuid4(), "reverse": uuid4()}
    source = b"mixed"
    reported: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/attempts/1"):
            preparation_id = request.url.path.split("/")[-3]
            capability_id = next(
                key
                for key, value in preparation_ids.items()
                if str(value) == preparation_id
            )
            work = PreparationWork(
                preparation_id=preparation_ids[capability_id],
                owner_kind="agent",
                owner_id="a1",
                runtime_id="fred-agents",
                capability_id=capability_id,
                input_revision=f"revision-{capability_id}",
                rules_version="v2" if capability_id == "reverse" else "v1",
                attempt=1,
                assets=(
                    PreparationAsset(
                        asset_id=assets[capability_id],
                        slot_key="source",
                        filename="source.txt",
                        sha256=hashlib.sha256(source).hexdigest(),
                        size=len(source),
                    ),
                ),
            )
            return httpx.Response(200, json={"work": work.model_dump(mode="json")})
        if "/assets/" in request.url.path:
            return httpx.Response(200, content=source)
        if request.url.path.endswith("/result"):
            import json

            reported.append(json.loads(request.content))
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
        worker = CapabilityPreparationActivities(
            cast(
                CapabilityRegistry, Registry(Capability(), reverse=ReverseCapability())
            ),
            client,
            cast(Any, filesystem),
            config,
        )
        for preparation_id in preparation_ids.values():
            await worker.prepare_once(str(preparation_id), 1)
    assert {result["state"] for result in reported} == {"succeeded"}
    assert (
        filesystem.objects[
            f"capability-results/{preparation_ids['example']}/1/result.bin"
        ]
        == b"MIXED"
    )
    assert (
        filesystem.objects[
            f"capability-results/{preparation_ids['reverse']}/1/result.bin"
        ]
        == b"dexim"
    )


@pytest.mark.asyncio
async def test_cleanup_deletes_only_the_leased_preparation_prefix() -> None:
    preparation_id = uuid4()
    claim_id = uuid4()
    completed: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cleanup/claim"):
            assert request.url.params["runtime_id"] == "fred-agents"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "preparation_id": str(preparation_id),
                            "claim_id": str(claim_id),
                        }
                    ]
                },
            )
        if request.url.path.endswith("/cleanup/complete"):
            import json

            completed.append(json.loads(request.content))
            return httpx.Response(200, json={"accepted": True})
        return httpx.Response(404)

    class Filesystem(MemoryFilesystem):
        async def delete(self, path: str) -> None:
            assert path == f"capability-results/{preparation_id}"
            self.objects = {
                key: value
                for key, value in self.objects.items()
                if not key.startswith(path + "/")
            }

    filesystem = Filesystem()
    filesystem.objects = {
        f"capability-results/{preparation_id}/1/result.bin": b"old",
        "capability-results/other/1/result.bin": b"keep",
    }
    config = cast(
        AgentPodConfig,
        SimpleNamespace(
            app=SimpleNamespace(runtime_id="fred-agents"),
            preparation=SimpleNamespace(per_capability_concurrency={}),
        ),
    )
    async with httpx.AsyncClient(
        base_url="http://control-plane/control-plane/v1",
        transport=httpx.MockTransport(handler),
    ) as client:
        worker = CapabilityPreparationActivities(
            cast(CapabilityRegistry, Registry(Capability())),
            client,
            cast(Any, filesystem),
            config,
        )
        assert await worker.cleanup_once() == 1
    assert filesystem.objects == {"capability-results/other/1/result.bin": b"keep"}
    assert completed == [{"claim_id": str(claim_id)}]
