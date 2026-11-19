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

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.conversation_traces.api import router
from control_plane_backend.conversation_traces.store import ConversationTraceStore
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.session_metadata_models import SessionMetadataRow
from control_plane_backend.sessions.store import SessionMetadataStore
from fastapi import FastAPI, HTTPException, Request
from fred_core import KeycloakUser, OrganizationPermission
from fred_core.common import TeamId
from fred_core.security.oidc import get_current_user_or_service, require_own_credential
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

_ADMIN = "/admin/conversation-traces"
_INGEST = "/internal/runtimes/fred-agents/conversation-traces"
_AGENT = {"x-test-principal": "agentic"}
_READER = {"x-test-principal": "reader"}


class _TraceRebac:
    async def check_user_permission_or_raise(self, user, permission, resource_id):
        assert permission is OrganizationPermission.CAN_MANAGE_CONVERSATION_TRACES
        assert resource_id == "fred"
        if user.uid not in {"reader", "admin"}:
            raise HTTPException(403)


async def _test_user(request: Request) -> KeycloakUser:
    principal = request.headers.get("x-test-principal", "outsider")
    return KeycloakUser(
        uid=principal,
        username=principal,
        roles=["service_agent"] if principal == "agentic" else [],
        client_id="agentic" if principal == "agentic" else "app",
    )


@pytest.mark.asyncio
async def test_catalog_admission_finalization_and_erasure_through_api(
    control_plane_sql_engine: AsyncEngine,
):
    engine = control_plane_sql_engine
    async with async_sessionmaker(engine).begin() as session:
        session.add(
            AgentInstanceRow(
                agent_instance_id="agent",
                team_id="team",
                template_id="synthetic",
                source_runtime_id="fred-agents",
                source_agent_id="synthetic",
                display_name="Synthetic assistant",
            )
        )
        session.add(
            SessionMetadataRow(
                session_id="session",
                team_id="team",
                user_id="owner",
                agent_instance_id="agent",
                title="Private conversation title",
            )
        )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_own_credential] = _test_user
    app.dependency_overrides[get_current_user_or_service] = _test_user
    app.dependency_overrides[get_application_container] = lambda: SimpleNamespace(
        get_rebac_engine=_TraceRebac,
        get_conversation_trace_store=lambda: ConversationTraceStore(engine),
        configuration=SimpleNamespace(
            security=SimpleNamespace(m2m=SimpleNamespace(enabled=True)),
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(
                        runtime_id="fred-agents",
                        enabled=True,
                        preparation_client_id="agentic",
                    ),
                ]
            ),
        ),
    )
    admission = {
        "session_id": "session",
        "exchange_id": str(uuid4()),
        "user_id": "owner",
        "agent_instance_id": "agent",
        "history_rank": 8,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(f"{_ADMIN}/settings", headers=_READER)).json() == {
            "enabled": False
        }
        for path in (_ADMIN, f"{_ADMIN}/session", f"{_ADMIN}/settings"):
            assert (await client.get(path)).status_code == 403
        assert (
            await client.put(f"{_ADMIN}/settings", json={"enabled": True})
        ).status_code == 403
        assert (
            await client.post(f"{_INGEST}/admit", headers=_READER, json=admission)
        ).status_code == 403
        assert (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=admission)
        ).json() is None

        enabled = await client.put(
            f"{_ADMIN}/settings", headers=_READER, json={"enabled": True}
        )
        assert enabled.json() == {"enabled": True}
        result = await client.post(f"{_INGEST}/admit", headers=_AGENT, json=admission)
        capture_id = result.json()["capture_id"]
        later = {**admission, "exchange_id": str(uuid4()), "history_rank": 14}
        later_id = (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=later)
        ).json()["capture_id"]
        disabled = await client.put(
            f"{_ADMIN}/settings", headers=_READER, json={"enabled": False}
        )
        assert disabled.json() == {"enabled": False}
        off_turn = {**admission, "exchange_id": str(uuid4()), "history_rank": 18}
        assert (
            await client.post(f"{_INGEST}/admit", headers=_AGENT, json=off_turn)
        ).json() is None

        failed = {
            "outcome": "failed",
            "duration_ms": 20,
            "turn_number": 2,
            "call_ids": ["call-1"],
        }
        assert (
            await client.put(f"{_INGEST}/{capture_id}", headers=_READER, json=failed)
        ).status_code == 403
        assert (
            await client.put(f"{_INGEST}/{capture_id}", headers=_AGENT, json=failed)
        ).status_code == 204
        done = {"outcome": "completed", "duration_ms": 2, "turn_number": 3}
        assert (
            await client.put(f"{_INGEST}/{later_id}", headers=_AGENT, json=done)
        ).status_code == 204

        failure_page = (await client.get(_ADMIN, headers=_READER)).json()[
            "conversations"
        ]
        all_page = (
            await client.get(_ADMIN, headers=_READER, params={"failed_only": False})
        ).json()["conversations"]
        assert [row["outcome"] for row in failure_page] == ["failed"]
        assert [row["outcome"] for row in all_page] == ["completed"]
        detail = await client.get(
            f"{_ADMIN}/session", headers=_READER, params={"limit": 1}
        )
        assert "Private conversation title" not in detail.text
        first = detail.json()
        assert first["agent_display_name"] == "Synthetic assistant"
        assert [turn["turn_number"] for turn in first["turns"]] == [2]
        assert first["turns"][0]["call_ids"] == ["call-1"]
        second = await client.get(
            f"{_ADMIN}/session",
            headers=_READER,
            params={"cursor": first["next_cursor"]},
        )
        assert [turn["turn_number"] for turn in second.json()["turns"]] == [3]

        assert await SessionMetadataStore(engine).delete(
            "session", TeamId("team"), "owner"
        )
        assert (
            await client.put(f"{_INGEST}/{later_id}", headers=_AGENT, json=done)
        ).status_code == 204
        assert (
            await client.get(f"{_ADMIN}/session", headers=_READER)
        ).status_code == 404
        assert (await client.get(_ADMIN, headers=_READER)).json()["conversations"] == []
