"""Capability routes read only current, authorized preparation artifacts."""

from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from fred_runtime.capabilities.preparation_routes import RuntimePreparationRouteReader


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
            client=client,
            filesystem=Filesystem(),  # type: ignore[arg-type]
            authorization="Bearer person",
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
            client=client,
            filesystem=object(),  # type: ignore[arg-type]
            authorization="Bearer denied",
        )
        with pytest.raises(HTTPException) as error:
            await reader.agent_status("t1", "a1", "example")
        assert error.value.status_code == 403
        with pytest.raises(PermissionError):
            await reader.read_result("capability-results/current/1/inventory.json")
