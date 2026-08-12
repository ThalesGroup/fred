# Copyright Thales 2025
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

from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx
import pytest
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer import KPIWriter
from fred_runtime.runtime_support import user_token_refresher
from fred_runtime.runtime_support.user_token_refresher import (
    aclose_token_refresh_client,
    refresh_user_access_token_from_keycloak,
)

REALM = "http://keycloak/realms/test"

# Every test here drives the async refresher; pytest-asyncio runs in strict mode
# in this package, so the marker is applied module-wide rather than per test.
pytestmark = pytest.mark.asyncio


def _install_transport(monkeypatch, handler) -> None:
    """Route the refresher's client through a MockTransport running `handler`.

    Builds the client through the PRODUCTION factory so its real configuration
    (cookie policy, limits, timeout) is what these tests exercise — a bare
    `httpx.AsyncClient` here would silently test a different client.
    """
    real_factory = user_token_refresher._new_async_client

    def _factory() -> httpx.AsyncClient:
        return real_factory(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(user_token_refresher, "_new_async_client", _factory)


def _token_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


# ---------------------------------------------------------------------------
# Happy path (ported from the pre-async suite)
# ---------------------------------------------------------------------------


async def test_returns_new_token_on_success(monkeypatch):
    payload = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 300,
    }
    _install_transport(monkeypatch, lambda request: _token_response(payload))

    result = await refresh_user_access_token_from_keycloak(
        REALM, "client-id", "old-refresh"
    )

    assert result["access_token"] == "new-access"
    assert result["refresh_token"] == "new-refresh"


async def test_adds_expires_at_timestamp(monkeypatch):
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 60}),
    )

    before = time.time()
    result = await refresh_user_access_token_from_keycloak(
        REALM, "client-id", "old-refresh"
    )
    after = time.time()

    expires_at = result["expires_at_timestamp"]
    assert isinstance(expires_at, float)
    # ~55s from now (expires_in=60, minus the 5s safety buffer)
    assert before + 50 <= expires_at <= after + 60


async def test_expires_at_never_negative_when_expires_in_is_zero(monkeypatch):
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 0}),
    )

    result = await refresh_user_access_token_from_keycloak(
        REALM, "client-id", "old-refresh"
    )

    expires_at = result["expires_at_timestamp"]
    assert isinstance(expires_at, float)
    assert expires_at >= time.time() - 1


async def test_token_url_and_form_built_correctly(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _token_response({"access_token": "tok", "expires_in": 300})

    _install_transport(monkeypatch, handler)

    await refresh_user_access_token_from_keycloak(
        f"{REALM}/",  # trailing slash must be stripped
        "my-client",
        "old-refresh",
    )

    assert str(seen[0].url) == f"{REALM}/protocol/openid-connect/token"
    body = dict(httpx.QueryParams(seen[0].content.decode()))
    assert body["grant_type"] == "refresh_token"
    assert body["client_id"] == "my-client"
    assert body["refresh_token"] == "old-refresh"


# ---------------------------------------------------------------------------
# Error paths — bounded and fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,payload,expected",
    [
        (400, {"error": "invalid_grant"}, "invalid_grant"),
        (401, {"error": "unauthorized_client"}, "unauthorized_client"),
        # Anything outside RFC 6749 §5.2 is reported generically, never echoed.
        (400, {"error": "session_not_active"}, "unrecognized"),
        # A non-string `error` must degrade too — an unhashable one (a list)
        # previously made the frozenset membership test raise TypeError from
        # inside the except handler, escaping the RuntimeError normalization.
        (400, {"error": []}, "unrecognized"),
        (400, {"error": {"code": "invalid_grant"}}, "unrecognized"),
        (400, {"error": 42}, "unrecognized"),
        (500, None, "unparseable"),  # HTML error page from a proxy, say
    ],
)
async def test_http_error_reports_an_allow_listed_code(
    monkeypatch, status, payload, expected
):
    _install_transport(
        monkeypatch,
        lambda request: (
            httpx.Response(status, json=payload)
            if payload is not None
            else httpx.Response(status, text="<html>gateway error</html>")
        ),
    )

    with pytest.raises(RuntimeError, match="Token refresh failed") as exc_info:
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    message = str(exc_info.value)
    assert expected in message
    assert str(status) in message


async def test_error_body_never_reaches_the_log_or_the_exception(monkeypatch, caplog):
    """A Keycloak error body is untrusted free text (OWASP A09 / CWE-532).

    It previously landed in this module's log AND the RuntimeError, which
    Knowledge Flow and MCP log again — carrying whatever the body contained.
    """
    body = {
        "error": "invalid_grant",
        "error_description": "Session not active for user 8f2c-UID-alice; refresh_token=eyJhbGci.SECRET",
    }
    _install_transport(monkeypatch, lambda request: httpx.Response(400, json=body))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as exc_info:
            await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    blob = caplog.text + str(exc_info.value)
    for secret in ("8f2c-UID-alice", "SECRET", "error_description"):
        assert secret not in blob, f"{secret!r} leaked into a log sink"
    # …while staying diagnosable.
    assert "invalid_grant" in blob and "400" in blob


@pytest.mark.parametrize(
    "body,label",
    [
        ({"access_token": "tok", "expires_in": "8f2c-UID-alice SECRET"}, "expires_in"),
        ({"access_token": "tok", "expires_in": {"nested": "SECRET"}}, "expires_in"),
        ({"access_token": "tok", "expires_in": True}, "bool expires_in"),
        # Explicit JSON null is NOT absent: absent gets the RFC 6749 §5.1
        # default, null is a response that failed to state its own lifetime
        # (both reach `payload.get()` as None — the `_MISSING` sentinel is what
        # keeps them apart).
        ({"access_token": "tok", "expires_in": None}, "null expires_in"),
        # No OAuth server issues a token that expired before it was sent.
        ({"access_token": "tok", "expires_in": -300}, "negative expires_in"),
        ({"access_token": "tok", "expires_in": "-300"}, "negative str expires_in"),
        ({"expires_in": 300}, "missing access_token"),
        ({"access_token": "", "expires_in": 300}, "empty access_token"),
        ({"access_token": ["SECRET"], "expires_in": 300}, "non-string access_token"),
        ([{"access_token": "tok"}], "top-level array"),
    ],
    ids=lambda v: v if isinstance(v, str) else "",
)
async def test_malformed_2xx_body_never_reaches_a_log_sink(
    monkeypatch, caplog, body, label
):
    """A 200 is not a promise of a well-formed token response.

    `int(payload["expires_in"])` put the rejected value straight into a
    ValueError, and a missing/!str `access_token` deferred the failure to
    wherever the token got used. Both escaped through the same downstream
    loggers as the non-2xx path this module already sanitizes.
    """
    _install_transport(monkeypatch, lambda request: httpx.Response(200, json=body))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="malformed token response") as exc_info:
            await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    blob = caplog.text + str(exc_info.value)
    for secret in ("8f2c-UID-alice", "SECRET", "nested"):
        assert secret not in blob, f"{secret!r} leaked from a malformed {label}"


async def test_non_json_2xx_body_fails_closed(monkeypatch):
    """A proxy's HTML error page served as 200 must not become a token."""
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, text="<html>gateway is confused</html>"),
    )

    with pytest.raises(RuntimeError, match="malformed token response"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")


async def test_huge_expires_in_is_clamped_to_the_ceiling(monkeypatch):
    """A bogus lifetime must not mint an effectively immortal expiry.

    `expires_in: 1e15` from a misconfigured IdP or intercepting proxy would
    otherwise put `expires_at_timestamp` decades out, and callers that gate on
    it (`_workspace_access_token`) would re-present a long-dead bearer forever
    without ever attempting another refresh.
    """
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 10**15}),
    )

    result = await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    expires_at = result["expires_at_timestamp"]
    assert isinstance(expires_at, float)
    assert expires_at <= time.time() + 86_400


async def test_absent_expires_in_falls_back_to_the_documented_default(monkeypatch):
    """`expires_in` is OPTIONAL (RFC 6749 §5.1) — absent is valid, unlike junk."""
    _install_transport(
        monkeypatch, lambda request: _token_response({"access_token": "tok"})
    )

    result = await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    expires_at = result["expires_at_timestamp"]
    assert isinstance(expires_at, float)
    assert expires_at >= time.time() + 290


async def test_malformed_body_emits_error_status_not_ok(monkeypatch):
    """A rejected 2xx must not be counted as a successful refresh."""
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={"expires_in": 300}),
    )
    writer = _install_kpi(monkeypatch)

    with pytest.raises(RuntimeError, match="malformed token response"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    assert writer.emitted[0][1]["status"] == "error"


async def test_timeout_is_bounded_and_fails_closed(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("keycloak too slow", request=request)

    _install_transport(monkeypatch, handler)

    with pytest.raises(RuntimeError, match="timed out"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")


async def test_transport_error_fails_closed(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("keycloak unreachable", request=request)

    _install_transport(monkeypatch, handler)

    with pytest.raises(RuntimeError, match="transport error"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")


async def test_raw_os_error_is_normalized_not_leaked(monkeypatch):
    """An ssl/socket error surfacing below httpx must still become RuntimeError.

    The 401-recovery callers catch RuntimeError to turn a failed refresh into
    an ordinary auth failure; a raw ConnectionResetError escaping this module
    would hit the tool path as an unhandled exception instead.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise ConnectionResetError("peer reset during TLS handshake")

    _install_transport(monkeypatch, handler)

    with pytest.raises(RuntimeError, match="transport error"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")


async def test_failure_does_not_wedge_the_singleflight_slot(monkeypatch):
    """A failed refresh must not poison later refreshes for the same identity."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="boom")
        return _token_response({"access_token": "recovered", "expires_in": 300})

    _install_transport(monkeypatch, handler)

    with pytest.raises(RuntimeError):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    result = await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    assert result["access_token"] == "recovered"
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Singleflight — coalesce per identity, never across principals
# ---------------------------------------------------------------------------


async def test_concurrent_refreshes_for_one_identity_coalesce(monkeypatch):
    calls = {"n": 0}
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        await release.wait()
        return _token_response({"access_token": "shared-access", "expires_in": 300})

    _install_transport(monkeypatch, handler)

    waiters = [
        asyncio.create_task(
            refresh_user_access_token_from_keycloak(REALM, "client-id", "same-refresh")
        )
        for _ in range(10)
    ]
    await asyncio.sleep(0)  # let every waiter reach the registry
    release.set()
    results = await asyncio.gather(*waiters)

    assert calls["n"] == 1, "10 concurrent refreshes must share one Keycloak round trip"
    assert {r["access_token"] for r in results} == {"shared-access"}


async def test_distinct_principals_never_share_a_token(monkeypatch):
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        body = dict(httpx.QueryParams(request.content.decode()))
        await release.wait()
        # Each principal's own refresh token decides its access token.
        return _token_response(
            {"access_token": f"access-for-{body['refresh_token']}", "expires_in": 300}
        )

    _install_transport(monkeypatch, handler)

    alice = asyncio.create_task(
        refresh_user_access_token_from_keycloak(REALM, "client-id", "alice-refresh")
    )
    bob = asyncio.create_task(
        refresh_user_access_token_from_keycloak(REALM, "client-id", "bob-refresh")
    )
    await asyncio.sleep(0)
    release.set()
    alice_payload, bob_payload = await asyncio.gather(alice, bob)

    assert alice_payload["access_token"] == "access-for-alice-refresh"
    assert bob_payload["access_token"] == "access-for-bob-refresh"


async def test_same_token_different_client_id_does_not_coalesce(monkeypatch):
    """The coalescing key spans the realm and client, not just the token."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _token_response({"access_token": "tok", "expires_in": 300})

    _install_transport(monkeypatch, handler)

    await asyncio.gather(
        refresh_user_access_token_from_keycloak(REALM, "client-a", "same"),
        refresh_user_access_token_from_keycloak(REALM, "client-b", "same"),
    )

    assert calls["n"] == 2


async def test_concurrent_callers_all_see_a_refresh_failure(monkeypatch):
    """Retrieving the exception in the cleanup callback must not swallow it."""
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await release.wait()
        return httpx.Response(500, text="boom")

    _install_transport(monkeypatch, handler)

    waiters = [
        asyncio.create_task(
            refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
        )
        for _ in range(3)
    ]
    await asyncio.sleep(0)
    release.set()
    outcomes = await asyncio.gather(*waiters, return_exceptions=True)

    assert all(isinstance(o, RuntimeError) for o in outcomes), outcomes


async def test_cancelled_sole_caller_leaves_no_unretrieved_exception(monkeypatch):
    """A disconnect mid-refresh must not leave asyncio complaining at teardown.

    The refresh is shielded, so it outlives its only caller. If nothing then
    retrieved the failure, asyncio would log "Task exception was never
    retrieved" when the task is collected.
    """
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await release.wait()
        return httpx.Response(500, text="boom")

    _install_transport(monkeypatch, handler)

    solo = asyncio.create_task(
        refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    )
    await asyncio.sleep(0)
    solo.cancel()
    await asyncio.sleep(0)
    release.set()
    await asyncio.sleep(0.05)

    inner = [t for t in asyncio.all_tasks() if t.get_name() == "keycloak-token-refresh"]
    assert not inner, "the shielded refresh should have finished by now"
    # The cleanup callback already consumed the exception; asyncio therefore has
    # nothing left to report when the task object is collected.


async def test_cancelled_caller_does_not_abort_the_shared_refresh(monkeypatch):
    """A disconnecting client must not kill the refresh its peers are awaiting."""
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await release.wait()
        return _token_response({"access_token": "survived", "expires_in": 300})

    _install_transport(monkeypatch, handler)

    quitter = asyncio.create_task(
        refresh_user_access_token_from_keycloak(REALM, "client-id", "shared")
    )
    stayer = asyncio.create_task(
        refresh_user_access_token_from_keycloak(REALM, "client-id", "shared")
    )
    await asyncio.sleep(0)
    quitter.cancel()
    await asyncio.sleep(0)
    release.set()

    assert (await stayer)["access_token"] == "survived"


# ---------------------------------------------------------------------------
# The defect itself: the event loop must keep running during a refresh
# ---------------------------------------------------------------------------


async def test_refresh_does_not_block_the_event_loop(monkeypatch):
    """Unrelated work must keep advancing while a slow refresh is in flight.

    This is the offline stand-in for the issue's delayed-Keycloak scenario: the
    ticker models another SSE turn on the same pod. Against the pre-change
    synchronous implementation the ticker cannot advance at all, because the
    refresh owns the only thread until it returns.
    """
    refresh_window = 0.20
    ticks = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(refresh_window)
        return _token_response({"access_token": "tok", "expires_in": 300})

    _install_transport(monkeypatch, handler)

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    ticker_task = asyncio.create_task(ticker())
    try:
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    finally:
        ticker_task.cancel()

    assert ticks >= 5, (
        f"event loop stalled during the refresh window: only {ticks} ticks "
        "advanced while the refresh was in flight"
    )


# ---------------------------------------------------------------------------
# Observability — duration and outcome, no secrets or user identity
# ---------------------------------------------------------------------------


class _CapturingKpiStore:
    """Minimal BaseKPIStore that keeps every event the real writer emits."""

    def __init__(self) -> None:
        self.events: list = []

    def ensure_ready(self) -> None:
        return None

    def index_event(self, event) -> None:
        self.events.append(event)

    def bulk_index(self, events) -> None:
        self.events.extend(events)

    def query(self, q: KPIQuery) -> KPIQueryResult:
        raise NotImplementedError("these tests only assert on emitted events")


class _KpiCapture:
    """Records emissions through the REAL KPIWriter.

    Deliberately not a hand-rolled timer double: the behaviour under test is
    `KPIWriter._TimerImpl.__exit__` forcing `status="error"` on an exception.
    A fake that re-implements that rule would assert against its own copy and
    keep passing if the real writer ever changed.
    """

    def __init__(self) -> None:
        self.store = _CapturingKpiStore()
        self.writer = KPIWriter(store=self.store)

    @property
    def emitted(self) -> list[tuple[str, dict]]:
        return [(e.metric.name, dict(e.dims or {})) for e in self.store.events]


def _install_kpi(monkeypatch) -> _KpiCapture:
    capture = _KpiCapture()

    class _Ctx:
        def get_kpi_writer(self):
            return capture.writer

    monkeypatch.setattr(user_token_refresher, "get_runtime_context", lambda: _Ctx())
    return capture


async def test_success_emits_duration_and_ok_status(monkeypatch):
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 300}),
    )
    writer = _install_kpi(monkeypatch)

    await refresh_user_access_token_from_keycloak(REALM, "client-id", "secret-refresh")

    assert len(writer.emitted) == 1
    name, dims = writer.emitted[0]
    # A dedicated metric name, NOT a `phase` dim on app.phase_latency_ms:
    # `phase` is not in PROMETHEUS_ALLOWED_LABELS and would be stripped, making
    # refresh timings indistinguishable from every other phase emitter.
    assert name == "auth.token_refresh_latency_ms"
    assert dims["status"] == "ok"


async def test_metric_labels_survive_the_prometheus_allow_list(monkeypatch):
    """Every dim emitted here must actually reach Grafana, not be stripped."""
    from fred_core.kpi.prometheus_kpi_store import PROMETHEUS_ALLOWED_LABELS

    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 300}),
    )
    writer = _install_kpi(monkeypatch)

    await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    emitted_dims = set(writer.emitted[0][1])
    stripped = emitted_dims - set(PROMETHEUS_ALLOWED_LABELS)
    assert not stripped, f"these dims never reach Prometheus: {stripped}"


async def test_failure_emits_error_status(monkeypatch):
    _install_transport(monkeypatch, lambda request: httpx.Response(500, text="boom"))
    writer = _install_kpi(monkeypatch)

    with pytest.raises(RuntimeError):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    assert writer.emitted[0][1]["status"] == "error"


async def test_timeout_emits_timeout_status_not_error(monkeypatch):
    """The timeout outcome must survive to the metric.

    Raising inside the timer block would make KPIWriter force status="error",
    collapsing "Keycloak is slow" into the same series as "Keycloak said no".
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("keycloak too slow", request=request)

    _install_transport(monkeypatch, handler)
    writer = _install_kpi(monkeypatch)

    with pytest.raises(RuntimeError, match="timed out"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    assert writer.emitted[0][1]["status"] == "timeout"


async def test_total_wait_is_bounded_even_if_a_phase_hangs(monkeypatch):
    """httpx's timeout is per-phase; the caller-visible bound is the total."""

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(60)  # far longer than the budget
        return _token_response({"access_token": "never", "expires_in": 300})

    _install_transport(monkeypatch, handler)
    monkeypatch.setattr(user_token_refresher, "REFRESH_TIMEOUT_SECONDS", 0.05)

    started = time.perf_counter()
    with pytest.raises(RuntimeError, match="timed out"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    elapsed = time.perf_counter() - started

    assert elapsed < 5, f"caller parked {elapsed:.1f}s despite the total budget"


async def test_the_exchange_task_itself_is_bounded_not_just_its_waiters(monkeypatch):
    """The total deadline must live in the shared task, not at the await site.

    A peer that keeps every individual phase alive — one byte inside each read
    window — never trips httpx's per-phase timeout. With the bound at the await
    site only, each caller gave up on schedule while the task ran on
    indefinitely, holding its `inflight` slot and a pooled connection; 32 such
    identities would pin the pool with nobody left waiting to notice. Sleeping
    inside the handler reproduces that shape: MockTransport awaits the handler
    inline, so no phase timeout can fire.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(60)
        return _token_response({"access_token": "never", "expires_in": 300})

    _install_transport(monkeypatch, handler)
    monkeypatch.setattr(user_token_refresher, "REFRESH_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(RuntimeError, match="timed out"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    state = user_token_refresher._LOOP_STATE[asyncio.get_running_loop()]
    assert state.inflight == {}, "the timed-out exchange kept its singleflight slot"
    survivors = [
        t for t in asyncio.all_tasks() if t.get_name() == "keycloak-token-refresh"
    ]
    assert survivors == [], "the exchange task outlived its own total deadline"


async def test_emitted_dims_carry_no_secret_or_user_identity(monkeypatch):
    _install_transport(
        monkeypatch,
        lambda request: _token_response(
            {"access_token": "super-secret-access", "expires_in": 300}
        ),
    )
    writer = _install_kpi(monkeypatch)

    await refresh_user_access_token_from_keycloak(
        REALM, "client-id", "super-secret-refresh"
    )

    blob = json.dumps(writer.emitted)
    for forbidden in ("super-secret-refresh", "super-secret-access"):
        assert forbidden not in blob
    # Identity dimensions must never reach the metric pipeline at all.
    # `actor_type` is the writer's own "system" tag, not a user identity.
    assert set(writer.emitted[0][1]) <= {"status", "actor_type"}
    assert writer.emitted[0][1]["actor_type"] == "system"


async def test_aclose_releases_the_loop_client(monkeypatch):
    """Shutdown must drop the cached client rather than leak it to the GC."""
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 300}),
    )
    await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    loop = asyncio.get_running_loop()
    state = user_token_refresher._LOOP_STATE[loop]

    await aclose_token_refresh_client()

    assert state.client.is_closed
    # The entry deliberately SURVIVES, marked closed. Dropping it let the next
    # refresh on the same still-running loop rebuild a 32-connection client that
    # nothing would ever close — a real leak during lifespan shutdown, where
    # ASGI is still finishing and a straggling 401 recovery can arrive.
    assert state.closed is True
    # Idempotent: a second close on an already-closed loop is a no-op.
    await aclose_token_refresh_client()


async def test_refresh_after_shutdown_fails_instead_of_rebuilding_a_client(monkeypatch):
    """A post-shutdown refresh must fail-closed, not silently leak a new pool."""
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 300}),
    )
    await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    first = user_token_refresher._LOOP_STATE[asyncio.get_running_loop()].client
    await aclose_token_refresh_client()

    with pytest.raises(RuntimeError, match="shut down"):
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    # Same (closed) client — no second pool was built behind the closer's back.
    assert user_token_refresher._LOOP_STATE[asyncio.get_running_loop()].client is first


async def test_client_closed_under_an_inflight_exchange_is_reported_as_shutdown(
    monkeypatch, caplog
):
    """The closed-client RuntimeError branch, driven by the REAL httpx message.

    The branch is selected by matching `"client has been closed"` in the
    exception text, which is httpx's own wording
    (`httpx/_client.py:1616`, httpx 0.28.1) and therefore silently ours to lose
    on any upgrade that rewords it. A hand-built `RuntimeError("...closed...")`
    would assert nothing about that; closing the real client and letting httpx
    raise is what makes this test break when the wording moves, instead of the
    branch degrading to "internal error" in production with no test noticing.

    The window is real, not contrived: the shutdown drain closes the client
    once its deadline expires, and `state.closed` is set only after — so a 401
    recovery arriving in between gets a live state holding a closed client.
    """
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 300}),
    )
    await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    state = user_token_refresher._LOOP_STATE[asyncio.get_running_loop()]
    # Exactly the drain's own step, without marking the state closed — the
    # `_loop_state()` shutdown guard would otherwise answer first and this
    # branch would never be reached.
    await state.client.aclose()

    # The setup refresh above logs its own INFO "succeeded" line, and whether
    # that line is CAPTURED depends on the log level whichever test ran before
    # this one happened to leave behind — so the assertion below is only
    # order-independent once the setup's records are dropped.
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="client closed"):
            await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "client closed during shutdown" in caplog.records[0].message


async def test_unexpected_runtime_error_is_not_reported_as_an_orderly_shutdown(
    monkeypatch, caplog
):
    """A RuntimeError that is NOT the closed client must say so, loudly.

    `NotImplementedError` is a `RuntimeError` subclass and not an
    `httpx.HTTPError`, so it lands in the same clause as the closed-client case
    — it is what httpx's base transport raises when none is wired. Reporting a
    wiring bug as "client closed" at WARNING is how that misconfiguration
    survives a deploy; the type has to be named, at ERROR, with a traceback.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise NotImplementedError("no transport wired")

    _install_transport(monkeypatch, handler)

    caplog.clear()  # same order-independence guard as the test above
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="internal error"):
            await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    assert [r.levelname for r in caplog.records] == ["ERROR"]
    assert "NotImplementedError" in caplog.records[0].getMessage()
    assert caplog.records[0].exc_info is not None


async def test_every_401_recovery_hop_is_still_a_coroutine():
    """Guard the whole chain, not just the helper (issue #2125 criterion 1).

    The liveness test above constrains only the refresher's own body. These are
    the four 401-recovery chains that reach it; if any hop is made sync again to
    satisfy some caller, the blocking-in-async defect is back and every other
    test here would still pass.
    """
    import inspect

    from fred_runtime.app.agent_app import _MediaClientAgentAdapter
    from fred_runtime.common.kf_base_client import KfBaseClient
    from fred_runtime.integrations.v2_runtime import adapters

    hops = [
        # Knowledge Flow clients
        KfBaseClient._try_refresh_token,
        KfBaseClient._current_access_token,
        # media fetch
        _MediaClientAgentAdapter.refresh_user_access_token,
        # MCP + vector search + workspace shims
        adapters._VectorSearchAgentShim.refresh_user_access_token,
        adapters._McpRuntimeAgentShim.refresh_user_access_token,
        adapters._WorkspaceAgentShim.refresh_user_access_token,
        # workspace filesystem (not in the original issue evidence)
        adapters.FredWorkspaceFs._token,
        adapters._workspace_access_token,
        adapters._refresh_runtime_context_access_token,
        # the shared helper itself
        refresh_user_access_token_from_keycloak,
    ]

    sync = [f.__qualname__ for f in hops if not inspect.iscoroutinefunction(f)]
    assert not sync, f"these must stay awaitable or the event loop blocks again: {sync}"


async def test_shared_client_never_persists_cookies_across_principals(monkeypatch):
    """One principal's Keycloak cookies must not ride along on the next.

    The pre-change code used a throwaway `httpx.post` per refresh, so no cookie
    state could cross principals. The shared client can, which is why its jar
    refuses to store.
    """
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie", ""))
        return httpx.Response(
            200,
            json={"access_token": "tok", "expires_in": 300},
            headers={"set-cookie": "KEYCLOAK_IDENTITY=principal-a; Path=/"},
        )

    _install_transport(monkeypatch, handler)

    await refresh_user_access_token_from_keycloak(REALM, "client-id", "alice-refresh")
    await refresh_user_access_token_from_keycloak(REALM, "client-id", "bob-refresh")

    assert seen == ["", ""], f"cookie leaked between principals: {seen}"


async def test_aclose_drains_inflight_before_closing_the_transport(monkeypatch):
    """Shutdown waits for an in-flight refresh instead of closing under it.

    Asserted as an ORDERING, not just a successful result: closing the
    transport while a shielded refresh is still running is what produces
    "Cannot send a request, as the client has been closed", and a
    MockTransport that has already been entered would survive that anyway — so
    only the order proves the drain actually happened.
    """
    order: list[str] = []
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await release.wait()
        order.append("refresh-completed")
        return _token_response({"access_token": "survived", "expires_in": 300})

    _install_transport(monkeypatch, handler)

    inflight = asyncio.create_task(
        refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    )
    await asyncio.sleep(0)

    async def _close() -> None:
        await aclose_token_refresh_client()
        order.append("client-closed")

    closing = asyncio.create_task(_close())
    await asyncio.sleep(0)
    release.set()

    assert (await inflight)["access_token"] == "survived"
    await closing
    assert order == ["refresh-completed", "client-closed"], order


async def test_refresh_still_works_without_a_runtime_context(monkeypatch):
    """Metrics are optional: the CLI and unit tests have no runtime context."""

    def _raise() -> None:
        raise RuntimeError("RuntimeContext has not been initialized.")

    monkeypatch.setattr(user_token_refresher, "get_runtime_context", _raise)
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 300}),
    )

    result = await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")
    assert result["access_token"] == "tok"


# Deliberately a SYNC test — it must drive two SEPARATE event loops to their
# graveyard, which no single pytest-asyncio loop can do. The module-wide
# asyncio pytestmark then mislabels it, which is cosmetic; silence just that.
@pytest.mark.filterwarnings(
    "ignore:The test .* is marked with '@pytest.mark.asyncio' but it is not an async function"
)
def test_dead_loop_state_is_swept_not_leaked(monkeypatch):
    """The registry must not grow one orphaned client per finished event loop.

    A WeakKeyDictionary looked self-cleaning but never was: each value holds
    asyncio.Tasks (which hold their loop) and a loop-bound client, so the
    weakly-referenced key stayed strongly reachable through its own value and
    no entry was ever collected. The sweep in `_loop_state()` is the actual
    mechanism; this pins it.
    """
    _install_transport(
        monkeypatch,
        lambda request: _token_response({"access_token": "tok", "expires_in": 300}),
    )

    async def one_refresh() -> None:
        await refresh_user_access_token_from_keycloak(REALM, "client-id", "tok")

    asyncio.run(one_refresh())  # loop A lives, refreshes, then closes
    assert len(user_token_refresher._LOOP_STATE) == 1  # A's entry still there

    observed: dict[str, object] = {}

    async def touch_registry() -> None:
        # Loop B: the sweep runs on first touch. Assertions must happen HERE,
        # while B is alive — after asyncio.run returns, B itself is closed.
        state = user_token_refresher._loop_state()
        observed["entries"] = len(user_token_refresher._LOOP_STATE)
        observed["current_registered"] = (
            user_token_refresher._LOOP_STATE.get(asyncio.get_running_loop()) is state
        )

    asyncio.run(touch_registry())

    assert observed == {"entries": 1, "current_registered": True}, (
        f"dead loop A's entry survived the sweep: {observed}"
    )


async def test_refresh_arriving_mid_drain_is_also_drained(monkeypatch):
    """The drain must cover exchanges that START while it is waiting.

    Asserted as an ORDERING, not an outcome: the drain has to still be running
    when the late exchange finishes. Asserting "neither call raised" does not
    discriminate — httpx only checks the closed state at the START of send, so a
    request already inside the transport survives a close that a one-shot
    snapshot of `inflight` would have performed too early.
    """
    order: list[str] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    release_second = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        body = dict(httpx.QueryParams(request.content.decode()))
        if body["refresh_token"] == "tok-a":
            first_started.set()
            await release_first.wait()
        else:
            # Held so it can only finish while the drain is still running: that
            # is the whole property under test.
            await release_second.wait()
        return _token_response({"access_token": "tok", "expires_in": 300})

    _install_transport(monkeypatch, handler)

    async def refresh(tag: str, token: str) -> None:
        await refresh_user_access_token_from_keycloak(REALM, "client-id", token)
        order.append(tag)

    first = asyncio.create_task(refresh("first", "tok-a"))
    await first_started.wait()

    async def close() -> None:
        await aclose_token_refresh_client()
        order.append("drain-finished")

    closer = asyncio.create_task(close())
    await asyncio.sleep(0)  # the drain is now waiting on `first`

    # Registers in `inflight` AFTER the drain began, so a one-shot snapshot
    # cannot see it and the drain would finish without ever waiting for it.
    second = asyncio.create_task(refresh("second", "tok-b"))
    await asyncio.sleep(0)

    release_first.set()
    await first
    await asyncio.sleep(0)  # give the drain a chance to re-read `inflight`
    release_second.set()
    await asyncio.gather(second, closer)

    assert order.index("second") < order.index("drain-finished"), (
        f"the drain finished without waiting for the mid-drain exchange: {order}"
    )


async def test_coalesced_callers_each_get_their_own_payload(monkeypatch):
    """One shared task resolves to ONE object; waiters must not share it.

    The isolation rests on TWO things, so both are asserted: each waiter gets a
    distinct dict, AND the payload is a flat projection of the response rather
    than the decoded body. The projection is what makes a shallow copy exact —
    an earlier version returned `raw`, where a nested value stayed shared
    between waiters and only a deep copy (unbounded, on the event loop) helped.
    """
    _install_transport(
        monkeypatch,
        lambda request: _token_response(
            {
                "access_token": "tok",
                "refresh_token": "next",
                "expires_in": 300,
                # A nested, attacker-shaped extra the projection must DROP.
                "other_claims": {"roles": ["a", "b"]},
            }
        ),
    )

    a, b = await asyncio.gather(
        refresh_user_access_token_from_keycloak(REALM, "client-id", "same"),
        refresh_user_access_token_from_keycloak(REALM, "client-id", "same"),
    )

    assert a == b
    assert a is not b, "coalesced callers share one payload object"
    # Projected, not passed through: nothing nested survives to be shared.
    assert set(a) == {"access_token", "refresh_token", "expires_at_timestamp"}
    assert all(not isinstance(v, (dict, list)) for v in a.values())
    a["access_token"] = "mutated-by-caller-a"
    assert b["access_token"] == "tok"
