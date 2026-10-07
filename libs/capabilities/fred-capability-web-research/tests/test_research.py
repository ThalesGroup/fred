# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import asyncio

import httpx
import pytest
from fred_capability_web_research.research import (
    PublicNetworkBackend,
    is_public,
)
from fred_sdk.contracts.web_research import (
    WebPage,
    WebResearchDeploymentConfig,
    WebResearchError,
)


class Provider:
    trusted = False

    def __init__(self):
        self.requests = []

    async def search(self, request, run):
        self.requests.append(request)
        return [WebPage(url="https://example.com", title="Source", snippet="Evidence")]


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "224.0.0.1",
    ],
)
def test_private_and_transition_addresses_are_refused(address):
    assert not is_public(address)


@pytest.mark.asyncio
async def test_tcp_connect_uses_only_vetted_address_and_preserves_hostname_above_backend(
    monkeypatch,
):
    calls = []

    async def resolve(host, port):
        calls.append((host, port))
        return "8.8.8.8"

    async def connect(self, host, port, *args):
        assert host == "8.8.8.8"
        return object()

    monkeypatch.setattr("fred_capability_web_research.research.resolve_public", resolve)
    monkeypatch.setattr(
        "fred_capability_web_research.research.AutoBackend.connect_tcp", connect
    )
    await PublicNetworkBackend().connect_tcp("example.com", 443)
    assert calls == [("example.com", 443)]


@pytest.mark.asyncio
async def test_mixed_dns_record_is_rejected_before_connection(monkeypatch):
    from fred_capability_web_research.research import resolve_public

    async def addresses(*args, **kwargs):
        return [(2, 1, 6, "", ("8.8.8.8", 443)), (2, 1, 6, "", ("10.0.0.1", 443))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
    with pytest.raises(WebResearchError, match="unsafe_destination"):
        await resolve_public("example.com", 443)


@pytest.mark.asyncio
async def test_safesearch_floor_in_internal_engine(monkeypatch):
    from fred_capability_web_research.research import ResearchEngine
    from fred_sdk.contracts.web_research import WebSearchRequest

    async def resolve(host, port):
        return "8.8.8.8"

    monkeypatch.setattr("fred_capability_web_research.research.resolve_public", resolve)
    provider = Provider()
    async with httpx.AsyncClient() as client:
        engine = ResearchEngine(
            WebResearchDeploymentConfig(enabled=True), provider, client
        )
        result = await engine.execute(
            WebSearchRequest(query="PRIVATE-QUERY", safesearch="off")
        )
        assert result.safesearch == "on"
        assert provider.requests[0].safesearch == "on"


@pytest.mark.asyncio
async def test_redirects_are_checked_and_binary_responses_rejected(monkeypatch):
    from fred_capability_web_research.research import ResearchEngine
    from fred_sdk.contracts.web_research import FetchRequest

    calls = []

    def respond(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(302, headers={"location": "file:///secret"})
        raise AssertionError("unsafe redirect connected")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        egress = ResearchEngine(
            WebResearchDeploymentConfig(enabled=True), Provider(), client
        )
        with pytest.raises(WebResearchError, match="unsafe_destination"):
            await egress.fetch(FetchRequest(url="https://example.com"))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_text_fetch_is_bounded_and_focus_selects_passages():
    from fred_capability_web_research.research import ResearchEngine
    from fred_sdk.contracts.web_research import FetchRequest

    def respond(request):
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=httpx.ByteStream(b"Evidence first\n\nUnrelated content"),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        page = await ResearchEngine(
            WebResearchDeploymentConfig(enabled=True), Provider(), client
        ).fetch(
            FetchRequest(url="https://example.com", focus="evidence", max_passages=1)
        )
    assert page.content == "Evidence first"


@pytest.mark.asyncio
async def test_provider_uses_guarded_client_and_actual_safesearch_parameter():
    from urllib.parse import parse_qs

    from fred_capability_web_research.providers import DuckDuckGoProvider
    from fred_capability_web_research.research import ResearchEngine
    from fred_sdk.contracts.web_research import WebSearchRequest

    def respond(request):
        assert str(request.url) == "https://html.duckduckgo.com/html/"
        assert parse_qs(request.content.decode())["kp"] == ["1"]
        assert request.headers["cookie"] == ""
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                b'<div class="result"><a class="result__a" href="https://example.com">Evidence</a><a class="result__snippet">Text</a></div>'
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        egress = ResearchEngine(
            WebResearchDeploymentConfig(enabled=True), Provider(), client
        )
        provider = DuckDuckGoProvider(client, 5000)
        pages = await provider.search(WebSearchRequest(query="query"), egress.in_thread)
        assert pages[0].url == "https://example.com"
        assert pages[0].snippet == "Text"


@pytest.mark.asyncio
async def test_cookies_not_forwarded_across_users_or_redirects():
    from fred_capability_web_research.research import ResearchEngine
    from fred_sdk.contracts.web_research import FetchRequest

    calls = []

    def respond(request):
        assert request.headers.get("cookie") == ""
        calls.append(request.url.host)
        if request.url.host == "first.example.com":
            return httpx.Response(
                302,
                headers={
                    "location": "https://second.example.com",
                    "set-cookie": "secret=from-first; Domain=example.com",
                },
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            stream=httpx.ByteStream(b"public"),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        egress = ResearchEngine(
            WebResearchDeploymentConfig(enabled=True), Provider(), client
        )
        await egress.fetch(FetchRequest(url="https://first.example.com"))
        await egress.fetch(FetchRequest(url="https://second.example.com"))
    assert calls == ["first.example.com", "second.example.com", "second.example.com"]


@pytest.mark.asyncio
async def test_binary_and_encoded_responses_fail_closed():
    from fred_capability_web_research.research import ResearchEngine
    from fred_sdk.contracts.web_research import FetchRequest

    for headers in [
        {"content-type": "application/octet-stream"},
        {"content-type": "text/plain", "content-encoding": "br"},
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request, headers=headers: httpx.Response(
                    200, headers=headers, stream=httpx.ByteStream(b"binary")
                )
            )
        ) as client:
            egress = ResearchEngine(
                WebResearchDeploymentConfig(enabled=True), Provider(), client
            )
            with pytest.raises(WebResearchError, match="unsupported_content"):
                await egress.fetch(FetchRequest(url="https://example.com"))


@pytest.mark.asyncio
async def test_valid_unicode_arguments_need_no_wire_serialization():
    from fred_capability_web_research.research import ResearchEngine
    from fred_sdk.contracts.web_research import FetchRequest

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                stream=httpx.ByteStream(b"public"),
            )
        )
    ) as client:
        engine = ResearchEngine(
            WebResearchDeploymentConfig(enabled=True), Provider(), client
        )
        result = await engine.execute(
            FetchRequest(url="https://example.com/" + "😀" * 4000, focus="😀" * 2048)
        )
        assert result.results[0].content == "public"


def test_deployment_ceilings_bound_every_operation():
    from fred_capability_web_research.research import ResearchEngine
    from fred_sdk.contracts.web_research import (
        FetchRequest,
        WebSearchRequest,
    )

    config = WebResearchDeploymentConfig(
        enabled=True, max_results=2, max_chars_per_page=1000
    )
    engine = ResearchEngine(config, Provider(), httpx.AsyncClient())
    search = engine.capped(WebSearchRequest(query="q", max_results=30))
    fetch = engine.capped(FetchRequest(url="https://example.com", max_chars=50_000))
    small = engine.capped(WebSearchRequest(query="q", max_results=1))
    assert isinstance(search, WebSearchRequest) and search.max_results == 2
    assert isinstance(fetch, FetchRequest) and fetch.max_chars == 1000
    assert isinstance(small, WebSearchRequest) and small.max_results == 1
