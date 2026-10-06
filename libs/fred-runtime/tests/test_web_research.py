# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
from fred_runtime.app.web_research import WebResearchService
from fred_runtime.app.web_research_activity import (
    WebResearchActivityBase,
    WebResearchActivityRow,
    utcnow,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.web_research import (
    WebResearchDeploymentConfig,
    WebResearchError,
    WebSearchRequest,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def service(monkeypatch):
    monkeypatch.setenv(
        "WEB_RESEARCH_EGRESS_TOKEN", "test-service-token-01234567890123456789"
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(WebResearchActivityBase.metadata.create_all)

    async def reply(request):
        assert "user_id" not in request.content.decode()
        assert request.headers["x-request-id"]
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://example.com", "snippet": "PAGE-CONTENT"}]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(reply), base_url="https://egress/"
    )
    backend = WebResearchService(
        WebResearchDeploymentConfig(enabled=True, egress_url="https://egress"),
        engine,
        client=client,
    )
    yield backend, engine
    await backend.close()
    await engine.dispose()


def binding(user="user"):
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(user_id=user),
        portable_context=PortableContext(
            request_id="request",
            correlation_id="correlation",
            actor=user,
            tenant="default",
            environment=PortableEnvironment.DEV,
            user_id=user,
            session_id="session",
        ),
    )


@pytest.mark.asyncio
async def test_attribution_one_record_no_page_content_and_retention(service):
    backend, engine = service
    result = await backend.bind(binding()).execute(
        WebSearchRequest(query="PRIVATE-QUERY")
    )
    assert result.results[0].snippet == "PAGE-CONTENT"
    rows = await backend.store.list(user_id="user", limit=10)
    assert len(rows) == 1
    assert rows[0].query == "PRIVATE-QUERY"
    assert rows[0].user_id == "user" and rows[0].outcome == "succeeded"
    assert rows[0].result_count == 1
    assert "PAGE-CONTENT" not in rows[0].model_dump_json()
    assert rows[0].expires_at - rows[0].created_at == timedelta(days=30)
    async with engine.begin() as connection:
        await connection.execute(
            update(WebResearchActivityRow).values(
                expires_at=utcnow() - timedelta(seconds=1)
            )
        )
    assert await backend.store.list(user_id=None, limit=10) == []
    await backend.store.purge()
    assert await backend.store.erase_user("user") == 0


@pytest.mark.asyncio
async def test_activity_failure_prevents_egress(service, monkeypatch):
    backend, _ = service

    async def fail(**kwargs):
        raise RuntimeError("PRIVATE-QUERY DB failure")

    monkeypatch.setattr(backend.store, "begin", fail)
    with pytest.raises(WebResearchError, match="activity_unavailable"):
        await backend.bind(binding()).execute(WebSearchRequest(query="PRIVATE-QUERY"))


@pytest.mark.asyncio
async def test_cancelled_call_keeps_terminal_outcome_and_user_erasure(service):
    backend, _ = service
    started = asyncio.Event()

    async def blocked(request):
        started.set()
        await asyncio.Event().wait()
        return httpx.Response(200)

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(blocked), base_url="https://egress/"
    )
    task = asyncio.create_task(
        backend.bind(binding()).execute(WebSearchRequest(query="PRIVATE-QUERY"))
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    rows = await backend.store.list(user_id="user", limit=10)
    assert len(rows) == 1 and rows[0].outcome == "cancelled"
    assert await backend.store.erase_user("user") == 1
    assert await backend.store.list(user_id="user", limit=10) == []


def test_egress_configuration_requires_verified_https():
    with pytest.raises(ValueError):
        WebResearchDeploymentConfig(egress_url="http://untrusted")
    with pytest.raises(ValueError):
        WebResearchDeploymentConfig(
            egress_url="https://secret:token@egress"  # pragma: allowlist secret
        )


@pytest.mark.asyncio
async def test_erasure_fences_late_begin_and_is_shared_by_new_store(service):
    from fred_runtime.app.web_research_activity import WebResearchActivityStore

    backend, engine = service
    await backend.store.erase_user("user")
    other_replica = WebResearchActivityStore(engine, 30)
    with pytest.raises(WebResearchError, match="rejected"):
        await other_replica.begin(
            request_id="late",
            user_id="user",
            correlation_id="corr",
            operation="web_search",
            query="LATE-QUERY",
        )
    assert await other_replica.list(user_id="user", limit=10) == []
    with pytest.raises(WebResearchError, match="rejected"):
        await backend.bind(binding()).execute(WebSearchRequest(query="LATE-QUERY"))
    # Other subjects retain independent access.
    await other_replica.begin(
        request_id="other",
        user_id="other",
        correlation_id="corr",
        operation="web_search",
        query="public",
    )
    assert len(await other_replica.list(user_id="other", limit=10)) == 1


@pytest.mark.asyncio
async def test_valid_combined_unicode_response_within_wire_budget(service):
    from fred_sdk.contracts.web_research import SearchAndFetchRequest

    backend, _ = service
    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        {"url": "https://example.com", "content": "😀" * 50_000}
                        for _ in range(10)
                    ]
                },
            )
        ),
        base_url="https://egress/",
    )
    result = await backend.bind(binding()).execute(
        SearchAndFetchRequest(query="query", max_results=10, max_chars_per_page=50_000)
    )
    assert len(result.results) == 10
