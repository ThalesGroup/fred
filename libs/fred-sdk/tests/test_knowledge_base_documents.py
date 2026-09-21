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

"""A pod writes into its library, follows each write to its end, and reads back.

A write is accepted before it is ingested, so the publisher hands out a task to
follow rather than a verdict. What matters most here: a failed ingestion comes
back as a value, a wait that runs out never cancels the task, and a failed write
is the only one not listed as held — so it is written again.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from fred_sdk.knowledge_base.configuration import PodConfiguration
from fred_sdk.knowledge_base import documents as documents_module
from fred_sdk.knowledge_base.documents import (
    DocumentHandle,
    DocumentPublisher,
    DocumentPublishError,
    DocumentWaitTimeout,
)

BASE = "http://kf.invalid/knowledge-flow/v1"
LIBRARY = "lib-1"
TASK = "task-42"

ACCEPTED = {
    "source_key": "docs/a.md",
    "path": "docs/a.md",
    "document_version": "etag-1",
    "created": True,
    "document_uid": "uid-1",
    "task_id": TASK,
}


def _configuration() -> PodConfiguration:
    payload: dict[str, Any] = {
        "knowledge_base": {
            "prefix": "acme.kb",
            "control_plane_url": "http://example.invalid/control-plane/v1/",
            "knowledge_flow_url": BASE,
        },
        "security": {
            "m2m": {
                "realm_url": "http://keycloak.invalid/realms/app",
                "client_id": "kb-local-folder",
                "secret_env_var": "ACME_KB_CLIENT_SECRET",  # pragma: allowlist secret
            }
        },
    }
    return PodConfiguration.model_validate(payload)


def _summary(state: str, **extra: Any) -> dict[str, Any]:
    return {"task_id": TASK, "kind": "ingestion", "state": state, **extra}


class _Fred:
    """Stands in for the token minter and the HTTP client behind the publisher.

    Answers are scripted per method; the last one repeats, so an ingestion that
    never ends is one answer, not an endless list. An exception in place of an
    answer is raised instead, the way a lost connection would be.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._answers: dict[str, list[tuple[int, Any] | BaseException]] = {}

    def answers(
        self, method: str, *answers: tuple[int, Any] | BaseException
    ) -> "_Fred":
        self._answers[method] = list(answers)
        return self

    def _respond(self, method: str, url: str, kwargs: dict[str, Any]) -> httpx.Response:
        self.calls.append((method, url, kwargs))
        queue = self._answers[method]
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, BaseException):
            raise answer
        status, body = answer
        request = httpx.Request(method, url)
        if isinstance(body, str):
            return httpx.Response(status, text=body, request=request)
        return httpx.Response(status, json=body, request=request)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fred = self

        class _Tokens:
            def __init__(self, _config) -> None:
                pass

            async def get_token(self) -> str:
                return "a-token"  # pragma: allowlist secret

        class _Client:
            def __init__(self, **_kwargs) -> None:
                pass

            async def post(self, url, **kwargs):
                return fred._respond("POST", url, kwargs)

            async def get(self, url, **kwargs):
                return fred._respond("GET", url, kwargs)

            async def request(self, method, url, **kwargs):
                return fred._respond(method, url, kwargs)

            async def aclose(self) -> None:
                return None

        monkeypatch.setattr(
            "fred_sdk.knowledge_base.documents.M2MTokenProvider", _Tokens
        )
        monkeypatch.setattr(
            "fred_sdk.knowledge_base.documents.httpx.AsyncClient", _Client
        )


def _publisher(fred: _Fred, monkeypatch: pytest.MonkeyPatch) -> DocumentPublisher:
    fred.install(monkeypatch)
    return DocumentPublisher(_configuration(), library_id=LIBRARY, source_tag="fred")


def test_a_write_is_handed_over_and_answered_with_what_to_follow(monkeypatch):
    fred = _Fred().answers("POST", (202, ACCEPTED))
    publisher = _publisher(fred, monkeypatch)

    handle = asyncio.run(
        publisher.publish(relative_path="docs/a.md", content=b"# A", version="etag-1")
    )

    method, url, kwargs = fred.calls[0]
    assert (method, url) == ("POST", f"{BASE}/libraries/{LIBRARY}/documents")
    assert kwargs["files"]["file"][0] == "docs/a.md"
    assert kwargs["files"]["file"][1] == b"# A"
    assert kwargs["data"] == {
        "path": "docs/a.md",
        "source_key": "docs/a.md",
        "source_tag": "fred",
        "document_version": "etag-1",
    }
    assert handle == DocumentHandle(
        task_id=TASK,
        document_uid="uid-1",
        source_key="docs/a.md",
        document_version="etag-1",
        created=True,
    )


def test_a_write_without_a_version_claims_none(monkeypatch):
    fred = _Fred().answers("POST", (202, {**ACCEPTED, "document_version": None}))
    publisher = _publisher(fred, monkeypatch)

    handle = asyncio.run(publisher.publish(relative_path="docs/a.md", content=b""))

    assert "document_version" not in fred.calls[0][2]["data"]
    assert handle.document_version is None


def test_a_refused_write_names_the_path(monkeypatch):
    fred = _Fred().answers("POST", (413, "too large"))
    publisher = _publisher(fred, monkeypatch)

    with pytest.raises(DocumentPublishError, match="docs/a.md: 413"):
        asyncio.run(publisher.publish(relative_path="docs/a.md", content=b"x"))


def test_wait_follows_the_ingestion_until_it_ends(monkeypatch):
    fred = _Fred().answers(
        "GET",
        (200, _summary("running", progress=0.2, step="extract")),
        (200, _summary("running", progress=0.7, step="vectorize")),
        (200, _summary("succeeded", progress=1.0)),
    )
    publisher = _publisher(fred, monkeypatch)

    outcome = asyncio.run(publisher.wait(TASK, poll_interval=0.001))

    assert [url for _, url, _ in fred.calls] == [f"{BASE}/tasks/{TASK}"] * 3
    assert outcome.succeeded is True
    assert outcome.terminal is True
    assert outcome.progress == 1.0


def test_a_failed_ingestion_is_an_outcome_not_an_error(monkeypatch):
    """The document did not land, but the pod learned that — nothing broke."""
    fred = _Fred().answers(
        "GET",
        (200, _summary("running")),
        (200, _summary("failed", error="conversion failed", step="extract")),
    )
    publisher = _publisher(fred, monkeypatch)

    outcome = asyncio.run(publisher.wait(TASK, poll_interval=0.001))

    assert outcome.terminal is True
    assert outcome.succeeded is False
    assert outcome.error == "conversion failed"


@pytest.mark.parametrize("state", ["pending", "running", "cancelling"])
def test_a_wait_that_runs_out_leaves_the_task_running(monkeypatch, state):
    fred = _Fred().answers("GET", (200, _summary(state)))
    publisher = _publisher(fred, monkeypatch)

    with pytest.raises(DocumentWaitTimeout, match=TASK):
        asyncio.run(publisher.wait(TASK, timeout=0.01, poll_interval=0.001))

    # Every call was a read of the task: nothing cancelled or deleted it.
    assert {(m, u) for m, u, _ in fred.calls} == {("GET", f"{BASE}/tasks/{TASK}")}


def test_a_blip_on_the_way_to_fred_does_not_end_the_wait(monkeypatch):
    """Neither a lost connection nor an ingress 5xx says anything about the task."""
    fred = _Fred().answers(
        "GET",
        httpx.ConnectError("connection reset"),
        (503, "bad gateway"),
        (200, _summary("running")),
        (200, _summary("succeeded")),
    )
    publisher = _publisher(fred, monkeypatch)

    outcome = asyncio.run(publisher.wait(TASK, poll_interval=0.001))

    assert outcome.succeeded is True
    assert len(fred.calls) == 4


@pytest.mark.parametrize("status", [408, 429])
def test_a_timeout_or_a_throttle_on_the_way_is_not_an_answer_about_the_task(
    monkeypatch, status
):
    fred = _Fred().answers(
        "GET",
        (status, "later"),
        (200, _summary("running")),
        (200, _summary("succeeded")),
    )
    publisher = _publisher(fred, monkeypatch)

    outcome = asyncio.run(publisher.wait(TASK, poll_interval=0.001))

    assert outcome.succeeded is True
    assert len(fred.calls) == 3


def test_a_long_ingestion_is_asked_about_less_and_less_often(monkeypatch):
    """Each poll waits twice as long as the last, up to the cap."""
    slept: list[float] = []

    async def _record(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(documents_module.asyncio, "sleep", _record)
    fred = _Fred().answers(
        "GET", *([(200, _summary("running"))] * 5), (200, _summary("succeeded"))
    )
    publisher = _publisher(fred, monkeypatch)

    outcome = asyncio.run(publisher.wait(TASK, poll_interval=2))

    assert outcome.succeeded is True
    assert slept == [2, 4, 8, 15, 15]


def test_a_refused_poll_ends_the_wait_at_once(monkeypatch):
    """A 4xx is Fred's answer about this task, so there is nothing to wait for."""
    fred = _Fred().answers("GET", (404, "no such task"))
    publisher = _publisher(fred, monkeypatch)

    with pytest.raises(DocumentPublishError, match=f"task {TASK}: 404") as refused:
        asyncio.run(publisher.wait(TASK, poll_interval=0.001))

    assert refused.value.status_code == 404
    assert len(fred.calls) == 1


def test_a_wait_that_never_reaches_fred_still_ends_at_the_deadline(monkeypatch):
    fred = _Fred().answers("GET", httpx.ConnectError("connection reset"))
    publisher = _publisher(fred, monkeypatch)

    with pytest.raises(DocumentWaitTimeout, match=TASK):
        asyncio.run(publisher.wait(TASK, timeout=0.01, poll_interval=0.001))


def test_the_terminal_states_mirror_the_platform():
    """A pod reads states without installing the platform, so the copy is checked here."""
    models = pytest.importorskip("fred_core.tasks.models")

    terminal = {state.value for state in models.TaskState if state.is_terminal}

    assert set(documents_module._TERMINAL_STATES) == terminal
    assert documents_module._SUCCEEDED == models.TaskState.succeeded.value


def test_an_unknown_task_names_itself_and_the_status(monkeypatch):
    fred = _Fred().answers("GET", (404, "no such task"))
    publisher = _publisher(fred, monkeypatch)

    with pytest.raises(DocumentPublishError, match=f"task {TASK}: 404"):
        asyncio.run(publisher.outcome(TASK))


def test_what_landed_or_is_landing_is_held_and_a_failure_is_not(monkeypatch):
    """An in-flight write is not written twice; a failed one is, by its absence."""
    fred = _Fred().answers(
        "GET",
        (
            200,
            {
                "items": [
                    {
                        "source_key": "docs/a.md",
                        "document_uid": "uid-1",
                        "document_version": "etag-1",
                        "state": "succeeded",
                    },
                    {
                        "source_key": "docs/b.md",
                        "document_uid": "uid-2",
                        "document_version": None,
                        "state": "succeeded",
                    },
                    {
                        "source_key": "docs/c.md",
                        "document_uid": "uid-3",
                        "document_version": "etag-3",
                        "state": "in_progress",
                    },
                    {
                        "source_key": "docs/d.md",
                        "document_uid": "uid-4",
                        "document_version": "etag-4",
                        "state": "failed",
                    },
                ],
                "truncated": False,
            },
        ),
    )
    publisher = _publisher(fred, monkeypatch)

    held = asyncio.run(publisher.documents())

    assert fred.calls[0][:2] == ("GET", f"{BASE}/libraries/{LIBRARY}/documents")
    assert held == {"docs/a.md": "etag-1", "docs/b.md": None, "docs/c.md": "etag-3"}


def test_a_refused_inventory_names_the_library(monkeypatch):
    fred = _Fred().answers("GET", (403, "not yours"))
    publisher = _publisher(fred, monkeypatch)

    with pytest.raises(DocumentPublishError, match=f"library {LIBRARY}: 403"):
        asyncio.run(publisher.documents())


def test_a_partial_inventory_is_said_so_and_still_returned(monkeypatch, caplog):
    fred = _Fred().answers(
        "GET",
        (
            200,
            {
                "items": [
                    {
                        "source_key": "docs/a.md",
                        "document_uid": "uid-1",
                        "document_version": "etag-1",
                        "state": "succeeded",
                    }
                ],
                "truncated": True,
            },
        ),
    )
    publisher = _publisher(fred, monkeypatch)

    with caplog.at_level("WARNING"):
        held = asyncio.run(publisher.documents())

    assert held == {"docs/a.md": "etag-1"}
    assert f"only part of library {LIBRARY}" in caplog.text


def test_every_call_carries_the_pod_identity(monkeypatch):
    fred = (
        _Fred()
        .answers("POST", (202, ACCEPTED))
        .answers("GET", (200, _summary("succeeded")))
        .answers("DELETE", (204, ""))
    )
    publisher = _publisher(fred, monkeypatch)

    async def _one_of_everything() -> None:
        async with publisher:
            await publisher.publish(relative_path="docs/a.md", content=b"x")
            await publisher.outcome(TASK)
            await publisher.retract(relative_path="docs/a.md")

    asyncio.run(_one_of_everything())

    assert len(fred.calls) == 3
    assert all(
        kwargs["headers"]["Authorization"] == "Bearer a-token"
        for _, _, kwargs in fred.calls
    )
