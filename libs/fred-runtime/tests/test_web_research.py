# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
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
    FetchRequest,
    WebResearchDeploymentConfig,
    WebResearchError,
    WebSearchRequest,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def service(monkeypatch):
    async def resolve(host, port):
        return "8.8.8.8"

    monkeypatch.setattr("fred_runtime.app.web_research_engine.resolve_public", resolve)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(WebResearchActivityBase.metadata.create_all)

    async def reply(request):
        assert "user_id" not in request.content.decode()
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                b'<div class="result"><a class="result__a" href="https://example.com">Source</a><a class="result__snippet">PAGE-CONTENT</a></div>'
            ),
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(reply),
    )
    backend = WebResearchService(
        WebResearchDeploymentConfig(enabled=True),
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
async def test_cancelled_call_keeps_terminal_outcome_and_user_erasure(
    service, monkeypatch
):
    backend, _ = service
    started = asyncio.Event()

    async def blocked(request):
        started.set()
        await asyncio.Event().wait()
        return httpx.Response(200)

    await backend.research.client.aclose()
    backend.research.client = httpx.AsyncClient(transport=httpx.MockTransport(blocked))
    monkeypatch.setattr(backend.research.provider, "client", backend.research.client)
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


def test_proxy_configuration_rejects_embedded_credentials_and_old_service_fields():
    with pytest.raises(ValueError):
        WebResearchDeploymentConfig(
            proxy_url="https://secret:token@proxy"  # pragma: allowlist secret
        )
    with pytest.raises(ValueError):
        WebResearchDeploymentConfig.model_validate(
            {"egress_url": "https://old-service"}
        )
    with pytest.raises(ValueError):
        WebResearchDeploymentConfig(proxy_auth_env="PROXY_AUTH")


@pytest.mark.asyncio
async def test_busy_call_is_recorded_without_dispatch(service):
    backend, _ = service
    backend._slots = asyncio.Semaphore(0)
    with pytest.raises(WebResearchError, match="busy"):
        await backend.bind(binding()).execute(WebSearchRequest(query="query"))
    rows = await backend.store.list(user_id="user", limit=10)
    assert rows[0].outcome == "failed" and rows[0].error_code == "busy"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ("403 Forbidden", "proxy_refused"),
        ("407 Proxy Authentication Required", "unavailable"),
        ("502 Bad Gateway", "unavailable"),
    ],
)
async def test_only_a_proxy_403_is_a_refusal(
    service, monkeypatch, caplog, answer, code
):
    backend, _ = service

    async def tunnel(request):
        raise httpx.ProxyError(answer)

    monkeypatch.setattr(backend.research, "execute", tunnel)
    with caplog.at_level(logging.INFO, logger="fred_runtime.app.web_research"):
        with pytest.raises(WebResearchError, match=code):
            await backend.bind(binding()).execute(
                WebSearchRequest(query="PRIVATE-QUERY")
            )
    rows = await backend.store.list(user_id="user", limit=10)
    assert rows[0].error_code == code
    # One content-free line: code, cause and request_id, never the query.
    [record] = [r for r in caplog.records if "event=web_research " in r.getMessage()]
    line = record.getMessage()
    assert f"error_code={code}" in line
    assert f"cause=ProxyError status={answer[:3]}" in line
    assert f"request_id={rows[0].request_id}" in line
    assert "PRIVATE-QUERY" not in line
    assert record.levelno == (
        logging.INFO if code == "proxy_refused" else logging.WARNING
    )


@pytest.mark.asyncio
async def test_daily_quota_refuses_before_dispatch_per_operation(service):
    backend, _ = service
    backend.config = backend.config.model_copy(
        update={"max_searches_per_user_per_day": 2}
    )
    port = backend.bind(binding())
    remaining = []
    for _ in range(2):
        result = await port.execute(WebSearchRequest(query="query"))
        assert result.daily_quota is not None
        remaining.append(result.daily_quota.remaining)
    assert remaining == [1, 0]
    dispatched = backend.research.execute

    async def must_not_dispatch(request):
        raise AssertionError("quota refusals never reach the network")

    backend.research.execute = must_not_dispatch
    for _ in range(2):
        with pytest.raises(WebResearchError, match="quota_exceeded"):
            await port.execute(WebSearchRequest(query="query"))
    backend.research.execute = dispatched
    # Page reads have their own, here absent, cap; another user is unaffected.
    page = await port.execute(FetchRequest(url="https://example.com/"))
    assert page.daily_quota is None
    other = await backend.bind(binding("other")).execute(WebSearchRequest(query="q"))
    assert other.daily_quota is not None and other.daily_quota.remaining == 1
    rows = await backend.store.list(user_id="user", limit=10)
    assert [r.error_code for r in rows].count("quota_exceeded") == 2
    assert await backend.store.count_today("user", "web_search") == 2


@pytest.mark.asyncio
async def test_no_quota_configured_never_refuses(service):
    backend, _ = service
    port = backend.bind(binding())
    for _ in range(3):
        result = await port.execute(WebSearchRequest(query="query"))
        assert result.daily_quota is None


@pytest.mark.asyncio
async def test_admin_kpi_event_is_content_free_and_costs_only_searches(
    service, monkeypatch
):
    backend, _ = service
    backend.config = backend.config.model_copy(update={"cost_per_1000_searches": 5.0})
    events = []

    class Writer:
        def emit(self, **event):
            events.append(event)

    class Runtime:
        def get_kpi_writer(self):
            return Writer()

    monkeypatch.setattr(
        "fred_runtime.app.web_research.get_runtime_context_or_none", Runtime
    )
    await backend.bind(binding()).execute(WebSearchRequest(query="PRIVATE-QUERY"))
    (event,) = events
    assert event["name"] == "web_research.request"
    assert event["dims"]["tool_name"] == "web_search"
    assert event["dims"]["status"] == "ok"
    assert event["cost"] == {"usd": 0.005}
    assert event["actor"].user_id == "user"
    assert "PRIVATE-QUERY" not in repr(event) and "example.com" not in repr(event)
