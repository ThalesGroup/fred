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

import base64
import json
from urllib.parse import parse_qsl

import httpx

from fred_runtime.client import (
    AgentPodClient,
    KeycloakLoginConfig,
    KeycloakUserSessionManager,
    build_cli_token_provider,
    build_hitl_resume_payload,
    build_parser,
    completion_candidates,
    default_agent_metrics_url,
    default_agent_pod_base_url,
    default_keycloak_token_file,
    execution_mode_label,
    load_cli_environment,
    normalize_base_url,
    parse_mode_command,
    parse_prometheus_text_exposition,
    render_kpi_report,
    resolve_keycloak_login_config,
    run_single_turn,
    summarize_prometheus_histograms,
)


def test_default_agent_pod_base_url_normalizes_env_override(monkeypatch) -> None:
    """
    Verify the chat client honors and normalizes the base URL env override.

    Why this test exists:
    - developers often want one persistent pod URL without passing CLI flags
    - the default helper should trim trailing slashes predictably

    How to use it:
    - run as part of the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    monkeypatch.setenv("FRED_AGENT_POD_URL", "http://localhost:9999/fred/agents/v2/")

    assert default_agent_pod_base_url() == "http://localhost:9999/fred/agents/v2"


def test_default_agent_metrics_url_honors_env_override(monkeypatch) -> None:
    """
    Verify the CLI honors an explicit metrics URL override.

    Why this test exists:
    - `/kpi` should stay usable against forwarded or remote pods whose metrics
      endpoint is not discoverable from the local config file alone

    How to use it:
    - run as part of the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    monkeypatch.setenv("FRED_AGENT_METRICS_URL", "http://localhost:9115/metrics/")

    assert default_agent_metrics_url() == "http://localhost:9115/metrics"


def test_default_keycloak_token_file_honors_env_override(monkeypatch) -> None:
    """
    Verify the client can override the local token-cache file path.

    Why this test exists:
    - developers may want a separate cache file per environment while testing
      multiple secured pods

    How to use it:
    - run with the offline `fred-runtime` test suite
    """

    monkeypatch.setenv("FRED_AGENT_TOKEN_FILE", "/tmp/fred-agent-token.json")

    assert str(default_keycloak_token_file()) == "/tmp/fred-agent-token.json"


def test_resolve_keycloak_login_config_reads_pod_configuration(tmp_path) -> None:
    """
    Verify the client can auto-discover Keycloak settings from pod config.

    Why this test exists:
    - developers should not have to duplicate realm and client settings when
      the pod project already declares them in `configuration.yaml`

    How to use it:
    - run with the offline `fred-runtime` test suite
    """

    config_file = tmp_path / "configuration.yaml"
    config_file.write_text(
        """
app:
  name: "Test Pod"
security:
  m2m:
    enabled: false
    realm_url: "http://localhost:8080/realms/fred"
    client_id: "m2m-client"
  user:
    enabled: true
    realm_url: "http://localhost:8080/realms/fred"
    client_id: "fred-ui"
  authorized_origins: []
ai:
  knowledge_flow_url: "http://localhost:8111/knowledge-flow/v1"
storage:
  postgres:
    sqlite_path: "./runtime.sqlite3"
scheduler:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    config = resolve_keycloak_login_config(
        realm_url=None,
        client_id=None,
        client_secret=None,
        config_file=config_file,
    )

    assert config is not None
    assert config.realm_url == "http://localhost:8080/realms/fred"
    assert config.client_id == "fred-ui"


def test_default_agent_metrics_url_reads_pod_configuration(
    tmp_path, monkeypatch
) -> None:
    """
    Verify the CLI derives the metrics scrape URL from pod configuration.

    Why this test exists:
    - `/kpi` should follow the same pod config as the runtime and rewrite
      wildcard bind addresses into a curlable host

    How to use it:
    - run with the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    config_file = tmp_path / "configuration.yaml"
    config_file.write_text(
        """
app:
  name: "Test Pod"
  metrics_address: "0.0.0.0"
  metrics_port: 9115
security:
  user:
    enabled: false
ai:
  knowledge_flow_url: "http://localhost:8111/knowledge-flow/v1"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.delenv("FRED_AGENT_METRICS_URL", raising=False)
    monkeypatch.setenv("CONFIG_FILE", str(config_file))

    assert (
        default_agent_metrics_url(base_url="http://127.0.0.1:8000/pod/v1")
        == "http://127.0.0.1:9115/metrics"
    )


def test_cli_environment_loads_config_file_selection_from_env_file(
    tmp_path, monkeypatch
) -> None:
    """
    Verify the CLI honors the same ENV_FILE -> CONFIG_FILE chain as the pod.

    Why this test exists:
    - developers expect `fred-agents-cli` to target the same YAML profile as
      the agent pod without exporting extra shell variables manually

    How to use it:
    - run with the offline `fred-runtime` test suite
    """

    prod_config = tmp_path / "configuration_prod.yaml"
    prod_config.write_text(
        """
security:
  user:
    enabled: true
    realm_url: "http://localhost:8080/realms/app"
    client_id: "app"
""".strip(),
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        f'CONFIG_FILE="{prod_config}"\n',
        encoding="utf-8",
    )

    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.delenv("FRED_AGENT_KEYCLOAK_REALM_URL", raising=False)
    monkeypatch.delenv("FRED_AGENT_KEYCLOAK_CLIENT_ID", raising=False)

    load_cli_environment(str(env_file))
    config = resolve_keycloak_login_config(
        realm_url=None,
        client_id=None,
        client_secret=None,
        config_file=None,
    )

    assert config is not None
    assert config.realm_url == "http://localhost:8080/realms/app"
    assert config.client_id == "app"


def test_completion_candidates_support_agent_switching() -> None:
    """
    Verify tab completion suggests known agent ids for the switch command.

    Why this test exists:
    - the interactive client should make frequent agent switching easy
    - the completion helper should stay independent from readline state

    How to use it:
    - run with the normal unit test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    assert completion_candidates(
        "/agent sent",
        agent_ids=("sentinel.react.v2", "graph.demo.v1"),
    ) == ["sentinel.react.v2"]


def test_completion_candidates_support_mode_switching() -> None:
    """
    Verify tab completion suggests the supported execution modes.

    Why this test exists:
    - the interactive client now supports changing transport mode from inside
      the chat loop
    - the completion helper should guide developers toward valid values

    How to use it:
    - run with the normal unit test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    assert completion_candidates("/mode st", agent_ids=()) == ["stream"]


def test_completion_candidates_suggest_team_command() -> None:
    """
    Verify tab completion suggests the team-scope command.

    Why this test exists:
    - team-scoped validation is now a first-class CLI workflow
    - the new command should stay discoverable from the shell prompt

    How to use it:
    - run with the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    assert "/team" in completion_candidates("/te", agent_ids=())


def test_parse_mode_command_handles_show_and_switch_requests() -> None:
    """
    Verify the mode command parser accepts the supported interactive forms.

    Why this test exists:
    - the REPL now allows execution-mode changes without restarting the client
    - parsing should remain predictable and independent from terminal I/O

    How to use it:
    - run with the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    assert parse_mode_command("/mode") is None
    assert parse_mode_command("/mode final") == "final"
    assert parse_mode_command("/mode stream") == "stream"
    assert parse_mode_command("/mode eval") == "eval"
    assert execution_mode_label("final") == "final"
    assert execution_mode_label("stream") == "stream"
    assert execution_mode_label("eval") == "eval"


def test_build_parser_accepts_team_id_flag() -> None:
    """
    Verify the CLI parser accepts an explicit team-scoping flag.

    Why this test exists:
    - team-scoped execution should be available in one-shot and interactive
      modes without relying only on REPL commands

    How to use it:
    - run with the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    parser = build_parser()
    args = parser.parse_args(["--team-id", "fredlab", "hello"])

    assert args.team_id == "fredlab"
    assert args.message == ["hello"]


def test_build_parser_accepts_metrics_url_flag() -> None:
    """
    Verify the CLI parser accepts an explicit metrics scrape URL.

    Why this test exists:
    - developers may need `/kpi` against a forwarded or custom metrics endpoint
      without changing configuration files

    How to use it:
    - run with the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    parser = build_parser()
    args = parser.parse_args(["--metrics-url", "http://localhost:9115/metrics"])

    assert args.metrics_url == "http://localhost:9115/metrics"


def test_agent_pod_client_lists_agents_and_streams_events() -> None:
    """
    Verify the reusable client parses both agent discovery and SSE execution.

    Why this test exists:
    - the developer chat client should stay fully offline in default tests
    - mock HTTP transport lets us validate the shared pod contract without a
      running server

    How to use it:
    - run with `make test` inside `fred-runtime`

    Example:
    - `pytest tests/test_client.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/agents"):
            return httpx.Response(200, json=["sentinel.react.v2"])
        if request.url.path.endswith("/agents/execute"):
            return httpx.Response(
                200,
                json={"kind": "final", "content": "sentinel ok"},
            )
        if request.url.path.endswith("/agents/execute/stream"):
            return httpx.Response(
                200,
                text='data: {"kind":"final","content":"sentinel ok"}\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url="http://localhost:8010/fred/agents/v2",
        http_client=http_client,
    )

    assert client.list_agents() == ["sentinel.react.v2"]
    assert client.execute(
        agent_id="sentinel.react.v2",
        message="hello",
        session_id="demo",
        user_id="alice",
    ) == {"kind": "final", "content": "sentinel ok"}
    assert client.stream_events(
        agent_id="sentinel.react.v2",
        message="hello",
        session_id="demo",
        user_id="alice",
    ) == [{"kind": "final", "content": "sentinel ok"}]

    http_client.close()


def test_agent_pod_client_fetches_metrics_text() -> None:
    """
    Verify the reusable client can fetch plain-text Prometheus metrics.

    Why this test exists:
    - `/kpi` depends on the same HTTP client lifecycle as the rest of the CLI
    - the metrics fetch should stay offline-testable without a running pod

    How to use it:
    - run with `make test` inside `fred-runtime`

    Example:
    - `pytest tests/test_client.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/metrics":
            return httpx.Response(
                200,
                text='process_cpu_percent 12.5\nagent_tool_failed_total{tool_name="demo"} 1\n',
                headers={"content-type": "text/plain; version=0.0.4"},
            )
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url="http://localhost:8010/fred/agents/v2",
        metrics_url="http://localhost:9115/metrics",
        http_client=http_client,
    )

    assert "process_cpu_percent" in client.get_metrics_text()

    http_client.close()


def test_parse_prometheus_text_exposition_and_histogram_summary() -> None:
    """
    Verify `/kpi` parsing keeps histogram counts, sums, and labels.

    Why this test exists:
    - the CLI should summarize runtime latency histograms without depending on
      bucket-by-bucket output

    How to use it:
    - run with the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    text = """
# HELP agent_tool_latency_ms KPI timer
agent_tool_latency_ms_bucket{tool_name="search",team_id="fredlab",le="10.0"} 1
agent_tool_latency_ms_bucket{tool_name="search",team_id="fredlab",le="+Inf"} 2
agent_tool_latency_ms_sum{tool_name="search",team_id="fredlab"} 25
agent_tool_latency_ms_count{tool_name="search",team_id="fredlab"} 2
process_cpu_percent 12.5
""".strip()

    samples = parse_prometheus_text_exposition(text)
    histograms = summarize_prometheus_histograms(samples)

    assert len(samples) == 5
    assert histograms[0].name == "agent_tool_latency_ms"
    assert histograms[0].labels == {"tool_name": "search", "team_id": "fredlab"}
    assert histograms[0].count == 2
    assert histograms[0].sum_value == 25
    assert histograms[0].avg_value == 12.5


def test_render_kpi_report_renders_latency_process_and_counters() -> None:
    """
    Verify `/kpi` renders a compact human-readable KPI summary.

    Why this test exists:
    - the CLI output should stay useful for laptop benchmarking without raw
      Prometheus exposition noise

    How to use it:
    - run with the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    samples = parse_prometheus_text_exposition(
        """
agent_tool_latency_ms_sum{tool_name="search"} 40
agent_tool_latency_ms_count{tool_name="search"} 4
process_cpu_percent 18.2
agent_tool_failed_total{tool_name="search",error_code="TimeoutError"} 2
""".strip()
    )

    lines = render_kpi_report(samples, color_enabled=False)
    report = "\n".join(lines)

    assert "Phase / latency breakdown:" in report
    assert "[search]" in report
    assert "avg=     10 ms" in report
    assert "Process gauges:" in report
    assert "process_cpu_percent" in report
    assert "Counters:" in report
    assert "agent_tool_failed_total" in report


def test_agent_pod_client_passes_resume_payload_through_execute_and_stream() -> None:
    """
    Verify the reusable client forwards structured HITL resume payloads.

    Why this test exists:
    - graph HITL resumes rely on the client preserving the exact JSON payload
      returned by the interactive shell
    - the bank-transfer sample regressed because choice resumes were not kept
      structured end-to-end

    How to use it:
    - run with `make test` inside `fred-runtime`

    Example:
    - `pytest tests/test_client.py -q`
    """

    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        assert isinstance(body, dict)
        seen_payloads.append(body)
        if request.url.path.endswith("/agents/execute"):
            return httpx.Response(200, json={"kind": "final", "content": "ok"})
        if request.url.path.endswith("/agents/execute/stream"):
            return httpx.Response(
                200,
                text='data: {"kind":"final","content":"ok"}\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url="http://localhost:8010/fred/agents/v2",
        http_client=http_client,
    )

    resume_payload = {"choice_id": "confirm"}
    client.execute(
        agent_id="fred.samples.bank_transfer.graph",
        message="",
        session_id="demo",
        user_id="alice",
        resume_payload=resume_payload,
    )
    client.stream_events(
        agent_id="fred.samples.bank_transfer.graph",
        message="",
        session_id="demo",
        user_id="alice",
        resume_payload=resume_payload,
    )

    assert [payload["resume_payload"] for payload in seen_payloads] == [
        resume_payload,
        resume_payload,
    ]

    http_client.close()


def test_agent_pod_client_passes_team_id_through_execute_and_stream() -> None:
    """
    Verify the reusable client forwards team scope in runtime_context.

    Why this test exists:
    - backend completeness validation now depends on exercising a team-scoped
      execution path from the CLI
    - the CLI must preserve `team_id` for both final and streamed execution

    How to use it:
    - run with `make test` inside `fred-runtime`

    Example:
    - `pytest tests/test_client.py -q`
    """

    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8"))
        assert isinstance(body, dict)
        seen_payloads.append(body)
        if request.url.path.endswith("/agents/execute"):
            return httpx.Response(200, json={"kind": "final", "content": "ok"})
        if request.url.path.endswith("/agents/execute/stream"):
            return httpx.Response(
                200,
                text='data: {"kind":"final","content":"ok"}\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url="http://localhost:8010/fred/agents/v2",
        http_client=http_client,
    )

    client.execute(
        agent_id="sentinel.react.v2",
        message="hello",
        session_id="demo",
        user_id="alice",
        team_id="fredlab",
    )
    client.stream_events(
        agent_id="sentinel.react.v2",
        message="hello",
        session_id="demo",
        user_id="alice",
        team_id="fredlab",
    )

    assert [payload["runtime_context"] for payload in seen_payloads] == [
        {"user_id": "alice", "team_id": "fredlab"},
        {"user_id": "alice", "team_id": "fredlab"},
    ]

    http_client.close()


def test_build_hitl_resume_payload_supports_choice_index_and_raw_id() -> None:
    """
    Verify the interactive chat converts menu answers into structured resumes.

    Why this test exists:
    - developers commonly type `1` at the HITL prompt, while the graph runtime
      expects `{"choice_id": ...}` when resuming
    - this helper keeps the terminal bank-transfer demo functional

    How to use it:
    - run with `make test` inside `fred-runtime`

    Example:
    - `pytest tests/test_client.py -q`
    """

    choices = [
        {"id": "confirm", "label": "Yes, confirm transfer"},
        {"id": "cancel", "label": "No, cancel"},
    ]

    assert build_hitl_resume_payload(raw_response="1", choices=choices) == {
        "choice_id": "confirm"
    }
    assert build_hitl_resume_payload(raw_response="cancel", choices=choices) == {
        "choice_id": "cancel"
    }


def test_agent_pod_client_injects_bearer_token() -> None:
    """
    Verify the pod client forwards the current bearer token on requests.

    Why this test exists:
    - secured pod testing depends on the client sending the latest user token
      automatically once login support is enabled

    How to use it:
    - run with the offline `fred-runtime` test suite
    """

    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("Authorization"))
        return httpx.Response(200, json=["sentinel.react.v2"])

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url="http://localhost:8010/fred/agents/v2",
        http_client=http_client,
        token_provider=lambda: "token-123",
    )

    assert client.list_agents() == ["sentinel.react.v2"]
    assert seen_headers == ["Bearer token-123"]

    http_client.close()


def test_keycloak_user_session_manager_logs_in_and_refreshes(
    tmp_path,
) -> None:
    """
    Verify the CLI login manager caches and refreshes a real user session.

    Why this test exists:
    - secured manual testing should survive access-token expiry without forcing
      a fresh password prompt every time

    How to use it:
    - run with the offline `fred-runtime` test suite
    """

    requests_seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST":
            return httpx.Response(404)
        body = request.read().decode("utf-8")
        form = dict(parse_qsl(body))
        requests_seen.append(form)
        if form.get("grant_type") == "password":
            return httpx.Response(
                200,
                json={
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 120,
                },
            )
        if form.get("grant_type") == "refresh_token":
            return httpx.Response(
                200,
                json={
                    "access_token": "access-2",
                    "refresh_token": "refresh-2",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(400)

    auth_http = httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)
    manager = KeycloakUserSessionManager(
        config=KeycloakLoginConfig(
            realm_url="http://localhost:8080/realms/fred",
            client_id="fred-ui",
        ),
        cache_file=tmp_path / "token.json",
        http_client=auth_http,
    )

    manager.login(
        username="alice",
        password="dummy-password",  # pragma: allowlist secret
    )
    assert manager.current_username() == "alice"
    assert manager.get_access_token() == "access-1"

    assert manager._session is not None
    manager._session.expires_at_timestamp = 0
    assert manager.get_access_token() == "access-2"
    assert manager.is_logged_in() is True
    assert requests_seen[0]["grant_type"] == "password"
    assert requests_seen[1]["grant_type"] == "refresh_token"

    manager.close()
    auth_http.close()


def test_keycloak_user_session_manager_supports_browser_pkce_login(
    tmp_path, monkeypatch
) -> None:
    """
    Verify the CLI supports browser-based PKCE login without password grant.

    Why this test exists:
    - production-like CLI usage should be able to mirror the frontend browser
      login family while staying fully offline in tests

    How to use it:
    - run with the offline `fred-runtime` test suite
    """

    opened_urls: list[str] = []
    requests_seen: list[dict[str, str]] = []

    def _jwt(payload: dict[str, str]) -> str:
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        return f"header.{encoded.decode('utf-8').rstrip('=')}.signature"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST":
            return httpx.Response(404)
        body = request.read().decode("utf-8")
        form = dict(parse_qsl(body))
        requests_seen.append(form)
        if form.get("grant_type") == "authorization_code":
            return httpx.Response(
                200,
                json={
                    "access_token": _jwt({"preferred_username": "alice"}),
                    "refresh_token": "refresh-1",
                    "expires_in": 120,
                },
            )
        return httpx.Response(400)

    auth_http = httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)
    manager = KeycloakUserSessionManager(
        config=KeycloakLoginConfig(
            realm_url="http://localhost:8080/realms/app",
            client_id="app",
        ),
        cache_file=tmp_path / "session.json",
        http_client=auth_http,
    )

    monkeypatch.setattr(
        manager,
        "_wait_for_pkce_callback",
        lambda request, timeout_seconds: "auth-code-123",
    )
    manager.login_with_pkce(
        callback_host="127.0.0.1",
        callback_port=8765,
        url_opener=lambda url: opened_urls.append(url) or True,
    )

    assert manager.current_username() == "alice"
    assert opened_urls
    assert "code_challenge_method=S256" in opened_urls[0]
    assert requests_seen[0]["grant_type"] == "authorization_code"
    assert requests_seen[0]["client_id"] == "app"
    assert requests_seen[0]["code"] == "auth-code-123"
    assert requests_seen[0]["redirect_uri"] == "http://127.0.0.1:8765/callback"
    assert requests_seen[0]["code_verifier"]

    manager.close()
    auth_http.close()


def test_build_cli_token_provider_falls_back_after_refresh_failure(
    tmp_path, capsys
) -> None:
    """
    Verify the CLI still starts when the cached Keycloak session cannot refresh.

    Why this test exists:
    - developers expect `fred-agents-cli` to remain usable even when the local
      refresh token was revoked or expired
    - public pod endpoints such as `/agents` should still work, and the user
      should be able to recover with `/login`

    How to use it:
    - run with the offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    auth_http = httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)
    manager = KeycloakUserSessionManager(
        config=KeycloakLoginConfig(
            realm_url="http://localhost:8080/realms/fred",
            client_id="fred-ui",
        ),
        cache_file=tmp_path / "token.json",
        http_client=auth_http,
    )
    manager._session = manager._build_session_from_token_payload(
        {
            "access_token": "expired-access",
            "refresh_token": "expired-refresh",
            "expires_in": 0,
        },
        username="alice",
    )
    manager._session.expires_at_timestamp = 0

    token_provider = build_cli_token_provider(
        auth_session=manager,
        static_token=None,
    )

    assert token_provider() is None
    assert manager.is_logged_in() is False
    assert "Use /login to authenticate again." in capsys.readouterr().out

    manager.close()
    auth_http.close()


def test_run_single_turn_prints_final_answer(capsys) -> None:
    """
    Verify one-shot mode prints the final answer content for developers.

    Why this test exists:
    - the CLI is most useful when it behaves like a clean replacement for
      repetitive `curl` commands
    - this test locks in the user-facing output for the common success path

    How to use it:
    - run with the offline test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"kind": "final", "content": "all green"},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url=normalize_base_url("http://localhost:8010/fred/agents/v2/"),
        http_client=http_client,
    )

    exit_code, hitl = run_single_turn(
        client=client,
        agent_id="sentinel.react.v2",
        message="status",
        session_id="demo",
        user_id="alice",
        team_id=None,
        verbose=False,
        stream=False,
        color_enabled=False,
    )
    assert exit_code == 0
    assert hitl is None
    assert capsys.readouterr().out.strip() == "all green"

    http_client.close()


def test_run_single_turn_stream_prints_live_events(capsys) -> None:
    """
    Verify stream mode renders the SSE response as the events arrive.

    Why this test exists:
    - the chat client should expose the runtime stream clearly when developers
      opt into `--stream`
    - the streamed rendering should stay simple and offline-testable

    How to use it:
    - run with the offline test suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                'data: {"kind":"tool_call","tool_name":"demo.search"}\n\n'
                'data: {"kind":"final","content":"streamed answer"}\n\n'
            ),
            headers={"content-type": "text/event-stream"},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url="http://localhost:8010/fred/agents/v2",
        http_client=http_client,
    )

    exit_code, hitl = run_single_turn(
        client=client,
        agent_id="sentinel.react.v2",
        message="status",
        session_id="demo",
        user_id="alice",
        team_id=None,
        verbose=False,
        stream=True,
        color_enabled=False,
    )
    assert exit_code == 0
    assert hitl is None
    assert capsys.readouterr().out.splitlines() == [
        "[tool] demo.search",
        "streamed answer",
    ]

    http_client.close()


def test_run_single_turn_stream_with_assistant_delta_avoids_duplicate_final(
    capsys,
) -> None:
    """
    Verify stream mode does not print the final answer twice after deltas.

    Why this test exists:
    - SSE streams often emit assistant deltas followed by a final event with the
      same content
    - the terminal rendering should avoid duplicate output in that common case

    How to use it:
    - run with the offline unit tests

    Example:
    - `pytest tests/test_client.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                'data: {"kind":"assistant_delta","delta":"hello"}\n\n'
                'data: {"kind":"final","content":"hello"}\n\n'
            ),
            headers={"content-type": "text/event-stream"},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url="http://localhost:8010/fred/agents/v2",
        http_client=http_client,
    )

    exit_code, hitl = run_single_turn(
        client=client,
        agent_id="sentinel.react.v2",
        message="status",
        session_id="demo",
        user_id="alice",
        team_id=None,
        verbose=False,
        stream=True,
        color_enabled=False,
    )
    assert exit_code == 0
    assert hitl is None
    assert capsys.readouterr().out == "hello\n"

    http_client.close()


def test_run_single_turn_verbose_stream_prints_raw_json(capsys) -> None:
    """
    Verify verbose stream mode keeps the raw event visibility for debugging.

    Why this test exists:
    - developers sometimes need the exact runtime payloads, not the friendly
      renderer
    - the `--verbose --stream` combination should preserve that path

    How to use it:
    - run with the normal offline unit suite

    Example:
    - `pytest tests/test_client.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                'data: {"kind":"status","status":"thinking"}\n\n'
                'data: {"kind":"final","content":"done"}\n\n'
            ),
            headers={"content-type": "text/event-stream"},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = AgentPodClient(
        base_url="http://localhost:8010/fred/agents/v2",
        http_client=http_client,
    )

    exit_code, hitl = run_single_turn(
        client=client,
        agent_id="sentinel.react.v2",
        message="status",
        session_id="demo",
        user_id="alice",
        team_id=None,
        verbose=True,
        stream=True,
        color_enabled=False,
    )
    assert exit_code == 0
    assert hitl is None
    assert capsys.readouterr().out.splitlines() == [
        '{"kind": "status", "status": "thinking"}',
        '{"kind": "final", "content": "done"}',
    ]

    http_client.close()
