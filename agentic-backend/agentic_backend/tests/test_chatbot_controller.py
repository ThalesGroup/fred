# Copyright Thales 2025
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

# agentic_backend/tests/controllers/test_chatbot_controller.py

from typing import cast

from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, get_current_user

from agentic_backend.common.structures import Agent
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec


class TestChatbotController:
    base_payload = {
        "session_id": None,
        "user_id": "mock@user.com",
        "message": "Qui est shakespeare ?",
        "agent_id": "basic.react.v2",
        "argument": "none",
    }

    headers = {"Authorization": "Bearer dummy-token"}

    def test_list_agents(self, client: TestClient):
        response = client.get("/agentic/v1/agents", headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        flows = response.json()
        assert isinstance(flows, list)
        assert all("name" in flow for flow in flows)

    def test_inspect_v2_agent_returns_structured_inspection(
        self, client: TestClient, app_context
    ):
        v2_agent = Agent(
            id="basic-v2-inspect",
            name="Basic ReAct V2 Inspect",
            class_path="agentic_backend.agents.v2.production.basic_react.BasicReActDefinition",
            enabled=True,
            tuning=AgentTuning(
                role="assistant",
                description="A basic ReAct agent for testing",
                # BasicReActDefinition has no default prompt, so we have to define one
                fields=[
                    FieldSpec(
                        key="prompts.system",
                        type="prompt",
                        title="System Prompt",
                        default="You are a helpful assistant.",
                    )
                ],
            ),
        )
        app_context.configuration.ai.agents.append(v2_agent)
        try:
            response = client.get(
                "/agentic/v1/agents/basic-v2-inspect/inspect", headers=self.headers
            )
        finally:
            app_context.configuration.ai.agents.pop()

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["agent_id"] == "basic-v2-inspect"
        assert payload["execution_category"] == "react"
        assert payload["preview"]["kind"] == "text"
        assert "ReAct runtime" in payload["preview"]["content"]

    def test_inspect_default_v2_agent_returns_structured_inspection(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/agentic/v1/agents/basic.react.v2/inspect", headers=self.headers
        )

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["agent_id"] == "basic.react.v2"
        assert payload["execution_category"] == "react"

    def test_get_team_model_routing_config_requires_admin_role(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/agentic/v1/config/model-routing/teams/team-alpha", headers=self.headers
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "admin privileges" in response.json()["detail"]

    def test_get_team_model_routing_config_returns_team_scoped_preview(
        self, client: TestClient, monkeypatch, tmp_path, app_context
    ) -> None:
        catalog_file = tmp_path / "models_catalog.yaml"
        catalog_file.write_text(
            """
version: v1
common_model_settings:
  temperature: 0.0
default_profile_by_capability:
  chat: chat.openai.gpt5
profiles:
  - profile_id: chat.openai.gpt5
    capability: chat
    model:
      provider: openai
      name: gpt-5
      settings: {}
  - profile_id: chat.openai.gpt5mini
    capability: chat
    model:
      provider: openai
      name: gpt-5-mini
      settings: {}
rules:
  - rule_id: react.phase.routing.fast
    capability: chat
    operation: routing
    target_profile_id: chat.openai.gpt5mini
  - rule_id: react.phase.planning.team_alpha
    capability: chat
    operation: planning
    team_id: team-alpha
    target_profile_id: chat.openai.gpt5
  - rule_id: react.phase.planning.team_beta
    capability: chat
    operation: planning
    team_id: team-beta
    target_profile_id: chat.openai.gpt5
""".strip(),
            encoding="utf-8",
        )
        monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(catalog_file))
        previous_catalog_mode = app_context.configuration.ai.enable_catalog_mode
        app_context.configuration.ai.enable_catalog_mode = True
        cast(FastAPI, client.app).dependency_overrides[get_current_user] = lambda: (
            KeycloakUser(
                uid="admin-1",
                username="admin",
                email="admin@example.com",
                roles=["admin"],
            )
        )
        try:
            response = client.get(
                "/agentic/v1/config/model-routing/teams/team-alpha",
                headers=self.headers,
            )

            assert response.status_code == status.HTTP_200_OK
            payload = response.json()
            assert payload["team_id"] == "team-alpha"
            assert payload["catalog_exists"] is True
            assert (
                payload["default_profile_by_capability"]["chat"] == "chat.openai.gpt5"
            )

            rule_ids = [rule["rule_id"] for rule in payload["rules"]]
            assert rule_ids == [
                "react.phase.routing.fast",
                "react.phase.planning.team_alpha",
            ]
            assert payload["rules"][0]["scope"] == "global"
            assert payload["rules"][1]["scope"] == "team"
        finally:
            app_context.configuration.ai.enable_catalog_mode = previous_catalog_mode
