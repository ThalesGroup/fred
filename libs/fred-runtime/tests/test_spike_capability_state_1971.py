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
SPIKE #1971 — capability middleware state persistence through FredSqlCheckpointer.

This file is SPIKE MATERIAL for the Agent Capability track (#1961,
docs/swift/rfc/AGENT-CAPABILITY-RFC.md §5.2 / §12 Q3). It is deliberately not
product code: it builds a throwaway toy `AgentMiddleware` with a custom
`state_schema` (one JSON-primitive channel with a reducer + one Pydantic-model
channel) and drives it through the full lifecycle against `FredSqlCheckpointer`:

    write -> executor rebuild -> read -> interrupt() -> resume

"Executor rebuild" is simulated faithfully: a *fresh* AsyncEngine, a *fresh*
FredSqlCheckpointer and a *fresh* `create_agent(...)` graph are constructed
between phases, so nothing survives in process memory — only the SQL rows.

Probes (each is a test):
  1. JSON-primitive channel values           -> expected to round-trip intact.
  2. Pydantic-model channel values           -> expected to come back DEGRADED
     (plain dict) because the checkpointer's `JsonPlusSerializer` msgpack
     allowlist is closed (single legacy entry); also shows that extending the
     allowlist restores the typed instance.
  3. Mismatch: a checkpoint carrying a state channel from a capability that is
     no longer installed (feeds the suspension design, RFC §3.9).

How to run:
  - offline (SQLite, runs in `make test`):
        .venv/bin/pytest tests/test_spike_capability_state_1971.py -v
  - against a live Postgres (the dev `app-postgres` container), with the dev
    DSN exported first (see fred .env):
        export SPIKE_PG_DSN="postgresql+asyncpg://fred:Azerty123_@localhost:5432/fred"  # pragma: allowlist secret
        .venv/bin/pytest tests/test_spike_capability_state_1971.py -v -m integration
    The Postgres run uses its own `spike1971_` table prefix and drops those
    tables afterwards.

No LLM / network is involved: the model is a deterministic scripted fake.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated, Any, NotRequired, cast

import pytest
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command, interrupt
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_PG_DSN_ENV = "SPIKE_PG_DSN"
_PG_PREFIX = "spike1971_"


# --------------------------------------------------------------------------
# Toy capability — Pydantic channel value
# --------------------------------------------------------------------------


class CapDoc(BaseModel):
    """A Pydantic value a capability might be tempted to keep in graph state."""

    doc_id: str
    version: int
    tags: list[str]


def _merge_seen(
    left: dict[str, int] | None, right: dict[str, int] | None
) -> dict[str, int]:
    """Reducer: merge per-doc counters (right wins per key)."""
    return {**(left or {}), **(right or {})}


class CapState(AgentState):
    """Toy capability state schema — the §5.2 `doc_versions_seen` shape."""

    cap_seen: NotRequired[Annotated[dict[str, int], _merge_seen]]  # JSON-primitive
    cap_doc: NotRequired[CapDoc]  # Pydantic — the degradation probe


@tool
async def cap_approval(action: str) -> str:
    """Ask a human to approve the action before doing it."""
    decision = interrupt({"question": f"approve {action}?"})
    return f"decision={decision['decision']}"


class ToyCapabilityMiddleware(AgentMiddleware):
    """Toy capability: one state channel with a reducer + one Pydantic channel."""

    state_schema = CapState
    tools = [cap_approval]

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        seen = dict(state.get("cap_seen") or {})
        n = seen.get("doc-1", 0) + 1
        return {
            "cap_seen": {"doc-1": n},
            "cap_doc": CapDoc(doc_id="doc-1", version=n, tags=["spike", "1971"]),
        }


# --------------------------------------------------------------------------
# Deterministic scripted model (no network)
# --------------------------------------------------------------------------


class ScriptedChatModel(BaseChatModel):
    """Fake chat model: emits a tool call when asked to, else a final answer."""

    @property
    def _llm_type(self) -> str:
        return "scripted-spike-1971"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self  # tools are ignored; the script decides when to call one

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        last = messages[-1]
        if isinstance(last, ToolMessage):
            msg = AIMessage(content=f"tool said: {last.content}")
        elif isinstance(last, HumanMessage) and "interrupt" in str(last.content):
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "cap_approval",
                        "args": {"action": "write"},
                        "id": "call-spike-1",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            msg = AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=msg)])


# --------------------------------------------------------------------------
# Executor (re)builders — a fresh engine+checkpointer+graph each call
# --------------------------------------------------------------------------


def _build_agent(engine: AsyncEngine, *, with_capability: bool):
    """One 'executor': fresh checkpointer + fresh create_agent graph."""
    prefix = _PG_PREFIX if engine.dialect.name == "postgresql" else "v2_"
    checkpointer = FredSqlCheckpointer(engine, prefix=prefix)
    middleware = [ToyCapabilityMiddleware()] if with_capability else []
    agent = create_agent(
        model=ScriptedChatModel(),
        tools=[],
        system_prompt="You are a spike probe.",
        middleware=middleware,
        checkpointer=checkpointer,
    )
    return agent, checkpointer


@pytest.fixture(
    params=[
        pytest.param("sqlite"),
        pytest.param("postgres", marks=pytest.mark.integration),
    ]
)
def fresh_engine(request, tmp_path):
    """Factory producing a NEW engine per call (simulates process rebuild)."""
    engines: list[AsyncEngine] = []
    if request.param == "sqlite":
        db = tmp_path / "spike1971.sqlite3"

        def make() -> AsyncEngine:
            eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
            engines.append(eng)
            return eng

        yield make
    else:
        dsn = os.environ.get(
            _PG_DSN_ENV,
            "postgresql+asyncpg://fred:Azerty123_@localhost:5432/fred",  # pragma: allowlist secret
        )

        def make() -> AsyncEngine:
            eng = create_async_engine(dsn)
            engines.append(eng)
            return eng

        yield make
        # Leave the shared dev DB clean: drop the spike-prefixed tables.
        import asyncio

        async def _cleanup() -> None:
            eng = create_async_engine(dsn)
            async with eng.begin() as conn:
                for table in (
                    "langgraph_checkpoint",
                    "langgraph_checkpoint_blob",
                    "langgraph_checkpoint_write",
                    "checkpoint_thread_owner",
                ):
                    await conn.execute(
                        text(f'DROP TABLE IF EXISTS "{_PG_PREFIX}{table}"')
                    )
            await eng.dispose()

        asyncio.run(_cleanup())


def _config(thread_id: str) -> Any:
    return {"configurable": {"thread_id": thread_id}}


# --------------------------------------------------------------------------
# Probe 1+2 — full lifecycle: write -> rebuild -> read -> interrupt -> resume
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capability_state_full_lifecycle(fresh_engine):
    thread_id = f"spike-1971-{uuid.uuid4()}"
    cfg = _config(thread_id)

    # ---- Phase 1: WRITE (turn 1, capability installed) --------------------
    eng1 = fresh_engine()
    agent1, _ = _build_agent(eng1, with_capability=True)
    res1 = await agent1.ainvoke({"messages": [HumanMessage("hello")]}, cfg)
    # In-process the values are still typed:
    assert res1["cap_seen"] == {"doc-1": 1}
    assert isinstance(res1["cap_doc"], CapDoc)
    await eng1.dispose()

    # ---- Phase 2: EXECUTOR REBUILD + READ ---------------------------------
    eng2 = fresh_engine()
    agent2, _ = _build_agent(eng2, with_capability=True)
    state = await agent2.aget_state(cfg)

    # Probe 1 — JSON-primitive channel: round-trips INTACT through the
    # closed-allowlist serializer (dict/int are native msgpack types).
    assert state.values["cap_seen"] == {"doc-1": 1}

    # Probe 2 — Pydantic channel: comes back DEGRADED. The msgpack allowlist
    # is closed (single legacy entry), so the ext hook refuses to reconstruct
    # CapDoc and returns the raw constructor payload — a plain dict.
    observed_doc = state.values["cap_doc"]
    assert not isinstance(observed_doc, CapDoc), (
        "UNEXPECTED: Pydantic value survived the closed allowlist — "
        f"got {type(observed_doc)!r}. The §5.2 rule needs revisiting."
    )
    assert observed_doc == {
        "doc_id": "doc-1",
        "version": 1,
        "tags": ["spike", "1971"],
    }, f"degraded shape changed: {observed_doc!r}"

    # ---- Phase 3: interrupt() on the rebuilt executor ---------------------
    res2 = await agent2.ainvoke({"messages": [HumanMessage("please interrupt")]}, cfg)
    interrupts = res2["__interrupt__"]
    assert len(interrupts) == 1
    assert interrupts[0].value == {"question": "approve write?"}
    await eng2.dispose()

    # ---- Phase 4: REBUILD AGAIN + RESUME ----------------------------------
    eng3 = fresh_engine()
    agent3, _ = _build_agent(eng3, with_capability=True)
    res3 = await agent3.ainvoke(Command(resume={"decision": "approved"}), cfg)
    final = res3["messages"][-1]
    assert "decision=approved" in str(final.content)

    # The reducer kept accumulating across turns/rebuilds — reading the
    # JSON-primitive channel back from SQL fed before_model correctly.
    assert res3["cap_seen"]["doc-1"] >= 2, res3["cap_seen"]

    # The degraded Pydantic dict did NOT poison the resume: before_model just
    # overwrote it with a fresh instance (in-process value is typed again).
    assert isinstance(res3["cap_doc"], CapDoc)
    await eng3.dispose()


# --------------------------------------------------------------------------
# Probe 3 — mismatch: checkpoint carries a channel whose capability is gone
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orphaned_capability_channel_mismatch(fresh_engine):
    thread_id = f"spike-1971-{uuid.uuid4()}"
    cfg = _config(thread_id)

    # Turn 1 with the capability installed.
    eng1 = fresh_engine()
    agent1, _ = _build_agent(eng1, with_capability=True)
    await agent1.ainvoke({"messages": [HumanMessage("hello")]}, cfg)
    await eng1.dispose()

    # Rebuild WITHOUT the capability (package uninstalled / rolled back).
    eng2 = fresh_engine()
    agent2, cp2 = _build_agent(eng2, with_capability=False)

    # Raw checkpoint still carries the orphaned channels...
    tup = await cp2.aget_tuple(cfg)
    assert tup is not None
    raw_channels = set(tup.checkpoint["channel_values"].keys())
    assert "cap_seen" in raw_channels

    # ...but the graph-level read silently HIDES them (no error, no warning):
    state = await agent2.aget_state(cfg)
    assert "cap_seen" not in state.values
    assert "cap_doc" not in state.values

    # A turn on the capability-less executor SILENTLY SUCCEEDS — LangGraph
    # neither crashes nor complains about the orphaned channels.
    res = await agent2.ainvoke({"messages": [HumanMessage("hi again")]}, cfg)
    assert str(res["messages"][-1].content) == "done"
    await eng2.dispose()

    # Reinstall the capability: is the old state recovered or lost?
    eng3 = fresh_engine()
    agent3, cp3 = _build_agent(eng3, with_capability=True)
    state3 = await agent3.aget_state(cfg)
    recovered_seen = state3.values.get("cap_seen")
    tup3 = await cp3.aget_tuple(cfg)
    assert tup3 is not None
    latest_versions = set(
        cast(dict, tup3.checkpoint.get("channel_versions", {})).keys()
    )

    # Observed: the capability-less turn wrote a checkpoint that still carries
    # the orphaned channel versions forward, so reinstalling recovers state.
    # (If this assert fires, the checkpoint dropped the channels — that would
    # make suspension (RFC §3.9) mandatory before any capability-less turn.)
    assert recovered_seen == {"doc-1": 1}, (
        f"orphaned channel after reinstall: values={state3.values!r} "
        f"latest_versions={sorted(latest_versions)}"
    )
    await eng3.dispose()


# --------------------------------------------------------------------------
# Serde-level probe — isolates the serializer conclusion from graph mechanics
# --------------------------------------------------------------------------


def _fred_serde() -> JsonPlusSerializer:
    """The exact serde FredSqlCheckpointer builds (closed allowlist, 1 entry)."""
    return JsonPlusSerializer(
        allowed_msgpack_modules=list(FredSqlCheckpointer._FRED_MSGPACK_ALLOWLIST)
    )


def test_serde_json_primitive_roundtrips_intact():
    serde = _fred_serde()
    value = {"doc-1": 3, "nested": {"tags": ["a", "b"], "ok": True, "pi": 3.14}}
    assert serde.loads_typed(serde.dumps_typed(value)) == value


def test_serde_pydantic_degrades_to_dict_and_allowlist_restores():
    serde = _fred_serde()
    doc = CapDoc(doc_id="doc-1", version=7, tags=["x"])
    dumped = serde.dumps_typed(doc)

    # Closed allowlist -> degraded read: raw constructor payload (plain dict).
    degraded = serde.loads_typed(dumped)
    assert not isinstance(degraded, CapDoc)
    assert degraded == {"doc_id": "doc-1", "version": 7, "tags": ["x"]}

    # Extending the allowlist (what capability *registration* would do)
    # restores the typed instance from the very same stored bytes.
    extended = serde.with_msgpack_allowlist([CapDoc])
    restored = extended.loads_typed(dumped)
    assert isinstance(restored, CapDoc)
    assert restored == doc
