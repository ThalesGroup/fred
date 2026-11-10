"""Knowledge Flow owns the configured vision call and its workload boundary."""

import asyncio
import io
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fred_core import get_current_user, get_current_user_or_service, get_current_user_without_gcu
from PIL import Image

from knowledge_flow_backend.features.vision import controller as vision_controller
from knowledge_flow_backend.features.vision.controller import VisionController


def _png() -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (2, 2)).save(stream, format="PNG")
    return stream.getvalue()


def _app(*, configured: bool = True, client_id: str = "agentic"):
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="answer")))
    context = SimpleNamespace(
        configuration=SimpleNamespace(
            vision_model=object() if configured else None,
            vision_worker_client_id="agentic",
            security=SimpleNamespace(m2m=SimpleNamespace(enabled=True)),
        ),
        get_vision_model=lambda: model,
    )
    router = APIRouter()
    VisionController(router, cast(Any, context))
    app = FastAPI()
    app.include_router(router)

    async def principal():
        return SimpleNamespace(caller=SimpleNamespace(client_id=client_id))

    async def current_user():
        return object()

    app.dependency_overrides[vision_controller._worker_principal_context] = principal
    app.dependency_overrides[get_current_user_without_gcu] = current_user
    return app, model


@pytest.mark.asyncio
async def test_worker_identity_bypasses_human_gcu_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = _app()
    del app.dependency_overrides[vision_controller._worker_principal_context]

    async def service_subject():
        return object()

    async def human_gcu_gate():
        raise AssertionError("Service requests must not enter the human GCU gate")

    async def principal(_request, _subject):
        return SimpleNamespace(caller=SimpleNamespace(client_id="agentic"))

    app.dependency_overrides[get_current_user_or_service] = service_subject
    app.dependency_overrides[get_current_user] = human_gcu_gate
    monkeypatch.setattr(vision_controller, "get_principal_context", principal)
    monkeypatch.setattr(vision_controller, "is_service_agent", lambda _caller: True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post(
            "/internal/vision/describe",
            data={"prompt": "Identify numbered slots"},
            files={"image": ("slide.png", _png(), "image/png")},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_only_configured_worker_can_describe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "knowledge_flow_backend.features.vision.controller.is_service_agent",
        lambda caller: True,
    )
    app, model = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post(
            "/internal/vision/describe",
            data={"prompt": "Identify numbered slots"},
            files={"image": ("slide.png", _png(), "image/png")},
        )
        assert response.status_code == 200
        assert response.json() == {"text": "answer"}
        assert model.ainvoke.await_count == 1
        bad_app, _ = _app(client_id="other")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(bad_app), base_url="http://test") as bad:
            forbidden = await bad.post(
                "/internal/vision/describe",
                data={"prompt": "Identify numbered slots"},
                files={"image": ("slide.png", _png(), "image/png")},
            )
            assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_availability_and_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "knowledge_flow_backend.features.vision.controller.is_service_agent",
        lambda caller: True,
    )
    app, _ = _app(configured=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        assert (await client.get("/vision/availability")).json() == {"available": False}
        unavailable = await client.post(
            "/internal/vision/describe",
            data={"prompt": "Describe"},
            files={"image": ("slide.png", _png(), "image/png")},
        )
        assert unavailable.status_code == 503
    app, _ = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        assert (await client.get("/vision/availability")).json() == {"available": True}
        invalid = await client.post(
            "/internal/vision/describe",
            data={"prompt": "Describe"},
            files={"image": ("slide.png", b"invalid", "image/png")},
        )
        assert invalid.status_code == 422
        oversized_prompt = await client.post(
            "/internal/vision/describe",
            data={"prompt": "x" * 16_001},
            files={"image": ("slide.png", _png(), "image/png")},
        )
        assert oversized_prompt.status_code == 422
        monkeypatch.setattr("knowledge_flow_backend.features.vision.controller._MAX_IMAGE_BYTES", 8)
        oversized_image = await client.post(
            "/internal/vision/describe",
            data={"prompt": "Describe"},
            files={"image": ("slide.png", _png(), "image/png")},
        )
        assert oversized_image.status_code == 413


@pytest.mark.asyncio
async def test_model_timeout_and_capacity_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "knowledge_flow_backend.features.vision.controller.is_service_agent",
        lambda caller: True,
    )
    monkeypatch.setattr("knowledge_flow_backend.features.vision.controller._TIMEOUT_SECONDS", 0.01)
    app, model = _app()

    async def slow(_messages):
        await asyncio.sleep(1)

    model.ainvoke.side_effect = slow
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        timeout = await client.post(
            "/internal/vision/describe",
            data={"prompt": "Describe"},
            files={"image": ("slide.png", _png(), "image/png")},
        )
        assert timeout.status_code == 504

    monkeypatch.setattr("knowledge_flow_backend.features.vision.controller._TIMEOUT_SECONDS", 1)
    monkeypatch.setattr("knowledge_flow_backend.features.vision.controller._CAPACITY_WAIT_SECONDS", 0.01)
    app, model = _app()
    started = asyncio.Event()
    release = asyncio.Event()

    async def waiting(_messages):
        started.set()
        await release.wait()
        return SimpleNamespace(content="answer")

    model.ainvoke.side_effect = waiting
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        first = [
            asyncio.create_task(
                client.post(
                    "/internal/vision/describe",
                    data={"prompt": "Describe"},
                    files={"image": ("slide.png", _png(), "image/png")},
                )
            )
            for _ in range(4)
        ]
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.sleep(0.02)
        saturated = await client.post(
            "/internal/vision/describe",
            data={"prompt": "Describe"},
            files={"image": ("slide.png", _png(), "image/png")},
        )
        assert saturated.status_code == 429
        release.set()
        assert all(result.status_code == 200 for result in await asyncio.gather(*first))
