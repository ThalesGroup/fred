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

"""Evaluator-only chat-model override on prepare-execution (#2584).

`prepare_execution()`'s `agent_model_override` param forces the target
instance's chat model for that one call only, never persisted. Covers:
- a service-identity caller with a usable profile gets it written into the
  returned `agent_profile_overrides` for this instance's source_agent_id
- a regular user token is rejected (403) before profile validation ever runs
- a profile the team can't use is rejected (422), not silently ignored
"""

from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.app.dependencies import get_application_container_from_app
from control_plane_backend.config.models import RuntimeCatalogSourceConfig
from control_plane_backend.main import create_app
from control_plane_backend.routing_policy import service as routing_policy_service
from control_plane_backend.routing_policy.schemas import ProfileNotUsableError
from fred_core import KeycloakUser, get_current_user
from httpx import ASGITransport, AsyncClient
from test_main import (
    _fake_require_team_access,
    _FakeAgentInstanceStore,
    _make_record,
    _patch_store,
)

pytestmark = pytest.mark.asyncio

_INSTANCE_ID = "inst-override-1"
_SOURCE_AGENT_ID = "rags.sample.echo"  # _make_record's default


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


def _build_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access",
        _fake_require_team_access,
    )
    store = _FakeAgentInstanceStore(
        [
            _make_record(
                agent_instance_id=_INSTANCE_ID,
                source_runtime_id="runtime-ovr",
                source_agent_id=_SOURCE_AGENT_ID,
            )
        ]
    )
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-ovr",
            base_url="http://runtime-ovr.internal",
            enabled=True,
            ingress_prefix="/runtime/runtime-ovr",
        )
    ]
    return app


async def test_service_agent_with_usable_profile_overwrites_the_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="evaluator", username="evaluator", roles=["service_agent"]
    )

    async def _fake_check(
        deps: Any, *, team_id: Any, profile_id: Any, source_runtime_ids: Any
    ) -> None:
        return None

    monkeypatch.setattr(
        routing_policy_service, "check_profile_usable_for_team", _fake_check
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/control-plane/v1/teams/personal/agent-instances/{_INSTANCE_ID}/prepare-execution",
            params={"agent_model_override": "chat.openai.gpt52"},
        )

    assert resp.status_code == 200
    assert (
        resp.json()["agent_profile_overrides"][_SOURCE_AGENT_ID] == "chat.openai.gpt52"
    )


async def test_regular_user_token_is_rejected_before_any_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    # No get_current_user override: the default no-security mock user carries
    # roles=["admin"] (fred_core.security.oidc.get_current_user_without_gcu) —
    # never a service identity.
    called = False

    async def _fail_if_called(deps: Any, **kwargs: Any) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        routing_policy_service, "check_profile_usable_for_team", _fail_if_called
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/control-plane/v1/teams/personal/agent-instances/{_INSTANCE_ID}/prepare-execution",
            params={"agent_model_override": "chat.openai.gpt52"},
        )

    assert resp.status_code == 403
    assert called is False, (
        "a regular user's request must never reach profile validation"
    )


async def test_non_usable_profile_is_rejected_not_silently_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="evaluator", username="evaluator", roles=["service_agent"]
    )

    async def _fake_check(
        deps: Any, *, team_id: Any, profile_id: Any, source_runtime_ids: Any
    ) -> None:
        raise ProfileNotUsableError(team_id=team_id, profile_ids=[profile_id])

    monkeypatch.setattr(
        routing_policy_service, "check_profile_usable_for_team", _fake_check
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/control-plane/v1/teams/personal/agent-instances/{_INSTANCE_ID}/prepare-execution",
            params={"agent_model_override": "chat.some.disabled"},
        )

    assert resp.status_code == 422
