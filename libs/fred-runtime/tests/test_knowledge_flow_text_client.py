"""The preparation worker calls Knowledge Flow's bounded text endpoint."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fred_runtime.capabilities.text_client import (
    KnowledgeFlowTextClient,
    TextServiceUnavailable,
)


@pytest.mark.asyncio
async def test_text_client_retries_capacity_responses_per_asset(monkeypatch) -> None:
    calls = 0

    async def immediate(_delay: float) -> None:
        return None

    monkeypatch.setattr(
        "fred_runtime.capabilities.text_client.asyncio.sleep", immediate
    )

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429 if calls < 3 else 200, json={"text": "analysis"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        base_url="http://knowledge-flow/knowledge-flow/v1",
    ) as http_client:
        assert (
            await KnowledgeFlowTextClient(
                http_client,
                url="http://knowledge-flow/knowledge-flow/v1",
                preparation_id="preparation",
                credentials=AsyncMock(
                    workload_token_lease=AsyncMock(
                        return_value=SimpleNamespace(token="worker")
                    )
                ),
            ).complete("Role", "Map")
            == "analysis"
        )
    assert calls == 3


@pytest.mark.asyncio
async def test_text_client_uses_internal_endpoint_and_checks_answer() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": "analysis"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle),
        base_url="http://knowledge-flow/knowledge-flow/v1",
    ) as http_client:
        client = KnowledgeFlowTextClient(
            http_client,
            url="http://knowledge-flow/knowledge-flow/v1",
            preparation_id="preparation",
            credentials=AsyncMock(
                workload_token_lease=AsyncMock(
                    return_value=SimpleNamespace(token="worker")
                )
            ),
        )
        assert await client.complete("Role", "Map") == "analysis"
    assert requests[0].url.path == "/knowledge-flow/v1/internal/text/complete"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"text": ""})
        ),
        base_url="http://knowledge-flow/knowledge-flow/v1",
    ) as http_client:
        with pytest.raises(TextServiceUnavailable):
            await KnowledgeFlowTextClient(
                http_client,
                url="http://knowledge-flow/knowledge-flow/v1",
                preparation_id="preparation",
                credentials=AsyncMock(
                    workload_token_lease=AsyncMock(
                        return_value=SimpleNamespace(token="worker")
                    )
                ),
            ).complete("Role", "Map")
