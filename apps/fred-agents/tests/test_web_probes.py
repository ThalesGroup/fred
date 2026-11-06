# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from fred_agents.test_assistant.web_probes import (
    BYPASS_PROBES,
    GUARD_PROBES,
    SCHEMA_PROBES,
    run_probes,
)
from fred_sdk.contracts.web_research import (
    FetchRequest,
    WebPage,
    WebResearchError,
    WebResearchPort,
    WebResearchRequest,
    WebResearchResult,
)

SAFE_LEVELS = {"off": 0, "moderate": 1, "on": 2}


class _ProtectiveEngine(WebResearchPort):
    """Behaves as the real engine does on a deployment with the Internet."""

    def __init__(self, *, floor: str = "on", ready: bool = True) -> None:
        self.floor = floor
        self.ready = ready
        self.requests: list[WebResearchRequest] = []

    async def check_ready(self) -> None:
        if not self.ready:
            raise WebResearchError("activity_unavailable")

    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        self.requests.append(request)
        if isinstance(request, FetchRequest):
            url = request.url
            if "httpbin.org/redirect/" in url:
                raise WebResearchError("too_many_redirects")
            if "httpbin.org/image/" in url:
                raise WebResearchError("unsupported_content")
            if url.startswith("https://example.com/"):
                return WebResearchResult(
                    results=[
                        WebPage(
                            url=url,
                            final_url=url,
                            title="Example Domain",
                            content="For documentation examples.",
                        )
                    ]
                )
            if "postgres" in url or "kubernetes" in url:
                raise WebResearchError("unavailable")
            raise WebResearchError("unsafe_destination")
        level = max((request.safesearch, self.floor), key=SAFE_LEVELS.__getitem__)
        return WebResearchResult(
            results=[
                WebPage(url=f"https://example.org/{index}", title="r")
                for index in range(request.max_results)
            ],
            safesearch=level,  # type: ignore[arg-type]
        )


class _OpenEngine(_ProtectiveEngine):
    """A broken engine that connects anywhere: every guard probe must fail."""

    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        if isinstance(request, FetchRequest):
            return WebResearchResult(
                results=[WebPage(url=request.url, final_url=request.url)]
            )
        return await super().execute(request)


class _Offline(_ProtectiveEngine):
    """No Internet: every request that would leave the deployment is unavailable."""

    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        if isinstance(request, FetchRequest) and (
            urlsplit(request.url).hostname or ""
        ).endswith(("httpbin.org", "nip.io", "example.com")):
            raise WebResearchError("unavailable")
        if not isinstance(request, FetchRequest):
            raise WebResearchError("provider_failed")
        return await super().execute(request)


@pytest.mark.asyncio
async def test_schema_probes_never_reach_the_engine() -> None:
    engine = _ProtectiveEngine()
    await run_probes(engine)
    dispatched = {getattr(r, "url", None) for r in engine.requests}
    for _, _, url in SCHEMA_PROBES:
        if url in {u for _, _, u in BYPASS_PROBES}:
            continue  # the bypass probes dispatch the same URL on purpose
        assert url not in dispatched


@pytest.mark.asyncio
async def test_an_engine_that_connects_anywhere_fails_every_guard() -> None:
    reports = {r.id: r for r in await run_probes(_OpenEngine())}
    for probe_id, *_ in GUARD_PROBES + BYPASS_PROBES:
        assert reports[probe_id].verdict == "failed", probe_id
    for probe_id in ("redirect_to_loopback", "redirect_to_metadata", "dns_to_loopback"):
        assert reports[probe_id].verdict == "failed", probe_id


@pytest.mark.asyncio
async def test_unreachable_endpoints_are_skipped_never_passed() -> None:
    reports = {r.id: r for r in await run_probes(_Offline())}
    for probe_id in (
        "dns_to_loopback",
        "redirect_to_loopback",
        "redirect_chain",
        "binary_content",
        "safesearch_on",
        "fetch_public",
    ):
        assert reports[probe_id].verdict == "skipped", probe_id
    # The local guards do not need the Internet and still pass.
    assert reports["cloud_metadata"].verdict == "passed"


@pytest.mark.asyncio
async def test_a_policy_letting_the_model_turn_safesearch_off_fails() -> None:
    reports = {r.id: r for r in await run_probes(_ProtectiveEngine(floor="off"))}
    assert reports["safesearch_off"].verdict == "passed"
    assert reports["safesearch_policy"].verdict == "failed"
    assert reports["safesearch_on"].verdict == "passed"


@pytest.mark.asyncio
async def test_an_engine_weakening_safesearch_fails() -> None:
    class _Weakening(_ProtectiveEngine):
        async def execute(self, request: WebResearchRequest) -> WebResearchResult:
            result = await super().execute(request)
            if not isinstance(request, FetchRequest):
                return result.model_copy(update={"safesearch": "off"})
            return result

    reports = {r.id: r for r in await run_probes(_Weakening())}
    assert reports["safesearch_on"].verdict == "failed"
    assert reports["safesearch_moderate"].verdict == "failed"


class _BehindProxy(_ProtectiveEngine):
    """The runtime resolves no names behind a proxy: the proxy refuses internal targets."""

    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        if isinstance(request, FetchRequest) and (
            urlsplit(request.url).hostname or ""
        ).endswith(".nip.io"):
            raise WebResearchError("proxy_refused")
        return await super().execute(request)


@pytest.mark.asyncio
async def test_a_proxy_refusal_holds_the_destination_policy() -> None:
    reports = {r.id: r for r in await run_probes(_BehindProxy())}
    assert reports["dns_to_loopback"].verdict == "passed"
    assert reports["dns_to_loopback"].observed == "proxy_refused"
