# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""Offline guards against a green report when upload/retrieval never succeeded."""

import json

import httpx
import pytest

from document_probe import (
    assert_found,
    final_event,
    ingest,
    library,
    unlink,
    wait_until,
)


def response(body: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, text=body, request=httpx.Request("POST", "https://fixture.invalid")
    )


@pytest.mark.parametrize(
    "body",
    [
        "",
        'data: {"kind":"status"}\n\n',
        'data: {"kind":"execution_error"}\n\ndata: {"kind":"final","sources":[]}\n\n',
    ],
)
def test_incomplete_or_failed_stream_cannot_pass_as_empty_retrieval(body: str) -> None:
    with pytest.raises(AssertionError):
        final_event(response(body))


def test_final_frame_accepts_multiline_data_and_checks_trailing_error() -> None:
    body = (
        ': heartbeat\n\ndata: {"kind":"final",\ndata: "sources":[]}\n\ndata: [DONE]\n\n'
    )
    assert final_event(response(body))["sources"] == []
    with pytest.raises(AssertionError, match="execution error"):
        final_event(response(body + 'data: {"kind":"error"}\n\n'))


def test_positive_control_requires_uid_and_marker_on_the_same_hit() -> None:
    with pytest.raises(AssertionError, match="Positive retrieval"):
        assert_found(
            [
                {"uid": "expected", "content": "other"},
                {"uid": "other", "content": "marker"},
            ],
            "expected",
            "marker",
        )


@pytest.mark.parametrize("terminal", ["succeeded", "failed", "cancelled"])
def test_ingestion_waits_for_task_outcome(terminal: str) -> None:
    states = iter(["running", terminal])
    polls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/upload-process-documents"
            return httpx.Response(
                200,
                text='{"status":"success","document_uid":"doc","task_id":"task"}\n{"step":"done","status":"success"}\n',
            )
        polls.append(request.url.path)
        return httpx.Response(200, json={"state": next(states)})

    with httpx.Client(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)
    ) as client:
        if terminal == "succeeded":
            assert ingest(client, ["library"], "marker") == "doc"
        else:
            with pytest.raises(AssertionError, match=terminal):
                ingest(client, ["library"], "marker")
    assert polls == ["/tasks/task", "/tasks/task"]


@pytest.mark.parametrize(
    "events",
    [
        [{"status": "success", "document_uid": "doc"}],
        [
            {"status": "error", "document_uid": "doc"},
            {"step": "done", "status": "success"},
        ],
        [{"step": "done", "status": "success"}],
    ],
)
def test_upload_http_success_does_not_hide_missing_or_failed_document(
    events: list[dict],
) -> None:
    with httpx.Client(
        base_url="https://fixture.invalid",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text="\n".join(json.dumps(e) for e in events))
        ),
    ) as client:
        with pytest.raises(AssertionError):
            ingest(client, ["library"], "marker")


def test_cleanup_uses_created_id_even_when_the_scenario_fails() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(201, json={"id": "owned"})
        return httpx.Response(204 if request.method == "DELETE" else 404)

    with httpx.Client(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(RuntimeError, match="scenario"):
            with library(client, "team"):
                raise RuntimeError("scenario failed")
    assert calls == [
        ("POST", "/tags"),
        ("DELETE", "/tags/owned"),
        ("GET", "/tags/owned"),
    ]


def test_unlink_preserves_every_other_document() -> None:
    writes = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, json={"name": "owned", "item_ids": ["keep", "remove"]}
            )
        writes.append(json.loads(request.content))
        return httpx.Response(200, json={})

    with httpx.Client(
        base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)
    ) as client:
        unlink(client, {"id": "owned"}, "remove")
    assert writes[0]["item_ids"] == ["keep"]


def test_visibility_wait_has_a_deadline() -> None:
    with pytest.raises(AssertionError, match="Timed out"):
        wait_until(lambda: False, description="fixture indexing", timeout=0)
