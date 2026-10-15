# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied.

"""Exercise the live driver's confirmation and negative-result guards offline."""

import json

import httpx
import pytest

from scenarios.test_document_access import Conversation


def stream(events: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        text="".join(f"data: {json.dumps(e)}\n\n" for e in events),
        request=httpx.Request("POST", "https://fixture.invalid/runtime"),
    )


def test_confirmation_preserves_session_context_and_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = []

    def post(url: str, **kwargs: object) -> httpx.Response:
        bodies.append(kwargs["json"])
        if len(bodies) == 1:
            return stream(
                [
                    {
                        "kind": "tool_result",
                        "tool_name": "search_documents_using_vectorization",
                        "is_error": False,
                    },
                    {
                        "kind": "awaiting_human",
                        "request": {
                            "stage": "test_document_confirm",
                            "interrupt_id": "interrupt",
                            "occurrence_id": "occurrence",
                        },
                    },
                ]
            )
        return stream(
            [{"kind": "final", "sources": [{"uid": "doc", "content": "marker"}]}]
        )

    monkeypatch.setattr(httpx, "post", post)
    with httpx.Client(
        base_url="https://fixture.invalid",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"execute_stream_url": "/runtime"})
        ),
    ) as cp:
        final = Conversation(
            cp, "team", "instance", "session", lambda: "fixture-token"
        ).turn(documents=["doc"])
    assert final["sources"][0]["uid"] == "doc"
    assert len(bodies) == 2
    assert bodies[0]["session_id"] == bodies[1]["session_id"] == "session"
    assert bodies[0]["runtime_context"] == bodies[1]["runtime_context"]
    assert bodies[1]["interrupt_id"] == "interrupt"
    assert bodies[1]["occurrence_id"] == "occurrence"
    assert bodies[1]["resume_payload"] == {"answer": "confirm", "choice_id": "confirm"}


@pytest.mark.parametrize(
    "events",
    [
        [{"kind": "final", "content": "capability unavailable", "sources": []}],
        [
            {
                "kind": "tool_result",
                "tool_name": "search_documents_using_vectorization",
                "is_error": True,
            },
            {"kind": "final", "sources": []},
        ],
        [
            {
                "kind": "tool_result",
                "tool_name": "search_documents_using_vectorization",
            },
            {"kind": "awaiting_human", "request": {"stage": "tool_approval"}},
        ],
    ],
)
def test_missing_capability_failed_tool_or_unexpected_pause_is_not_a_negative_pass(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: stream(events))
    with httpx.Client(
        base_url="https://fixture.invalid",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"execute_stream_url": "/runtime"})
        ),
    ) as cp:
        with pytest.raises(AssertionError):
            Conversation(
                cp, "team", "instance", "session", lambda: "fixture-token"
            ).turn(documents=["forbidden"])
