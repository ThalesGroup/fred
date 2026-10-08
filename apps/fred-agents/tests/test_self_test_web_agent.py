# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The web research self-test harness: its verdicts, not the engine itself."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast
from urllib.parse import urlsplit

import pytest
from fred_agents.registry import build_registry
from fred_agents.self_test_web.graph_agent import WEB_SELF_TEST_AGENT
from fred_agents.self_test_web.graph_state import WebSelfTestState
from fred_agents.self_test_web.graph_steps import (
    NOT_ENABLED,
    NOT_READY,
    REPORT_HEADER,
    probe_step,
)
from fred_agents.self_test_web.probes import (
    BYPASS_PROBES,
    GUARD_PROBES,
    SCHEMA_PROBES,
    run_probes,
)
from fred_sdk import GraphNodeContext
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


def _context(port: WebResearchPort | None) -> SimpleNamespace:
    context = SimpleNamespace(services=SimpleNamespace(web_research=port), statuses=[])
    context.emit_status = lambda status, detail=None: context.statuses.append(
        (status, detail)
    )
    return context


async def _report(port: WebResearchPort | None) -> dict[str, object]:
    state = WebSelfTestState(latest_user_text="go")
    result = await probe_step(state, cast(GraphNodeContext, _context(port)))
    text = result.state_update["final_text"]
    assert isinstance(text, str) and text.startswith(f"{REPORT_HEADER} ")
    return json.loads(text.removeprefix(f"{REPORT_HEADER} "))


@pytest.mark.asyncio
async def test_disabled_web_research_is_reported_and_probes_nothing() -> None:
    report = await _report(None)
    assert report == {
        "enabled": False,
        "ready": False,
        "reason": NOT_ENABLED,
        "probes": [],
    }


@pytest.mark.asyncio
async def test_activity_store_not_ready_runs_no_probe() -> None:
    engine = _ProtectiveEngine(ready=False)
    report = await _report(engine)
    assert report["enabled"] is True and report["ready"] is False
    assert report["reason"] == NOT_READY
    assert engine.requests == []


@pytest.mark.asyncio
async def test_a_protective_engine_passes_every_probe() -> None:
    report = await _report(_ProtectiveEngine())
    probes = cast(list[dict[str, object]], report["probes"])
    failed = [p for p in probes if p["verdict"] != "passed"]
    assert failed == []
    expected = len(SCHEMA_PROBES) + len(GUARD_PROBES) + len(BYPASS_PROBES)
    assert len(probes) > expected


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


def test_harness_is_registered_and_hidden() -> None:
    assert build_registry()["fred.github.self_test_web"] is WEB_SELF_TEST_AGENT
    assert WEB_SELF_TEST_AGENT.public is False


class _BehindProxy(_ProtectiveEngine):
    """Fred resolves no names behind a proxy: the proxy refuses internal targets."""

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
