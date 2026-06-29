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

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_runtime.app import agent_app as agent_app_module
from fred_sdk import load_agent_prompt_markdown
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


class RecordingStaticChatModelFactory(StaticChatModelFactory):
    """
    Test chat-model factory that records requested operation labels.

    Why this helper exists:
    - the graph test assistant now includes an optional model-probe scenario
      that should exercise operation-aware routing without needing a live model

    How to use it:
    - construct with one deterministic fake model
    - inspect `requested_operations` after the streamed turn completes

    Example:
    - `factory = RecordingStaticChatModelFactory(model)`
    """

    def __init__(self, model: ToolFriendlyFakeChatModel) -> None:
        super().__init__(model)
        self.requested_operations: list[str | None] = []

    def build_for_operation(
        self, *, definition, binding, purpose: str, operation: str | None
    ):
        self.requested_operations.append(operation)
        return super().build_for_operation(
            definition=definition,
            binding=binding,
            purpose=purpose,
            operation=operation,
        )


def _build_offline_agents_app(monkeypatch, tmp_path, factory) -> FastAPI:
    """
    Build the fred-agents pod app with an offline MCP catalog and fake model factory.

    Why this helper exists:
    - the smoke tests need the same fully offline pod wiring multiple times
      without duplicating environment and monkeypatch setup

    How to use it:
    - pass the pytest `monkeypatch`, a temporary directory, and a test chat
      model factory
    - returns the fully initialized FastAPI app

    Example:
    - `app = _build_offline_agents_app(monkeypatch, tmp_path, factory)`
    """

    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: factory,
    )
    config_file = Path(__file__).resolve().parents[1] / "config" / "configuration.yaml"
    offline_mcp_catalog = tmp_path / "mcp_catalog.yaml"
    offline_mcp_catalog.write_text("version: v1\nservers: []\n", encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(offline_mcp_catalog))

    from fred_agents.main import create_app

    return create_app()


def _parse_sse_payloads(stream_text: str) -> list[dict[str, object]]:
    """
    Parse SSE `data:` lines from one streamed runtime response.

    Why this helper exists:
    - several smoke tests need the final runtime events without repeating the
      same JSON extraction logic inline

    How to use it:
    - pass `response.text` from a streaming execute call
    - returns the decoded JSON payloads in stream order

    Example:
    - `payloads = _parse_sse_payloads(stream_response.text)`
    """

    return [
        json.loads(line.removeprefix("data: "))
        for line in stream_text.splitlines()
        if line.startswith("data: ")
    ]


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
    app = _build_offline_agents_app(
        monkeypatch,
        tmp_path,
        StaticChatModelFactory(model),
    )

    with TestClient(app) as client:
        assert client.get("/api/v1/agents").status_code == 404

        list_response = client.get("/fred/agents/v2/agents")
        assert list_response.status_code == 200
        registered = list_response.json()
        assert "fred.github.sentinel" in registered
        assert "fred.github.rag_expert" in registered
        assert "fred.dt.mindmap.graph" in registered

        templates_response = client.get("/fred/agents/v2/agents/templates")
        assert templates_response.status_code == 200
        template_ids = {
            template["template_agent_id"] for template in templates_response.json()
        }
        assert "fred.dt.mindmap.graph" in template_ids
        assert "fred.github.sentinel" in template_ids
        assert "fred.github.rag_expert" in template_ids
        assert "fred.github.test_assistant" in template_ids

        test_assistant_template = next(
            template
            for template in templates_response.json()
            if template["template_agent_id"] == "fred.github.test_assistant"
        )
        field_keys = {
            field["key"]
            for field in test_assistant_template["default_tuning"]["fields"]
        }
        assert {
            # prompt type
            "prompts.system",
            "prompts.planning",
            "prompts.routing",
            # boolean + integer (existing)
            "settings.verbose",
            "settings.delay_ms",
            # new scalar types
            "settings.greeting",  # string
            "settings.language",  # select
            "settings.timeout_s",  # number
            "settings.notes",  # text-multiline
            "settings.tags",  # array
            # credentials
            "credentials.api_key",  # secret
            "credentials.webhook_url",  # url
        }.issubset(field_keys)

        general_assistant_template = next(
            template
            for template in templates_response.json()
            if template["template_agent_id"] == "fred.github.assistant"
        )
        general_assistant_field_keys = {
            field["key"]
            for field in general_assistant_template["default_tuning"]["fields"]
        }
        # chat_options.attach_files is no longer an agent-level field — it now lives in
        # the MCP catalog (search-documents server) per MCP-CATALOG-CONFIG-FIELDS-RFC §10.
        assert "chat_options.attach_files" not in general_assistant_field_keys

        react_rag_mcp_template = next(
            template
            for template in templates_response.json()
            if template["template_agent_id"] == "fred.github.react_rag_mcp"
        )
        react_rag_mcp_field_keys = {
            field["key"] for field in react_rag_mcp_template["default_tuning"]["fields"]
        }
        # Migrated to the MCP catalog (search-documents server), see
        # MCP-CATALOG-CONFIG-FIELDS-RFC §10 — no longer an agent-level field.
        assert "chat_options.attach_files" not in react_rag_mcp_field_keys

        stream_response = client.post(
            "/fred/agents/v2/agents/execute/stream",
            json={
                "agent_id": "fred.github.sentinel",
                "input": "Give me a short health summary.",
                "session_id": "sentinel-session",
                "runtime_context": {"user_id": "sentinel-user"},
            },
        )
        assert stream_response.status_code == 200

    payloads = _parse_sse_payloads(stream_response.text)
    assert payloads
    assert not any("error" in payload for payload in payloads)
    assert payloads[-1]["kind"] == "final"
    assert payloads[-1]["content"] == "Sentinel is ready."


def test_fred_test_assistant_echo_stays_off_model_routing_path(
    monkeypatch, tmp_path
) -> None:
    """
    Verify the no-LLM test-assistant scenarios do not request operation routing.

    Why this test exists:
    - the test assistant should remain safe for offline UI work even when the
      pod has a model factory configured
    - only the explicit model-probe scenario should touch operation-aware model
      routing

    How to use it:
    - run via `make test` from the `fred-agents` project

    Example:
    - `pytest tests/test_smoke.py -q`
    """

    factory = RecordingStaticChatModelFactory(
        ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    )
    app = _build_offline_agents_app(monkeypatch, tmp_path, factory)

    with TestClient(app) as client:
        stream_response = client.post(
            "/fred/agents/v2/agents/execute/stream",
            json={
                "agent_id": "fred.github.test_assistant",
                "input": "echo hello from smoke test",
                "session_id": "test-assistant-echo",
                "runtime_context": {"user_id": "test-user"},
            },
        )
        assert stream_response.status_code == 200

    payloads = _parse_sse_payloads(stream_response.text)
    assert payloads
    assert payloads[-1]["kind"] == "final"
    assert "Echo: echo hello from smoke test" in str(payloads[-1]["content"])
    assert factory.requested_operations == []


def test_fred_test_assistant_model_probe_uses_operation_aware_routing(
    monkeypatch, tmp_path
) -> None:
    """
    Verify the optional model-probe scenario requests an explicit routing operation.

    Why this test exists:
    - the test assistant should double as a deterministic exerciser for graph
      operation-aware model routing when a fake or real model is available

    How to use it:
    - run via `make test` from the `fred-agents` project

    Example:
    - `pytest tests/test_smoke.py -q`
    """

    factory = RecordingStaticChatModelFactory(
        ToolFriendlyFakeChatModel(
            responses=[AIMessage(content="Routing probe model response.")]
        )
    )
    app = _build_offline_agents_app(monkeypatch, tmp_path, factory)

    with TestClient(app) as client:
        stream_response = client.post(
            "/fred/agents/v2/agents/execute/stream",
            json={
                "agent_id": "fred.github.test_assistant",
                "input": "model routing explain the selection",
                "session_id": "test-assistant-model-routing",
                "runtime_context": {"user_id": "test-user"},
            },
        )
        assert stream_response.status_code == 200

    payloads = _parse_sse_payloads(stream_response.text)
    assert payloads
    assert payloads[-1]["kind"] == "final"
    assert "operation **`routing`**" in str(payloads[-1]["content"])
    assert "Routing probe model response." in str(payloads[-1]["content"])
    assert "routing" in factory.requested_operations


def test_mindmap_prompt_files_load_from_packaged_module() -> None:
    """
    Verify packaged mindmap prompts resolve through the shipped module path.

    Why this test exists:
    - the graph steps load prompt markdown dynamically from the package name
    - a stale package reference breaks the agent at runtime even when imports succeed

    How to use it:
    - run via `make test` from the `fred-agents` project

    Example:
    - `pytest tests/test_smoke.py -q`
    """

    for prompt_name in (
        "extract_mindmap.md",
        "refine_mindmap.md",
        "render_response.md",
    ):
        prompt = load_agent_prompt_markdown(
            package="fred_agents.mindmap",
            file_name=prompt_name,
        )
        assert prompt.strip()


def test_non_public_agent_is_hidden_and_not_directly_executable(monkeypatch, tmp_path):
    """The self-test agent is `public=False` (AGENT-VISIBILITY-RFC): hidden from the
    default template catalog, discoverable only with include_non_public, and NOT
    executable through the bare-agent_id (no-grant) path — that is the runtime-side
    enforcement of the visibility boundary."""
    model = ToolFriendlyFakeChatModel(responses=[AIMessage(content="unused")])
    app = _build_offline_agents_app(
        monkeypatch, tmp_path, StaticChatModelFactory(model)
    )

    with TestClient(app) as client:
        default_ids = {
            t["template_agent_id"]
            for t in client.get("/fred/agents/v2/agents/templates").json()
        }
        assert "fred.github.self_test" not in default_ids

        all_ids = {
            t["template_agent_id"]
            for t in client.get(
                "/fred/agents/v2/agents/templates?include_non_public=true"
            ).json()
        }
        assert "fred.github.self_test" in all_ids

        # Direct, grant-less execution of a non-public agent must be refused (404).
        resp = client.post(
            "/fred/agents/v2/agents/execute/stream",
            json={
                "agent_id": "fred.github.self_test",
                "input": "hi",
                "session_id": "s",
                "runtime_context": {"user_id": "u"},
            },
        )
        assert resp.status_code == 404
