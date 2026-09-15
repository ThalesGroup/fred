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

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from fred_agents.registry import build_registry
from fred_agents.self_test import graph_steps
from fred_agents.self_test.graph_agent import SELF_TEST_AGENT
from fred_agents.self_test.graph_state import SelfTestState
from fred_agents.self_test.graph_steps import baseline_step, hold_step, retrieve_step
from fred_core.store import VectorSearchHit
from fred_sdk import GraphNodeContext, ThoughtKind


class _FakeContext:
    """Tiny graph-node context: records the tool call, returns canned hits."""

    def __init__(
        self,
        *,
        sources: list[VectorSearchHit],
        tuning_values=None,
        context_prompt_text: str | None = None,
        folders: object | None = None,
    ) -> None:
        self._result = SimpleNamespace(sources=tuple(sources), blocks=())
        self.tuning_values = dict(tuning_values or {})
        self.services = SimpleNamespace(document_folders=folders)
        # Mirror BoundRuntimeContext.runtime_context.context_prompt_text so the
        # agent can echo the conversation-scoped (marketplace) prompt.
        self.binding = SimpleNamespace(
            runtime_context=SimpleNamespace(context_prompt_text=context_prompt_text)
        )
        self.statuses: list[tuple[str, str | None]] = []
        self.thoughts: list[tuple[str, str]] = []
        # Statuses are buffered by the runtime and thoughts stream live, so their
        # relative order is part of what the hold has to get right.
        self.emit_order: list[str] = []
        self.tool_calls: list[tuple[str, dict[str, object]]] = []

    def emit_status(self, status: str, detail: str | None = None) -> None:
        self.statuses.append((status, detail))
        self.emit_order.append("status")

    def emit_thought(
        self,
        phase: ThoughtKind,
        text: str,
        *,
        title: str | None = None,
        conclusion: str | None = None,
    ) -> None:
        self.thoughts.append((phase, text))
        self.emit_order.append("thought")

    async def invoke_tool(self, tool_ref: str, payload: dict[str, object]) -> object:
        self.tool_calls.append((tool_ref, dict(payload)))
        return self._result


def _ctx(ctx: _FakeContext) -> GraphNodeContext:
    return cast(GraphNodeContext, ctx)


# The realm's challenge on an expired bearer, verbatim, plus body text that the
# classifier must never pass on.
_TOKEN_EXPIRED_CHALLENGE = (
    "Bearer error='invalid_token', error_description='token expired'"
)
_UPSTREAM_DETAIL = "upstream refusal detail"
_METADATA_REQUEST = httpx.Request("GET", "https://service.invalid/tags")


def _folders_answering(status: int, *, challenge: str | None = None) -> SimpleNamespace:
    """Metadata client that answers `status` and fails the way httpx itself does."""

    async def resolve_folder(folder: str) -> str | None:
        response = httpx.Response(
            status,
            headers={"WWW-Authenticate": challenge} if challenge else {},
            text=_UPSTREAM_DETAIL,
            request=_METADATA_REQUEST,
        )
        response.raise_for_status()
        return None

    return SimpleNamespace(resolve_folder=resolve_folder)


def _folders_unreachable() -> SimpleNamespace:
    """Metadata client the transport never reached."""

    async def resolve_folder(folder: str) -> str | None:
        raise httpx.ConnectError(_UPSTREAM_DETAIL, request=_METADATA_REQUEST)

    return SimpleNamespace(resolve_folder=resolve_folder)


@pytest.fixture
def slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record the hold's waits instead of spending them, so no test waits."""
    durations: list[float] = []

    async def _record(seconds: float) -> None:
        durations.append(seconds)

    monkeypatch.setattr(graph_steps, "_sleep", _record)
    return durations


@pytest.mark.asyncio
async def test_echoes_retrieved_marker() -> None:
    hit = VectorSearchHit(
        uid="d1",
        title="Alpha",
        content="The festival is in Marchtober.",
        score=0.9,
        type="md",
    )
    ctx = _FakeContext(sources=[hit])

    result = await retrieve_step(
        SelfTestState(latest_user_text="When is the festival?"), _ctx(ctx)
    )

    update = result.state_update
    assert update["hit_count"] == 1
    assert "Marchtober" in str(update["final_text"])
    assert update["done_reason"] == "self_test_ok"
    # It used the real knowledge-search tool with the user's question and default top_k.
    tool_ref, payload = ctx.tool_calls[0]
    assert payload == {"query": "When is the festival?", "top_k": 5}


@pytest.mark.asyncio
async def test_reports_empty_scope() -> None:
    ctx = _FakeContext(sources=[])

    result = await retrieve_step(SelfTestState(latest_user_text="anything"), _ctx(ctx))

    assert result.state_update["hit_count"] == 0
    assert result.state_update["done_reason"] == "self_test_empty"
    assert "no chunks" in str(result.state_update["final_text"]).lower()


@pytest.mark.asyncio
async def test_top_k_is_tunable() -> None:
    hit = VectorSearchHit(uid="d1", title="A", content="x", score=0.5, type="md")
    ctx = _FakeContext(sources=[hit], tuning_values={"settings.top_k": 3})

    await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))

    assert ctx.tool_calls[0][1]["top_k"] == 3


@pytest.mark.asyncio
async def test_echoes_system_prompt_tuning() -> None:
    """Path A: the per-instance system prompt (tuning) is echoed back."""
    ctx = _FakeContext(
        sources=[],
        tuning_values={"prompts.system": "SYSPROMPT-abc123"},
    )

    result = await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))

    final_text = str(result.state_update["final_text"])
    assert "system_prompt: SYSPROMPT-abc123" in final_text
    # No conversation prompt was attached this turn.
    assert "context_prompt: (none)" in final_text


@pytest.mark.asyncio
async def test_echoes_context_prompt_text() -> None:
    """Path B: the conversation-scoped (marketplace) prompt is echoed back."""
    ctx = _FakeContext(
        sources=[],
        context_prompt_text="CTXPROMPT-xyz789",
    )

    result = await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))

    final_text = str(result.state_update["final_text"])
    assert "context_prompt: CTXPROMPT-xyz789" in final_text
    assert "system_prompt: (none)" in final_text


@pytest.mark.asyncio
async def test_zero_hold_goes_straight_to_retrieval(slept: list[float]) -> None:
    hit = VectorSearchHit(uid="d1", title="A", content="x", score=0.5, type="md")
    ctx = _FakeContext(sources=[hit])
    state = SelfTestState(latest_user_text="q")

    await hold_step(state, _ctx(ctx))

    assert slept == []
    assert ctx.emit_order == []

    await retrieve_step(state, _ctx(ctx))

    assert len(ctx.tool_calls) == 1
    assert ctx.tool_calls[0][1]["query"] == "q"


@pytest.mark.asyncio
async def test_hold_heartbeats_live_then_retrieves(slept: list[float]) -> None:
    hit = VectorSearchHit(uid="d1", title="A", content="x", score=0.5, type="md")
    ctx = _FakeContext(sources=[hit], tuning_values={"settings.hold_seconds": 25})
    state = SelfTestState(latest_user_text="is the marker still reachable?")

    await hold_step(state, _ctx(ctx))

    assert sum(slept) == 25
    assert max(slept) <= 10
    assert ctx.thoughts == [
        ("tool_use", "holding 10/25 s before retrieval"),
        ("tool_use", "holding 20/25 s before retrieval"),
        ("tool_use", "holding 25/25 s before retrieval"),
    ]
    assert ctx.statuses == [("hold", "25/25 s before retrieval")]
    assert ctx.emit_order == ["thought", "thought", "thought", "status"]

    await retrieve_step(state, _ctx(ctx))

    assert len(ctx.tool_calls) == 1
    assert ctx.tool_calls[0][1]["query"] == "is the marker still reachable?"


@pytest.mark.asyncio
async def test_hold_is_clamped_to_its_maximum(slept: list[float]) -> None:
    ctx = _FakeContext(sources=[], tuning_values={"settings.hold_seconds": 5000})

    await hold_step(SelfTestState(latest_user_text="q"), _ctx(ctx))

    assert sum(slept) == 900


def test_hold_field_and_workflow_are_wired() -> None:
    spec = next(f for f in SELF_TEST_AGENT.fields if f.key == "settings.hold_seconds")
    assert spec.type == "integer"
    assert (spec.default, spec.min) == (0, 0)
    # One bound: the declared maximum is the value the step clamps to.
    assert spec.max == graph_steps.MAX_HOLD_SECONDS

    access = next(f for f in SELF_TEST_AGENT.fields if f.key == "settings.check_access")
    assert (access.type, access.default) == ("boolean", False)

    workflow = SELF_TEST_AGENT.workflow
    assert workflow is not None
    # The credential is proven before any waiting, in its own node so that
    # evidence reaches the stream before the hold rather than after it.
    assert workflow.entry == "baseline"
    assert workflow.edges["baseline"] == "hold"
    assert workflow.edges["hold"] == "retrieve"
    assert workflow.edges["retrieve"] == "finalize"


def test_agent_is_registered() -> None:
    assert "fred.github.self_test" in build_registry()


@pytest.mark.asyncio
@pytest.mark.parametrize("renewed", [False, True])
async def test_retrieval_reports_only_observed_renewal(renewed: bool) -> None:
    ctx = _FakeContext(sources=[], tuning_values={"settings.hold_seconds": 60})
    ctx.binding.runtime_context.access_token = "synthetic-before"

    async def invoke(tool_ref: str, payload: dict[str, object]) -> object:
        if renewed:
            ctx.binding.runtime_context.access_token = "synthetic-after"
        return SimpleNamespace(sources=(), blocks=())

    ctx.invoke_tool = invoke
    await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))
    assert (
        ("credential_renewed", None) in ctx.statuses
        if renewed
        else ("credential_renewed", None) not in ctx.statuses
    )
    assert "synthetic-" not in str(ctx.statuses)


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [False, True])
async def test_retrieval_distinguishes_confirmed_expiry_from_other_refusals(
    expired: bool,
) -> None:
    ctx = _FakeContext(sources=[], tuning_values={"settings.hold_seconds": 60})

    async def invoke(tool_ref: str, payload: dict[str, object]) -> object:
        headers = {"WWW-Authenticate": _TOKEN_EXPIRED_CHALLENGE} if expired else {}
        response = httpx.Response(
            401,
            headers=headers,
            request=httpx.Request("POST", "https://service.invalid/search"),
        )
        response.raise_for_status()

    ctx.invoke_tool = invoke
    expected = (
        graph_steps.CREDENTIAL_EXPIRED
        if expired
        else graph_steps.PROTECTED_CALL_REFUSED
    )
    with pytest.raises(RuntimeError, match=f"^{expected}$"):
        await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))


@pytest.mark.asyncio
async def test_access_check_accepts_empty_metadata_without_retrieving_documents(
    slept: list[float],
) -> None:
    resolve = AsyncMock(return_value=None)
    ctx = _FakeContext(
        sources=[],
        tuning_values={"settings.hold_seconds": 10, "settings.check_access": True},
        folders=SimpleNamespace(resolve_folder=resolve),
    )
    state = SelfTestState(latest_user_text="Check access")

    await baseline_step(state, _ctx(ctx))
    await hold_step(state, _ctx(ctx))
    result = await retrieve_step(state, _ctx(ctx))

    assert resolve.await_count == 2
    assert ctx.tool_calls == []
    assert [s for s, _ in ctx.statuses] == [
        "credential_baseline",
        "hold",
        "protected_call_succeeded",
    ]
    assert result.state_update["sources_data"] == []
    assert result.state_update["done_reason"] == "self_test_access_ok"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("folders", "expected"),
    [
        (
            _folders_answering(401, challenge=_TOKEN_EXPIRED_CHALLENGE),
            graph_steps.CREDENTIAL_EXPIRED,
        ),
        (_folders_answering(401), graph_steps.PROTECTED_CALL_REFUSED),
        (_folders_answering(503), graph_steps.PROTECTED_CALL_REFUSED),
        (_folders_unreachable(), graph_steps.PROTECTED_CALL_FAILED),
    ],
    ids=["expired", "refused-401", "refused-503", "unreachable"],
)
async def test_access_check_classifies_a_failed_call_without_echoing_it(
    folders: SimpleNamespace, expected: str
) -> None:
    ctx = _FakeContext(
        sources=[], tuning_values={"settings.check_access": True}, folders=folders
    )

    with pytest.raises(RuntimeError) as raised:
        await graph_steps._check_access(_ctx(ctx))

    assert str(raised.value) == expected
    assert _UPSTREAM_DETAIL not in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("renewed", [False, True])
async def test_access_check_reports_only_observed_renewal(renewed: bool) -> None:
    ctx = _FakeContext(sources=[], tuning_values={"settings.check_access": True})
    ctx.binding.runtime_context.access_token = "synthetic-before"

    async def resolve_folder(folder: str) -> str | None:
        if renewed:
            ctx.binding.runtime_context.access_token = "synthetic-after"
        return None

    ctx.services.document_folders = SimpleNamespace(resolve_folder=resolve_folder)

    await retrieve_step(SelfTestState(latest_user_text="q"), _ctx(ctx))

    emitted = [status for status, _ in ctx.statuses]
    assert ("credential_renewed" in emitted) is renewed
    assert "protected_call_succeeded" in emitted
    assert "synthetic-" not in str(ctx.statuses)


@pytest.mark.asyncio
async def test_access_check_reports_an_absent_metadata_service() -> None:
    ctx = _FakeContext(sources=[], tuning_values={"settings.check_access": True})

    with pytest.raises(
        RuntimeError, match="^authenticated metadata check unavailable$"
    ):
        await graph_steps._check_access(_ctx(ctx))
