# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fred_core.security.backend_to_backend_auth import M2MBearerAuth, TokenLease
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.security import weaver_admission

PERSON = AssertedUser(uid="person", client_id="pod", run_id="run", agent_id="agent")


@pytest.mark.asyncio
async def test_scope_uses_knowledge_flow_credential_and_rechecks_revocation(monkeypatch):
    anchor = uuid4()
    seen = []

    def respond(request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer knowledge-flow-token"
        assert dict(request.url.params) == {"person": PERSON.uid, "run": PERSON.run_id, "agent": PERSON.agent_id}
        assert request.url.path == "/authorize/scope"
        return httpx.Response(200, json={"space_id": str(anchor), "space_ids": []}) if len(seen) == 1 else httpx.Response(403)

    token_provider = SimpleNamespace(get_token_lease=AsyncMock(return_value=TokenLease("knowledge-flow-token", 1)))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), auth=M2MBearerAuth(token_provider)) as client:
        context = SimpleNamespace(configuration=SimpleNamespace(control_plane_url="https://authority.test"), get_authorization_client=lambda: client)
        monkeypatch.setattr(weaver_admission, "get_app_context", lambda: context)
        assert await weaver_admission.require_space_read(PERSON, anchor) == ()
        with pytest.raises(HTTPException) as error:
            await weaver_admission.require_space_read(PERSON, anchor)
        assert error.value.status_code == 403
        assert len(seen) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["wrong_anchor", "invalid_id", "missing_corpus", "duplicates", "server_error", "workload_rejected"])
async def test_malformed_scope_never_becomes_empty_or_unrestricted(monkeypatch, kind):
    anchor = uuid4()
    body = {"space_id": str(anchor), "space_ids": []}
    if kind == "wrong_anchor":
        body["space_id"] = str(uuid4())
    if kind == "invalid_id":
        body["space_ids"] = ["invalid"]
    if kind == "missing_corpus":
        del body["space_ids"]
    if kind == "duplicates":
        body["space_ids"] = [str(anchor), str(anchor)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401 if kind == "workload_rejected" else 500 if kind == "server_error" else 200, json=body))) as client:
        monkeypatch.setattr(
            weaver_admission, "get_app_context", lambda: SimpleNamespace(configuration=SimpleNamespace(control_plane_url="https://authority.test"), get_authorization_client=lambda: client)
        )
        with pytest.raises(HTTPException) as error:
            await weaver_admission.require_space_read(PERSON, anchor)
        assert error.value.status_code == 503


@pytest.mark.parametrize("missing", ["credentials", "delegation", "control_plane_url"])
def test_authorization_startup_requires_own_delegation_credentials(missing):
    from knowledge_flow_backend.application_context import ApplicationContext

    context = SimpleNamespace(
        configuration=SimpleNamespace(
            control_plane_url=None if missing == "control_plane_url" else "https://authority.test",
            security=SimpleNamespace(
                m2m=SimpleNamespace(enabled=missing != "credentials"),
                delegation=SimpleNamespace(act_for_people=missing != "delegation"),
            ),
        )
    )
    with pytest.raises(ValueError, match="requires Control Plane"):
        ApplicationContext.open_authorization_client(context)
