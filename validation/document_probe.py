# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""Public-API helpers for live document validation; no backend imports or store writes."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol
from uuid import uuid4

import httpx

# These helpers consume the deployed API's JSON, not the checkout's backend models.
Json = dict[str, Any]


class ApiClient(Protocol):
    def get(self, path: str, **kwargs: Any) -> httpx.Response: ...
    def post(self, path: str, **kwargs: Any) -> httpx.Response: ...
    def put(self, path: str, **kwargs: Any) -> httpx.Response: ...
    def delete(self, path: str, **kwargs: Any) -> httpx.Response: ...


ClientFactory = Callable[[str], ApiClient]
PROBE = "What is the validation observatory access code?"


def checked(response: httpx.Response) -> httpx.Response:
    # Do not include response bodies: diagnostic endpoints may echo credentials.
    assert response.is_success, (
        f"{response.request.method} {response.request.url.path}: HTTP {response.status_code}"
    )
    return response


@contextmanager
def library(client: ApiClient, team_id: str) -> Iterator[Json]:
    tag = checked(
        client.post(
            "/tags",
            json={
                "name": f"validation-documents-{uuid4().hex}",
                "type": "document",
                "team_id": team_id,
            },
        )
    ).json()
    try:
        yield tag
    finally:
        checked(client.delete(f"/tags/{tag['id']}"))
        assert client.get(f"/tags/{tag['id']}").status_code in (403, 404), (
            f"Fixture library {tag['id']} is still accessible after cleanup"
        )


def search(
    client: ApiClient,
    *,
    team_id: str,
    libraries: list[str] | None = None,
    documents: list[str] | None = None,
    policy: str = "semantic",
    session_id: str | None = None,
    corpus: bool = True,
) -> list[Json]:
    return checked(
        client.post(
            "/vector/search",
            json={
                "question": PROBE,
                "top_k": 100,
                "search_policy": policy,
                "owner_filter": "team",
                "team_id": team_id,
                "document_library_tags_ids": libraries,
                "document_uids": documents,
                "session_id": session_id,
                "include_session_scope": session_id is not None,
                "include_corpus_scope": corpus,
            },
            timeout=60,
        )
    ).json()


def assert_found(hits: list[Json], uid: str, marker: str) -> None:
    assert any(h.get("uid") == uid and marker in h.get("content", "") for h in hits), (
        f"Positive retrieval control failed for {uid}; returned UIDs: {sorted(hit_uids(hits))}"
    )


def hit_uids(hits: list[Json]) -> set[str]:
    return {hit["uid"] for hit in hits}


def wait_until(check: Callable[[], bool], *, description: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        if check():
            return
        assert time.monotonic() < deadline, f"Timed out after {timeout}s: {description}"
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def ingest(client: ApiClient, libraries: list[str], marker: str) -> str:
    filename = f"validation-{uuid4().hex}.md"
    response = checked(
        client.post(
            "/upload-process-documents",
            files={
                "files": (
                    filename,
                    f"# Validation observatory\n\nThe validation observatory access code is {marker}.\n",
                    "text/markdown",
                )
            },
            data={"metadata_json": json.dumps({"tags": libraries, "profile": "fast"})},
            timeout=180,
        )
    )
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events and events[-1].get("step") == "done", (
        "Incomplete upload progress stream"
    )
    assert all(
        e.get("status") not in {"failed", "error", "conflict", "ignored"}
        for e in events
    ), "Upload did not succeed; inspect the ingestion task and service logs"
    uids = {e["document_uid"] for e in events if e.get("document_uid")}
    assert len(uids) == 1, f"Expected one document from upload, got {len(uids)}"
    for task_id in {e["task_id"] for e in events if e.get("task_id")}:

        def complete() -> bool:
            state = checked(client.get(f"/tasks/{task_id}")).json()["state"]
            assert state not in {"failed", "cancelled"}, (
                f"Ingestion task {task_id}: {state}"
            )
            return state == "succeeded"

        wait_until(complete, description=f"ingestion task {task_id}", timeout=180)
    return uids.pop()


def wait_indexed(
    client: ApiClient, *, team_id: str, library_id: str, uid: str, marker: str
) -> None:
    # Only setup polls for index visibility. Negative security assertions never retry away a leak.
    wait_until(
        lambda: any(
            h.get("uid") == uid and marker in h.get("content", "")
            for h in search(client, team_id=team_id, libraries=[library_id])
        ),
        description=f"index visibility for {uid} in {library_id}",
        timeout=30,
    )


def unlink(client: ApiClient, tag: Json, uid: str) -> None:
    current = checked(client.get(f"/tags/{tag['id']}")).json()
    assert uid in current["item_ids"], (
        "Removal precondition failed: document is not in the library"
    )
    checked(
        client.put(
            f"/tags/{tag['id']}",
            json={
                "name": current["name"],
                "path": current.get("path"),
                "type": "document",
                "description": current.get("description"),
                "item_ids": [item for item in current["item_ids"] if item != uid],
            },
        )
    )


def runtime_events(response: httpx.Response) -> list[Json]:
    checked(response)
    frames: list[Json] = []
    data: list[str] = []
    for line in [*response.text.splitlines(), ""]:
        if line.startswith("data:"):
            data.append(line.removeprefix("data:").lstrip())
        elif not line and data:
            raw = "\n".join(data)
            data.clear()
            if raw != "[DONE]":
                frames.append(json.loads(raw))
    assert not any(
        (
            e.get("kind") in {"error", "node_error", "execution_error"}
            or (e.get("kind") == "tool_result" and e.get("is_error"))
        )
        for e in frames
    ), "Agent stream reported an execution error; this is not a successful empty search"
    return frames


def final_event(response: httpx.Response) -> Json:
    frames = runtime_events(response)
    assert not any(e.get("kind") == "awaiting_human" for e in frames), (
        "Agent did not finish after confirmation"
    )
    finals = [e for e in frames if e.get("kind") == "final"]
    assert len(finals) == 1, f"Expected one final event, got {len(finals)}"
    return finals[0]
