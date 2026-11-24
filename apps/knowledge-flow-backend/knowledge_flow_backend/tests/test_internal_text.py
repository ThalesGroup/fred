"""Preparation text uses the CP-admitted organization model and bounded inputs."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI

from knowledge_flow_backend.features.text import controller as module

PREPARATION = "9b1c9f71-9b83-4cc8-b8a6-10ffdf989cc1"


def _app(status: int = 200):
    admitted = json.loads((Path(__file__).parents[4] / "libs/fred-sdk/tests/fixtures/inference_admission.json").read_text())
    request = httpx.Request("GET", f"http://cp/capability-preparations/{PREPARATION}/text-admission")
    authority = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(status, json=admitted, request=request)))
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="answer", text="answer")))
    context = SimpleNamespace(
        configuration=SimpleNamespace(control_plane_url="http://cp"), get_authorization_client=lambda: authority, get_document_models=lambda: SimpleNamespace(chat=lambda _admission: model)
    )
    router = APIRouter()
    module.TextController(router, cast(Any, context))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[module.oidc.authenticate_request] = lambda: SimpleNamespace(uid="worker")
    return app, model, authority


@pytest.mark.asyncio
async def test_worker_identity_and_model_are_decided_by_control_plane() -> None:
    app, model, authority = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/internal/text/complete", headers={"Authorization": "Bearer worker"}, json={"preparation_id": PREPARATION, "system": "Role", "user": "Map"})
    assert response.status_code == 200
    assert response.json() == {"text": "answer"}
    assert authority.get.await_args.kwargs["auth"] is None
    assert authority.get.await_args.kwargs["headers"] == {"Authorization": "Bearer worker"}
    assert [message.content for message in model.ainvoke.await_args.args[0]] == ["Role", "Map"]
    app, model, _ = _app(403)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        denied = await client.post("/internal/text/complete", headers={"Authorization": "Bearer wrong-worker"}, json={"preparation_id": PREPARATION, "system": "Role", "user": "Map"})
    assert denied.status_code == 403
    assert model.ainvoke.await_count == 0


@pytest.mark.asyncio
async def test_text_bounds_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    app, model, _ = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        invalid = await client.post("/internal/text/complete", json={"preparation_id": PREPARATION, "system": "", "user": "Map"})
        oversized = await client.post("/internal/text/complete", json={"preparation_id": PREPARATION, "system": "Role", "user": "x" * 64001})
        assert invalid.status_code == oversized.status_code == 422
        assert model.ainvoke.await_count == 0
        monkeypatch.setattr(module, "_TIMEOUT_SECONDS", 0.01)

        async def slow(_messages):
            await asyncio.sleep(1)

        model.ainvoke.side_effect = slow
        timed = await client.post("/internal/text/complete", headers={"Authorization": "Bearer worker"}, json={"preparation_id": PREPARATION, "system": "Role", "user": "Map"})
        assert timed.status_code == 504
