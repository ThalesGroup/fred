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

"""A Graph run left unfinished is offered back, continued or restarted."""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from fred_runtime.graph.graph_executor import GraphExecutor
from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from fred_sdk import GraphAgent, GraphWorkflow, StepResult, typed_node
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.runtime import (
    ExecutionConfig,
    ExecutionInterruptedRuntimeEvent,
    FinalRuntimeEvent,
    RuntimeServices,
)
from fred_sdk.graph.runtime import GraphNodeContext
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import create_async_engine

RUNS: Counter[str] = Counter()
ORDER: list[str] = []
BEHAVIOUR: dict[str, str] = {}
PUBLISH_ENTERED: list[asyncio.Event] = []


class _Input(BaseModel):
    message: str = Field(..., min_length=1)


class _State(BaseModel):
    latest_user_text: str
    plan: str | None = None
    operation_id: str | None = None
    receipt: str | None = None
    final_text: str | None = None


@typed_node(_State)
async def _prepare(state: _State, context: GraphNodeContext) -> StepResult:
    RUNS["prepare"] += 1
    ORDER.append("node:prepare")
    return StepResult(state_update={
        "plan": f"plan for {state.latest_user_text}", "operation_id": uuid4().hex,
    })


@typed_node(_State)
async def _publish(state: _State, context: GraphNodeContext) -> StepResult:
    RUNS["publish"] += 1
    ORDER.append("node:publish")
    if BEHAVIOUR.get("publish") == "hang":
        PUBLISH_ENTERED[0].set()
        await asyncio.Event().wait()  # the process is lost while publishing
    if BEHAVIOUR.get("publish") == "exit":
        os._exit(9)  # a real process loss, mid-step
    if BEHAVIOUR.get("publish") == "fail":
        raise RuntimeError("publication refused")
    if destination := BEHAVIOUR.get("destination"):
        assert state.operation_id and state.plan
        path = Path(destination) / state.operation_id
        if path.exists():
            assert path.read_text() == state.plan
        else:
            path.write_text(state.plan)
        if BEHAVIOUR.get("publish") == "response_lost":
            raise TimeoutError("Destination committed, response lost")
        if BEHAVIOUR.get("publish") == "exit_after_commit":
            os._exit(9)
        return StepResult(state_update={"receipt": state.operation_id})
    return StepResult(state_update={})


@typed_node(_State)
async def _finalize(state: _State, context: GraphNodeContext) -> StepResult:
    RUNS["finalize"] += 1
    if BEHAVIOUR.get("finalize") == "fail":
        raise RuntimeError("Finalization unavailable")
    return StepResult(state_update={"final_text": f"published {state.plan}"})


class _Agent(GraphAgent):
    agent_id: str = "fred.tests.interrupted"
    role: str = "Interruption probe"
    description: str = "Prepare, publish, finalize."
    input_schema = _Input
    state_schema = _State
    input_to_state = {"message": "latest_user_text"}
    workflow = GraphWorkflow(
        entry="prepare",
        nodes={"prepare": _prepare, "publish": _publish, "finalize": _finalize},
        edges={"prepare": "publish", "publish": "finalize"},
    )


@pytest.fixture(autouse=True)
def _reset() -> None:
    RUNS.clear()
    ORDER.clear()
    BEHAVIOUR.clear()
    PUBLISH_ENTERED[:] = []


@pytest_asyncio.fixture
async def checkpointer(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cp.sqlite3'}")
    yield FredSqlCheckpointer(engine, prefix="v2_")
    await engine.dispose()


def _binding(
    session_id: str = "s1", instance: str | None = "inst-1"
) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id, user_id="alice", team_id="t1"
        ),
        portable_context=PortableContext(
            request_id="r1",
            correlation_id="c1",
            actor="alice",
            tenant="t1",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            user_id="alice",
            team_id="t1",
            baggage={"agent_instance_id": instance} if instance else {},
        ),
    )


async def _executor(checkpointer: Any, **binding: Any) -> GraphExecutor:
    runtime = GraphRuntime(
        definition=_Agent(), services=RuntimeServices(checkpointer=checkpointer)
    )
    runtime.bind(_binding(**binding))
    return cast(GraphExecutor, await runtime.get_executor())


async def _turn(executor: GraphExecutor, **config: Any) -> list[Any]:
    message = config.pop("message", "migrate")
    session_id = config.pop("session_id", "s1")
    return [
        event
        async for event in executor.stream(
            _Input(message=message), ExecutionConfig(session_id=session_id, **config)
        )
    ]


async def _lose_run_while_publishing(checkpointer: Any, **binding: Any) -> None:
    BEHAVIOUR["publish"] = "hang"
    PUBLISH_ENTERED[:] = [asyncio.Event()]
    session_id = binding.get("session_id", "s1")
    executor = await _executor(checkpointer, **binding)
    run = asyncio.create_task(_turn(executor, session_id=session_id))
    await PUBLISH_ENTERED[0].wait()
    run.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await run
    BEHAVIOUR.clear()


async def _interruption(
    checkpointer: FredSqlCheckpointer,
) -> ExecutionInterruptedRuntimeEvent:
    events = await _turn(await _executor(checkpointer), message="again")
    assert len(events) == 1 and isinstance(events[0], ExecutionInterruptedRuntimeEvent)
    return events[0]


@pytest.mark.asyncio
async def test_a_lost_run_is_offered_back_instead_of_restarted(
    checkpointer: FredSqlCheckpointer,
) -> None:
    await _lose_run_while_publishing(checkpointer)
    runs_before = dict(RUNS)

    event = await _interruption(checkpointer)

    assert dict(RUNS) == runs_before  # nothing ran
    assert event.request.stage == "execution_interrupted"
    assert event.request.metadata["node_id"] == "publish"
    assert [choice.id for choice in event.request.choices] == ["continue", "restart"]


_CRASHING_CHILD = """
import asyncio, sys
from sqlalchemy.ext.asyncio import create_async_engine
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
import test_graph_interrupted_execution as t

async def main():
    t.BEHAVIOUR["publish"] = "exit"
    engine = create_async_engine("sqlite+aiosqlite:///" + sys.argv[1])
    await t._turn(await t._executor(FredSqlCheckpointer(engine, prefix="v2_")))

asyncio.run(main())
"""


@pytest.mark.asyncio
async def test_a_new_process_continues_after_the_previous_one_died(tmp_path) -> None:
    database = tmp_path / "cp.sqlite3"
    child = subprocess.run(
        [sys.executable, "-c", _CRASHING_CHILD, str(database)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert child.returncode == 9, child.stderr

    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    try:
        reopened = FredSqlCheckpointer(engine, prefix="v2_")
        event = await _interruption(reopened)
        events = await _turn(
            await _executor(reopened),
            interrupted_action="continue",
            interruption_id=event.interruption_id,
        )
    finally:
        await engine.dispose()

    assert isinstance(events[-1], FinalRuntimeEvent)
    assert events[-1].content == "published plan for migrate"
    assert RUNS == Counter(
        publish=1, finalize=1
    )  # prepare ran in the dead process only


@pytest.mark.asyncio
async def test_continue_runs_only_the_interrupted_step(
    checkpointer: FredSqlCheckpointer,
) -> None:
    await _lose_run_while_publishing(checkpointer)
    event = await _interruption(checkpointer)

    events = await _turn(
        await _executor(checkpointer),
        message="ignored",
        interrupted_action="continue",
        interruption_id=event.interruption_id,
    )

    assert isinstance(events[-1], FinalRuntimeEvent)
    assert events[-1].content == "published plan for migrate"
    assert RUNS == Counter(prepare=1, publish=2, finalize=1)


@pytest.mark.asyncio
async def test_repeated_continuations_preserve_a_completed_tool_task(
    checkpointer: FredSqlCheckpointer,
) -> None:
    from fred_runtime.capabilities.assembly import CapabilityAgentBlock
    from langchain_core.tools import tool

    calls: list[str] = []
    entered = asyncio.Event()
    hanging = True

    @tool("save")
    async def save(plan: str) -> str:
        """Record the external effect once; LangGraph caches its result."""
        calls.append(plan)
        return plan

    @typed_node(_State)
    async def publish(state: _State, context: GraphNodeContext) -> StepResult:
        assert state.plan is not None
        result = await context.invoke_runtime_tool("save", {"plan": state.plan})
        assert result == state.plan
        entered.set()
        if hanging:
            await asyncio.Event().wait()
        return StepResult(state_update={})

    class Agent(_Agent):
        workflow = GraphWorkflow(
            entry="prepare",
            nodes={"prepare": _prepare, "publish": publish, "finalize": _finalize},
            edges={"prepare": "publish", "publish": "finalize"},
        )

    async def executor() -> GraphExecutor:
        runtime = GraphRuntime(
            definition=Agent(),
            services=RuntimeServices(checkpointer=checkpointer),
            capability_block=CapabilityAgentBlock(
                middleware=(), tools=(save,), hitl={}
            ),
        )
        runtime.bind(_binding())
        result = await runtime.get_executor()
        assert isinstance(result, GraphExecutor)
        return result

    config = {}
    for _ in range(2):
        entered.clear()
        run = asyncio.create_task(_turn(await executor(), **config))
        await asyncio.wait_for(entered.wait(), timeout=5)
        run.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run
        event = await _interruption(checkpointer)
        config = {
            "interrupted_action": "continue",
            "interruption_id": event.interruption_id,
        }

    hanging = False
    events = await _turn(await executor(), **config)
    assert isinstance(events[-1], FinalRuntimeEvent)
    assert calls == ["plan for migrate"]
    assert RUNS["prepare"] == 1


@pytest.mark.asyncio
async def test_closing_a_continuation_stream_releases_admission_immediately(
    checkpointer: FredSqlCheckpointer,
) -> None:
    from fred_runtime.runtime_support.graph_resume_lock import (
        GraphResumeAlreadyRunningError,
    )

    await _lose_run_while_publishing(checkpointer)
    event = await _interruption(checkpointer)
    executor = await _executor(checkpointer)
    config = ExecutionConfig(
        session_id="s1",
        interrupted_action="continue",
        interruption_id=event.interruption_id,
    )
    stream = executor.stream(_Input(message="ignored"), config)
    try:
        assert isinstance(await anext(stream), FinalRuntimeEvent)
        with pytest.raises(GraphResumeAlreadyRunningError):
            async with checkpointer.graph_resume_lock.acquire(
                executor.thread_id(config)
            ):
                pytest.fail("The continuation released ownership before stream exit")
    finally:
        await stream.aclose()
    async with checkpointer.graph_resume_lock.acquire(executor.thread_id(config)):
        pass


@pytest.mark.asyncio
async def test_a_stale_or_unknown_interruption_is_rejected(
    checkpointer: FredSqlCheckpointer,
) -> None:
    await _lose_run_while_publishing(checkpointer)
    runs_before = dict(RUNS)

    with pytest.raises(RuntimeError, match="no interrupted step"):
        await _turn(
            await _executor(checkpointer),
            interrupted_action="continue",
            interruption_id="not-the-current-one",
        )
    assert dict(RUNS) == runs_before


@pytest.mark.asyncio
async def test_continue_without_an_interrupted_run_is_rejected(
    checkpointer: FredSqlCheckpointer,
) -> None:
    with pytest.raises(RuntimeError, match="no interrupted step"):
        await _turn(
            await _executor(checkpointer),
            interrupted_action="continue",
            interruption_id="anything",
        )
    assert not RUNS


@pytest.mark.asyncio
async def test_restart_runs_a_new_turn_from_the_entry_step(
    checkpointer: FredSqlCheckpointer,
) -> None:
    await _lose_run_while_publishing(checkpointer)

    events = await _turn(
        await _executor(checkpointer), message="fresh", interrupted_action="restart"
    )

    assert isinstance(events[-1], FinalRuntimeEvent)
    assert events[-1].content == "published plan for fresh"
    assert RUNS["prepare"] == 2


@pytest.mark.asyncio
async def test_invoke_has_no_one_to_ask_and_restarts(
    checkpointer: FredSqlCheckpointer,
) -> None:
    await _lose_run_while_publishing(checkpointer)

    output = await (await _executor(checkpointer)).invoke(
        _Input(message="fresh"), ExecutionConfig(session_id="s1")
    )

    assert output.model_dump()["content"] == "published plan for fresh"


@pytest.mark.asyncio
async def test_a_node_failure_preserves_preparation_for_explicit_continuation(
    checkpointer: FredSqlCheckpointer,
) -> None:
    BEHAVIOUR["publish"] = "fail"
    executor = await _executor(checkpointer)
    failed = await _turn(executor)
    assert "An error occurred" in failed[-1].content
    snapshot = await executor._compiled.aget_state(
        executor._thread_config(ExecutionConfig(session_id="s1"))
    )
    assert snapshot.next == ("publish",)
    assert snapshot.values["plan"] == "plan for migrate"  # carry-forward intact

    BEHAVIOUR.clear()
    event = await _interruption(checkpointer)
    events = await _turn(
        await _executor(checkpointer),
        interrupted_action="continue", interruption_id=event.interruption_id,
    )
    assert isinstance(events[-1], FinalRuntimeEvent)
    assert RUNS["prepare"] == 1


@pytest.mark.asyncio
async def test_the_step_limit_preserves_pending_work(
    checkpointer: FredSqlCheckpointer,
) -> None:
    executor = await _executor(checkpointer)
    stopped = await _turn(executor, max_steps=1)
    assert "max_steps=1" in stopped[-1].content

    event = await _interruption(checkpointer)
    result = await _turn(
        await _executor(checkpointer),
        interrupted_action="continue", interruption_id=event.interruption_id,
    )
    assert result[-1].content == "published plan for migrate"
    assert RUNS["prepare"] == 1


@pytest.mark.asyncio
async def test_a_step_is_persisted_before_the_next_step_starts(
    checkpointer: FredSqlCheckpointer, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_aput = checkpointer.aput

    async def slow_aput(*args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0.05)
        result = await original_aput(*args, **kwargs)
        ORDER.append("persisted")
        return result

    monkeypatch.setattr(checkpointer, "aput", slow_aput)
    await _turn(await _executor(checkpointer))

    between = ORDER[ORDER.index("node:prepare") + 1 : ORDER.index("node:publish")]
    assert "persisted" in between


# ── Through the pod's execute endpoint ──────────────────────────────────────


def _post(client: Any, **body: Any) -> dict[str, Any]:
    response = client.post(
        "/pod/v1/agents/execute",
        json={
            "agent_id": _Agent().agent_id,
            "session_id": "sess-1",
            "runtime_context": {"user_id": "alice"},
            **body,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def _offline_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
    from fred_runtime.app import agent_app as agent_app_module
    from langchain_core.messages import AIMessage

    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="echo")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )


def _app_with(definition: Any, tmp_path: Any) -> Any:
    from fred_runtime.app.agent_app import create_agent_app
    from test_agent_app import _build_test_config

    return create_agent_app(
        registry={definition.agent_id: definition}, config=_build_test_config(tmp_path)
    )


def _lose_run_in_pod() -> Any:
    from fred_runtime.runtime_context import get_runtime_context

    checkpointer = get_runtime_context().config.checkpointer
    asyncio.run(
        _lose_run_while_publishing(checkpointer, session_id="sess-1", instance=None)
    )
    return checkpointer


def test_pod_reports_the_interruption_and_keeps_history_untouched(
    tmp_path, _offline_model
) -> None:
    from fastapi.testclient import TestClient
    from fred_runtime.runtime_context import get_runtime_context

    with TestClient(_app_with(_Agent(), tmp_path)) as client:
        _lose_run_in_pod()
        reported = _post(client, input="again")
        history = get_runtime_context().config.history_store
        rows = asyncio.run(history.get("sess-1")) if history is not None else []

    assert reported["kind"] == "execution_interrupted"
    assert reported["request"]["metadata"]["node_id"] == "publish"
    assert rows == []


def test_pod_continue_finishes_without_a_user_row(tmp_path, _offline_model) -> None:
    from fastapi.testclient import TestClient
    from fred_runtime.runtime_context import get_runtime_context

    with TestClient(_app_with(_Agent(), tmp_path)) as client:
        _lose_run_in_pod()
        reported = _post(client, input="again")
        final = _post(
            client,
            interrupted_action="continue",
            interruption_id=reported["interruption_id"],
        )
        history = get_runtime_context().config.history_store
        rows = asyncio.run(history.get("sess-1")) if history is not None else []

    assert final["kind"] == "final"
    assert final["content"] == "published plan for migrate"
    assert RUNS == Counter(prepare=1, publish=2, finalize=1)
    assert rows and all(str(row.role) != "user" for row in rows)


def test_pod_refuses_a_continue_another_replica_already_holds(
    tmp_path: Path, _offline_model: None
) -> None:
    from fastapi.testclient import TestClient

    with TestClient(_app_with(_Agent(), tmp_path)) as client:
        checkpointer = _lose_run_in_pod()
        reported = _post(client, input="again")
        publishes = RUNS["publish"]
        admission = checkpointer.graph_resume_lock.acquire(
            f"sess-1:{_Agent().agent_id}"
        )
        with asyncio.Runner() as runner:
            runner.run(admission.__aenter__())
            try:
                refused = _post(
                    client,
                    interrupted_action="continue",
                    interruption_id=reported["interruption_id"],
                )
            finally:
                runner.run(admission.__aexit__(None, None, None))

    assert refused["kind"] == "execution_error"
    assert RUNS["publish"] == publishes


_CRASHING_CONTINUATION = """
import sys
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
from langchain_core.messages import AIMessage
import test_graph_interrupted_execution as t

model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
with patch("fred_runtime.app.agent_app._build_chat_model_factory",
           lambda config: StaticChatModelFactory(model)):
    with TestClient(t._app_with(t._Agent(), Path(sys.argv[1]))) as client:
        t._lose_run_in_pod()
        reported = t._post(client, input="again")
        t.BEHAVIOUR["publish"] = "exit"
        t._post(client, interrupted_action="continue",
                interruption_id=reported["interruption_id"])
"""


def test_pod_continues_again_after_its_continuing_process_dies(
    tmp_path: Path, _offline_model: None
) -> None:
    from fastapi.testclient import TestClient
    from test_agent_app import _hitl_claim_rows

    child = subprocess.run(
        [sys.executable, "-c", _CRASHING_CONTINUATION, str(tmp_path)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 9, child.stderr

    with TestClient(_app_with(_Agent(), tmp_path)) as client:
        reported = _post(client, input="again")
        final = _post(
            client,
            interrupted_action="continue",
            interruption_id=reported["interruption_id"],
        )
        from fred_runtime.runtime_context import get_runtime_context

        checkpointer = get_runtime_context().config.checkpointer
        assert asyncio.run(_hitl_claim_rows(checkpointer)) == []

    assert final["kind"] == "final"
    assert final["content"] == "published plan for migrate"
    assert RUNS == Counter(publish=1, finalize=1)


def test_pod_continuation_ignores_an_old_permanent_technical_claim(
    tmp_path: Path, _offline_model: None
) -> None:
    from fastapi.testclient import TestClient
    from test_agent_app import _hitl_claim_rows

    with TestClient(_app_with(_Agent(), tmp_path)) as client:
        checkpointer = _lose_run_in_pod()
        reported = _post(client, input="again")
        identity = {
            "thread_id": f"sess-1:{_Agent().agent_id}",
            "checkpoint_ns": "",
            "interrupt_id": f"continue:{reported['interruption_id']}",
        }
        token = asyncio.run(checkpointer.aclaim_hitl_resume(**identity))
        assert token is not None
        assert asyncio.run(
            checkpointer.astart_hitl_resume(**identity, claim_token=token)
        )
        rows_before = asyncio.run(_hitl_claim_rows(checkpointer))
        final = _post(
            client,
            interrupted_action="continue",
            interruption_id=reported["interruption_id"],
        )
        assert asyncio.run(_hitl_claim_rows(checkpointer)) == rows_before

    assert final["kind"] == "final"
    assert RUNS["prepare"] == 1


def test_pod_refuses_continue_for_a_non_graph_agent(tmp_path, _offline_model) -> None:
    from fastapi.testclient import TestClient
    from test_agent_app import _EchoAgent

    echo = _EchoAgent()
    with TestClient(_app_with(echo, tmp_path)) as client:
        refused = _post(
            client,
            agent_id=echo.agent_id,
            interrupted_action="continue",
            interruption_id="anything",
        )

    assert refused["kind"] == "execution_error"


def test_pod_rejects_an_unauthorized_caller_before_any_event(
    tmp_path, monkeypatch: pytest.MonkeyPatch, _offline_model
) -> None:
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from fred_runtime.app import agent_app as agent_app_module

    async def _deny(*args: Any, **kwargs: Any) -> None:
        raise HTTPException(status_code=403, detail="not your session")

    monkeypatch.setattr(agent_app_module, "_enforce_session_ownership", _deny)
    with TestClient(_app_with(_Agent(), tmp_path)) as client:
        _lose_run_in_pod()
        response = client.post(
            "/pod/v1/agents/execute",
            json={
                "agent_id": _Agent().agent_id,
                "session_id": "sess-1",
                "input": "again",
                "runtime_context": {"user_id": "mallory"},
            },
        )

    assert response.status_code == 403
    assert "execution_interrupted" not in response.text


def test_openai_compat_cannot_answer_the_card_so_a_lost_run_restarts(
    tmp_path, _offline_model
) -> None:
    from fastapi.testclient import TestClient

    with TestClient(_app_with(_Agent(), tmp_path)) as client:
        _lose_run_in_pod()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": _Agent().agent_id,
                "messages": [{"role": "user", "content": "again"}],
            },
            headers={"X-Fred-Session-Id": "sess-1"},
        )

    assert response.status_code == 200, response.text
    assert '"finish_reason":"stop"' in response.text
    assert RUNS["prepare"] == 2  # restarted from the entry step


def test_pod_rejects_a_stale_continue_without_leaving_a_claim(
    tmp_path, _offline_model
) -> None:
    from fastapi.testclient import TestClient
    from test_agent_app import _hitl_claim_rows

    with TestClient(_app_with(_Agent(), tmp_path)) as client:
        checkpointer = _lose_run_in_pod()
        refused = _post(
            client, interrupted_action="continue", interruption_id="stale-or-made-up"
        )
        rows = asyncio.run(_hitl_claim_rows(checkpointer))

    assert refused["kind"] == "execution_error"
    assert rows == []


@pytest.mark.asyncio
async def test_publication_response_loss_reuses_identity_and_content(checkpointer, tmp_path) -> None:
    BEHAVIOUR.update(destination=str(tmp_path), publish="response_lost")
    events = await _turn(await _executor(checkpointer))
    assert "An error occurred" in events[-1].content
    # Use the persisted identity to inspect the fake destination, not a new key.
    executor = await _executor(checkpointer)
    state = await executor._compiled.aget_state(executor._thread_config(ExecutionConfig(session_id="s1")))
    operation_id = state.values["operation_id"]
    assert (tmp_path / operation_id).read_text() == "plan for migrate"
    BEHAVIOUR.pop("publish")
    event = await _interruption(checkpointer)
    result = await _turn(executor, interrupted_action="continue", interruption_id=event.interruption_id)
    assert result[-1].content == "published plan for migrate"
    assert (tmp_path / operation_id).read_text() == "plan for migrate"
    assert RUNS == Counter(prepare=1, publish=2, finalize=1)


@pytest.mark.asyncio
async def test_durable_receipt_skips_publication_when_finalization_is_retried(checkpointer, tmp_path) -> None:
    BEHAVIOUR.update(destination=str(tmp_path), finalize="fail")
    await _turn(await _executor(checkpointer))
    event = await _interruption(checkpointer)
    BEHAVIOUR.pop("finalize")
    result = await _turn(await _executor(checkpointer), interrupted_action="continue", interruption_id=event.interruption_id)
    assert result[-1].content == "published plan for migrate"
    assert RUNS == Counter(prepare=1, publish=1, finalize=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["preparation", "receipt"])
async def test_failed_persistence_does_not_advance_to_next_step(checkpointer, tmp_path, monkeypatch, boundary) -> None:
    BEHAVIOUR["destination"] = str(tmp_path)
    original = checkpointer.aput

    async def fail_boundary(config, checkpoint, *args, **kwargs):
        values = checkpoint.get("channel_values", {})
        if (boundary == "preparation" and values.get("plan")) or (boundary == "receipt" and values.get("receipt")):
            raise OSError("Checkpoint unavailable")
        return await original(config, checkpoint, *args, **kwargs)

    monkeypatch.setattr(checkpointer, "aput", fail_boundary)
    result = await _turn(await _executor(checkpointer))
    assert "An error occurred" in result[-1].content
    assert RUNS["finalize"] == 0
    assert RUNS["publish"] == (0 if boundary == "preparation" else 1)
    monkeypatch.setattr(checkpointer, "aput", original)
    event = await _interruption(checkpointer)
    result = await _turn(await _executor(checkpointer), interrupted_action="continue", interruption_id=event.interruption_id)
    assert result[-1].content == "published plan for migrate"


@pytest.mark.asyncio
async def test_process_loss_after_publication_reuses_the_same_operation(tmp_path) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    database = tmp_path / "cp.sqlite3"
    child_code = _CRASHING_CHILD.replace(
        'BEHAVIOUR["publish"] = "exit"',
        'BEHAVIOUR.update(publish="exit_after_commit", destination=' + repr(str(destination)) + ')',
    )
    assert child_code != _CRASHING_CHILD
    child = subprocess.run([sys.executable, "-c", child_code, str(database)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent)}, capture_output=True, text=True, timeout=120)
    assert child.returncode == 9, child.stderr
    before = {p.name: p.read_text() for p in destination.iterdir()}
    assert len(before) == 1
    BEHAVIOUR["destination"] = str(destination)
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    try:
        reopened = FredSqlCheckpointer(engine, prefix="v2_")
        event = await _interruption(reopened)
        result = await _turn(await _executor(reopened), interrupted_action="continue", interruption_id=event.interruption_id)
    finally:
        await engine.dispose()
    assert result[-1].content == "published plan for migrate"
    assert RUNS["prepare"] == 0
    assert {p.name: p.read_text() for p in destination.iterdir()} == before


@pytest.mark.asyncio
async def test_closing_during_progress_waits_for_node_teardown(checkpointer) -> None:
    from fred_runtime.runtime_support.graph_resume_lock import GraphResumeAlreadyRunningError
    from fred_sdk.contracts.runtime import StatusRuntimeEvent

    cleaned = asyncio.Event()

    @typed_node(_State)
    async def publish(state: _State, context: GraphNodeContext) -> StepResult:
        context.emit_status("publishing")
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()
        return StepResult(state_update={})

    await _lose_run_while_publishing(checkpointer)
    event = await _interruption(checkpointer)

    class Agent(_Agent):
        workflow = GraphWorkflow(
            entry="prepare", nodes={"prepare": _prepare, "publish": publish, "finalize": _finalize},
            edges={"prepare": "publish", "publish": "finalize"},
        )

    runtime = GraphRuntime(definition=Agent(), services=RuntimeServices(checkpointer=checkpointer))
    runtime.bind(_binding())
    executor = cast(GraphExecutor, await runtime.get_executor())
    config = ExecutionConfig(session_id="s1", interrupted_action="continue", interruption_id=event.interruption_id)
    stream = executor.stream(_Input(message="ignored"), config)
    try:
        assert isinstance(await anext(stream), StatusRuntimeEvent)
        with pytest.raises(GraphResumeAlreadyRunningError):
            async with checkpointer.graph_resume_lock.acquire(executor.thread_id(config)):
                pytest.fail("Admission released while the node is active")
    finally:
        await stream.aclose()
    assert cleaned.is_set()
    async with checkpointer.graph_resume_lock.acquire(executor.thread_id(config)):
        pass
