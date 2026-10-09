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
`POST …/agent-templates/{template_id}/draft-agent`: the control plane offers
the pod only capabilities the team may use on that template, forwards the
caller's token, and maps pod failures to clear statuses.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx
import pytest
from control_plane_backend.platform_prompt.store import StoredCreationAssistantSettings
from control_plane_backend.product import api as product_api
from fred_core import KeycloakUser, TeamPermission
from fred_core.common import TeamId
from fred_sdk.contracts.agent_draft import AgentDraftRequest
from httpx import ASGITransport, AsyncClient
from test_capability_selection_1974 import (
    RAGS_SAMPLE_ECHO_TEMPLATE_ID,
    _setup,
    _wire_rebac,
)

_TEAM_ID = "team-a"


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


_URL = (
    f"/control-plane/v1/teams/{_TEAM_ID}"
    "/agent-templates/runtime-a:rags.sample.echo/draft-agent"
)
_BODY = {
    "description": "Answer buyers' questions about supplier offers.",
    "language": "en",
    "capabilities": [
        {"id": "demo_echo", "name": "Echo", "description": "Repeats things"},
        {"id": "probe_echo", "name": "Probe", "description": ""},
        {"id": "smuggled", "name": "Not on this template", "description": ""},
    ],
}


def _wire_pod(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: int = 200,
    answer: Any = None,
    error: Exception | None = None,
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if error is not None:
            raise error
        payload = (
            answer
            if answer is not None
            else {
                "name": "Buyer helper",
                "role": "Compares offers",
                "description": "Helps buyers compare offers.",
                "system_prompt": "You help buyers.",
                "capability_ids": ["probe_echo", "demo_echo"],
            }
        )
        return httpx.Response(status, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_runtime_http_client",
        lambda self: client,
    )
    return seen


async def _post(app, body: dict[str, Any] = _BODY) -> httpx.Response:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            _URL, json=body, headers={"Authorization": "Bearer user-token"}
        )


@pytest.mark.asyncio
async def test_forwards_only_capabilities_the_team_may_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, {_TEAM_ID: {RAGS_SAMPLE_ECHO_TEMPLATE_ID, "demo_echo"}})
    app, _store = _setup(monkeypatch)
    seen = _wire_pod(monkeypatch)

    response = await _post(app)

    assert response.status_code == 200
    # The pod recommended probe_echo too; the team cannot use it.
    assert response.json() == {
        "name": "Buyer helper",
        "role": "Compares offers",
        "description": "Helps buyers compare offers.",
        "system_prompt": "You help buyers.",
        "capability_ids": ["demo_echo"],
    }
    (request,) = seen
    assert str(request.url) == (
        "http://runtime-a/pod/v1/agents/creation-assistant/draft"
    )
    assert request.headers["Authorization"] == "Bearer user-token"
    sent = json.loads(request.content)
    assert [c["id"] for c in sent["capabilities"]] == ["demo_echo"]
    assert sent["capabilities"][0]["name"] == "Echo"
    assert sent["team_id"] == _TEAM_ID
    assert sent["description"] == _BODY["description"]


@pytest.mark.asyncio
async def test_rebac_disabled_offers_every_template_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, None)
    app, _store = _setup(monkeypatch)
    seen = _wire_pod(monkeypatch)

    response = await _post(app)

    assert response.status_code == 200
    sent = json.loads(seen[0].content)
    assert [c["id"] for c in sent["capabilities"]] == ["demo_echo", "probe_echo"]
    assert response.json()["capability_ids"] == ["probe_echo", "demo_echo"]


@pytest.mark.asyncio
async def test_unknown_template_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_rebac(monkeypatch, None)
    app, _store = _setup(monkeypatch)
    seen = _wire_pod(monkeypatch)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            _URL.replace("rags.sample.echo", "ghost"), json=_BODY
        )

    assert response.status_code == 404
    assert seen == []


@pytest.mark.asyncio
async def test_template_the_team_may_not_use_is_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, {_TEAM_ID: {"demo_echo"}})
    app, _store = _setup(monkeypatch)
    seen = _wire_pod(monkeypatch)

    assert (await _post(app)).status_code == 404
    assert seen == []


@pytest.mark.asyncio
async def test_pod_validation_errors_read_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, None)
    app, _store = _setup(monkeypatch)
    _wire_pod(
        monkeypatch,
        status=422,
        answer={"detail": [{"loc": ["body"], "msg": "String too long"}]},
    )

    response = await _post(app)

    assert response.status_code == 422
    assert response.json()["detail"] == "String too long"


@pytest.mark.asyncio
async def test_blank_description_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_rebac(monkeypatch, None)
    app, _store = _setup(monkeypatch)
    seen = _wire_pod(monkeypatch)

    response = await _post(app, {**_BODY, "description": "  "})

    assert response.status_code == 422
    assert seen == []


@pytest.mark.parametrize(
    ("pod_status", "error", "expected"),
    [
        (422, None, 422),
        (403, None, 403),
        (401, None, 502),
        (503, None, 503),
        (504, None, 504),
        (502, None, 502),
        (500, None, 502),
        (404, None, 501),
        (200, httpx.ReadTimeout("slow"), 504),
        (200, httpx.PoolTimeout("busy"), 503),
        (200, httpx.ConnectError("down"), 503),
    ],
)
@pytest.mark.asyncio
async def test_pod_failures_are_mapped(
    monkeypatch: pytest.MonkeyPatch,
    pod_status: int,
    error: Exception | None,
    expected: int,
) -> None:
    _wire_rebac(monkeypatch, None)
    app, _store = _setup(monkeypatch)
    _wire_pod(
        monkeypatch, status=pod_status, answer={"detail": "pod says"}, error=error
    )

    response = await _post(app)

    assert response.status_code == expected


@pytest.mark.asyncio
async def test_pool_wait_is_short_and_not_reported_as_a_slow_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, None)
    app, _store = _setup(monkeypatch)
    seen = _wire_pod(monkeypatch, error=httpx.PoolTimeout("busy"))

    response = await _post(app)

    assert response.status_code == 503
    assert "too long" not in response.json()["detail"]
    timeout = seen[0].extensions["timeout"]
    assert (timeout["pool"], timeout["connect"], timeout["read"]) == (5.0, 5.0, 55.0)


@pytest.mark.asyncio
async def test_malformed_pod_answer_is_502(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_rebac(monkeypatch, None)
    app, _store = _setup(monkeypatch)
    _wire_pod(monkeypatch, answer={"unexpected": True})

    assert (await _post(app)).status_code == 502


@pytest.mark.asyncio
async def test_requires_can_update_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    get_team = AsyncMock(return_value=TeamId("t"))
    monkeypatch.setattr(product_api, "require_team_access", get_team)
    monkeypatch.setattr(product_api, "draft_agent", AsyncMock())

    await product_api.post_draft_agent(
        TeamId("t"),
        "runtime-a:agent",
        AgentDraftRequest(description="d"),
        cast(Any, SimpleNamespace(team_dependencies=SimpleNamespace())),
        cast(Any, SimpleNamespace(headers={})),
        KeycloakUser(uid="u", username="u", roles=[], email=None),
    )

    assert get_team.await_args is not None
    assert get_team.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_UPDATE_AGENTS
    ]


@pytest.mark.asyncio
async def test_pod_body_never_carries_admin_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, {_TEAM_ID: {RAGS_SAMPLE_ECHO_TEMPLATE_ID, "demo_echo"}})
    app, _store = _setup(monkeypatch)
    seen = _wire_pod(monkeypatch)
    injected = {
        **_BODY,
        "creation_assistant_prompt": "INJECTED",
        "model_profile_id": "chat.injected",
    }

    assert (await _post(app, injected)).status_code == 200
    sent = json.loads(seen[0].content)
    assert "creation_assistant_prompt" not in sent
    assert "model_profile_id" not in sent


async def _get_settings(app) -> httpx.Response:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(
            f"/control-plane/v1/teams/{_TEAM_ID}/creation-assistant/settings"
        )


@pytest.mark.asyncio
async def test_pod_reads_the_saved_admin_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_rebac(monkeypatch, None)
    app, _store = _setup(monkeypatch)
    saved: list[StoredCreationAssistantSettings | None] = [None]

    async def _resolve(_deps: Any) -> StoredCreationAssistantSettings | None:
        return saved[0]

    monkeypatch.setattr(
        "control_plane_backend.product.creation_assistant.resolve_creation_assistant_settings",
        _resolve,
    )

    response = await _get_settings(app)
    assert response.status_code == 200
    assert response.json() == {
        "creation_assistant_prompt": None,
        "model_profile_id": None,
        "reasoning_effort": "off",
    }

    saved[0] = StoredCreationAssistantSettings(
        text="ADMIN {language}",
        model_profile_id="chat.large",
        reasoning_effort="high",
        updated_by="admin",
        updated_at=None,
    )
    response = await _get_settings(app)
    assert response.json() == {
        "creation_assistant_prompt": "ADMIN {language}",
        "model_profile_id": "chat.large",
        "reasoning_effort": "high",
    }


@pytest.mark.asyncio
async def test_settings_read_requires_can_update_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_team = AsyncMock(return_value=TeamId("t"))
    monkeypatch.setattr(product_api, "require_team_access", get_team)
    monkeypatch.setattr(product_api, "creation_assistant_runtime_settings", AsyncMock())

    await product_api.get_creation_assistant_runtime_settings(
        TeamId("t"),
        cast(Any, SimpleNamespace(team_dependencies=SimpleNamespace())),
        KeycloakUser(uid="u", username="u", roles=[], email=None),
    )

    assert get_team.await_args is not None
    assert get_team.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_UPDATE_AGENTS
    ]
