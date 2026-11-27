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
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fred_core import KeycloakUser
from fred_core.conversation_trace import TraceHistoryAccess
from fred_core.history.history_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    Role,
    TextPart,
    make_tool_call,
    make_tool_result,
    make_user_text,
)
from fred_core.history.managed_session_erasure import SESSION_ERASURE_HEADER
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    create_history_schema,
)
from fred_core.security.oidc import get_current_user_or_service, require_own_credential
from fred_runtime.app import agent_app
from fred_runtime.app.conversation_trace_history import router
from fred_runtime.app.dependencies import get_pod_container
from fred_runtime.migrations import upgrade_sqlite_database
from fred_runtime.runtime_support.checkpoints import (
    active_managed_checkpoint_session,
    checkpoint_config,
    graph_thread_id,
)
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_runtime_erasure_requires_platform_permission_for_service_agents(
    monkeypatch,
):
    app = FastAPI()
    app.include_router(agent_app._build_agent_router({}, True, 100))
    worker = KeycloakUser(
        uid="lifecycle",
        username="lifecycle",
        roles=["service_agent"],
        service_account=True,
    )
    app.dependency_overrides[get_current_user_or_service] = lambda: worker
    app.dependency_overrides[get_pod_container] = lambda: object()
    has_permission = False

    async def permission(caller):
        assert caller.uid == worker.uid
        return has_permission

    async def erase_history(*, session_id, user_id):
        assert session_id == "managed"
        assert user_id is None
        return 2

    monkeypatch.setattr(agent_app, "_caller_can_manage_platform", permission)
    monkeypatch.setattr(
        agent_app,
        "get_runtime_context",
        lambda: SimpleNamespace(
            config=SimpleNamespace(
                history_store=SimpleNamespace(delete_session=erase_history)
            )
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in (
            "/agents/sessions/managed",
            "/agents/sessions/managed/filesystem",
            "/agents/checkpoints/managed",
        ):
            assert (await client.delete(path)).status_code == 403
        has_permission = True
        result = await client.delete("/agents/sessions/managed")
        assert result.status_code == 200
        assert result.json() == {"deleted": 2}


@pytest.mark.asyncio
async def test_accepted_erasure_fences_managed_writes_across_runtimes(
    tmp_path, monkeypatch
):
    url = f"sqlite+aiosqlite:///{tmp_path / 'managed-erasure.db'}"
    reader_engine = create_async_engine(url)
    writer_engine = create_async_engine(url)
    try:
        await create_history_schema(reader_engine)
        eraser = PostgresHistoryStore(reader_engine)
        writer = PostgresHistoryStore(writer_engine)
        reader_checkpoints = FredSqlCheckpointer(reader_engine)
        writer_checkpoints = FredSqlCheckpointer(writer_engine)
        session_id = "managed"
        owner = KeycloakUser(uid="owner", username="owner", roles=[])
        opening = dict(
            session_id=session_id,
            user_id=owner.uid,
            team_id="team",
            agent_instance_id="agent",
        )
        assert await writer.claim_initial_user_message(
            **opening, message=make_user_text(session_id, "first", 0, "Fictional input")
        )

        app = FastAPI()
        app.include_router(agent_app._build_agent_router({}, True, 100))
        app.dependency_overrides[get_current_user_or_service] = lambda: owner
        app.dependency_overrides[get_pod_container] = lambda: object()
        monkeypatch.setattr(
            agent_app,
            "get_runtime_context",
            lambda: SimpleNamespace(
                config=SimpleNamespace(
                    history_store=eraser, checkpointer=reader_checkpoints
                )
            ),
        )

        async def not_platform(_caller):
            return False

        async def no_retained_history(*_args):
            return set()

        accepted = False

        async def erasure_accepted(
            _container, authorization, sessions, *, erasing_only
        ):
            assert authorization == "Bearer owner"
            assert erasing_only and sessions == [session_id]
            return {session_id} if accepted else set()

        monkeypatch.setattr(agent_app, "_caller_can_manage_platform", not_platform)
        monkeypatch.setattr(agent_app, "owner_hidden_sessions", no_retained_history)
        monkeypatch.setattr(agent_app, "hidden_managed_sessions", erasure_accepted)

        thread_id = graph_thread_id(session_id, "agent")
        config = checkpoint_config(thread_id=thread_id)
        token = active_managed_checkpoint_session.set(session_id)
        try:
            initial = await writer_checkpoints.aput(
                config, empty_checkpoint(), {}, {"message": "1"}
            )
            await writer_checkpoints.aput_writes(initial, [("tool", "result")], "task")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer owner"},
            ) as client:
                path = f"/agents/checkpoints/{session_id}"
                flag = {SESSION_ERASURE_HEADER: "true"}
                assert (await client.delete(path, headers=flag)).status_code == 403
                assert (await client.delete(path)).json() == {"deleted": 1}
                await writer_checkpoints.aput(
                    config, empty_checkpoint(), {}, {"message": "2"}
                )
                accepted = True
                app.dependency_overrides[get_current_user_or_service] = lambda: (
                    KeycloakUser(uid="other", username="other", roles=[])
                )
                assert (await client.delete(path, headers=flag)).status_code == 403
                app.dependency_overrides[get_current_user_or_service] = lambda: owner
                assert (await client.delete(path, headers=flag)).json() == {
                    "deleted": 1
                }
                assert (
                    await client.delete(f"/agents/sessions/{session_id}")
                ).json() == {"deleted": 1}
                assert (await client.delete(path, headers=flag)).json() == {
                    "deleted": 0
                }

            late = await writer_checkpoints.aput(
                config, empty_checkpoint(), {}, {"message": "3"}
            )
            await writer_checkpoints.aput_writes(late, [("tool", "late")], "task")
            assert (
                await writer_checkpoints.aclaim_hitl_resume(
                    thread_id=thread_id, checkpoint_ns="", interrupt_id="late"
                )
                is None
            )
            assert not await writer.save_managed_turn(
                **opening, messages=[make_user_text(session_id, "late", 1, "Late")]
            )
            with pytest.raises(ValueError, match="session_erasing"):
                await writer.claim_initial_user_message(**opening, message=None)
            with pytest.raises(ValueError, match="session_erasing"):
                await writer.submit_steered_message(
                    **opening, message_id="late-steer", content="Late"
                )
            assert await eraser.pending_steered_messages(session_id, owner.uid) == []
            assert await eraser.get(session_id, owner.uid) == []
            async with reader_engine.connect() as connection:
                for table in (
                    reader_checkpoints.checkpoints_table,
                    reader_checkpoints.blobs_table,
                    reader_checkpoints.writes_table,
                    reader_checkpoints.thread_owner_table,
                    reader_checkpoints.hitl_claim_table,
                ):
                    assert (
                        await connection.scalar(select(func.count()).select_from(table))
                        == 0
                    )
        finally:
            active_managed_checkpoint_session.reset(token)
    finally:
        await writer_engine.dispose()
        await reader_engine.dispose()


@pytest.mark.asyncio
async def test_runtime_serves_only_history_at_the_active_boundary():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        await create_history_schema(engine)
        store = PostgresHistoryStore(engine)
        await store.save(
            "session",
            [
                make_user_text("session", "first", 0, "Shared question"),
                make_tool_call(
                    "session", "first", 1, "call", "lookup", {"term": "example"}
                ),
                make_tool_result("session", "first", 2, "call", "Shared result"),
            ],
            "owner",
        )
        cutoff = await store.trace_boundary("session", "owner", "first")
        assert cutoff is not None
        error_ref = "1" * 32
        await store.save(
            "session",
            [
                ChatMessage(
                    session_id="session",
                    exchange_id="first",
                    rank=3,
                    timestamp=datetime.now(timezone.utc),
                    role=Role.system,
                    channel=Channel.error,
                    parts=[TextPart(text="Terminal failure")],
                    metadata=ChatMetadata(support_error_ref=error_ref),
                ),
                make_user_text(
                    "session", "first", 4, "Late content in a prior exchange"
                ),
                make_user_text("session", "later", 5, "Later private turn"),
            ],
            "owner",
        )
        await store.save(
            "session",
            [make_user_text("session", "first", 0, "Different owner")],
            "other",
        )

        granted = TraceHistoryAccess(owner_id="owner", cutoff=cutoff, grant_id="grant")
        revoked = TraceHistoryAccess(owner_id="owner")
        current = granted
        revoke_on_recheck = False
        reads = 0

        async def history_access(session_id, authorization, exchange_id=None):
            nonlocal reads
            assert session_id == "session"
            if authorization != "Bearer reader":
                raise HTTPException(403)
            reads += 1
            return revoked if revoke_on_recheck and reads == 2 else current

        async def caller(request: Request) -> KeycloakUser:
            name = request.headers["Authorization"].removeprefix("Bearer ")
            return KeycloakUser(uid=name, username=name, roles=[])

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_own_credential] = caller
        security = SimpleNamespace(
            profile="c3",
            user=SimpleNamespace(enabled=True),
            m2m=SimpleNamespace(enabled=True),
            rebac=None,
        )
        app.dependency_overrides[get_pod_container] = lambda: SimpleNamespace(
            get_history_store=lambda: store,
            configuration=SimpleNamespace(security=security),
            conversation_trace_client=SimpleNamespace(history_access=history_access),
        )
        base = "/agents/sessions/session/trace-history-turns"
        reader = {"Authorization": "Bearer reader"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            incident_path = (
                f"/agents/sessions/session/trace-history-incident/{error_ref}"
            )
            incident = await client.get(
                incident_path, headers={"Authorization": "Bearer owner"}
            )
            assert incident.status_code == 200
            assert incident.json()["cutoff"]["last_rank"] == 3
            assert incident.json()["cutoff"]["exchange_id"] == "first"
            assert incident.json()["support_error_ref"] == error_ref
            assert (await client.get(incident_path, headers=reader)).json() is None

            response = await client.get(f"{base}/first", headers=reader)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert [message["rank"] for message in response.json()["messages"]] == [
                0,
                1,
                2,
            ]
            assert "Shared result" in response.text
            assert "Different owner" not in response.text
            assert "Late content" not in response.text
            assert (
                await client.get(f"{base}/later", headers=reader)
            ).status_code == 403
            assert (
                await client.get(
                    f"{base}/first", headers={"Authorization": "Bearer other"}
                )
            ).status_code == 403
            assert (await client.get(f"{base}/missing", headers=reader)).json()[
                "available"
            ] is False

            reads = 0
            revoke_on_recheck = True
            assert (
                await client.get(f"{base}/first", headers=reader)
            ).status_code == 403
            revoke_on_recheck = False
            current = revoked
            assert (
                await client.get(f"{base}/first", headers=reader)
            ).status_code == 403

        current = TraceHistoryAccess(owner_id="owner", local_content_access=True)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as local:
            assert (await local.get(f"{base}/first", headers=reader)).status_code == 403
            security.profile = None
            security.user.enabled = False
            security.m2m.enabled = False
            assert (await local.get(f"{base}/first", headers=reader)).status_code == 200
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("192.0.2.1", 5130)),
            base_url="http://localhost",
        ) as remote:
            assert (
                await remote.get(f"{base}/first", headers=reader)
            ).status_code == 403
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_terminal_incident_keeps_its_cutoff_when_transcript_write_fails(tmp_path):
    database = tmp_path / "history.sqlite"
    upgrade_sqlite_database(database)
    writer_engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    reader_engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    try:
        writer = PostgresHistoryStore(writer_engine)
        reader = PostgresHistoryStore(reader_engine)
        await writer.save(
            "session",
            [make_user_text("session", "earlier", 0, "Earlier history")],
            "owner",
            agent_instance_id="managed",
        )
        async with writer_engine.begin() as conn:
            await conn.execute(
                text("""
                CREATE TRIGGER reject_terminal_history BEFORE INSERT ON session_history
                WHEN NEW.channel = 'error'
                BEGIN SELECT RAISE(ABORT, 'test terminal history failure'); END
            """)
            )

        error_ref = "1" * 32
        captured_rank = await agent_app._write_turn_history(
            session_id="session",
            user_id="owner",
            agent_instance_id="managed",
            exchange_id="failed",
            request_message="Unpersisted input",
            payloads=[
                {
                    "kind": "execution_error",
                    "message": "Terminal error",
                    "support_error_ref": error_ref,
                }
            ],
            history_store=writer,
            base_rank=await writer.next_rank("session"),
            observe_saved_rank=True,
        )
        incident = await reader.trace_history_incident("session", "owner", error_ref)
        assert incident is not None
        assert incident.cutoff.exchange_id == "failed"
        assert incident.cutoff.turn_number == 2
        assert (incident.cutoff.first_rank, incident.cutoff.last_rank) == (1, 2)
        assert captured_rank == incident.cutoff.last_rank
        assert (
            await reader.trace_history_incident("session", "other", error_ref) is None
        )
        assert await reader.trace_history_incident("session", "owner", "2" * 32) is None
        assert await reader.trace_boundary("session", "owner", "failed") is None

        next_rank = await reader.next_rank("session")
        assert next_rank == 3
        await reader.save(
            "session",
            [make_user_text("session", "later", next_rank, "Later private turn")],
            "owner",
            agent_instance_id="managed",
        )
        turns = await reader.trace_history_page(
            "session", "owner", limit=10, after=None
        )
        assert [(turn.exchange_id, turn.turn_number) for turn in turns] == [
            ("earlier", 1),
            ("later", 3),
        ]
        page = await reader.trace_history_page(
            "session", "owner", limit=1, after=(0, "earlier")
        )
        assert page == turns[1:]
        empty_page = await reader.trace_history_page(
            "session", "owner", limit=1, after=(next_rank, "later")
        )
        assert not empty_page
        assert (
            await writer.trace_history_incident("session", "owner", error_ref)
            == incident
        )
        await reader.delete_session("session")
        assert (
            await writer.trace_history_incident("session", "owner", error_ref) is None
        )
    finally:
        await reader_engine.dispose()
        await writer_engine.dispose()


@pytest.mark.asyncio
async def test_slow_incident_write_leaves_the_saved_error_fallback(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    proof_cleanup = asyncio.Event()
    release_cleanup = asyncio.Event()
    proof_closed = asyncio.Event()
    proof_started = 0
    try:
        await create_history_schema(engine)
        store = PostgresHistoryStore(engine)

        async def held_proof(**_kwargs):
            nonlocal proof_started
            proof_started += 1
            try:
                await asyncio.Future()
            finally:
                proof_cleanup.set()
                await release_cleanup.wait()
                proof_closed.set()

        monkeypatch.setattr(store, "_write_trace_incident", held_proof)
        error_ref = "2" * 32
        captured_rank = await asyncio.wait_for(
            agent_app._write_turn_history(
                session_id="session",
                user_id="owner",
                agent_instance_id="managed",
                exchange_id="failed",
                request_message="Input",
                payloads=[
                    {
                        "kind": "execution_error",
                        "message": "Error",
                        "support_error_ref": error_ref,
                    }
                ],
                history_store=store,
                base_rank=0,
                observe_saved_rank=True,
            ),
            timeout=1.0,
        )
        assert proof_cleanup.is_set()
        assert not proof_closed.is_set()
        with pytest.raises(TimeoutError, match="saturated"):
            await store.trace_exchange_start("session", "owner", "failed")
        with pytest.raises(TimeoutError, match="saturated"):
            await store.record_trace_incident(
                session_id="other-session",
                user_id="owner",
                agent_instance_id="managed",
                first_rank=0,
                started_at=datetime.now(timezone.utc),
                failure=make_user_text("other-session", "other-failure", 1, "Input"),
            )
        assert proof_started == 1
        incident = await store.trace_history_incident("session", "owner", error_ref)
        assert incident is not None
        assert captured_rank == incident.cutoff.last_rank == 1
    finally:
        release_cleanup.set()
        if proof_cleanup.is_set():
            await asyncio.wait_for(proof_closed.wait(), timeout=1)
        await engine.dispose()
