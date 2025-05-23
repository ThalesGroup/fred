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

import json
import pytest
from fastapi.testclient import TestClient
from fastapi import APIRouter, FastAPI

from fred.application_context import ApplicationContext
from chatbot.chatbot_controller import ChatbotController
from common.utils import parse_server_configuration
from services.ai.ai_service import AIService
from services.kube.kube_service import KubeService


@pytest.fixture(scope="module")
def test_app():
    """
    Fixture to create a FastAPI test client for the chatbot controller.
    This fixture sets up the FastAPI application and includes the necessary
    routers and controllers for testing.
    """

    config = parse_server_configuration("./config/configuration.yaml")
    ApplicationContext(config)

    kube_service = KubeService()
    ai_service = AIService(kube_service)
    app = FastAPI()
    router = APIRouter(prefix="/fred")

    ChatbotController(router, ai_service)
    app.include_router(router)
    return TestClient(app)


def test_post_streaming_query(test_app):
    """
    Test the POST endpoint for streaming responses.
    This endpoint is the preferred way to get streaming responses.
    """
    # Send a POST request to the streaming endpoint
    payload = {
        "session_id": None,
        "user_id": "mock@user.com",
        "message": "Qui est shakespeare ?",
        "agent_name": "GeneralistExpert"
    }

    headers = {
        "Authorization": "Bearer dummy-token"
    }

    response = test_app.post("/fred/chatbot/query/stream", json=payload, headers=headers)

    assert response.status_code == 200

    chunks = []
    for line in response.iter_lines():
        line = line.strip()
        if line:
            print(line)
            try:
                data = json.loads(line)
                chunks.append(data)
            except json.JSONDecodeError:
                assert False, f"Invalid JSON line: {line}"


def test_post_single_query(test_app):
    """
    Test the POST endpoint for a single query.
    This endpoint is used for non-streaming responses. It is great for
    testing the chatbot.
    """
    payload = {
        "session_id": None,
        "user_id": "mock@user.com",
        "message": "Qui est shakespeare ?",
        "agent_name": "GeneralistExpert"
    }

    headers = {
        "Authorization": "Bearer dummy-token"
    }

    response = test_app.post("/fred/chatbot/query", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "session" in data
    assert "messages" in data
    assert "type" in data

def test_get_agentic_flows(test_app):
    """
    Test the GET endpoint for listing agentic flows.
    This endpoint retrieves all available agentic flows. 
    """
    headers = {
        "Authorization": "Bearer dummy-token"
    }

    response = test_app.get("/fred/chatbot/agenticflows", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert all("name" in flow for flow in data)
    assert any(flow["name"] == "fred" or flow["name"] == "Fred" for flow in data)
