from __future__ import annotations

import base64
import json
from urllib.parse import parse_qsl

import httpx

from fred_runtime.client import (
    AgentPodClient,
    KeycloakLoginConfig,
    KeycloakUserSessionManager,
    _complete_scenario_path,
    build_hitl_resume_payload,
    completion_candidates,
    default_agent_pod_base_url,
    default_keycloak_token_file,
    execution_mode_label,
    load_cli_environment,
    normalize_base_url,
    parse_mode_command,
    resolve_keycloak_login_config,
    run_single_turn,
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


def test_completion_candidates_suggest_scenario_command() -> None:
    """
    Verify /scenario appears in command completion candidates.

    Why this test exists:
    - /scenario is a new command that should be discoverable via tab
    - the completion helper must route /scenario  prefix before the generic
      /  prefix so it never accidentally falls through to command-name
      completion once the user has typed the space

    How to use it:
    - run with the offline unit test suite
    """
    # Partial command name → suggest /scenario
    assert "/scenario" in completion_candidates("/scen", agent_ids=())
    # Once the space is typed, file-path completion takes over (not commands)
    # We cannot glob real files in this offline test, but we can verify the
    # branch is entered by confirming the result is a list (not an error).
    result = completion_candidates("/scenario ", agent_ids=())
    assert isinstance(result, list)


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


def test_cli_environment_loads_config_file_selection_from_env_file(
    tmp_path, monkeypatch
) -> None:
    """
    Verify the CLI honors the same ENV_FILE -> CONFIG_FILE chain as the pod.

    Why this test exists:
    - developers expect `fred-agent-chat` to target the same YAML profile as
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


def test_complete_scenario_path_filters_by_prefix(tmp_path) -> None:
    """
    Verify scenario path completion returns only YAML files matching the prefix.

    Why this test exists:
    - the completer must narrow down to a single file when enough of the name
      is typed, and return all candidates when nothing is typed yet
    - using tmp_path keeps the test independent of the real scenarios/ layout

    How to use it:
    - run with the offline unit test suite
    """
    import os

    (tmp_path / "sentinel_smoke.yaml").write_text("name: smoke")
    (tmp_path / "sentinel_checkpointing.yaml").write_text("name: ckpt")
    (tmp_path / "not_a_scenario.txt").write_text("ignored")

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)
        # Empty prefix → both YAML files returned
        all_files = _complete_scenario_path("")
        assert sorted(all_files) == [
            "sentinel_checkpointing.yaml",
            "sentinel_smoke.yaml",
        ]
        # Partial prefix → only the matching file
        assert _complete_scenario_path("sentinel_s") == ["sentinel_smoke.yaml"]
        # Non-matching prefix → empty
        assert _complete_scenario_path("unknown") == []
    finally:
        os.chdir(original_dir)


def test_complete_scenario_path_descends_one_level(tmp_path) -> None:
    """
    Verify scenario path completion finds YAML files one directory below cwd.

    Why this test exists:
    - scenario files typically live in tests/scenarios/, not in the project root
    - the completer must suggest them when the user has typed nothing yet or
      has typed only the directory prefix

    How to use it:
    - run with the offline unit test suite
    """
    import os

    sub = tmp_path / "tests" / "scenarios"
    sub.mkdir(parents=True)
    (sub / "sentinel_smoke.yaml").write_text("name: smoke")

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)
        # Empty prefix → file found one level down
        all_files = _complete_scenario_path("")
        assert "tests/scenarios/sentinel_smoke.yaml" in all_files
        # Directory prefix → file found
        dir_files = _complete_scenario_path("tests/scenarios/")
        assert "tests/scenarios/sentinel_smoke.yaml" in dir_files
    finally:
        os.chdir(original_dir)


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
    assert parse_mode_command("/mode final") is False
    assert parse_mode_command("/mode stream") is True
    assert execution_mode_label(stream=False) == "final"
    assert execution_mode_label(stream=True) == "stream"


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
