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
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_core.security import oidc
from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider
from fred_core.security.delegation import DelegationConfig, preserved_delegation
from fred_core.security.rebac.authorization_binding import AuthorizationBinding
from fred_core.security.structure import KeycloakUser
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.common.kf_http_client import close_shared_kf_async_client
from fred_runtime.common.outbound_credentials import (
    DelegationRuntime,
    get_delegation_runtime,
    set_delegation_runtime,
)
from fred_runtime.model_routing.turn import current_turn
from fred_runtime.runtime_context import (
    get_runtime_context_or_none,
    set_runtime_context,
)
from fred_sdk import load_agent_prompt_markdown
from fred_sdk.contracts.weaver import WeaverRuntimeBinding
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage


@pytest.fixture(autouse=True)
def offline_pod_authorization(monkeypatch):
    """Smoke tests exercise shipped agents, with the startup authority mocked."""
    previous = get_runtime_context_or_none()
    previous_delegation = get_delegation_runtime()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", oidc.KEYCLOAK_ENABLED)

    async def prepare(container):
        security = container.configuration.security
        assert security is not None
        oidc.configure_token_security(security)
        oidc.initialize_user_security(security.user)
        await container.initialize_sql()
        return security.rebac, AuthorizationBinding("fred", "test-store", "test-model")

    engine = SimpleNamespace(enabled=False, get_client=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(agent_app_module, "prepare_authorization", prepare)
    monkeypatch.setattr(
        agent_app_module, "PublishedOpenFgaRebacEngine", lambda *a, **k: engine
    )
    with preserved_delegation():
        try:
            yield
        finally:
            close_shared_kf_async_client()
            set_runtime_context(previous)
            set_delegation_runtime(previous_delegation)


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
        current_turn().check_context(binding.runtime_context, definition.agent_id)
        return self._model


SPACE_ID = "00000000-0000-0000-0000-000000000002"
INSTANCE_ID = "00000000-0000-0000-0000-000000000003"


def _runtime_binding(request: httpx.Request, template_id: str) -> WeaverRuntimeBinding:
    """Trusted Control Plane facts for one offline instance and model offer."""
    from fred_agents.registry import REGISTRY

    tuning = agent_app_module._definition_to_agent_tuning(REGISTRY[template_id])
    org = "00000000-0000-0000-0000-000000000001"
    key = {"source_id": "offline", "upstream_model_id": "fake"}
    return WeaverRuntimeBinding.model_validate(
        {
            "subject_id": "smoke-user",
            "run_id": request.url.params["run"],
            "conversation_id": request.url.params["conversation"],
            "space": {
                "id": SPACE_ID,
                "kind": "team",
                "organization_id": org,
                "team_id": SPACE_ID,
                "project_id": None,
            },
            "agent": {
                "instance_id": INSTANCE_ID,
                "runtime_id": "fred-agents",
                "template_id": "00000000-0000-0000-0000-000000000004",
                "template_key": template_id,
                "configuration_updated_at": "2026-10-26T00:00:00Z",
                "configuration": tuning.model_dump(mode="json"),
            },
            "models": {
                "policy": {
                    "organization_id": org,
                    "revision": 1,
                    "permitted": [key],
                    "reasoning_enabled": [],
                    "default": key,
                    "fallback": None,
                    "created_by": None,
                    "created_at": None,
                    "updated_by": None,
                    "updated_at": None,
                },
                "recommendation": key,
                "options": {},
                "legacy_profile_id": None,
                "requires_reselection": False,
                "offers": [
                    {
                        "key": key,
                        "permitted": True,
                        "candidate": True,
                        "selectable": True,
                        "diagnostics": [],
                        "metadata": {
                            "chat": True,
                            "chat_provenance": "source_guarantee",
                            "display_name": None,
                            "context_window_tokens": None,
                            "max_input_tokens": None,
                            "max_output_tokens": None,
                        },
                        "observation": {
                            "source_id": "offline",
                            "source_revision": 1,
                            "enabled": True,
                            "state": "ok",
                            "error_code": None,
                            "checked_at": None,
                            "last_success_at": None,
                            "snapshot_revision": 1,
                            "snapshot_source_revision": 1,
                        },
                        "connection": {
                            "provider": "openai",
                            "api_root": "https://model.invalid/v1",
                            "credential_binding": "offline",
                        },
                    }
                ],
            },
        }
    )


def _build_offline_agents_app(
    monkeypatch, tmp_path, factory, *, template_id="fred.github.assistant"
) -> FastAPI:
    """Boot the shipped pod with fake identity, resolver HTTP, MCP and model I/O."""
    user = KeycloakUser(uid="smoke-user", username="smoke-user", roles=[])
    for dependency in ("_make_user_dependency", "_make_execution_dependency"):
        monkeypatch.setattr(agent_app_module, dependency, lambda *args: lambda: user)
    requests: list[httpx.Request] = []

    def resolve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert (
            request.url.path
            == f"/api/spaces/{SPACE_ID}/agent-instances/{INSTANCE_ID}/runtime"
        )
        assert request.headers["Authorization"] == "Bearer smoke-workload-token"
        assert request.url.params["person"] == user.uid
        assert request.url.params["agent"] == INSTANCE_ID
        return httpx.Response(
            200, json=_runtime_binding(request, template_id).model_dump(mode="json")
        )

    def initialize(container):
        container._control_plane_http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(resolve)
        )

    monkeypatch.setattr(
        PodApplicationContext, "initialize_control_plane_client", initialize
    )
    monkeypatch.setattr(
        agent_app_module,
        "_build_chat_model_factory",
        lambda config: factory,
    )
    # Load the pod's real configuration.yaml but redirect the SQLite fallback
    # path into `tmp_path`. Pointing CONFIG_FILE straight at the checked-in
    # file (as before) made every "offline" smoke test share
    # `~/.fred/fred-agents/runtime.sqlite3` with whatever `make run` dev pod
    # happens to be running on this machine (any checkout, since the path is
    # under `~`, not the repo) — SQLite has no busy-timeout/WAL here, so a
    # concurrent writer intermittently trips "database is locked" and the
    # turn surfaces as an unhandled execution error instead of `final`.
    real_config_file = (
        Path(__file__).resolve().parents[1] / "config" / "configuration.yaml"
    )
    config_payload = yaml.safe_load(real_config_file.read_text(encoding="utf-8"))
    config_payload["storage"]["postgres"]["sqlite_path"] = str(
        tmp_path / "runtime.sqlite3"
    )
    config_payload["platform"]["control_plane_url"] = "https://control.invalid/api"
    config_file = tmp_path / "configuration.yaml"
    config_file.write_text(yaml.safe_dump(config_payload), encoding="utf-8")

    offline_mcp_catalog = tmp_path / "mcp_catalog.yaml"
    offline_mcp_catalog.write_text(
        # Every id any registered template names in `default_mcp_servers` must
        # be at least KNOWN to this pod at boot, or boot now fails loudly
        # (RFC §2) instead of letting the id disappear silently the first
        # time a request lists templates. `enabled: false` keeps them in the
        # already-documented tolerated-disabled state (warning-only — the
        # live tool provider skips them at assembly, never a live MCP
        # connection this offline pod has no server to answer).
        "version: v1\n"
        "servers:\n"
        '  - id: "mcp-knowledge-flow-mcp-tabular"\n'
        '    name: "mcp.servers.tabular.name"\n'
        "    enabled: false\n"
        '  - id: "mcp-knowledge-flow-prometheus-ops"\n'
        '    name: "mcp.servers.prometheus.name"\n'
        "    enabled: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(offline_mcp_catalog))

    from fred_agents.main import create_app
    from fred_runtime.app.config_loader import load_agent_pod_config
    from fred_runtime.migrations import upgrade_sqlite_database

    # The pod refuses to start against an unmigrated database (#2290) — stores no
    # longer create their own tables. Apply the real Alembic tree to the shipped
    # config's SQLite file, which is what the deploy migration job
    # (`python -m fred_runtime migrate`) does.
    sqlite_path = load_agent_pod_config().storage.postgres.sqlite_path
    if sqlite_path:
        upgrade_sqlite_database(sqlite_path)

    app = create_app()
    monkeypatch.setenv("FRED_SMOKE_WORKLOAD_SECRET", "synthetic")
    tokens = M2MTokenProvider(
        M2MAuthConfig(
            keycloak_realm_url="https://iam.invalid/realms/test",
            client_id="smoke-workload",
            secret_env="FRED_SMOKE_WORKLOAD_SECRET",  # pragma: allowlist secret - environment variable name only
        ),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"access_token": "smoke-workload-token", "expires_in": 300}
            )
        ),
    )
    set_delegation_runtime(
        DelegationRuntime(
            config=DelegationConfig(act_for_people=True), token_provider=tokens
        )
    )
    app.state.resolver_requests = requests
    return app


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


def test_fred_agents_pod_registers_and_streams_custom_assistant_offline(
    monkeypatch, tmp_path
) -> None:
    """
    Verify the standalone pod exposes Custom assistant through the reusable app factory.

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
        responses=[AIMessage(content="Custom assistant is ready.")]
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
        assert "fred.github.assistant" in registered
        assert "fred.github.rag_expert" in registered
        assert "fred.dt.mindmap.graph" in registered

        templates_response = client.get("/fred/agents/v2/agents/templates")
        assert templates_response.status_code == 200
        template_ids = {
            template["template_agent_id"] for template in templates_response.json()
        }
        assert "fred.dt.mindmap.graph" in template_ids
        assert "fred.github.assistant" in template_ids
        assert "fred.github.rag_expert" in template_ids
        assert "fred.github.test_assistant" in template_ids

        test_assistant_template = next(
            template
            for template in templates_response.json()
            if template["template_agent_id"] == "fred.github.test_assistant"
        )
        assert test_assistant_template["supports_capabilities"] is True
        assert "document_access" in {
            capability["id"]
            for capability in test_assistant_template["available_capabilities"]
        }
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
                "agent_instance_id": INSTANCE_ID,
                "input": "Say hello.",
                "session_id": "custom-assistant-session",
                "runtime_context": {"space_id": SPACE_ID, "team_id": SPACE_ID},
            },
        )
        assert stream_response.status_code == 200, stream_response.text
        assert len(app.state.resolver_requests) == 1

    payloads = _parse_sse_payloads(stream_response.text)
    assert payloads
    assert not any("error" in payload for payload in payloads)
    assert payloads[-1]["kind"] == "final"
    assert payloads[-1]["content"] == "Custom assistant is ready."


def test_fred_agents_pod_streams_deep_assistant_offline(monkeypatch, tmp_path) -> None:
    """
    Verify the standalone pod actually runs `fred.github.deep_assistant` end to
    end through the real `deepagents.create_deep_agent` graph.

    Why this test exists:
    - `DeepAgentRuntime` existed for months with no `DeepAgentDefinition`
      registered anywhere, so nothing had ever exercised it through a real
      app boot + the real `deepagents` graph (unit tests elsewhere stub
      `_create_compiled_deep_agent` itself). This is the first agent to do
      so, so this smoke test is the actual proof it works, not just that it
      imports.

    How to use it:
    - run via `make test` from the `fred-agents` project

    Example:
    - `pytest tests/test_smoke.py -q`
    """

    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="Deep assistant is ready.")]
    )
    app = _build_offline_agents_app(
        monkeypatch,
        tmp_path,
        StaticChatModelFactory(model),
        template_id="fred.github.deep_assistant",
    )

    with TestClient(app) as client:
        registered = client.get("/fred/agents/v2/agents").json()
        assert "fred.github.deep_assistant" in registered

        templates_response = client.get("/fred/agents/v2/agents/templates")
        template_ids = {
            template["template_agent_id"] for template in templates_response.json()
        }
        assert "fred.github.deep_assistant" in template_ids

        stream_response = client.post(
            "/fred/agents/v2/agents/execute/stream",
            json={
                "agent_instance_id": INSTANCE_ID,
                "input": "Say hello.",
                "session_id": "deep-assistant-session",
                "runtime_context": {"space_id": SPACE_ID, "team_id": SPACE_ID},
            },
        )
        assert stream_response.status_code == 200, stream_response.text
        assert len(app.state.resolver_requests) == 1

    payloads = _parse_sse_payloads(stream_response.text)
    assert payloads
    assert not any("error" in payload for payload in payloads)
    assert payloads[-1]["kind"] == "final"
    assert payloads[-1]["content"] == "Deep assistant is ready."


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


def test_non_public_agent_is_hidden_unless_explicitly_requested(monkeypatch, tmp_path):
    """The shipped self-test template stays out of the default public catalog."""
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
