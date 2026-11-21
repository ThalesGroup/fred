"""The preparation worker calls Knowledge Flow's bounded text endpoint."""

import httpx
import pytest
from fred_runtime.capabilities.text_client import (
    KnowledgeFlowTextClient,
    TextServiceUnavailable,
)


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
        client = KnowledgeFlowTextClient(http_client)
        assert await client.complete("Role", "Map") == "analysis"
    assert requests[0].url.path == "/knowledge-flow/v1/internal/text/complete"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"text": ""})
        ),
        base_url="http://knowledge-flow/knowledge-flow/v1",
    ) as http_client:
        with pytest.raises(TextServiceUnavailable):
            await KnowledgeFlowTextClient(http_client).complete("Role", "Map")
