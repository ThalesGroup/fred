from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from fred_runtime.app import agent_app as agent_app_module
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


class ToolFriendlyFakeChatModel(FakeMessagesListChatModel):
    """
    Deterministic fake model that supports ReAct runtime tool binding in tests.

    Why this helper exists:
    - the stock fake chat model does not implement `bind_tools(...)`
    - the standalone pod smoke test must stay fully offline for default
      `make test`

    How to use it:
    - provide the exact scripted `AIMessage` sequence the runtime should
      consume

    Example:
    - `ToolFriendlyFakeChatModel(responses=[AIMessage(content="done")])`
    """

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self


class StaticChatModelFactory:
    """
    Minimal chat-model factory used by the standalone pod smoke test.

    Why this helper exists:
    - the pod runtime expects a `chat_model_factory`
    - this test should validate app wiring without calling a real LLM service

    How to use it:
    - monkeypatch `fred_runtime.app.agent_app._build_chat_model_factory`
    - return the same scripted fake model for the whole turn

    Example:
    - `factory = StaticChatModelFactory(model)`
    """

    def __init__(self, model: ToolFriendlyFakeChatModel) -> None:
        self._model = model

    def build(self, definition, binding):  # type: ignore[override]
        return self._model

    def build_for_operation(
        self, *, definition, binding, purpose: str, operation: str | None
    ):
        """
        Return the same fake model for operation-specific runtime routing.

        Why this function exists:
        - the ReAct runtime may request an operation-specific model before
          falling back to `build(...)`

        How to use it:
        - this smoke test returns the same deterministic fake model each time

        Example:
        - `factory.build_for_operation(definition=definition, binding=binding, purpose="react", operation="reasoner")`
        """

        return self.build(definition, binding)


def test_fred_agents_pod_registers_and_streams_sentinel_offline(
    monkeypatch, tmp_path
) -> None:
    """
    Verify the standalone pod exposes Sentinel through the reusable app factory.

    Why this test exists:
    - it validates that a plain exported `ReActAgentDefinition` is enough for
      `create_agent_app(...)`
    - it keeps the pod's default validation fully offline while still
      exercising the real FastAPI and streaming path

    How to use it:
    - run via `make test` from the `fred-agents` project

    Example:
    - `pytest tests/test_smoke.py -q`
    """

    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="Sentinel is ready.")]
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: StaticChatModelFactory(model),
    )
    config_file = Path(__file__).resolve().parents[1] / "config" / "configuration.yaml"
    offline_mcp_catalog = tmp_path / "mcp_catalog.yaml"
    offline_mcp_catalog.write_text("version: v1\nservers: []\n", encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(offline_mcp_catalog))

    from fred_agents.main import create_app

    app = create_app()

    with TestClient(app) as client:
        assert client.get("/api/v1/agents").status_code == 404

        list_response = client.get("/fred/agents/v2/agents")
        assert list_response.status_code == 200
        assert list_response.json() == [
            "sentinel.react.v2",
            "rag_expert.react.v2",
        ]

        templates_response = client.get("/fred/agents/v2/agents/templates")
        assert templates_response.status_code == 200
        assert {
            template["template_agent_id"] for template in templates_response.json()
        } == {"sentinel.react.v2", "rag_expert.react.v2"}

        stream_response = client.post(
            "/fred/agents/v2/agents/execute/stream",
            json={
                "agent_id": "sentinel.react.v2",
                "message": "Give me a short health summary.",
                "context": {
                    "session_id": "sentinel-session",
                    "user_id": "sentinel-user",
                },
            },
        )
        assert stream_response.status_code == 200

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in stream_response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert payloads
    assert not any("error" in payload for payload in payloads)
    assert payloads[-1]["kind"] == "final"
    assert payloads[-1]["content"] == "Sentinel is ready."
