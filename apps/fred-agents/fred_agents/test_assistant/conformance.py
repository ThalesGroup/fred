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
Graph-engine conformance checks, written once and run two ways.

Each check drives the test assistant through a scenario and inspects the
runtime events. pytest runs them offline on every engine with fake services
(`ExecutorDriver` in the tests); the `graph check` scenario runs them live
through the pod's own HTTP API, exactly as the frontend does (`HttpDriver`).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

Event = dict[str, Any]

# Sessions created by `graph check`; a later run sweeps any it left behind.
SESSION_PREFIX = "graphcheck-"


@dataclass(frozen=True)
class TurnResult:
    """Events of one turn, or why a resume was refused (HTTP 409 / RuntimeError)."""

    events: list[Event] = field(default_factory=list)
    rejected: str | None = None


class Driver(Protocol):
    @abstractmethod
    async def send(self, session_id: str, message: str) -> TurnResult:
        """Send a new turn through the driver."""

    @abstractmethod
    async def resume(
        self, session_id: str, request: Event, choice_id: str
    ) -> TurnResult:
        """Resume the requested pause with the selected choice."""


@dataclass(frozen=True)
class Check:
    name: str
    summary: str
    run: Callable[[Driver, str], Awaitable[list[str]]]


# ── event helpers ────────────────────────────────────────────────────────────


def _of(events: list[Event], kind: str) -> list[Event]:
    return [event for event in events if event.get("kind") == kind]


def _index(events: list[Event], kind: str, detail_prefix: str | None = None) -> int:
    for i, event in enumerate(events):
        if event.get("kind") != kind:
            continue
        if detail_prefix is None or str(event.get("detail") or "").startswith(
            detail_prefix
        ):
            return i
    return -1


def _final(turn: TurnResult) -> Event | None:
    finals = _of(turn.events, "final")
    return finals[-1] if finals else None


def _awaiting(turn: TurnResult) -> Event | None:
    pauses = _of(turn.events, "awaiting_human")
    return pauses[-1].get("request") if pauses else None


class _Expect:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def that(self, condition: bool, message: str) -> bool:
        if not condition:
            self.failures.append(message)
        return condition

    def final(self, turn: TurnResult, label: str) -> str:
        """The turn's final content; records a failure (and returns "") if absent."""
        if turn.rejected is not None:
            self.failures.append(f"{label}: rejected ({turn.rejected})")
            return ""
        final = _final(turn)
        if not self.that(final is not None, f"{label}: no final event"):
            return ""
        assert final is not None
        self.that(turn.events[-1] is final, f"{label}: events after the final event")
        return str(final.get("content") or "")

    def paused(self, turn: TurnResult, stage: str, label: str) -> Event | None:
        request = _awaiting(turn)
        if not self.that(
            request is not None, f"{label}: expected a pause at {stage!r}, got none"
        ):
            return None
        assert request is not None
        self.that(
            request.get("stage") == stage,
            f"{label}: paused at {request.get('stage')!r}, expected {stage!r}",
        )
        self.that(
            bool(request.get("interrupt_id")),
            f"{label}: pause carries no interrupt_id to resume it with",
        )
        return request


def _tool_calls(turn: TurnResult, tool: str) -> int:
    return sum(1 for e in _of(turn.events, "tool_call") if e.get("tool_name") == tool)


# ── checks ───────────────────────────────────────────────────────────────────


async def _echo(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    turn = await driver.send(session, "echo hi")
    content = expect.final(turn, "echo")
    expect.that(
        [e.get("sequence") for e in turn.events] == list(range(len(turn.events))),
        "sequence numbers are not 0..n-1",
    )
    details = [e.get("detail") for e in _of(turn.events, "status")]
    expect.that(
        details[-3:] == ["Receiving your message.", "Processing.", "Sending reply."],
        f"echo statuses: {details}",
    )
    expect.that(content.startswith("Echo: echo hi"), f"echo content: {content[:60]!r}")
    return expect.failures


async def _trace_order(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    turn = await driver.send(session, "trace")
    expect.final(turn, "trace")
    events = turn.events
    deltas = [i for i, e in enumerate(events) if e.get("kind") == "assistant_delta"]
    before = _index(events, "status", "Emitting streaming analysis text.")
    after = _index(events, "status", "Attaching mock sources.")
    if expect.that(bool(deltas), "no streamed tokens"):
        expect.that(0 <= before < deltas[0], "status arrived after the first token")
        expect.that(deltas[-1] < after, "status arrived before the last token")
    final = _final(turn) or {}
    expect.that(len(final.get("sources") or []) == 3, "final event lacks 3 sources")
    return expect.failures


async def _on_error(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    turn = await driver.send(session, "error")
    content = expect.final(turn, "error")
    status = _index(turn.events, "status", "About to raise")
    node_error = _index(turn.events, "node_error")
    expect.that(status >= 0, "failing node's status was lost")
    if expect.that(node_error >= 0, "no node_error event"):
        expect.that(status < node_error, "status after node_error")
        expect.that(
            turn.events[node_error].get("routed_to") == "finalize",
            "node_error not routed to finalize",
        )
    # The on_error target answers; the generic turn-failure text would also
    # quote the error, so match the finalize wording itself.
    expect.that(
        content.startswith("Test scenario encountered a node error:"),
        f"turn did not continue at finalize: {content[:80]!r}",
    )
    return expect.failures


async def _crash(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    turn = await driver.send(session, "crash")
    content = expect.final(turn, "crash")
    expect.that(
        _index(turn.events, "status", "About to fail the turn") >= 0,
        "crashing node's status was lost",
    )
    expect.that(content.startswith("An error occurred:"), f"final: {content[:80]!r}")
    return expect.failures


async def _hitl_resume(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    pause = expect.paused(
        await driver.send(session, "hitl choice"), "agent_question", "pause"
    )
    if pause is None:
        return expect.failures
    resumed = await driver.resume(session, pause, "option_a")
    expect.that(
        "approved" in expect.final(resumed, "resume"), "resume did not apply option_a"
    )
    replay = await driver.resume(session, pause, "option_b")
    expect.that(
        replay.rejected is not None, "an answered pause was accepted a second time"
    )
    return expect.failures


async def _assist(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    first = await driver.send(session, "assist what is fred")
    deltas = "".join(str(e.get("delta")) for e in _of(first.events, "assistant_delta"))
    expect.that("{" not in deltas, "structured routing output leaked as tokens")
    expect.that(
        _tool_calls(first, "knowledge.search") == 1, "knowledge.search not called once"
    )
    review = expect.paused(first, "assist_review", "gate 1")
    if review is None:
        return expect.failures
    second = await driver.resume(session, review, "approve")
    content = expect.final(second, "approve")
    expect.that(bool(content), "approved draft was not returned")
    expect.that(
        _tool_calls(second, "knowledge.search") == 0,
        "search re-ran on resume",
    )
    return expect.failures


async def _continuity(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    expect.final(await driver.send(session, "trace"), "turn 1")
    second = await driver.send(session, "echo again")
    content = expect.final(second, "turn 2")
    expect.that("Turns remembered: 1" in content, "history not carried to turn 2")
    expect.that(
        not ((_final(second) or {}).get("sources")), "turn 1 sources leaked into turn 2"
    )
    return expect.failures


async def _abandoned_pause(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    pause = expect.paused(
        await driver.send(session, "hitl choice"), "agent_question", "pause"
    )
    content = expect.final(await driver.send(session, "echo moving on"), "new message")
    expect.that(content.startswith("Echo: echo moving on"), "new message did not run")
    if pause is not None:
        late = await driver.resume(session, pause, "option_a")
        expect.that(late.rejected is not None, "an abandoned pause was resumed")
    return expect.failures


async def _delegate(driver: Driver, session: str) -> list[str]:
    expect = _Expect()
    turn = await driver.send(session, "delegate model hi")
    content = expect.final(turn, "delegate")
    expect.that(
        not _of(turn.events, "assistant_delta"),
        "sub-agent tokens leaked into the stream",
    )
    expect.that("(answered)" in content, f"sub-agent did not answer: {content[:100]!r}")
    return expect.failures


CHECKS: tuple[Check, ...] = (
    Check("echo", "statuses in order, contiguous sequence numbers", _echo),
    Check("trace-order", "statuses keep their place among tokens", _trace_order),
    Check("on-error", "node error routed, failing node's status kept", _on_error),
    Check("crash", "a node error without on_error fails the turn cleanly", _crash),
    Check("hitl-resume", "pause, resume, answered pause refused", _hitl_resume),
    Check("assist", "routing, search, draft and review gate", _assist),
    Check("continuity", "history carried, other fields reset", _continuity),
    Check(
        "abandoned-pause", "a new message discards a pending pause", _abandoned_pause
    ),
    Check("delegate", "sub-agent answers, its tokens stay out", _delegate),
)


# ── live driver: the pod's HTTP API, as the frontend drives it ──────────────


class HttpDriver:
    """Runs turns through `POST {base}/agents/execute/stream` with the user's token."""

    def __init__(
        self,
        *,
        base_url: str,
        control_plane_url: str,
        access_token: str,
        agent_instance_id: str,
        team_id: str,
        timeout_s: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._control_plane = control_plane_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self._agent_instance_id = agent_instance_id
        self._team_id = team_id
        self._timeout = timeout_s

    async def open_session(self, check: str) -> str:
        """Register a throwaway session with control-plane, as the frontend does
        before its first turn (prepare-execution 404s on an unknown session)."""
        session = f"{SESSION_PREFIX}{check}-{uuid.uuid4().hex[:8]}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._control_plane}/teams/{self._team_id}/sessions",
                headers=self._headers,
                json={
                    "session_id": session,
                    "agent_instance_id": self._agent_instance_id,
                    "title": f"graph check · {check}",
                },
            )
        response.raise_for_status()
        return session

    async def sweep(self) -> tuple[int, list[str]]:
        """Purge `graphcheck-*` sessions an earlier, interrupted run left behind."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base}/agents/sessions", headers=self._headers
            )
        response.raise_for_status()
        leftovers = [
            sid for sid in response.json() if str(sid).startswith(SESSION_PREFIX)
        ]
        errors = [
            f"{sid}: {error}"
            for sid in leftovers
            if (error := await self.purge(sid)) is not None
        ]
        return len(leftovers), errors

    async def send(self, session_id: str, message: str) -> TurnResult:
        return await self._stream(
            {
                "agent_instance_id": self._agent_instance_id,
                "session_id": session_id,
                "input": message,
                "runtime_context": await self._prepared_context(session_id),
            }
        )

    async def resume(
        self, session_id: str, request: Event, choice_id: str
    ) -> TurnResult:
        # Same body as the frontend's resume (useChatSse).
        return await self._stream(
            {
                "agent_instance_id": self._agent_instance_id,
                "session_id": session_id,
                "interrupt_id": request.get("interrupt_id"),
                "occurrence_id": request.get("occurrence_id"),
                "runtime_context": await self._prepared_context(session_id),
                "resume_payload": {"answer": choice_id, "choice_id": choice_id},
            }
        )

    async def _prepared_context(self, session_id: str) -> dict[str, Any]:
        """The runtime context the frontend sends: prepare-execution's routing,
        context prompt and reasoning activation folded in (`mergePreparation`)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._control_plane}/teams/{self._team_id}/agent-instances/"
                f"{self._agent_instance_id}/prepare-execution",
                params={"session_id": session_id},
                headers=self._headers,
            )
        response.raise_for_status()
        prep = response.json()
        context: dict[str, Any] = {"team_id": self._team_id, "ask_user": True}
        for key in (
            "context_prompt_text",
            "chat_default_profile_id",
            "reasoning_enabled_model_ids",
        ):
            if prep.get(key) is not None:
                context[key] = prep[key]
        if prep.get("agent_profile_overrides"):
            context["agent_profile_overrides"] = prep["agent_profile_overrides"]
        return context

    async def await_history(self, session_id: str, timeout_s: float = 10.0) -> bool:
        """Wait until the pod has persisted the session's turns (written after
        the stream closes); the session's ownership checks depend on them."""
        url = f"{self._base}/agents/sessions/{session_id}/messages"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for _ in range(int(timeout_s / 0.25)):
                response = await client.get(url, headers=self._headers)
                if response.status_code == 200 and response.json():
                    return True
                await asyncio.sleep(0.25)
        return False

    async def purge(self, session_id: str) -> str | None:
        """
        Delete a session the way the UI does, then prove nothing is left.

        Control-plane erases checkpoints, then history, then metadata. With a
        retention window it only hides the session, so what the pod still holds
        is erased here explicitly (checkpoints before the history that proves
        ownership). None when no thread of the session remains.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            product = await client.delete(
                f"{self._control_plane}/teams/{self._team_id}/sessions/{session_id}",
                headers=self._headers,
            )
            if product.status_code >= 400 and product.status_code != 404:
                return f"session delete → HTTP {product.status_code}"
            if await self._threads_left(client, session_id):
                for path in (f"checkpoints/{session_id}", f"sessions/{session_id}"):
                    await client.delete(
                        f"{self._base}/agents/{path}", headers=self._headers
                    )
            left = await self._threads_left(client, session_id)
        return f"{len(left)} thread(s) left after delete: {left}" if left else None

    async def _threads_left(
        self, client: httpx.AsyncClient, session_id: str
    ) -> list[str]:
        response = await client.get(
            f"{self._base}/agents/checkpoints",
            params={"limit": 1000},
            headers=self._headers,
        )
        response.raise_for_status()
        return [
            str(row.get("session_id"))
            for row in response.json()
            if str(row.get("session_id")) == session_id
            or str(row.get("session_id")).startswith(f"{session_id}:")
        ]

    async def _stream(self, body: dict[str, Any]) -> TurnResult:
        events: list[Event] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base}/agents/execute/stream",
                headers=self._headers,
                content=json.dumps({k: v for k, v in body.items() if v is not None}),
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode(errors="replace")
                    return TurnResult(
                        rejected=f"HTTP {response.status_code}: {detail[:160]}"
                    )
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        payload = line[len("data:") :].strip()
                        if payload:
                            events.append(json.loads(payload))
        errors = _of(events, "execution_error")
        if errors and not _of(events, "final"):
            return TurnResult(events=events, rejected=str(errors[-1].get("message")))
        return TurnResult(events=events)
