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

"""The fixed probe battery of the web research self-test.

Every probe goes through the real per-user port (`context.services.web_research`):
the restricted activity record, the deployment ceilings and the guarded
transport. The battery is code, not input: the harness never sends a request
the person typed, so it cannot be steered to an arbitrary destination.

Three groups:

- ``schema``: the tool contract refuses the arguments, nothing is dispatched.
- ``guard``: the request reaches the engine, which refuses the destination
  before any connection (``unsafe_destination``). A name the deployment cannot
  resolve (``unavailable``) opened no connection either.
- ``remote``: needs the Internet; a probe whose third-party endpoint is
  unreachable is skipped, never passed.
- ``search`` / ``fetch``: the feature works, and SafeSearch is never weaker
  than requested nor than the deployment policy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from fred_sdk.contracts.web_research import (
    FetchRequest,
    WebResearchError,
    WebResearchPort,
    WebResearchResult,
    WebSearchRequest,
)
from pydantic import BaseModel, ValidationError

ProbeGroup = Literal["schema", "guard", "remote", "search", "fetch"]
Verdict = Literal["passed", "failed", "skipped"]

SAFESEARCH_LEVELS = {"off": 0, "moderate": 1, "on": 2}
# Codes meaning the probe's third-party endpoint could not be reached.
UNREACHABLE = {"unavailable", "timed_out", "provider_failed", "http_error", "busy"}
NOT_DISPATCHED = {"unsafe_destination", "unavailable"}

SEARCH_QUERY = "Thales Group"
PUBLIC_PAGE = "https://example.com/"
PUBLIC_PAGE_MARKER = "Example Domain"
REDIRECTOR = "https://httpbin.org"


class ProbeReport(BaseModel):
    id: str
    group: ProbeGroup
    title: str
    verdict: Verdict
    expected: str
    observed: str
    detail: str | None = None


@dataclass(frozen=True)
class Outcome:
    """What one request produced: a result, a refusal code, or a schema refusal."""

    result: WebResearchResult | None = None
    code: str | None = None

    @property
    def observed(self) -> str:
        if self.code:
            return self.code
        count = len(self.result.results) if self.result else 0
        return f"ok ({count} result(s))"


async def _run(
    port: WebResearchPort, build: Callable[[], FetchRequest | WebSearchRequest]
) -> Outcome:
    try:
        request = build()
    except ValidationError:
        return Outcome(code="rejected_by_schema")
    try:
        return Outcome(result=await port.execute(request))
    except WebResearchError as error:
        return Outcome(code=error.code)


def _fetch(url: str, **arguments: object) -> Callable[[], FetchRequest]:
    return lambda: FetchRequest.model_validate({"url": url, **arguments})


def _unvalidated_fetch(url: str) -> Callable[[], FetchRequest]:
    # Skips the tool contract on purpose: the engine re-checks every hop itself.
    return lambda: FetchRequest.model_construct(
        operation="fetch_url",
        url=url,
        focus=None,
        max_passages=8,
        max_chars=12_000,
        offset=0,
        include_links=False,
    )


def _search(**arguments: object) -> Callable[[], WebSearchRequest]:
    return lambda: WebSearchRequest.model_validate({"query": SEARCH_QUERY, **arguments})


# (id, title, url) — refused by the tool contract before anything is dispatched.
SCHEMA_PROBES: tuple[tuple[str, str, str], ...] = (
    ("scheme_file", "file:// URL refused", "file:///etc/passwd"),
    ("scheme_ftp", "ftp:// URL refused", "ftp://example.com/"),
    ("scheme_gopher", "gopher:// URL refused", "gopher://example.com/"),
    ("scheme_javascript", "javascript: URL refused", "javascript:alert(1)"),
    (
        "credentials_in_url",
        "URL carrying credentials refused",
        "https://user:secret@example.com/",
    ),
    ("port_alternate", "Non-web port refused", "http://example.com:8080/"),
    (
        "port_internal_service",
        "Internal service port refused",
        "http://127.0.0.1:6379/",
    ),
    ("whitespace_in_url", "URL with whitespace refused", "https://example.com/ x"),
)

# (id, title, url, codes that pass) — the engine refuses before connecting.
GUARD_PROBES: tuple[tuple[str, str, str, frozenset[str]], ...] = tuple(
    (probe_id, title, url, frozenset({"unsafe_destination"}))
    for probe_id, title, url in (
        ("loopback_ipv4", "Loopback 127.0.0.1", "http://127.0.0.1/"),
        ("localhost", "localhost", "http://localhost/"),
        ("unspecified", "Unspecified 0.0.0.0", "http://0.0.0.0/"),
        ("private_10", "Private 10.0.0.0/8", "http://10.0.0.1/"),
        ("private_172", "Private 172.16.0.0/12", "http://172.16.0.1/"),
        ("private_192", "Private 192.168.0.0/16", "http://192.168.0.1/"),
        ("shared_cgnat", "Shared 100.64.0.0/10", "http://100.64.0.1/"),
        (
            "cloud_metadata",
            "Cloud metadata 169.254.169.254",
            "http://169.254.169.254/latest/meta-data/",
        ),
        ("loopback_ipv6", "Loopback [::1]", "http://[::1]/"),
        ("ipv4_mapped", "IPv4-mapped [::ffff:127.0.0.1]", "http://[::ffff:127.0.0.1]/"),
        ("nat64", "NAT64 [64:ff9b::a00:1]", "http://[64:ff9b::a00:1]/"),
        ("six_to_four", "6to4 [2002:7f00:1::]", "http://[2002:7f00:1::]/"),
        ("unique_local_ipv6", "Unique local [fd00::1]", "http://[fd00::1]/"),
        ("decimal_ip", "Decimal-encoded loopback 2130706433", "http://2130706433/"),
        ("hex_ip", "Hex-encoded loopback 0x7f.0.0.1", "http://0x7f.0.0.1/"),
    )
) + tuple(
    # A platform name either resolves to a private address or not at all here.
    (probe_id, title, url, frozenset(NOT_DISPATCHED))
    for probe_id, title, url in (
        ("platform_keycloak", "Platform service name keycloak", "http://keycloak/"),
        ("platform_postgres", "Platform service name postgres", "http://postgres/"),
        (
            "cluster_api",
            "Kubernetes API kubernetes.default.svc",
            "https://kubernetes.default.svc/",
        ),
    )
)

# (id, title, url) — the tool contract skipped: the engine's own check refuses.
BYPASS_PROBES: tuple[tuple[str, str, str], ...] = (
    ("engine_scheme_file", "Engine refuses file:// on its own", "file:///etc/passwd"),
    (
        "engine_credentials",
        "Engine refuses URL credentials on its own",
        "https://user:secret@example.com/",
    ),
    (
        "engine_port",
        "Engine refuses a non-web port on its own",
        "http://127.0.0.1:6379/",
    ),
)


def _report(
    probe_id: str,
    group: ProbeGroup,
    title: str,
    passed: bool,
    expected: str,
    outcome: Outcome,
    detail: str | None = None,
) -> ProbeReport:
    return ProbeReport(
        id=probe_id,
        group=group,
        title=title,
        verdict="passed" if passed else "failed",
        expected=expected,
        observed=outcome.observed,
        detail=detail,
    )


def _skipped(
    probe_id: str,
    group: ProbeGroup,
    title: str,
    expected: str,
    outcome: Outcome,
    why: str,
) -> ProbeReport:
    return ProbeReport(
        id=probe_id,
        group=group,
        title=title,
        verdict="skipped",
        expected=expected,
        observed=outcome.observed,
        detail=why,
    )


def _public_url(url: str | None) -> bool:
    parsed = urlsplit(url or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


async def run_probes(
    port: WebResearchPort,
    on_probe: Callable[[ProbeReport], Awaitable[None] | None] | None = None,
) -> list[ProbeReport]:
    """Run the whole battery in order, one request at a time."""
    reports: list[ProbeReport] = []

    async def add(report: ProbeReport) -> None:
        reports.append(report)
        if on_probe is not None:
            pending = on_probe(report)
            if pending is not None:
                await pending

    # ── Refused by the tool contract ────────────────────────────────────────
    for probe_id, title, url in SCHEMA_PROBES:
        outcome = await _run(port, _fetch(url))
        await add(
            _report(
                probe_id,
                "schema",
                title,
                outcome.code == "rejected_by_schema",
                "rejected_by_schema",
                outcome,
            )
        )
    outcome = await _run(port, _fetch(PUBLIC_PAGE, focus="example", offset=10))
    await add(
        _report(
            "focus_with_offset",
            "schema",
            "focus combined with offset refused",
            outcome.code == "rejected_by_schema",
            "rejected_by_schema",
            outcome,
        )
    )
    outcome = await _run(port, _search(max_results=31))
    await add(
        _report(
            "search_over_limit",
            "schema",
            "More than 30 results refused",
            outcome.code == "rejected_by_schema",
            "rejected_by_schema",
            outcome,
        )
    )

    # ── Refused by the engine before any connection ─────────────────────────
    for probe_id, title, url, accepted in GUARD_PROBES:
        outcome = await _run(port, _fetch(url))
        await add(
            _report(
                probe_id,
                "guard",
                title,
                outcome.code in accepted,
                " or ".join(sorted(accepted)),
                outcome,
            )
        )
    for probe_id, title, url in BYPASS_PROBES:
        outcome = await _run(port, _unvalidated_fetch(url))
        await add(
            _report(
                probe_id,
                "guard",
                title,
                outcome.code == "unsafe_destination",
                "unsafe_destination",
                outcome,
            )
        )

    # ── Needs the Internet: skipped, never passed, when the endpoint is down ─
    remote: tuple[tuple[str, str, str, str], ...] = (
        (
            "dns_to_loopback",
            "Public name resolving to 127.0.0.1",
            "http://127.0.0.1.nip.io/",
            "unsafe_destination",
        ),
        (
            "redirect_to_loopback",
            "Public redirect to 127.0.0.1",
            f"{REDIRECTOR}/redirect-to?url=http://127.0.0.1/",
            "unsafe_destination",
        ),
        (
            "redirect_to_metadata",
            "Public redirect to cloud metadata",
            f"{REDIRECTOR}/redirect-to?url=http://169.254.169.254/latest/meta-data/",
            "unsafe_destination",
        ),
        (
            "redirect_to_file",
            "Public redirect to file://",
            f"{REDIRECTOR}/redirect-to?url=file:///etc/passwd",
            "unsafe_destination",
        ),
        (
            "redirect_chain",
            "More than 5 redirects refused",
            f"{REDIRECTOR}/redirect/8",
            "too_many_redirects",
        ),
        (
            "binary_content",
            "Binary content refused",
            f"{REDIRECTOR}/image/png",
            "unsupported_content",
        ),
    )
    for probe_id, title, url, expected in remote:
        outcome = await _run(port, _fetch(url))
        if outcome.code != expected and (outcome.code in UNREACHABLE):
            await add(
                _skipped(
                    probe_id,
                    "remote",
                    title,
                    expected,
                    outcome,
                    "third-party endpoint unreachable from this deployment",
                )
            )
            continue
        await add(
            _report(
                probe_id, "remote", title, outcome.code == expected, expected, outcome
            )
        )

    # ── Search works, and SafeSearch only ever tightens ─────────────────────
    effective: dict[str, str] = {}
    for requested in ("on", "moderate", "off"):
        outcome = await _run(port, _search(safesearch=requested, max_results=3))
        title = f"Search with SafeSearch '{requested}' requested"
        if outcome.result is None:
            if outcome.code in UNREACHABLE:
                await add(
                    _skipped(
                        f"safesearch_{requested}",
                        "search",
                        title,
                        f">= {requested}",
                        outcome,
                        "search provider unreachable",
                    )
                )
            else:
                await add(
                    _report(
                        f"safesearch_{requested}",
                        "search",
                        title,
                        False,
                        f">= {requested}",
                        outcome,
                    )
                )
            continue
        level = outcome.result.safesearch or "off"
        effective[requested] = level
        urls_ok = all(_public_url(page.url) for page in outcome.result.results)
        passed = (
            SAFESEARCH_LEVELS[level] >= SAFESEARCH_LEVELS[requested]
            and outcome.result.untrusted_content is True
            and len(outcome.result.results) <= 3
            and urls_ok
        )
        await add(
            _report(
                f"safesearch_{requested}",
                "search",
                title,
                passed,
                f">= {requested}, <= 3 public results",
                outcome,
                f"applied SafeSearch: {level}",
            )
        )
    if "off" in effective:
        floor = effective["off"]
        outcome = Outcome(code=f"floor {floor}")
        await add(
            _report(
                "safesearch_policy",
                "search",
                "The model cannot turn SafeSearch off",
                floor != "off",
                "floor moderate or on",
                outcome,
                "deployment web_research.safesearch sets the floor",
            )
        )
    outcome = await _run(port, _search(max_results=1))
    if outcome.result is not None:
        await add(
            _report(
                "search_ceiling",
                "search",
                "Result count bounded by the request",
                len(outcome.result.results) <= 1,
                "<= 1 result",
                outcome,
            )
        )

    # ── Fetch works and stays within its bounds ─────────────────────────────
    outcome = await _run(port, _fetch(PUBLIC_PAGE, max_chars=500))
    page = (
        outcome.result.results[0] if outcome.result and outcome.result.results else None
    )
    if page is None and outcome.code in UNREACHABLE:
        await add(
            _skipped(
                "fetch_public",
                "fetch",
                "Read a public page",
                "page text",
                outcome,
                f"{PUBLIC_PAGE} unreachable",
            )
        )
    else:
        passed = (
            page is not None
            and PUBLIC_PAGE_MARKER in f"{page.title}\n{page.content or ''}"
            and len(page.content or "") <= 500
            and _public_url(page.final_url)
        )
        await add(
            _report(
                "fetch_public",
                "fetch",
                "Read a public page within max_chars",
                passed,
                f"'{PUBLIC_PAGE_MARKER}', <= 500 chars",
                outcome,
            )
        )
        outcome = await _run(port, _fetch(PUBLIC_PAGE, focus="documentation examples"))
        focused = (
            outcome.result.results[0]
            if outcome.result and outcome.result.results
            else None
        )
        await add(
            _report(
                "fetch_focus",
                "fetch",
                "Focused read returns matching passages",
                focused is not None and bool(focused.content),
                "non-empty passages",
                outcome,
            )
        )
    return reports
