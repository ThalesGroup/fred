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

from fastapi import status
from fastapi.testclient import TestClient

from agentic_backend.common.structures import Agent


class TestChatbotController:
    base_payload = {
        "session_id": None,
        "user_id": "mock@user.com",
        "message": "Qui est shakespeare ?",
        "agent_id": "Georges",
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
            class_path="agentic_backend.agents.v2.basic_react.BasicReActV2Definition",
            enabled=True,
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

    def test_inspect_legacy_agent_is_rejected(self, client: TestClient) -> None:
        response = client.get(
            "/agentic/v1/agents/Georges/inspect", headers=self.headers
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "only supported for v2" in response.json()["detail"]
