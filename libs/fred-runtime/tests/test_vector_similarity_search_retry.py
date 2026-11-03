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
no caller above the similarity adapter retries either - so a
single dropped connection would otherwise fail a whole comparison run. These
cases pin what counts as retryable (transport errors and 5xx, never a 4xx),
that the retry budget is bounded, and that the happy path costs no extra call.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
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
    request = httpx.Request("POST", "http://kf/documents/search")
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


@pytest.mark.parametrize(
    "exc,failures,expected_calls",
    [
        (httpx.ConnectError("dropped"), 1, 2),
        (_http_error(502), 1, 2),
        (_http_error(503), 1, 2),
        (_http_error(504), 1, 2),
        (httpx.ConnectError("dropped"), 99, 3),
        (httpx.ReadTimeout("slow"), 99, 1),
        (httpx.WriteTimeout("slow"), 99, 1),
        (_http_error(500), 99, 1),
        (_http_error(422), 99, 1),
    ],
)
async def test_search_similarity_options_retain_the_retry_contract(
    monkeypatch, exc, failures, expected_calls
) -> None:
    client = object.__new__(client_module.VectorSearchClient)
    calls = []
    context = DocumentAccessContext(
        space_id=UUID(int=1),
        document_scope=DocumentScope.from_ids(
            document_ids=["00000000-0000-0000-0000-000000000002"]
        ),
    )

    async def request(**kwargs):
        calls.append(kwargs)
        if len(calls) <= failures:
            raise exc
        return httpx.Response(
            200, json=[], request=httpx.Request("POST", "http://kf/documents/search")
        )

    monkeypatch.setattr(client, "_request_with_token_refresh", request)
    call = client.search(
        question="anchor",
        document_context=context,
        top_k=7,
        rerank=True,
        min_score=0.3,
        read_timeout=37.0,
        transient_retry=True,
    )
    if failures == 99:
        with pytest.raises(type(exc)):
            await call
    else:
        assert await call == []
    assert len(calls) == expected_calls
    for attempt in calls:
        assert attempt == {
            "method": "POST",
            "path": "/documents/search",
            "phase_name": "kf_vector_similarity_search",
            "headers": {DOCUMENT_CONTEXT_HEADER: context.model_dump_json()},
            "json": {
                "question": "anchor",
                "top_k": 7,
                "rerank": True,
                "min_score": 0.3,
            },
            "read_timeout": 37.0,
        }


async def test_ordinary_search_does_not_opt_into_similarity_transport(
    monkeypatch,
) -> None:
    client = object.__new__(client_module.VectorSearchClient)
    calls = []

    async def request(**kwargs):
        calls.append(kwargs)
        raise httpx.ConnectError("dropped")

    monkeypatch.setattr(client, "_request_with_token_refresh", request)
    with pytest.raises(httpx.ConnectError):
        await client.search(
            question="q",
            document_context=DocumentAccessContext(
                space_id=UUID(int=1),
                document_scope=DocumentScope(),
            ),
        )
    assert len(calls) == 1
    assert calls[0]["json"] == {"question": "q", "top_k": 10}
    assert calls[0]["read_timeout"] is None
    assert calls[0]["phase_name"] == "kf_vector_search"


@pytest.mark.parametrize(
    "exc,failures,expected_calls",
    [
        (httpx.ConnectError("dropped"), 1, 2),
        (_http_error(503), 1, 2),
        (_http_error(502), 99, 3),
        (httpx.ReadTimeout("slow"), 99, 1),
        (httpx.WriteTimeout("slow"), 99, 1),
        (_http_error(403), 99, 1),
        (_http_error(500), 99, 1),
    ],
)
async def test_tree_get_wire_context_and_transient_policy(
    monkeypatch, exc, failures, expected_calls
):
    from types import SimpleNamespace

    from fred_runtime.common import kf_document_client as module
    from fred_sdk.contracts.runtime import DocumentTreeResult

    client = object.__new__(module.KfDocumentClient)
    monkeypatch.setattr(
        module,
        "get_runtime_context",
        lambda: SimpleNamespace(
            config=SimpleNamespace(timeouts=SimpleNamespace(similarity_read=37.0))
        ),
    )
    context = DocumentAccessContext(
        space_id=UUID(int=1), document_scope=DocumentScope.from_ids([str(UUID(int=2))])
    )
    calls = []

    async def request(**kwargs):
        calls.append(kwargs)
        if len(calls) <= failures:
            raise exc
        return httpx.Response(
            200,
            json={"spaces": [], "folders": [], "documents": [], "truncated": False},
            request=httpx.Request("GET", "http://kf/documents/tree"),
        )

    monkeypatch.setattr(client, "_request_with_token_refresh", request)
    call = client.tree(document_context=context, folder_id=str(UUID(int=2)), limit=42)
    if failures == 99:
        with pytest.raises(type(exc)):
            await call
    else:
        assert await call == DocumentTreeResult()
    assert len(calls) == expected_calls
    assert all(
        attempt
        == {
            "method": "GET",
            "path": "/documents/tree",
            "phase_name": "kf_document_tree",
            "headers": {DOCUMENT_CONTEXT_HEADER: context.model_dump_json()},
            "params": {"folder_id": str(UUID(int=2)), "limit": 42},
            "read_timeout": 37.0,
        }
        for attempt in calls
    )
