"""Offline checks for the shared Knowledge Flow reranker."""

import asyncio
import json
import time

import httpx
import pytest

from knowledge_flow_backend.common.structures import RerankerModelConfiguration
from knowledge_flow_backend.features.vector_search.reranker import (
    MAX_RERANK_BODY_BYTES,
    DocumentReranker,
    RerankerUnavailable,
)


def _remote() -> RerankerModelConfiguration:
    return RerankerModelConfiguration.model_validate(
        {
            "provider": "rerank",
            "name": "remote-reranker",
            "settings": {"base_url": "https://models.example/v1", "api_key_env": "TEST_RERANKER_KEY"},
        }
    )


@pytest.mark.asyncio
async def test_remote_rerank_uses_indexed_results_and_auth(monkeypatch):
    monkeypatch.setenv("TEST_RERANKER_KEY", "secret-value")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ranker = DocumentReranker(_remote(), lambda: None, client=client)
        assert await ranker.rank("query", ["first", "second"], 2) == [1, 0]

    assert str(seen[0].url) == "https://models.example/v1/rerank"
    assert seen[0].headers["authorization"] == "Bearer secret-value"
    assert json.loads(seen[0].content) == {
        "model": "remote-reranker",
        "query": "query",
        "documents": ["first", "second"],
        "top_n": 2,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}, {"index": 0, "relevance_score": 0.1}]}),
        httpx.Response(200, json={"results": [{"index": 3, "relevance_score": 0.5}, {"index": 1, "relevance_score": 0.1}]}),
        httpx.Response(200, json={"results": [{"index": 0, "relevance_score": "bad"}, {"index": 1, "relevance_score": 0.1}]}),
        httpx.Response(200, json={"results": []}),
        httpx.Response(503),
    ],
)
async def test_remote_rerank_rejects_invalid_results(monkeypatch, response):
    monkeypatch.setenv("TEST_RERANKER_KEY", "secret-value")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: response)) as client:
        ranker = DocumentReranker(_remote(), lambda: None, client=client)
        with pytest.raises(RerankerUnavailable):
            await ranker.rank("query", ["first", "second"], 2)


@pytest.mark.asyncio
async def test_remote_rerank_rejects_timeout_and_oversized_response(monkeypatch):
    monkeypatch.setenv("TEST_RERANKER_KEY", "secret-value")

    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    for handler in (timeout, lambda _request: httpx.Response(200, content=b"x" * (MAX_RERANK_BODY_BYTES + 1))):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            ranker = DocumentReranker(_remote(), lambda: None, client=client)
            with pytest.raises(RerankerUnavailable):
                await ranker.rank("query", ["first", "second"], 2)


@pytest.mark.asyncio
async def test_remote_rerank_binds_encoded_cjk_request_size(monkeypatch):
    monkeypatch.setenv("TEST_RERANKER_KEY", "secret-value")
    sizes = []

    def handler(request: httpx.Request) -> httpx.Response:
        sizes.append(len(request.content))
        return httpx.Response(200, json={"results": [{"index": index, "relevance_score": float(index)} for index in range(40)]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ranker = DocumentReranker(_remote(), lambda: None, client=client)
        assert len(await ranker.rank("query", ["漢" * 5000] * 40, 40)) == 40
    assert sizes[0] <= MAX_RERANK_BODY_BYTES


@pytest.mark.asyncio
async def test_remote_rerank_batches_legacy_large_requests(monkeypatch):
    monkeypatch.setenv("TEST_RERANKER_KEY", "secret-value")
    batch_sizes = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batch_sizes.append(len(body["documents"]))
        results = [{"index": index, "relevance_score": float(content)} for index, content in enumerate(body["documents"])]
        return httpx.Response(200, json={"results": results})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ranker = DocumentReranker(_remote(), lambda: None, client=client)
        assert await ranker.rank("query", [str(index) for index in range(101)], 2) == [100, 99]
    assert batch_sizes == [100, 1]


@pytest.mark.asyncio
async def test_remote_rerank_has_total_deadline_for_trickling_response(monkeypatch):
    monkeypatch.setenv("TEST_RERANKER_KEY", "secret-value")
    monkeypatch.setattr("knowledge_flow_backend.features.vector_search.reranker.REMOTE_TOTAL_TIMEOUT_SECONDS", 0.01)

    class Trickle(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.005)
                yield b" "

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(200, stream=Trickle()))) as client:
        ranker = DocumentReranker(_remote(), lambda: None, client=client)
        with pytest.raises(RerankerUnavailable):
            await ranker.rank("query", ["text"], 1)


@pytest.mark.asyncio
async def test_remote_rerank_never_falls_back_after_failure(monkeypatch):
    monkeypatch.setenv("TEST_RERANKER_KEY", "secret-value")
    local_calls = 0

    def local_factory():
        nonlocal local_calls
        local_calls += 1
        raise AssertionError("local model must not load")

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _request: httpx.Response(503))) as client:
        ranker = DocumentReranker(_remote(), local_factory, client=client)
        with pytest.raises(RerankerUnavailable):
            await ranker.rank("query", ["first"], 1)
    assert local_calls == 0


@pytest.mark.asyncio
async def test_local_rerank_initializes_once_under_concurrency():
    loads = 0

    class Model:
        def predict(self, pairs):
            return [0.1, 0.9]

    def local_factory():
        nonlocal loads
        loads += 1
        time.sleep(0.02)
        return Model()

    ranker = DocumentReranker(None, local_factory)
    first, second = await asyncio.gather(
        ranker.rank("query", ["first", "second"], 1),
        ranker.rank("query", ["first", "second"], 1),
    )
    assert first == second == [1]
    assert loads == 1


@pytest.mark.asyncio
async def test_local_rerank_has_bounded_queue_wait(monkeypatch):
    monkeypatch.setattr("knowledge_flow_backend.features.vector_search.reranker.LOCAL_QUEUE_TIMEOUT_SECONDS", 0.01)
    ranker = DocumentReranker(None, lambda: None)
    ranker._local_slots = asyncio.Semaphore(0)

    with pytest.raises(RerankerUnavailable, match="queue"):
        await ranker.rank("query", ["text"], 1)
