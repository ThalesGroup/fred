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
Offline unit tests for fred_runtime.cli.history_display.run_single_turn's
HITL resume identity handling (#2216 blocking-regression fix).

Why this file exists:
- fred-agents-cli forwarded resume_payload but not interrupt_id, so every
  ReAct V2 HITL answer from the CLI got rejected (409) by the pod's
  `interrupt_id` exact-match gate. This file proves the fix: the CLI now
  extracts `interrupt_id` from the pending `AwaitingHumanRuntimeEvent`
  and echoes it back verbatim on resume — the same round trip
  `repl.py`'s interactive loop performs, exercised here through
  `run_single_turn` + `AgentPodClient` directly (no `input()` prompts to
  drive).
- also proves checkpoint_id (the unrelated legacy Graph V2 field) keeps
  round-tripping independently, and that a resume with neither id set
  (a Graph V2 caller that never received one) still works.

AgentPodClient accepts an injected httpx.Client, so the pod is a scripted
httpx.MockTransport — no network traffic, no real pod.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
from fred_runtime.cli.history_display import run_single_turn
from fred_runtime.cli.pod_client import AgentPodClient

BASE_URL = "http://test-pod/fred/agents/v2"


class _ScriptedPod:
    """Replays one canned JSON response per call, in order; records every
    request body it received."""

    def __init__(self, *responses: dict[str, Any]) -> None:
        self._responses = list(responses)
        self.request_bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.request_bodies.append(json.loads(request.content))
        response = self._responses.pop(0)
        return httpx.Response(200, json=response)


def _client(pod: Callable[[httpx.Request], httpx.Response]) -> AgentPodClient:
    return AgentPodClient(
        base_url=BASE_URL, http_client=httpx.Client(transport=httpx.MockTransport(pod))
    )


# ---------------------------------------------------------------------------
# Sequential ReAct V2 HITL round trip — the #2216 regression proof
# ---------------------------------------------------------------------------


def test_receive_real_hitl_event_echo_interrupt_id_resume_succeeds() -> None:
    """
    The exact sequence #2216 broke: (1) a turn pauses on a ReAct V2 HITL
    gate — the pod's response carries `request.interrupt_id`, LangGraph's
    own `Interrupt.id`, and no `checkpoint_id` at all; (2) the CLI must
    extract that `interrupt_id` (exactly like `repl.py`'s interactive loop:
    `req.get("interrupt_id")`) and forward it — not `checkpoint_id` — on
    the resume call; (3) the resume succeeds.
    """

    pod = _ScriptedPod(
        {
            "kind": "awaiting_human",
            "request": {
                "title": "Confirm tool execution",
                "question": "The agent wants to execute Update Ticket. Proceed?",
                "choices": [
                    {"id": "proceed", "label": "Proceed"},
                    {"id": "cancel", "label": "Cancel"},
                ],
                "free_text": True,
                "checkpoint_id": None,
                "interrupt_id": "9f3a7c2e4b1d6805af23c9de71b04f6a",
            },
        },
        {"kind": "final", "content": "done"},
    )
    client = _client(pod)

    exit_code, hitl = run_single_turn(
        client=client,
        agent_id="rags.sample.echo",
        message="update INC-1",
        session_id="sess-cli-2216",
        user_id="u1",
        team_id=None,
        verbose=False,
        stream=False,
        color_enabled=False,
    )

    assert exit_code == 0
    assert hitl is not None
    req = hitl["request"]
    resume_interrupt_id = req.get("interrupt_id")
    resume_checkpoint_id = req.get("checkpoint_id")
    assert resume_interrupt_id == "9f3a7c2e4b1d6805af23c9de71b04f6a"
    assert resume_checkpoint_id is None

    exit_code, hitl = run_single_turn(
        client=client,
        agent_id="rags.sample.echo",
        message="",
        session_id="sess-cli-2216",
        user_id="u1",
        team_id=None,
        verbose=False,
        stream=False,
        color_enabled=False,
        checkpoint_id=resume_checkpoint_id,
        interrupt_id=resume_interrupt_id,
        resume_payload={"choice_id": "proceed"},
    )

    assert exit_code == 0
    assert hitl is None  # turn completed — no further HITL pending

    resume_body = pod.request_bodies[1]
    assert resume_body["interrupt_id"] == "9f3a7c2e4b1d6805af23c9de71b04f6a"
    assert "checkpoint_id" not in resume_body  # None -> omitted, never aliased
    assert resume_body["resume_payload"] == {"choice_id": "proceed"}


def test_receive_real_hitl_event_echo_interrupt_id_resume_succeeds_streaming() -> None:
    """Same round trip, through the SSE streaming path (`iter_stream_events`)
    instead of the terminal-JSON path — both must forward interrupt_id."""

    def _sse(*events: dict[str, Any]) -> httpx.Response:
        lines = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
        return httpx.Response(
            200, text=lines, headers={"content-type": "text/event-stream"}
        )

    class _ScriptedStreamingPod:
        def __init__(self, *event_batches: list[dict[str, Any]]) -> None:
            self._batches = list(event_batches)
            self.request_bodies: list[dict[str, Any]] = []

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.request_bodies.append(json.loads(request.content))
            return _sse(*self._batches.pop(0))

    pod = _ScriptedStreamingPod(
        [
            {
                "kind": "awaiting_human",
                "request": {
                    "title": "Confirm",
                    "question": "Proceed?",
                    "choices": [],
                    "free_text": True,
                    "checkpoint_id": None,
                    "interrupt_id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
                },
            }
        ],
        [{"kind": "final", "content": "done"}],
    )
    client = _client(pod)

    _, hitl = run_single_turn(
        client=client,
        agent_id="rags.sample.echo",
        message="update INC-1",
        session_id="sess-cli-2216-stream",
        user_id="u1",
        team_id=None,
        verbose=False,
        stream=True,
        color_enabled=False,
    )
    assert hitl is not None
    req = hitl["request"]

    exit_code, hitl_after = run_single_turn(
        client=client,
        agent_id="rags.sample.echo",
        message="",
        session_id="sess-cli-2216-stream",
        user_id="u1",
        team_id=None,
        verbose=False,
        stream=True,
        color_enabled=False,
        checkpoint_id=req.get("checkpoint_id"),
        interrupt_id=req.get("interrupt_id"),
        resume_payload={"choice_id": "proceed"},
    )

    assert exit_code == 0
    assert hitl_after is None
    resume_body = pod.request_bodies[1]
    assert resume_body["interrupt_id"] == "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert "checkpoint_id" not in resume_body


def test_legacy_graph_v2_resume_still_forwards_checkpoint_id_not_interrupt_id() -> None:
    """Non-regression: a legacy Graph V2 pending request carries
    `checkpoint_id`, never `interrupt_id` — the CLI must forward exactly
    that field, unchanged from pre-#2216 behavior."""

    pod = _ScriptedPod(
        {
            "kind": "awaiting_human",
            "request": {
                "title": "Confirm",
                "question": "Proceed?",
                "choices": [],
                "free_text": True,
                "checkpoint_id": "cp-legacy-123",
                "interrupt_id": None,
            },
        },
        {"kind": "final", "content": "done"},
    )
    client = _client(pod)

    _, hitl = run_single_turn(
        client=client,
        agent_id="rags.sample.graph",
        message="do the thing",
        session_id="sess-cli-graph-v2",
        user_id="u1",
        team_id=None,
        verbose=False,
        stream=False,
        color_enabled=False,
    )
    assert hitl is not None
    req = hitl["request"]

    run_single_turn(
        client=client,
        agent_id="rags.sample.graph",
        message="",
        session_id="sess-cli-graph-v2",
        user_id="u1",
        team_id=None,
        verbose=False,
        stream=False,
        color_enabled=False,
        checkpoint_id=req.get("checkpoint_id"),
        interrupt_id=req.get("interrupt_id"),
        resume_payload={"choice_id": "proceed"},
    )

    resume_body = pod.request_bodies[1]
    assert resume_body["checkpoint_id"] == "cp-legacy-123"
    assert "interrupt_id" not in resume_body
