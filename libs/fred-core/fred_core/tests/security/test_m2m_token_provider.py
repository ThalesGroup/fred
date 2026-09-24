# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

import asyncio

import httpx
import pytest

from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider


class _Clock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _config() -> M2MAuthConfig:
    return M2MAuthConfig(
        keycloak_realm_url="https://identity.invalid/realms/test",
        client_id="workload",
        secret_env="TEST_M2M_PROVIDER_SECRET",  # pragma: allowlist secret  # nosec B106
    )


@pytest.mark.asyncio
async def test_concurrent_failures_are_serialized_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", "synthetic-secret")
    started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0
    active = 0
    max_active = 0

    async def _endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal attempts, active, max_active
        attempts += 1
        active += 1
        max_active = max(max_active, active)
        started.set()
        await release.wait()
        active -= 1
        return httpx.Response(503, request=request, text="upstream-private-detail")

    provider = M2MTokenProvider(
        _config(),
        transport=httpx.MockTransport(_endpoint),
    )
    callers = [asyncio.create_task(provider.get_token()) for _ in range(8)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*callers, return_exceptions=True)

    assert attempts == 8
    assert max_active == 1
    assert all(type(result) is RuntimeError for result in results)
    assert all(str(result) == "Workload token refresh failed." for result in results)


@pytest.mark.asyncio
async def test_immediate_retry_recovers_and_success_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", "synthetic-secret")
    clock = _Clock()
    attempts = 0
    available = False

    def _endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if not available:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            request=request,
            json={"access_token": "workload-token", "expires_in": 120},  # nosec B105 - protocol metadata or synthetic fixture
        )

    provider = M2MTokenProvider(
        _config(),
        wall_clock=clock,
        transport=httpx.MockTransport(_endpoint),
    )
    with pytest.raises(RuntimeError):
        await provider.get_token()
    available = True

    tokens = await asyncio.gather(*(provider.get_token() for _ in range(8)))

    assert tokens == ["workload-token"] * 8
    assert attempts == 2
    assert await provider.get_token() == "workload-token"
    assert attempts == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"access_token": "", "expires_in": 60},  # nosec B105 - protocol metadata or synthetic fixture
        {"access_token": "token", "expires_in": 0},  # nosec B105 - protocol metadata or synthetic fixture
        {"access_token": "token", "expires_in": float("inf")},  # nosec B105 - protocol metadata or synthetic fixture
        {"access_token": "token", "expires_in": True},  # nosec B105 - protocol metadata or synthetic fixture
    ],
)
async def test_invalid_token_response_is_a_bounded_failure(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", "synthetic-secret")

    def _endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=payload)

    provider = M2MTokenProvider(_config(), transport=httpx.MockTransport(_endpoint))

    with pytest.raises(RuntimeError) as raised:
        await provider.get_token()

    assert str(raised.value) == "Workload token refresh failed."
    assert raised.value.__cause__ is None


@pytest.mark.asyncio
async def test_unreachable_endpoint_stays_a_transport_error_on_immediate_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry keeps the transport error class and omits request details."""
    import secrets

    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", secrets.token_urlsafe())
    attempts = 0

    def _endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("upstream-private-detail", request=request)

    provider = M2MTokenProvider(
        _config(),
        transport=httpx.MockTransport(_endpoint),
    )
    with pytest.raises(httpx.ConnectError) as failed:
        await provider.get_token()
    with pytest.raises(httpx.ConnectError) as retried:
        await provider.get_token()

    assert attempts == 2
    for raised in (failed, retried):
        assert str(raised.value) == "Workload token refresh failed."
        assert raised.value.__cause__ is None
        with pytest.raises(RuntimeError):
            _ = raised.value.request


@pytest.mark.asyncio
async def test_token_expired_during_refresh_is_never_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", "synthetic-secret")
    clock = _Clock()

    def _endpoint(request: httpx.Request) -> httpx.Response:
        clock.advance(61.0)
        return httpx.Response(
            200,
            request=request,
            json={"access_token": "already-expired", "expires_in": 60},  # nosec B105 - protocol metadata or synthetic fixture
        )

    provider = M2MTokenProvider(
        _config(),
        wall_clock=clock,
        transport=httpx.MockTransport(_endpoint),
    )

    with pytest.raises(RuntimeError) as raised:
        await provider.get_token()

    assert str(raised.value) == "Workload token refresh failed."
    assert provider._token is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_missing_secret_name_is_not_disclosed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_name = "TEST_M2M_PROVIDER_SECRET"  # pragma: allowlist secret  # nosec B105
    monkeypatch.delenv(secret_name, raising=False)
    provider = M2MTokenProvider(_config())

    with pytest.raises(RuntimeError) as raised:
        await provider.get_token()

    assert secret_name not in str(raised.value)
    assert raised.value.__cause__ is None


@pytest.mark.asyncio
async def test_cancelled_refresh_allows_the_next_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", "synthetic-secret")
    started = asyncio.Event()
    block = asyncio.Event()
    attempts = 0

    async def _endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            started.set()
            await block.wait()
        return httpx.Response(
            200,
            request=request,
            json={"access_token": "recovered", "expires_in": 120},  # nosec B105 - protocol metadata or synthetic fixture
        )

    provider = M2MTokenProvider(_config(), transport=httpx.MockTransport(_endpoint))
    refresh = asyncio.create_task(provider.get_token())
    await started.wait()
    refresh.cancel()
    with pytest.raises(asyncio.CancelledError):
        await refresh

    assert await provider.get_token() == "recovered"
    assert attempts == 2


@pytest.mark.asyncio
async def test_metrics_distinguish_iam_calls_cache_and_failures(monkeypatch):
    import secrets

    from fred_pod.security import backend_to_backend_auth as auth

    from fred_core.security.auth_metrics import M2M_CACHE, M2M_REQUEST, observe_m2m

    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", secrets.token_urlsafe())
    monkeypatch.setattr(auth, "_token_observer", observe_m2m)
    token = secrets.token_urlsafe()
    before_requests = M2M_REQUEST.labels("initial", "success")._sum.get()
    before_hits = M2M_CACHE.labels("hit")._value.get()
    attempts = 0

    def endpoint(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={"access_token": token, "expires_in": 300})

    provider = M2MTokenProvider(_config(), transport=httpx.MockTransport(endpoint))
    assert await provider.get_token() == token
    assert await provider.get_token() == token
    assert attempts == 1
    assert M2M_REQUEST.labels("initial", "success")._sum.get() > before_requests
    assert M2M_CACHE.labels("hit")._value.get() == before_hits + 1


@pytest.mark.asyncio
async def test_metrics_observer_failure_cannot_break_auth(monkeypatch):
    import secrets

    from fred_pod.security import backend_to_backend_auth as auth

    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", secrets.token_urlsafe())

    def broken(*args):
        raise RuntimeError("metrics unavailable")

    monkeypatch.setattr(auth, "_token_observer", broken)
    token = secrets.token_urlsafe()
    provider = M2MTokenProvider(
        _config(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"access_token": token, "expires_in": 300}
            )
        ),
    )
    assert await provider.get_token() == token


@pytest.mark.asyncio
async def test_metrics_export_each_failed_request(monkeypatch):
    import secrets

    from fred_pod.security import backend_to_backend_auth as auth
    from prometheus_client import REGISTRY, generate_latest

    from fred_core.security.auth_metrics import observe_m2m

    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", secrets.token_urlsafe())
    monkeypatch.setattr(auth, "_token_observer", observe_m2m)
    metric = "fred_auth_m2m_request_seconds_count"
    before = (
        REGISTRY.get_sample_value(metric, {"operation": "initial", "outcome": "error"})
        or 0
    )
    provider = M2MTokenProvider(
        _config(), transport=httpx.MockTransport(lambda request: httpx.Response(503))
    )
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await provider.get_token()
    assert (
        REGISTRY.get_sample_value(metric, {"operation": "initial", "outcome": "error"})
        == before + 2
    )
    exported = generate_latest().decode()
    assert "identity.invalid" not in exported


@pytest.mark.asyncio
async def test_metrics_separate_initial_token_and_renewal(monkeypatch):
    import secrets

    from fred_pod.security import backend_to_backend_auth as auth
    from prometheus_client import REGISTRY

    from fred_core.security.auth_metrics import observe_m2m

    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", secrets.token_urlsafe())
    monkeypatch.setattr(auth, "_token_observer", observe_m2m)
    clock = _Clock()
    metric = "fred_auth_m2m_request_seconds_count"

    def count(operation):
        return (
            REGISTRY.get_sample_value(
                metric, {"operation": operation, "outcome": "success"}
            )
            or 0
        )

    initial, renewal = count("initial"), count("renewal")
    token = secrets.token_urlsafe()
    provider = M2MTokenProvider(
        _config(),
        wall_clock=clock,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"access_token": token, "expires_in": 120}
            )
        ),
    )
    await provider.get_token()
    await provider.get_token()
    assert count("initial") == initial + 1
    assert count("renewal") == renewal
    clock.advance(91)
    await provider.get_token()
    assert count("initial") == initial + 1
    assert count("renewal") == renewal + 1
