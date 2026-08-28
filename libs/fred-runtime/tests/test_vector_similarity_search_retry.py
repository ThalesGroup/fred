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

"""Transient-failure retry on the similarity-search path.

`KfBaseClient._request_with_token_refresh` retries a 401 and nothing else, and
no caller above `VectorSearchClient.similarity_search` retries either - so a
single dropped connection would otherwise fail a whole comparison run. These
cases pin what counts as retryable (transport errors and 5xx, never a 4xx),
that the retry budget is bounded, and that the happy path costs no extra call.
"""

from __future__ import annotations

import httpx
import pytest
from fred_runtime.common import kf_vectorsearch_client as client_module
from fred_runtime.common.kf_vectorsearch_client import _with_transient_retry

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the backoff maths, drop the wall-clock wait."""

    async def _instant(_delay: float) -> None:
        return None

    monkeypatch.setattr(client_module.asyncio, "sleep", _instant)


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://kf/vector/similarity-search")
    return httpx.HTTPStatusError(
        "boom", request=request, response=httpx.Response(status_code, request=request)
    )


class _Attempts:
    """Callable that fails a given number of times before succeeding."""

    def __init__(self, failures: int, exc: Exception) -> None:
        self._remaining = failures
        self._exc = exc
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            raise self._exc
        return "ok"


async def test_succeeds_first_try_without_retrying() -> None:
    attempts = _Attempts(failures=0, exc=_http_error(503))

    assert await _with_transient_retry(attempts) == "ok"
    assert attempts.calls == 1


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("dropped"),
        httpx.ConnectTimeout("slow"),
        # No connection was ever acquired, so nothing was sent - the transient
        # contention the per-passage fan-out makes likely.
        httpx.PoolTimeout("busy"),
        _http_error(503),
    ],
    ids=["connect_error", "connect_timeout", "pool_timeout", "service_unavailable"],
)
async def test_recovers_from_a_transient_failure(exc: Exception) -> None:
    attempts = _Attempts(failures=1, exc=exc)

    assert await _with_transient_retry(attempts) == "ok"
    assert attempts.calls == 2


@pytest.mark.parametrize(
    "exc",
    [httpx.ReadTimeout("slow"), httpx.WriteTimeout("slow")],
    ids=["read_timeout", "write_timeout"],
)
async def test_does_not_retry_once_work_is_already_in_flight(exc: Exception) -> None:
    """Knowledge Flow may still be reranking the first request; re-issuing
    multiplies load on an already-slow backend instead of recovering."""
    attempts = _Attempts(failures=99, exc=exc)

    with pytest.raises(httpx.TimeoutException):
        await _with_transient_retry(attempts)
    assert attempts.calls == 1


async def test_does_not_retry_a_plain_500() -> None:
    """KF wraps every unexpected exception in a 500, so retrying one buys three
    full pool-and-rerank round trips before failing anyway."""
    attempts = _Attempts(failures=99, exc=_http_error(500))

    with pytest.raises(httpx.HTTPStatusError):
        await _with_transient_retry(attempts)
    assert attempts.calls == 1


async def test_gives_up_once_the_retry_budget_is_spent() -> None:
    attempts = _Attempts(failures=99, exc=httpx.ConnectError("dropped"))

    with pytest.raises(httpx.ConnectError):
        await _with_transient_retry(attempts)
    assert attempts.calls == client_module._TRANSIENT_RETRIES + 1


async def test_does_not_retry_a_client_error() -> None:
    """A 4xx is the caller's fault - retrying only wastes a Knowledge Flow round trip."""
    attempts = _Attempts(failures=99, exc=_http_error(422))

    with pytest.raises(httpx.HTTPStatusError):
        await _with_transient_retry(attempts)
    assert attempts.calls == 1


async def test_rejects_an_empty_target_before_any_request() -> None:
    """Targeting is the point of this mode - an empty list is a client bug, not
    an invitation to search the whole corpus."""
    unbound = client_module.VectorSearchClient.__new__(client_module.VectorSearchClient)

    with pytest.raises(ValueError):
        await unbound.similarity_search(anchor="x", document_uids=[])
