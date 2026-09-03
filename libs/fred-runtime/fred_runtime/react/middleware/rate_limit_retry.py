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

"""RateLimitRetryMiddleware — absorb provider 429s instead of failing the turn."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

from fred_core import is_rate_limit
from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_core.kpi.kpi_writer_structures import MetricNames
from fred_sdk.contracts.context import BoundRuntimeContext
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse

from ..react_model_adapter import extract_model_name_from_object
from .shared import identity_kpi_dims

logger = logging.getLogger(__name__)

# Tuning knobs, deliberately conservative. A chat turn has a human waiting on
# it, so the wall-clock budget matters more than the attempt count: it is what
# stops a throttled provider from holding an SSE stream open indefinitely.
# Candidates to promote to configuration once live tuning settles them.
_MAX_ATTEMPTS = 4
_RETRY_BUDGET_S = 60.0
_BACKOFF_BASE_S = 2.0
_BACKOFF_CAP_S = 30.0
# Below this much budget left, waiting is not worth the turn's remaining time.
_MIN_USEFUL_WAIT_S = 1.0


class ProviderRateLimitError(RuntimeError):
    """Raised when a model call stays rate-limited after every retry.

    Its message reaches the user as the turn's `execution_error`, so it names
    the condition in plain language instead of leaking provider JSON.
    """

    def __init__(self, *, attempts: int, elapsed_s: float) -> None:
        plural = "" if attempts == 1 else "s"
        super().__init__(
            "The model provider is rate-limiting this deployment. Fred gave up "
            f"after {attempts} attempt{plural} over {elapsed_s:.0f}s. "
            "Please send your message again in a moment."
        )
        self.attempts = attempts
        self.elapsed_s = elapsed_s


class RateLimitRetryMiddleware(AgentMiddleware):
    """
    Retry a model call that came back rate-limited (HTTP 429).

    Why this exists, and why the provider SDK's own `max_retries` was not
    enough on its own: `RUNTIME-EXECUTION-CONTRACT.md` §8.64.

    Boundary of this class:
    - 429 only. Any other failure propagates untouched — a retry loop that
      swallows genuine errors is worse than no retry loop
    - it does NOT bound fan-out concurrency; retry buys patience, not headroom
    - it retries the CALL, so it assumes the provider rejected the request
      before streaming any of it — true of a 429, which is an HTTP status on
      the response. A gateway that streamed deltas and only then threw would
      have its prefix emitted twice.
    """

    def __init__(
        self,
        *,
        kpi: BaseKPIWriter | None,
        binding: BoundRuntimeContext,
    ) -> None:
        super().__init__()
        self._kpi = kpi
        self._binding = binding

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        started = time.monotonic()

        for attempt in range(_MAX_ATTEMPTS):
            try:
                return await handler(request)
            except Exception as exc:
                throttled, retry_after = is_rate_limit(exc)
                if not throttled:
                    raise

                # Resolved here, not before the call: the happy path runs on
                # every model call of every turn and must stay free of work
                # only the throttled path needs.
                model_name = extract_model_name_from_object(request.model)
                elapsed = time.monotonic() - started
                remaining = _RETRY_BUDGET_S - elapsed
                # Clamped, never rejected: a provider asking for longer than the
                # budget is the common TPM case (Mistral sends Retry-After: 60),
                # and treating it as unaffordable would retry nothing at all.
                delay = min(self._delay_for(attempt, retry_after), remaining)
                exhausted = (
                    attempt == _MAX_ATTEMPTS - 1 or remaining < _MIN_USEFUL_WAIT_S
                )
                self._record(model_name, exhausted=exhausted)

                if exhausted:
                    logger.error(
                        "model=%s rate limit persisted after %d attempts in %.1fs; "
                        "failing the turn",
                        model_name,
                        attempt + 1,
                        elapsed,
                    )
                    raise ProviderRateLimitError(
                        attempts=attempt + 1, elapsed_s=elapsed
                    ) from exc

                logger.warning(
                    "model=%s rate-limited (attempt %d/%d); backing off %.1fs",
                    model_name,
                    attempt + 1,
                    _MAX_ATTEMPTS,
                    delay,
                )
                await asyncio.sleep(delay)

        raise AssertionError("unreachable: the loop returns or raises")

    def _delay_for(self, attempt: int, retry_after: float | None) -> float:
        """Seconds the provider would have us wait; the caller clamps it to the
        budget still left.

        A provider hint wins. Otherwise exponential backoff, spread across a
        half-band so concurrent children of one fan-out do not wake together
        and re-trip the same limit.
        """

        if retry_after is not None and retry_after > 0:
            return retry_after + random.uniform(0, 1.0)  # nosec B311 — retry jitter, not security-sensitive
        ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2**attempt))
        return random.uniform(ceiling / 2, ceiling)  # nosec B311 — retry jitter, not security-sensitive

    def _record(self, model_name: str | None, *, exhausted: bool) -> None:
        if self._kpi is None:
            return
        # `model_name` is set unconditionally: PrometheusKPIStore freezes a
        # metric's label set from its FIRST event, so a dim omitted on the first
        # 429 of a pod's life is dropped from the counter for good.
        dims: dict[str, str | None] = {
            **identity_kpi_dims(self._binding),
            "status": "error" if exhausted else "ok",
            "model_name": model_name or "unknown",
        }
        self._kpi.count(
            MetricNames.LLM_RATE_LIMITS,
            1,
            dims=dims,
            actor=KPIActor(type="system"),
        )
