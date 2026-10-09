# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""One contract for every search provider, plus configuration-driven selection."""

import json

import httpx
import pytest
from fred_runtime.app.web_research_engine import ResearchEngine, create_engine
from fred_runtime.app.web_research_providers import (
    BraveProvider,
    DuckDuckGoProvider,
    FixtureProvider,
    build_provider,
)
from fred_sdk.contracts.web_research import (
    WebResearchDeploymentConfig,
    WebResearchError,
    WebSearchRequest,
)

KEY = "brave-secret-key"
URLS = [f"https://site{i}.example.org/page" for i in range(6)]


def ddg_reply(request: httpx.Request) -> httpx.Response:
    rows = "".join(
        f'<div class="result"><a class="result__a" href="{url}">Title {i}</a>'
        f'<a class="result__snippet">Snippet {i}</a></div>'
        for i, url in enumerate([*URLS, "javascript:alert(1)"])
    )
    return httpx.Response(200, stream=httpx.ByteStream(rows.encode()))


def brave_reply(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "api.search.brave.com"
    assert request.headers["x-subscription-token"] == KEY
    assert request.headers["cookie"] == ""
    results = [
        {
            "url": url,
            "title": f"Title {i}",
            "description": f"<strong>Snippet</strong> {i} &amp; more",
        }
        for i, url in enumerate([*URLS, "javascript:alert(1)"])
    ]
    body = json.dumps({"web": {"results": results}}).encode()
    return httpx.Response(200, stream=httpx.ByteStream(body))


def provider_for(name: str, reply):
    client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    if name == "duckduckgo":
        return DuckDuckGoProvider(client, 100_000)
    if name == "brave":
        return BraveProvider(client, 100_000, KEY)
    return FixtureProvider.load(None)


async def run_inline(parse):
    return parse()


CASES = [("duckduckgo", ddg_reply), ("brave", brave_reply), ("fixture", None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "reply"), CASES)
async def test_every_provider_returns_bounded_public_pages(name, reply):
    provider = provider_for(name, reply)
    pages = await provider.search(
        WebSearchRequest(query="q", max_results=2), run_inline
    )
    assert 1 <= len(pages) <= 2
    assert all(page.url.startswith(("http://", "https://")) for page in pages)
    assert all(page.title and "<" not in page.snippet for page in pages)
    assert all(KEY not in page.model_dump_json() for page in pages)


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "status"), [("duckduckgo", 503), ("brave", 429)])
async def test_provider_failures_are_bounded_without_fallback(name, status):
    calls = []

    def failing(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return httpx.Response(status, text=f"upstream detail {KEY}")

    provider = provider_for(name, failing)
    with pytest.raises(WebResearchError) as error:
        await provider.search(WebSearchRequest(query="q"), run_inline)
    assert error.value.code == "provider_failed"
    assert KEY not in str(error.value)
    assert len(set(calls)) == 1


@pytest.mark.asyncio
async def test_brave_maps_filters_and_strips_highlighting():
    seen = {}

    def reply(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        return brave_reply(request)

    provider = provider_for("brave", reply)
    pages = await provider.search(
        WebSearchRequest(
            query="q", region="fr-fr", safesearch="moderate", timelimit="w"
        ),
        run_inline,
    )
    assert seen["country"] == "FR"
    assert seen["safesearch"] == "moderate"
    assert seen["freshness"] == "pw"
    assert pages[0].snippet == "Snippet 0 & more"


def test_selection_follows_configuration_and_requires_the_key(monkeypatch, tmp_path):
    client = httpx.AsyncClient()
    assert isinstance(
        build_provider(WebResearchDeploymentConfig(enabled=True), client),
        DuckDuckGoProvider,
    )
    fixture = tmp_path / "results.json"
    fixture.write_text(
        json.dumps([{"url": "https://intranet.example/doc", "title": "Doc"}])
    )
    offline = build_provider(
        WebResearchDeploymentConfig(
            enabled=True, provider="fixture", fixture_file=str(fixture)
        ),
        client,
    )
    assert isinstance(offline, FixtureProvider)
    assert offline.pages[0].title == "Doc"

    brave = WebResearchDeploymentConfig(
        enabled=True, provider="brave", provider_key_env="WEB_RESEARCH_PROVIDER_KEY"
    )
    monkeypatch.delenv("WEB_RESEARCH_PROVIDER_KEY", raising=False)
    with pytest.raises(RuntimeError, match="provider key is missing"):
        create_engine(brave)
    monkeypatch.setenv("WEB_RESEARCH_PROVIDER_KEY", KEY)
    assert isinstance(build_provider(brave, client), BraveProvider)

    with pytest.raises(ValueError, match="provider_key_env"):
        WebResearchDeploymentConfig(enabled=True, provider="brave")
    with pytest.raises(ValueError, match="fixture provider"):
        WebResearchDeploymentConfig(enabled=True, fixture_file="x.json")


@pytest.mark.asyncio
async def test_fixture_search_needs_no_network(monkeypatch):
    async def no_dns(host, port):
        raise AssertionError("fixture results must not trigger DNS")

    monkeypatch.setattr("fred_runtime.app.web_research_engine.resolve_public", no_dns)
    config = WebResearchDeploymentConfig(enabled=True, provider="fixture")
    engine = ResearchEngine(config, FixtureProvider.load(None), httpx.AsyncClient())
    result = await engine.execute(WebSearchRequest(query="anything", max_results=2))
    assert [page.url for page in result.results] == [
        "https://www.python.org/",
        "https://en.wikipedia.org/wiki/Web_search_engine",
    ]
