# app/tests/controllers/test_chatbot_controller.py

from fastapi import status
from fastapi.testclient import TestClient


class TestChatbotController:
    base_payload = {
        "session_id": None,
        "user_id": "mock@user.com",
        "message": "Qui est shakespeare ?",
        "agent_name": "GeneralistExpert",
        "argument": "none"
    }

    headers = {
        "Authorization": "Bearer dummy-token"
    }

    def test_get_agentic_flows(self, client: TestClient):
        response = client.get("/agentic/v1/chatbot/agenticflows", headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        flows = response.json()
        assert isinstance(flows, list)
        assert all("name" in flow for flow in flows)
        assert any(flow["name"].lower() == "fred" for flow in flows)
