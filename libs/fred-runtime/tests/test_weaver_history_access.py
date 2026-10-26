# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Prepared M5b cases. No inference, run admission or external identity provider."""

from dataclasses import dataclass, replace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fred_core.security.delegation import AssertedUser
from fred_core.security.oidc import get_current_user
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import agent_app, history_access
from fred_runtime.runtime_context import RuntimeConfig, RuntimeContext
from fred_runtime.runtime_support.checkpoints import checkpoint_config, graph_thread_id
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

SESSION = "conversation"
BINDING = {
    "subject_id": "alice",
    "space_id": "11111111-1111-4111-8111-111111111111",
    "instance_id": "22222222-2222-4222-8222-222222222222",
    "template_id": "33333333-3333-4333-8333-333333333333",
    "runtime_id": "pod",
}


@dataclass
class _Case:
    client: httpx.AsyncClient
    store: AsyncMock
    checkpointer: AsyncMock
    calls: list[httpx.Request]
    metadata: dict
    app: FastAPI
    status: int = 200
    unavailable: bool = False


@pytest_asyncio.fixture
async def case(monkeypatch):
    store = AsyncMock()
    store.get.return_value = []
    store.list_sessions.return_value = [SESSION]
    cp = AsyncMock()
    cp.aget_conversation_binding.return_value = dict(BINDING)
    calls = []
    metadata = {
        "session_id": SESSION,
        "space_id": BINDING["space_id"],
        "agent_instance_id": BINDING["instance_id"],
        "template_id": BINDING["template_id"],
        "runtime_id": BINDING["runtime_id"],
        "agent_deleted": False,
        "agent_disabled": False,
    }

    def respond(request):
        calls.append(request)
        if value.unavailable:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(value.status, json=metadata)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        auth=httpx.BasicAuth("must-not", "override-person"),
    ) as authority:
        context = RuntimeContext(
            RuntimeConfig(
                knowledge_flow_url="https://unused.invalid",
                service_name="pod",
                control_plane_url="https://cp.invalid/api",
                control_plane_http_client=authority,
                history_store=store,
                checkpointer=cp,
            )
        )
        monkeypatch.setattr(agent_app, "get_runtime_context", lambda: context)
        monkeypatch.setattr(history_access, "get_runtime_context", lambda: context)
        app = FastAPI()
        app.include_router(agent_app._build_agent_router({}, True, 10000))
        # Admission is supplied at the existing authenticated dependency boundary.
        # The outbound PersonCredentialProvider remains the real implementation.
        app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
            uid="alice", username="alice", roles=[]
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="https://pod.invalid",
            headers={"Authorization": "Bearer synthetic-person-token"},
        ) as client:
            value = _Case(client, store, cp, calls, metadata, app)
            yield value


@pytest.mark.asyncio
@pytest.mark.parametrize("instance_state", [None, "agent_deleted", "agent_disabled"])
async def test_owned_empty_history_uses_person_metadata_api(case, instance_state):
    if instance_state:
        case.metadata[instance_state] = True
    response = await case.client.get(f"/agents/sessions/{SESSION}/messages")
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["Cache-Control"] == "no-store"
    case.store.get.assert_awaited_once_with(session_id=SESSION, user_id="alice")
    (sent,) = case.calls
    assert sent.headers["Authorization"] == "Bearer synthetic-person-token"
    assert not sent.url.query
    assert sent.url.path == f"/api/spaces/{BINDING['space_id']}/sessions/{SESSION}"
    case.checkpointer.abind_conversation.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["session_id", "space_id", "agent_instance_id", "template_id", "runtime_id"],
)
async def test_control_plane_provenance_mismatch_precedes_content(case, field):
    case.metadata[field] = "different"
    response = await case.client.get(f"/agents/sessions/{SESSION}/messages")
    assert response.status_code == 404
    case.store.get.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "binding",
    [None, {}, {**BINDING, "subject_id": "bob"}, {**BINDING, "runtime_id": "other"}],
)
async def test_foreign_old_or_wrong_runtime_never_queries_authority(case, binding):
    case.checkpointer.aget_conversation_binding.return_value = binding
    response = await case.client.get(f"/agents/sessions/{SESSION}/messages")
    assert response.status_code == 404
    assert case.calls == []
    case.store.get.assert_not_called()
    case.checkpointer.abind_conversation.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", [f"/agents/sessions/{SESSION}/messages", f"/agents/checkpoints/{SESSION}"]
)
@pytest.mark.parametrize(
    "upstream, expected", [(401, 401), (403, 404), (404, 404), (503, 503), (302, 503)]
)
async def test_refusal_and_failure_cover_both_content_readers(
    case, path, upstream, expected
):
    case.status = upstream
    response = await case.client.get(path)
    assert response.status_code == expected
    case.store.get.assert_not_called()
    case.checkpointer._ensure_tables.assert_not_called()
    assert len(case.calls) == 1


@pytest.mark.asyncio
async def test_independent_read_rechecks_revocation_and_query_ids_cannot_broaden(case):
    path = f"/agents/sessions/{SESSION}/messages?user_id=bob&space_id=other&runtime_id=other"
    assert (await case.client.get(path)).status_code == 200
    case.status = 403
    assert (await case.client.get(path)).status_code == 404
    assert len(case.calls) == 2
    assert all(str(call.url).endswith(f"/sessions/{SESSION}") for call in case.calls)
    assert case.store.get.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["authority", "provenance", "messages"])
async def test_technical_failure_is_never_empty_history(case, where):
    if where == "authority":
        case.unavailable = True
    elif where == "provenance":
        case.checkpointer.aget_conversation_binding.side_effect = SQLAlchemyError(
            "offline"
        )
    else:
        case.store.get.side_effect = SQLAlchemyError("offline")
    response = await case.client.get(f"/agents/sessions/{SESSION}/messages")
    assert response.status_code >= 500
    assert response.text != "[]"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "principal",
    [
        KeycloakUser(uid="alice", username="service", roles=[], service_account=True),
        KeycloakUser(uid="alice", username="service", roles=["service_agent"]),
        AssertedUser(
            uid="alice", client_id="workload", run_id="old-run", agent_id="agent"
        ),
    ],
)
async def test_service_or_asserted_person_has_no_read_authority(case, principal):
    case.app.dependency_overrides[get_current_user] = lambda: principal
    response = await case.client.get(f"/agents/sessions/{SESSION}/messages")
    assert response.status_code == 403
    case.checkpointer.aget_conversation_binding.assert_not_called()
    assert case.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/agents/sessions?user_id=bob", "/agents/checkpoints"]
)
async def test_indexes_filter_revocation_but_surface_infrastructure_errors(case, path):
    case.status = 403
    response = await case.client.get(path)
    assert response.status_code == 200
    assert response.json() == []
    case.store.list_sessions.assert_awaited_with(user_id="alice")
    case.status = 503
    assert (await case.client.get(path)).status_code == 503
    case.checkpointer._ensure_tables.assert_not_called()


@pytest.mark.asyncio
async def test_absent_bearer_and_substituted_session_cannot_load_content(case):
    response = await case.client.get(
        f"/agents/sessions/{SESSION}/messages", headers={"Authorization": ""}
    )
    assert response.status_code == 403
    case.checkpointer.aget_conversation_binding.assert_not_called()
    response = await case.client.get("/agents/sessions/other-session/messages")
    assert response.status_code == 404
    case.store.get.assert_not_called()


@pytest.mark.asyncio
async def test_personal_history_index_ignores_browser_user_id(case):
    response = await case.client.get("/agents/sessions?user_id=bob")
    assert response.status_code == 200
    assert response.json() == [SESSION]
    case.store.list_sessions.assert_awaited_once_with(user_id="alice")
    assert len(case.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("forbidden", ["conversation_a_extra", "conversationXa"])
async def test_checkpoint_index_includes_only_authorized_graph_threads(
    case, monkeypatch, tmp_path, forbidden
):
    allowed = "conversation_a"
    allowed_threads = {
        graph_thread_id(allowed, "graph"),
        graph_thread_id(allowed, "child"),
    }
    spaces = {
        allowed: BINDING["space_id"],
        forbidden: "44444444-4444-4444-8444-444444444444",
    }
    case.store.list_sessions.return_value = [allowed, forbidden]
    case.metadata["session_id"] = allowed
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith(f"/sessions/{allowed}"):
            return httpx.Response(200, json=case.metadata)
        return httpx.Response(403)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'graph.sqlite3'}")
    try:
        cp = FredSqlCheckpointer(engine)
        # Both are owned locally; only one retains current M5a space access.
        for session_id in (allowed, forbidden):
            assert await cp.abind_conversation(
                session_id,
                {**BINDING, "space_id": spaces[session_id]},
                allow_create=True,
            )
        # The allowed session has no root checkpoint, only Graph-derived threads.
        for thread in (
            *allowed_threads,
            forbidden,
            graph_thread_id(forbidden, "graph"),
        ):
            await cp.aput(
                checkpoint_config(thread_id=thread), empty_checkpoint(), {}, {}
            )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond)
        ) as authority:
            runtime = RuntimeContext(
                replace(
                    agent_app.get_runtime_context().config,
                    checkpointer=cp,
                    control_plane_http_client=authority,
                )
            )
            monkeypatch.setattr(agent_app, "get_runtime_context", lambda: runtime)
            monkeypatch.setattr(history_access, "get_runtime_context", lambda: runtime)
            response = await case.client.get("/agents/checkpoints")

        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        rows = response.json()
        # Keep the existing per-thread response, without folding it into a session row.
        assert {row["session_id"] for row in rows} == allowed_threads
        assert all(row["checkpoint_count"] == 1 for row in rows)
        assert all(row["checkpoint_bytes_total"] > 0 for row in rows)
        assert [request.url.path for request in requests] == [
            f"/api/spaces/{spaces[session_id]}/sessions/{session_id}"
            for session_id in (allowed, forbidden)
        ]
        assert all(
            request.headers["Authorization"] == "Bearer synthetic-person-token"
            for request in requests
        )
        case.store.get.assert_not_called()
    finally:
        await engine.dispose()
