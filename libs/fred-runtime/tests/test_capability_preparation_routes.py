"""Capability routes read only current, authorized preparation artifacts."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException, Request
from fred_runtime.capabilities import platform_ports
from fred_runtime.capabilities.preparation_routes import RuntimePreparationRouteReader
from fred_runtime.common.outbound_credentials import static_person_provider
from fred_sdk.contracts.runtime import CAPABILITY_PREPARATION_READER_STATE


@pytest.mark.asyncio
async def test_platform_reader_forwards_lowercase_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer person"
        return httpx.Response(200, json={"active": None, "candidate": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        config = SimpleNamespace(
            rebac_engine=None,
            chat_model_factory=None,
            control_plane_url="https://control-plane/control-plane/v1",
            service_name="fred-agents",
            control_plane_http_client=client,
            filesystem=object(),
            preparation_capabilities=("ppt_builder",),
        )
        monkeypatch.setattr(
            platform_ports,
            "get_runtime_context_or_none",
            lambda: SimpleNamespace(config=config),
        )
        monkeypatch.setattr(platform_ports, "platform_model_port", lambda *_: object())
        request = Request(
            {"type": "http", "headers": [(b"authorization", b"bearer person")]}
        )
        platform_ports._bind(request, None, False)
        reader = getattr(request.state, CAPABILITY_PREPARATION_READER_STATE)
        await reader.platform_status("ppt_builder", "template")


@pytest.mark.asyncio
async def test_route_reader_scopes_artifacts_to_control_plane_status() -> None:
    reference = "capability-results/current/1/inventory.json"
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        assert request.url.path.endswith("/teams/t1/agent-instances/a1/preparations")
        return httpx.Response(
            200,
            json={
                "items": [{"capability_id": "example", "result_reference": reference}]
            },
        )

    class Filesystem:
        async def read(self, path: str) -> bytes:
            return path.encode()

        async def exists(self, path: str) -> bool:
            return path.endswith("patterns.pdf")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reader = RuntimePreparationRouteReader(
            control_plane_url="https://control-plane/control-plane/v1",
            runtime_id="fred-agents",
            client=client,
            filesystem=Filesystem(),  # type: ignore[arg-type]
            credentials=static_person_provider("person"),
        )
        with pytest.raises(PermissionError):
            await reader.read_result(reference)
        assert await reader.agent_status("t1", "a1", "example") is not None
        assert await reader.read_result(reference) == reference.encode()
        assert (
            await reader.read_sibling(reference, "patterns.pdf")
            == ("capability-results/current/1/patterns.pdf").encode()
        )
        assert await reader.sibling_exists(reference, "patterns.pdf")
        with pytest.raises(PermissionError):
            await reader.read_result("capability-results/other/1/inventory.json")
        with pytest.raises(ValueError):
            await reader.read_sibling(reference, "../other")
    assert seen == ["Bearer person"]


@pytest.mark.asyncio
async def test_route_reader_does_not_expose_artifacts_after_denial() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(403)),
    ) as client:
        reader = RuntimePreparationRouteReader(
            control_plane_url="https://control-plane/control-plane/v1",
            runtime_id="fred-agents",
            client=client,
            filesystem=object(),  # type: ignore[arg-type]
            credentials=static_person_provider("denied"),
        )
        with pytest.raises(HTTPException) as error:
            await reader.agent_status("t1", "a1", "example")
        assert error.value.status_code == 403
        with pytest.raises(PermissionError):
            await reader.read_result("capability-results/current/1/inventory.json")


@pytest.mark.asyncio
async def test_platform_port_uses_scoped_control_plane_routes() -> None:
    methods: list[tuple[str, str]] = []
    reference = "capability-results/platform/1/inventory.json"

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append((request.method, request.url.path))
        assert request.headers.get("Authorization") == "Bearer manager"
        assert "/fred-agents/ppt_builder/template" in request.url.path
        return httpx.Response(
            200,
            json={"active": {"result_reference": reference}, "candidate": None},
        )

    class Filesystem:
        async def read(self, path: str) -> bytes:
            return path.encode()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        port = RuntimePreparationRouteReader(
            control_plane_url="https://control-plane/control-plane/v1",
            runtime_id="fred-agents",
            client=client,
            filesystem=Filesystem(),  # type: ignore[arg-type]
            credentials=static_person_provider("manager"),
        )
        assert (await port.platform_status("ppt_builder", "template"))["active"]
        assert await port.read_result(reference) == reference.encode()
        await port.upload_platform_candidate(
            "ppt_builder", "template", b"pptx", "template.pptx", {"use_vision": False}
        )
        await port.retry_platform_candidate("ppt_builder", "template")
        await port.refresh_platform_candidate(
            "ppt_builder", "template", {"use_vision": True}
        )
        await port.set_platform_settings("ppt_builder", "template", {"overrides": []})
        await port.reset_platform_selection("ppt_builder", "template")
    assert [method for method, _ in methods] == [
        "GET",
        "PUT",
        "POST",
        "POST",
        "PUT",
        "DELETE",
    ]
