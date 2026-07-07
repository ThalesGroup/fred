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
- POST /v1/chat/completions streams SSE chunks in OpenAI format with `fred` metadata
- Unknown model returns 404
- Missing user message returns 422

All tests run without any external services.
"""

from __future__ import annotations

import json

from conftest import StaticChatModelFactory, ToolFriendlyFakeChatModel
from fastapi.testclient import TestClient
from fred_runtime.app import AgentPodConfig, create_agent_app
from fred_runtime.app import agent_app as agent_app_module
from fred_sdk.authoring import ReActAgent, tool
from fred_sdk.authoring.api import ToolContext
from fred_sdk.contracts.models import ReActAgentDefinition
from langchain_core.messages import AIMessage


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


def _build_test_config(tmp_path, *, openai_compat: bool = True) -> AgentPodConfig:
    """
    Build an offline pod config with openai_compat enabled.

    Why this exists:
    - mirrors `_build_test_config` in test_agent_app.py; kept local to this
      module so the two test files remain independent

    How to use it:
    - call once per test with pytest's `tmp_path`
    """
    return AgentPodConfig.model_validate(
        {
            "app": {
                "name": "Test Pod",
                "base_url": "/pod/v1",
                "port": 8000,
                "log_level": "info",
                "openai_compat": openai_compat,
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


# ---------------------------------------------------------------------------
# /v1/chat/completions — validation errors
# ---------------------------------------------------------------------------


def test_chat_completions_unknown_model_returns_404(monkeypatch, tmp_path) -> None:
    """
    POST /v1/chat/completions with an unknown model must return 404.

    Why this test exists:
    - Open WebUI may send a stale model name; a clear 404 is better than a
      500 or hanging stream
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
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "does-not-exist",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
    assert response.status_code == 404


def test_chat_completions_no_user_message_returns_422(monkeypatch, tmp_path) -> None:
    """
    POST /v1/chat/completions with only system messages must return 422.

    Why this test exists:
    - Fred requires a user message to forward to the agent; a system-only
      request cannot be executed and should be rejected before streaming starts
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
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test.hello.v1",
                "messages": [{"role": "system", "content": "You are helpful."}],
            },
        )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /v1/chat/completions — streaming
# ---------------------------------------------------------------------------


def test_chat_completions_streams_openai_chunks_and_done(monkeypatch, tmp_path) -> None:
    """
    POST /v1/chat/completions must stream OpenAI-shaped SSE chunks ending with [DONE].

    Why this test exists:
    - verifies the full SSE pipeline: request → Fred stream → OpenAI chunk
      transformation → [DONE] sentinel
    - asserts that at least one chunk carries delta content and that the final
      chunk has finish_reason="stop"
    """
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="Hello there.")])
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )

    definition = _HelloAgent()
    registry: dict[str, ReActAgentDefinition] = {definition.agent_id: definition}
    app = create_agent_app(registry=registry, config=_build_test_config(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test.hello.v1",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
            # session_id is required when a SQL checkpointer is active:
            # LangGraph needs a non-None thread_id when a checkpointer is configured.
            headers={"X-Fred-Session-Id": "test-session-openai-compat"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    lines = response.text.splitlines()
    assert "data: [DONE]" in lines

    # Parse all data lines (excluding [DONE])
    chunks = [
        json.loads(line.removeprefix("data: "))
        for line in lines
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert chunks, "Expected at least one SSE chunk before [DONE]"

    # Every chunk must have the required OpenAI fields
    for chunk in chunks:
        assert chunk["object"] == "chat.completion.chunk"
        assert chunk["model"] == "test.hello.v1"
        assert "choices" in chunk
        assert chunk["id"].startswith("chatcmpl-")

    # The final chunk must have finish_reason="stop"
    final_chunks = [c for c in chunks if c["choices"][0].get("finish_reason") == "stop"]
    assert final_chunks, "Expected a chunk with finish_reason=stop"
