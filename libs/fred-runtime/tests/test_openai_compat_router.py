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
Offline unit tests for the OpenAI-compat /v1 router.

Tests cover:
- GET /v1/models returns registered agents in OpenAI model-list format
- POST /v1/chat/completions refuses execution until Weaver admission is wired
- Authentication errors retain their status before the unsupported route

All tests run without any external services.
"""

from __future__ import annotations

from unittest.mock import Mock

import fred_runtime.app.openai_compat_router as openai_compat_router_module
import pytest
from conftest import (
    StaticChatModelFactory,
    ToolFriendlyFakeChatModel,
    migrate_test_config,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import AgentPodConfig, create_agent_app
from fred_runtime.app import agent_app as agent_app_module
from fred_sdk.authoring import ReActAgent, tool
from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.models import ReActAgentDefinition
from langchain_core.messages import AIMessage

pytestmark = pytest.mark.usefixtures("offline_pod_infrastructure")


@tool("demo.hello", description="Return a greeting.")
async def _demo_hello(ctx: ToolContext) -> str:
    """Return a static greeting for offline tests."""
    return "hello from tool"


class _HelloAgent(ReActAgent):
    """
    Minimal authored agent for OpenAI-compat router tests.

    Why this exists:
    - the router test needs a real ReActAgent definition so the pod app factory
      wires it correctly; a plain dict would not pass registry validation

    How to use it:
    - register it in the test app registry
    """

    agent_id: str = "test.hello.v1"
    role: str = "Hello Agent"
    description: str = "Greets the user."
    system_prompt_template: str = "Greet the user briefly."
    tools = (_demo_hello,)


def _build_test_config(
    tmp_path,
    *,
    openai_compat: bool = True,
    max_chat_input_chars: int = 5_000,
) -> AgentPodConfig:
    """
    Build an offline pod config with openai_compat enabled.

    Why this exists:
    - mirrors `_build_test_config` in test_agent_app.py; kept local to this
      module so the two test files remain independent

    How to use it:
    - call once per test with pytest's `tmp_path`
    """
    config = AgentPodConfig.model_validate(
        {
            "app": {
                "runtime_id": "test-pod",
                "name": "Test Pod",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
                "openai_compat": openai_compat,
                "max_chat_input_chars": max_chat_input_chars,
            },
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "test-m2m",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "http://localhost:8080/realms/fred",
                    "client_id": "test-user",
                },
                "authorized_origins": [],
            },
            "ai": {"knowledge_flow_url": "http://localhost:8111/knowledge-flow/v1"},
            "observability": {
                "kpi": {
                    "log": {"enabled": True},
                    "prometheus": {"enabled": False},
                    "opensearch": {"enabled": False},
                }
            },
            "storage": {"postgres": {"sqlite_path": str(tmp_path / "runtime.sqlite3")}},
        }
    )
    # The pod refuses to start against an unmigrated database (#2290) —
    # create the Alembic-owned schema first, as the deploy migration job does.
    return migrate_test_config(config)


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------


def test_list_models_returns_registered_agents(monkeypatch, tmp_path) -> None:
    """
    GET /v1/models must return registered agents in OpenAI model-list format.

    Why this test exists:
    - Open WebUI calls /v1/models to populate the model selector; if this
      endpoint is absent or malformed the frontend cannot discover any agent
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="hi")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        response = client.get("/v1/models")

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "test.hello.v1"
    assert data["data"][0]["object"] == "model"
    assert data["data"][0]["owned_by"] == "fred"


def test_openai_compat_disabled_hides_v1_routes(monkeypatch, tmp_path) -> None:
    """
    When openai_compat is False, /v1/* must not exist.

    Why this test exists:
    - pods that explicitly opt out (e.g. internal workers) must not expose /v1
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="hi")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    config = _build_test_config(tmp_path, openai_compat=False)
    app = create_agent_app(registry=registry, config=config)

    with TestClient(app) as client:
        assert client.get("/v1/models").status_code == 404


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("model", [_HelloAgent().agent_id, "unknown"])
@pytest.mark.parametrize(
    "caller",
    [
        None,
        KeycloakUser(uid="alice", username="alice", roles=[]),
        KeycloakUser(uid="worker", username="worker", roles=["service_agent"]),
    ],
)
def test_direct_openai_execution_is_closed_without_weaver_authority(
    monkeypatch, stream, model, caller
):
    app = FastAPI()
    app.include_router(
        openai_compat_router_module.create_openai_compat_router(
            registry={_HelloAgent().agent_id: _HelloAgent()},
            security_enabled=True,
            max_chat_input_chars=5000,
            authenticated_user_dep=lambda: caller,
        ),
        prefix="/v1",
    )
    admit = Mock(side_effect=AssertionError("Unsupported route admitted a run"))
    iterate = Mock(side_effect=AssertionError("Unsupported route ran an agent"))
    monkeypatch.setattr(agent_app_module, "_admission_credentials", admit)
    monkeypatch.setattr(agent_app_module, "_iterate_runtime_event_payloads", iterate)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "hello"}],
                "stream": stream,
            },
        )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Direct-template OpenAI execution is not connected to Weaver authorization"
    }
    admit.assert_not_called()
    iterate.assert_not_called()


@pytest.mark.parametrize("status", [401, 403, 503])
def test_compatibility_route_preserves_authentication_refusal(status):
    from fastapi import HTTPException

    def refuse():
        raise HTTPException(status_code=status, detail="authentication_refused")

    app = FastAPI()
    app.include_router(
        openai_compat_router_module.create_openai_compat_router(
            registry={},
            security_enabled=True,
            max_chat_input_chars=5000,
            authenticated_user_dep=refuse,
        ),
        prefix="/v1",
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "unknown",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
    assert response.status_code == status
    assert response.json()["detail"] == "authentication_refused"
