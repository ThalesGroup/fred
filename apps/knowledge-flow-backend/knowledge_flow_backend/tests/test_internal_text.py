"""Knowledge Flow bounds worker text analysis and checks its service identity."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI

from knowledge_flow_backend.features.text import controller as text_controller
from knowledge_flow_backend.features.text.controller import TextController


def _app(client_id: str = "agentic"):
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="answer")))
    context = SimpleNamespace(
        configuration=SimpleNamespace(
            preparation_worker_client_id="agentic",
            security=SimpleNamespace(m2m=SimpleNamespace(enabled=True)),
        ),
        get_utility_model=lambda: model,
    )
    router = APIRouter()
    TextController(router, cast(Any, context))
    app = FastAPI()
    app.include_router(router)

    async def principal():
        return SimpleNamespace(caller=SimpleNamespace(client_id=client_id))

    app.dependency_overrides[text_controller._worker_principal_context] = principal
    return app, model


@pytest.mark.asyncio
async def test_only_preparation_worker_can_call_text_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(text_controller, "is_service_agent", lambda _caller: True)
    app, model = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/internal/text/complete", json={"system": "Role", "user": "Map"})
    assert response.status_code == 200
    assert response.json() == {"text": "answer"}
    assert [message.content for message in model.ainvoke.await_args.args[0]] == ["Role", "Map"]

    bad_app, _ = _app("other")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(bad_app), base_url="http://test") as client:
        response = await client.post("/internal/text/complete", json={"system": "Role", "user": "Map"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_text_model_bounds_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(text_controller, "is_service_agent", lambda _caller: True)
    app, model = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        invalid = await client.post("/internal/text/complete", json={"system": "", "user": "Map"})
        oversized = await client.post("/internal/text/complete", json={"system": "Role", "user": "x" * 64_001})
    assert invalid.status_code == oversized.status_code == 422
    assert model.ainvoke.await_count == 0

    monkeypatch.setattr(text_controller, "_TIMEOUT_SECONDS", 0.01)

    async def slow(_messages):
        await asyncio.sleep(1)

    model.ainvoke.side_effect = slow
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        timeout = await client.post("/internal/text/complete", json={"system": "Role", "user": "Map"})
    assert timeout.status_code == 504
