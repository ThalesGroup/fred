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

"""Controller-level test: an agent save whose toolkit asset processor rejects the input
returns ``422`` with the shared ``{ "errors": [{slide, key, code, message}] }`` shape.

This pins the error->HTTP translation (the ``ToolkitAssetValidationError`` exception
handler) so it stays identical to the analyze endpoint's error contract. The full save
wiring (real KF storage, real persistence) is heavy to stand up here, so the processor
itself is unit-tested in ``test_ppt_filler_processor.py``; this test fakes the service and
asserts only the controller boundary.
"""

from types import SimpleNamespace

from fastapi import APIRouter, FastAPI, status
from fastapi.testclient import TestClient
from fred_core import KeycloakUser, get_current_user

from agentic_backend.core.agents import agent_controller
from agentic_backend.core.tools.toolkit_asset_processor import (
    TemplateErrorLike,
    ToolkitAssetValidationError,
)

_UPDATE_URL = "/agentic/v1/agents/update"
_HEADERS = {"Authorization": "Bearer dummy-token"}

# A minimal AgentSettings body the /agents/update route accepts.
_AGENT_BODY = {
    "id": "agent-123",
    "name": "Deck Agent",
    "enabled": True,
    "tuning": {"role": "decks", "description": "fills decks"},
}


def _build_client(monkeypatch) -> TestClient:
    app = FastAPI()
    # Register the real exception handlers so the typed error -> 422 mapping is exercised.
    agent_controller.register_exception_handlers(app)

    router = APIRouter(prefix="/agentic/v1")
    router.include_router(agent_controller.router)
    app.include_router(router)

    class _RejectingAgentService:
        def __init__(self, agent_manager):
            self.agent_manager = agent_manager

        async def update_agent(self, user, agent_settings, *, asset_store=None):
            raise ToolkitAssetValidationError(
                [
                    TemplateErrorLike(
                        slide=2,
                        key="age",
                        code="key_without_description",
                        message="{{age}} appears on slide 2 but has no description.",
                    )
                ]
            )

    monkeypatch.setattr(agent_controller, "AgentService", _RejectingAgentService)
    app.state.agent_manager = SimpleNamespace()
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="u-1", username="tester", email="t@example.com", roles=["user"]
    )
    return TestClient(app)


def test_save_with_invalid_template_returns_422_with_shared_error_shape(monkeypatch):
    client = _build_client(monkeypatch)

    response = client.put(_UPDATE_URL, headers=_HEADERS, json=_AGENT_BODY)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    body = response.json()
    # Same shape as the analyze endpoint: a top-level "errors" list of structured errors.
    assert set(body.keys()) == {"errors"}
    assert body["errors"]
    for err in body["errors"]:
        assert set(err.keys()) == {"slide", "key", "code", "message"}
    assert body["errors"][0]["code"] == "key_without_description"
    assert body["errors"][0]["slide"] == 2
    assert body["errors"][0]["key"] == "age"
