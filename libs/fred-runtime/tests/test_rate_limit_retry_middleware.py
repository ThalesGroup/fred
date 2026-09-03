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

"""
Tests for `RateLimitRetryMiddleware` — the model-call 429 retry loop.

Covers what the frame-composition tests cannot: that a throttled call is
actually retried, that a non-429 failure is NOT, that both bounds (attempt
count and wall-clock budget) terminate the loop, and that throttling is
observable through `llm.rate_limit_events_total`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fred_core.kpi import KPIActor
from fred_runtime.react.middleware import (
    ProviderRateLimitError,
    RateLimitRetryMiddleware,
    rate_limit_retry,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from langchain.agents.middleware.types import ModelRequest

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for the `response` attribute of a provider error."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


class _RateLimited(Exception):
    def __init__(self, retry_after: str | None = None) -> None:
        super().__init__("Error code: 429 - {'type': 'rate_limited', 'code': '1300'}")
        headers = {"Retry-After": retry_after} if retry_after else {}
        self.response = _FakeResponse(429, headers)


class _Boom(Exception):
    """A failure that is emphatically not a rate limit."""


class _RecordingKPI:
    def __init__(self) -> None:
        self.counts: list[tuple[str, dict[str, Any]]] = []

    def count(
        self,
        name: str,
        inc: int = 1,
        *,
        dims: dict[str, Any] | None = None,
        labels: Any = None,
        actor: KPIActor,
    ) -> None:
        self.counts.append((name, dims or {}))


def _binding() -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(language=None),
        portable_context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _middleware(kpi: _RecordingKPI | None = None) -> RateLimitRetryMiddleware:
    return RateLimitRetryMiddleware(kpi=cast(Any, kpi), binding=_binding())


class _Request:
    """Only `.model` is read by the middleware."""

    model = None


def _request() -> ModelRequest:
    return cast(ModelRequest, _Request())


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Retry delays are asserted, never actually waited on.

    Sleeping advances a fake monotonic clock instead of blocking, so the
    wall-clock budget is exercised for real: with a no-op sleep, time never
    moves and the budget could never trip.
    """

    slept: list[float] = []
    now = 0.0

    async def _fake_sleep(delay: float) -> None:
        nonlocal now
        slept.append(delay)
        now += delay

    monkeypatch.setattr(rate_limit_retry, "asyncio", SimpleNamespace(sleep=_fake_sleep))
    monkeypatch.setattr(
        rate_limit_retry, "time", SimpleNamespace(monotonic=lambda: now)
    )
    return slept


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_throttled_call_is_retried_and_succeeds() -> None:
    attempts = 0

    async def handler(request: ModelRequest) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _RateLimited()
        return "answer"

    result = await _middleware().awrap_model_call(_request(), handler)

    assert result == "answer"
    assert attempts == 3


@pytest.mark.asyncio
async def test_a_non_rate_limit_failure_is_not_retried() -> None:
    """A retry loop that swallows genuine errors is worse than no retry loop."""

    attempts = 0

    async def handler(request: ModelRequest) -> Any:
        nonlocal attempts
        attempts += 1
        raise _Boom("connection reset")

    with pytest.raises(_Boom):
        await _middleware().awrap_model_call(_request(), handler)

    assert attempts == 1


@pytest.mark.asyncio
async def test_exhausted_retries_raise_a_shaped_error() -> None:
    """The user must see a rate-limit sentence, not the provider's raw JSON."""

    async def handler(request: ModelRequest) -> Any:
        raise _RateLimited()

    with pytest.raises(ProviderRateLimitError) as excinfo:
        await _middleware().awrap_model_call(_request(), handler)

    assert "rate-limiting" in str(excinfo.value)
    assert "1300" not in str(excinfo.value)
    assert excinfo.value.attempts == rate_limit_retry._MAX_ATTEMPTS
    assert isinstance(excinfo.value.__cause__, _RateLimited)


@pytest.mark.asyncio
async def test_the_attempt_count_bounds_the_loop() -> None:
    attempts = 0

    async def handler(request: ModelRequest) -> Any:
        nonlocal attempts
        attempts += 1
        raise _RateLimited()

    with pytest.raises(ProviderRateLimitError):
        await _middleware().awrap_model_call(_request(), handler)

    assert attempts == rate_limit_retry._MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_the_wall_clock_budget_bounds_the_loop(
    monkeypatch: pytest.MonkeyPatch,
    _no_real_sleep: list[float],
) -> None:
    """A provider asking for longer than the budget still gets one clamped
    wait — Mistral's TPM limit sends `Retry-After: 60`, which is exactly the
    incident this middleware exists for, so rejecting it would retry nothing."""

    monkeypatch.setattr(rate_limit_retry, "_MAX_ATTEMPTS", 50)
    attempts = 0

    async def handler(request: ModelRequest) -> Any:
        nonlocal attempts
        attempts += 1
        raise _RateLimited(retry_after=str(rate_limit_retry._RETRY_BUDGET_S + 10))

    with pytest.raises(ProviderRateLimitError):
        await _middleware().awrap_model_call(_request(), handler)

    assert attempts == 2
    assert _no_real_sleep == [rate_limit_retry._RETRY_BUDGET_S]


@pytest.mark.asyncio
async def test_the_budget_also_ends_a_loop_that_accumulates_into_it(
    monkeypatch: pytest.MonkeyPatch,
    _no_real_sleep: list[float],
) -> None:
    """Individually affordable waits still have to stop once they add up."""

    monkeypatch.setattr(rate_limit_retry, "_MAX_ATTEMPTS", 50)
    attempts = 0

    async def handler(request: ModelRequest) -> Any:
        nonlocal attempts
        attempts += 1
        raise _RateLimited(retry_after="25")

    with pytest.raises(ProviderRateLimitError):
        await _middleware().awrap_model_call(_request(), handler)

    assert attempts == 4
    assert sum(_no_real_sleep) <= rate_limit_retry._RETRY_BUDGET_S


@pytest.mark.asyncio
async def test_a_provider_retry_after_hint_wins_over_backoff(
    _no_real_sleep: list[float],
) -> None:
    attempts = 0

    async def handler(request: ModelRequest) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _RateLimited(retry_after="5")
        return "answer"

    await _middleware().awrap_model_call(_request(), handler)

    # The hint, plus at most the 1s spread that keeps concurrent children from
    # waking together.
    assert len(_no_real_sleep) == 1
    assert 5.0 <= _no_real_sleep[0] <= 6.0


@pytest.mark.asyncio
async def test_backoff_grows_and_stays_jittered(_no_real_sleep: list[float]) -> None:
    """Concurrent fan-out children must not wake in lockstep and re-trip the
    same limit, so each delay is spread across a band rather than fixed."""

    async def handler(request: ModelRequest) -> Any:
        raise _RateLimited()

    with pytest.raises(ProviderRateLimitError):
        await _middleware().awrap_model_call(_request(), handler)

    base = rate_limit_retry._BACKOFF_BASE_S
    for attempt, delay in enumerate(_no_real_sleep):
        ceiling = min(rate_limit_retry._BACKOFF_CAP_S, base * (2**attempt))
        assert ceiling / 2 <= delay <= ceiling


@pytest.mark.asyncio
async def test_every_throttle_event_is_counted() -> None:
    kpi = _RecordingKPI()
    attempts = 0

    async def handler(request: ModelRequest) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _RateLimited()
        return "answer"

    await _middleware(kpi).awrap_model_call(_request(), handler)

    assert [name for name, _ in kpi.counts] == [
        "llm.rate_limit_events_total",
        "llm.rate_limit_events_total",
    ]
    # Recovered, so neither event is an error.
    assert [dims["status"] for _, dims in kpi.counts] == ["ok", "ok"]


@pytest.mark.asyncio
async def test_the_counter_always_carries_a_model_name_label() -> None:
    """PrometheusKPIStore freezes a metric's labels from its first event, so an
    omitted dim would be dropped from the counter for the pod's whole life."""

    kpi = _RecordingKPI()

    async def handler(request: ModelRequest) -> Any:
        raise _RateLimited()

    with pytest.raises(ProviderRateLimitError):
        await _middleware(kpi).awrap_model_call(_request(), handler)

    assert all(dims.get("model_name") for _, dims in kpi.counts)


@pytest.mark.asyncio
async def test_the_last_throttle_event_is_flagged_as_an_error() -> None:
    kpi = _RecordingKPI()

    async def handler(request: ModelRequest) -> Any:
        raise _RateLimited()

    with pytest.raises(ProviderRateLimitError):
        await _middleware(kpi).awrap_model_call(_request(), handler)

    statuses = [dims["status"] for _, dims in kpi.counts]
    assert statuses == ["ok"] * (rate_limit_retry._MAX_ATTEMPTS - 1) + ["error"]


@pytest.mark.asyncio
async def test_kpi_is_optional() -> None:
    """The frame passes kpi=None in tests and offline runs."""

    async def handler(request: ModelRequest) -> Any:
        raise _RateLimited()

    with pytest.raises(ProviderRateLimitError):
        await _middleware(None).awrap_model_call(_request(), handler)
