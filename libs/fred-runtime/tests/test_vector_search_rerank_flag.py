"""The Knowledge Flow vector client sends the agent's reranking choice."""

from uuid import UUID

import httpx
import pytest
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DocumentAccessContext
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
    context = DocumentAccessContext(
        space_id=UUID(int=1),
        authorized_space_ids=(UUID(int=1),),
        document_scope=DocumentScope(),
    )
    assert (
        await client.search(question="query", document_context=context, rerank=rerank)
        == []
    )
    assert requests[0]["path"] == "/documents/search"
    assert requests[0]["json"].get("rerank", False) is rerank
