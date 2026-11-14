"""The Knowledge Flow vector client sends the agent's reranking choice."""

import httpx
import pytest
from fred_runtime.common.kf_vectorsearch_client import VectorSearchClient


@pytest.mark.asyncio
@pytest.mark.parametrize("rerank", [True, False])
async def test_search_request_carries_reranking_choice(
    rerank: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = VectorSearchClient.__new__(VectorSearchClient)
    requests = []

    async def fake_request(**kwargs):
        requests.append(kwargs)
        return httpx.Response(
            200,
            json=[],
            request=httpx.Request("POST", "https://knowledge.example/vector/search"),
        )

    monkeypatch.setattr(client, "_request_with_token_refresh", fake_request)
    assert await client.search(question="query", rerank=rerank) == []
    assert requests[0]["path"] == "/vector/search"
    assert requests[0]["json"]["rerank"] is rerank
