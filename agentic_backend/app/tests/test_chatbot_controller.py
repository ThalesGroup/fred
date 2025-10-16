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

# app/tests/controllers/test_chatbot_controller.py

from fastapi import status
from fastapi.testclient import TestClient


class TestChatbotController:
    base_payload = {
        "session_id": None,
        "user_id": "mock@user.com",
        "message": "Qui est shakespeare ?",
        "agent_name": "Georges",
        "argument": "none",
    }

    headers = {"Authorization": "Bearer dummy-token"}

    def test_get_agentic_flows(self, client: TestClient):
        response = client.get("/agentic/v1/chatbot/agenticflows", headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        flows = response.json()
        assert isinstance(flows, list)
        assert all("name" in flow for flow in flows)
        assert any(flow["name"].lower() == "fred" for flow in flows)
