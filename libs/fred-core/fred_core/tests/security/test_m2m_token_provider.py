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
from pydantic import AnyUrl, ValidationError

from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider
from fred_core.security.structure import M2MSecurity


class _Clock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _config(*, cooldown: float = 5.0) -> M2MAuthConfig:
    return M2MAuthConfig(
        keycloak_realm_url="https://identity.invalid/realms/test",
        client_id="workload",
        secret_env="TEST_M2M_PROVIDER_SECRET",  # pragma: allowlist secret  # nosec B106
        refresh_failure_cooldown_seconds=cooldown,
    )


@pytest.mark.asyncio
async def test_concurrent_failure_has_one_attempt_and_one_shared_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_M2M_PROVIDER_SECRET", "synthetic-secret")
    clock = _Clock()
    started = asyncio.Event()
    release = asyncio.Event()
    attempts = 0

    async def _endpoint(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        started.set()
        await release.wait()
        return httpx.Response(503, request=request, text="upstream-private-detail")

    provider = M2MTokenProvider(
        _config(),
        monotonic_clock=clock,
        wall_clock=clock,
        transport=httpx.MockTransport(_endpoint),
    )
    callers = [asyncio.create_task(provider.get_token()) for _ in range(8)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*callers, return_exceptions=True)

    assert attempts == 1
    assert all(type(result) is RuntimeError for result in results)
    assert all(str(result) == "Workload token refresh failed." for result in results)

    with pytest.raises(RuntimeError, match="Workload token refresh failed"):
        await provider.get_token()
    assert attempts == 1


@pytest.mark.asyncio
async def test_one_probe_recovers_after_cooldown_and_success_is_cached(
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
        monotonic_clock=clock,
        wall_clock=clock,
        transport=httpx.MockTransport(_endpoint),
    )
    with pytest.raises(RuntimeError):
        await provider.get_token()
    clock.advance(5.0)
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
        monotonic_clock=clock,
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
async def test_cancelled_refresh_does_not_start_a_cooldown(
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


@pytest.mark.parametrize("value", [0, -1, 61, float("inf"), float("nan")])
def test_refresh_failure_cooldown_is_positive_finite_and_bounded(value: float) -> None:
    with pytest.raises(ValidationError):
        _config(cooldown=value)
    with pytest.raises(ValidationError):
        M2MSecurity(
            realm_url=AnyUrl("https://identity.invalid/realms/test"),
            client_id="workload",
            refresh_failure_cooldown_seconds=value,
        )
