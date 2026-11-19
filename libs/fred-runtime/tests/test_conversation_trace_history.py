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
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    create_history_schema,
)
from fred_core.security.oidc import get_current_user_or_service, require_own_credential
from fred_runtime.app import agent_app
from fred_runtime.app.conversation_trace_history import router
from fred_runtime.app.dependencies import get_pod_container
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
