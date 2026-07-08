"""
Offline unit tests for the control-plane developer CLI.

Ref: docs/WORKPLAN.md D1 — control-plane `make cli` commands: templates, instances,
     enrollment, runtime binding, sessions, execution preparation, lifecycle inspection.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from typing import Any, cast

import httpx
from control_plane_backend.cli import (
    ControlPlaneApiClient,
    ControlPlaneCommandContext,
    ControlPlaneShellState,
    build_parser,
    completion_candidates,
    default_control_plane_base_url,
    main,
    run_command,
)
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    ManagedAgentInstanceSummary,
    PromptSummary,
)
from control_plane_backend.teams.schemas import Team
from fred_core.common import TeamId

cli_main_module = importlib.import_module("control_plane_backend.cli.main")


class _FakeAuthSession:
    """
    Lightweight login-session stand-in for offline CLI tests.

    Why this helper exists:
    - CLI command tests need to exercise `/login`, `/login-password`, and
      `/logout` branches without depending on real Keycloak configuration

    How to use it:
    - pass one instance as `auth_session` in `_make_cli_context(...)`

    Example:
    - `auth = _FakeAuthSession()`
    """

    def __init__(
        self,
        *,
        username: str | None = None,
        logged_in: bool = False,
        description: str = "mock session",
    ) -> None:
        self.username = username
        self.logged_in = logged_in
        self.description = description
        self.pkce_calls: list[tuple[str, int]] = []
        self.password_login_calls: list[tuple[str, str]] = []
        self.closed = False

    def login_with_pkce(self, *, callback_host: str, callback_port: int) -> None:
        """Record one PKCE login and simulate a cached logged-in user."""

        self.pkce_calls.append((callback_host, callback_port))
        self.username = self.username or "browser-user"
        self.logged_in = True

    def login(self, *, username: str, password: str) -> None:
        """Record one username/password login attempt."""

        self.password_login_calls.append((username, password))
        self.username = username
        self.logged_in = True

    def logout(self) -> None:
        """Clear the simulated cached login state."""

        self.logged_in = False

    def is_logged_in(self) -> bool:
        """Return whether this fake session currently looks authenticated."""

        return self.logged_in

    def current_username(self) -> str | None:
        """Return the simulated cached username."""

        return self.username

    def describe(self) -> str:
        """Return one human-readable session description."""

        return self.description

    def close(self) -> None:
        """Record session cleanup performed by the CLI."""

        self.closed = True


def _make_cli_context(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    current_team_id: str | None = None,
    known_teams: list[Team] | None = None,
    known_templates: list[AgentTemplateSummary] | None = None,
    known_instances: list[ManagedAgentInstanceSummary] | None = None,
    known_prompts: list[PromptSummary] | None = None,
    auth_session: _FakeAuthSession | None = None,
) -> tuple[httpx.Client, ControlPlaneCommandContext]:
    """
    Build one CLI command context backed by an HTTPX mock transport.

    Why this helper exists:
    - command tests should stay focused on CLI behavior instead of repeating
      transport and shell-state setup

    How to use it:
    - pass one mock-transport handler and the initial cached shell state

    Example:
    - `http_client, ctx = _make_cli_context(handler, current_team_id="fredlab")`
    """

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ControlPlaneApiClient(
        base_url="http://localhost:8222/control-plane/v1",
        http_client=http_client,
    )
    state = ControlPlaneShellState(
        current_team_id=current_team_id,
        known_teams=list(known_teams or []),
        known_templates=list(known_templates or []),
        known_instances=list(known_instances or []),
        known_prompts=list(known_prompts or []),
    )
    ctx = ControlPlaneCommandContext(
        client=client,
        state=state,
        color_enabled=False,
        auth_session=cast(Any, auth_session),
        callback_host="127.0.0.1",
        callback_port=8765,
    )
    return http_client, ctx


def _execution_preparation_payload(
    *,
    team_id: str = "fredlab",
    agent_instance_id: str = "instance-123",
) -> dict[str, object]:
    """
    Build one minimal valid execution-preparation payload for CLI tests.

    Why this helper exists:
    - `/prepare` tests only need one contract-valid payload, not runtime logic

    How to use it:
    - pass the team and instance identifiers expected by the command under test

    Example:
    - `payload = _execution_preparation_payload(team_id="personal")`
    """

    return {
        "agent_instance_id": agent_instance_id,
        "team_id": team_id,
        "runtime_id": "agents-v2",
        "execution_transport": "sse",
        "execute_url": "/runtime/agents-v2/agents/execute",
        "execute_stream_url": "/runtime/agents-v2/agents/execute/stream",
        "messages_url_template": "/runtime/agents-v2/agents/sessions/{session_id}/messages",
        "execution_grant": {
            "user_id": "alice",
            "team_id": team_id,
            "agent_instance_id": agent_instance_id,
            "action": "execute",
            "audience": "/runtime/agents-v2",
            "issued_at": 1714000000,
            "expires_at": 1714003600,
            "scopes": [],
            "trace_id": None,
            "correlation_id": None,
            "storage_scope": None,
        },
        "supports_streaming": True,
        "supports_hitl": True,
        "supports_ui_parts": True,
        "expires_at": "2026-01-01T00:10:00+00:00",
        "runtime_display_name": "Runtime A",
        "grant_refresh_required": False,
        "max_session_idle_seconds": 3600,
    }


def test_build_parser_accepts_team_id_flag() -> None:
    """
    Verify the control-plane CLI accepts an initial team context flag.

    Why this test exists:
    - the shell should support one stable team context without requiring an
      immediate `/team` command after startup

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    parser = build_parser()
    args = parser.parse_args(["--team-id", "fredlab", "teams"])

    assert args.team_id == "fredlab"
    assert args.command == ["teams"]


def test_default_control_plane_base_url_reads_configuration(
    tmp_path, monkeypatch
) -> None:
    """
    Verify the CLI derives its base URL from control-plane configuration.

    Why this test exists:
    - developers should not have to pass `--base-url` when the project config
      already declares the local bind address, port, and base path

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    config_file = tmp_path / "configuration.yaml"
    config_file.write_text(
        """
app:
  address: "0.0.0.0"
  port: 8222
  base_url: "/control-plane/v1"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.delenv("FRED_CONTROL_PLANE_URL", raising=False)

    assert default_control_plane_base_url() == "http://127.0.0.1:8222/control-plane/v1"


def test_main_help_command_skips_startup_prefetch(tmp_path, monkeypatch) -> None:
    """
    Verify one-shot `/help` does not prefetch remote control-plane resources.

    Why this test exists:
    - local help and shell discovery should stay usable even when Keycloak or
      control-plane are offline
    - one-shot commands that do not need API data should not trigger startup
      HTTP calls or token refresh noise

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    config_file = tmp_path / "configuration.yaml"
    config_file.write_text(
        """
app:
  address: "127.0.0.1"
  port: 8222
  base_url: "/control-plane/v1"
security:
  user:
    enabled: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.setattr(
        "control_plane_backend.cli.load_cli_environment",
        lambda log_prefix="[CLI CONFIG]": "test.env",
    )
    monkeypatch.setattr(
        "control_plane_backend.cli.ControlPlaneApiClient.list_teams",
        lambda self: (_ for _ in ()).throw(
            AssertionError("`/help` should not prefetch team data.")
        ),
    )

    assert main(["/help"]) == 0


def test_completion_candidates_suggest_team_and_instance_ids() -> None:
    """
    Verify shell completion uses the cached team and instance context.

    Why this test exists:
    - the new CLI should match `fred-agent-chat` in discoverability and reduce
      typing friction during repeated operator workflows

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    state = ControlPlaneShellState(
        current_team_id="af27a03a-48d4-451c-aaf4-6d5aa44733f1",
        known_teams=[
            Team(
                id=TeamId("af27a03a-48d4-451c-aaf4-6d5aa44733f1"),
                name="fredlab",
                member_count=3,
            )
        ],
        known_instances=[],
    )
    state.known_instances = []

    assert completion_candidates("/te", state=state)[:2] == ["/team", "/team-info"]
    assert completion_candidates("/team fr", state=state) == ["fredlab"]
    assert completion_candidates("/team af27", state=state) == [
        "af27a03a-48d4-451c-aaf4-6d5aa44733f1"
    ]

    state.known_instances = [
        ManagedAgentInstanceSummary(
            agent_instance_id="instance-123",
            team_id=TeamId("af27a03a-48d4-451c-aaf4-6d5aa44733f1"),
            template_id="fred-agents:fred.github.sentinel",
            display_name="Sentinel",
            status="enabled",
        )
    ]
    state.known_prompts = [
        PromptSummary(
            id="prompt-123",
            name="Daily brief",
        )
    ]
    assert completion_candidates("/prepare inst", state=state) == ["instance-123"]
    assert completion_candidates("/prompt pr", state=state) == ["prompt-123"]


def test_control_plane_api_client_injects_bearer_token_and_lists_teams() -> None:
    """
    Verify the typed control-plane client sends auth and parses team payloads.

    Why this test exists:
    - the CLI must talk to the public HTTP API like a real consumer
    - bearer-token wiring and response typing are the core contract of the CLI

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("Authorization"))
        if request.url.path.endswith("/teams"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "fredlab",
                        "name": "Fredlab",
                        "member_count": 3,
                        "owners": [],
                        "is_member": True,
                        "description": None,
                        "is_private": True,
                        "banner_image_url": None,
                    }
                ],
            )
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ControlPlaneApiClient(
        base_url="http://localhost:8222/control-plane/v1",
        http_client=http_client,
        token_provider=lambda: "token-123",
    )

    teams = client.list_teams()

    assert teams[0].id == "fredlab"
    assert seen_headers == ["Bearer token-123"]
    http_client.close()


def test_run_command_enroll_uses_template_default_display_name(capsys) -> None:
    """
    Verify `/enroll` defaults the display name from the chosen template.

    Why this test exists:
    - the CLI should keep common enrollment flows short and ergonomic
    - the operator should not need to retype the template display name just to
      create a standard managed instance

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    seen_requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/agent-instances"):
            body = json.loads(request.read().decode("utf-8"))
            seen_requests.append(body)
            return httpx.Response(
                201,
                json={
                    "agent_instance_id": "instance-123",
                    "team_id": "fredlab",
                    "template_id": "fred-agents:fred.github.sentinel",
                    "display_name": body["display_name"],
                    "description": body.get("description"),
                    "status": "enabled",
                    "created_at": None,
                    "updated_at": None,
                    "created_by": "alice",
                },
            )
        if request.method == "GET" and request.url.path.endswith("/agent-instances"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ControlPlaneApiClient(
        base_url="http://localhost:8222/control-plane/v1",
        http_client=http_client,
    )
    state = ControlPlaneShellState(
        current_team_id="fredlab",
        known_templates=[
            AgentTemplateSummary(
                template_id="fred-agents:fred.github.sentinel",
                source_runtime_id="fred-agents",
                source_agent_id="fred.github.sentinel",
                display_name="Sentinel",
                description="Operations sentinel",
                category="ops",
            )
        ],
    )
    ctx = ControlPlaneCommandContext(
        client=client,
        state=state,
        color_enabled=False,
        auth_session=None,
        callback_host="127.0.0.1",
        callback_port=8765,
    )

    assert run_command("/enroll fred-agents:fred.github.sentinel", ctx=ctx) is True
    assert seen_requests[0]["display_name"] == "Sentinel"
    assert seen_requests[0]["description"] == "Operations sentinel"
    assert "instance-123" in capsys.readouterr().out
    http_client.close()


def test_run_command_team_accepts_visible_team_name_selector(capsys) -> None:
    """
    Verify `/team` accepts one visible team name and stores the canonical id.

    Why this test exists:
    - operators should be able to switch to one team shown by `/teams` without
      copying a raw UUID from the terminal

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    team_id = "af27a03a-48d4-451c-aaf4-6d5aa44733f1"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/teams"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": team_id,
                        "name": "fredlab",
                        "member_count": 4,
                        "owners": [],
                        "is_member": True,
                        "description": None,
                        "is_private": True,
                        "banner_image_url": None,
                    }
                ],
            )
        if request.method == "GET" and request.url.path.endswith(f"/teams/{team_id}"):
            return httpx.Response(
                200,
                json={
                    "id": team_id,
                    "name": "fredlab",
                    "member_count": 4,
                    "owners": [],
                    "is_member": True,
                    "description": None,
                    "is_private": True,
                    "banner_image_url": None,
                    "permissions": ["can_read"],
                },
            )
        if request.method == "GET" and request.url.path.endswith(
            f"/teams/{team_id}/agent-templates"
        ):
            return httpx.Response(200, json=[])
        if request.method == "GET" and request.url.path.endswith(
            f"/teams/{team_id}/agent-instances"
        ):
            return httpx.Response(200, json=[])
        if request.method == "GET" and request.url.path.endswith(
            f"/teams/{team_id}/prompts"
        ):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ControlPlaneApiClient(
        base_url="http://localhost:8222/control-plane/v1",
        http_client=http_client,
    )
    state = ControlPlaneShellState()
    ctx = ControlPlaneCommandContext(
        client=client,
        state=state,
        color_enabled=False,
        auth_session=None,
        callback_host="127.0.0.1",
        callback_port=8765,
    )

    assert run_command("/team fredlab", ctx=ctx) is True
    assert state.current_team_id == team_id
    assert "name:       fredlab" in capsys.readouterr().out

    assert run_command("/team", ctx=ctx) is True
    assert "Current team: fredlab" in capsys.readouterr().out
    http_client.close()


def test_format_http_error_includes_detail_and_plain_fallback() -> None:
    """
    Verify CLI HTTP error formatting stays concise and actionable.

    Why this test exists:
    - operators should see one short API error summary instead of a raw stack
      or unparsed HTTPX exception object

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    request = httpx.Request("GET", "http://localhost:8222/control-plane/v1/teams")
    response = httpx.Response(
        403,
        request=request,
        json={"detail": "Forbidden for this user."},
    )
    status_error = httpx.HTTPStatusError(
        "403 Forbidden",
        request=request,
        response=response,
    )

    assert (
        cli_main_module.format_http_error(status_error)
        == "HTTP 403 GET http://localhost:8222/control-plane/v1/teams detail=Forbidden for this user."
    )

    connect_error = httpx.ConnectError("Connection refused", request=request)
    assert "Connection refused" in cli_main_module.format_http_error(connect_error)


def test_run_command_unbind_deletes_instance_and_refreshes_cache(capsys) -> None:
    """
    Verify `/unbind` deletes one instance and refreshes the cached instance list.

    Why this test exists:
    - the shell should keep autocompletion and later commands in sync after one
      managed-agent deletion

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE" and request.url.path.endswith(
            "/teams/fredlab/agent-instances/instance-123"
        ):
            return httpx.Response(204)
        if request.method == "GET" and request.url.path.endswith(
            "/teams/fredlab/agent-instances"
        ):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    http_client, ctx = _make_cli_context(
        handler,
        current_team_id="fredlab",
        known_instances=[
            ManagedAgentInstanceSummary(
                agent_instance_id="instance-123",
                team_id=TeamId("fredlab"),
                template_id="fred-agents:fred.github.sentinel",
                display_name="Sentinel",
                status="enabled",
            )
        ],
    )

    assert run_command("/unbind instance-123", ctx=ctx) is True
    assert ctx.state.known_instances == []
    assert "Deleted managed instance instance-123." in capsys.readouterr().out
    http_client.close()


def test_run_command_runtime_prints_binding_json(capsys) -> None:
    """
    Verify `/runtime` renders the typed runtime-binding payload as JSON.

    Why this test exists:
    - runtime binding is an operator inspection flow and should stay readable in
      the CLI without frontend tooling

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith(
            "/agent-instances/instance-123/runtime"
        ):
            return httpx.Response(
                200,
                json={
                    "agent_instance_id": "instance-123",
                    "template_agent_id": "fred.github.sentinel",
                    "display_name": "GitHub Sentinel",
                    "owner_scope": "team",
                    "owner_user_id": None,
                    "owner_team_id": "fredlab",
                    "enabled": True,
                    "tuning": {
                        "role": "Sentinel",
                        "description": "Operations sentinel",
                        "tags": [],
                        "fields": [],
                        "mcp_servers": [],
                    },
                },
            )
        return httpx.Response(404)

    http_client, ctx = _make_cli_context(handler, current_team_id="fredlab")

    assert run_command("/runtime instance-123", ctx=ctx) is True
    output = capsys.readouterr().out
    assert "Runtime Binding" in output
    assert '"template_agent_id": "fred.github.sentinel"' in output
    http_client.close()


def test_run_command_sessions_accepts_visible_team_name(capsys) -> None:
    """
    Verify `/sessions` accepts a readable team selector and prints session rows.

    Why this test exists:
    - session inspection should match the CLI's readable team-selector UX, not
      force UUID copy/paste

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    team_id = "af27a03a-48d4-451c-aaf4-6d5aa44733f1"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith(
            f"/teams/{team_id}/sessions"
        ):
            return httpx.Response(
                200,
                json=[
                    {
                        "session_id": "session-1",
                        "team_id": team_id,
                        "agent_instance_id": "instance-123",
                        "title": "First chat",
                        "created_at": "2026-01-01T10:00:00+00:00",
                        "updated_at": "2026-01-01T10:05:00+00:00",
                    }
                ],
            )
        return httpx.Response(404)

    http_client, ctx = _make_cli_context(
        handler,
        known_teams=[
            Team(
                id=TeamId(team_id),
                name="fredlab",
                member_count=3,
            )
        ],
    )

    assert run_command("/sessions fredlab", ctx=ctx) is True
    output = capsys.readouterr().out
    assert "Sessions" in output
    assert "First chat" in output
    http_client.close()


def test_run_command_prompts_accepts_visible_team_name(capsys) -> None:
    """
    Verify `/prompts` accepts a readable team selector and prints prompt rows.

    Why this test exists:
    - prompt-library inspection should follow the same team-selector ergonomics
      as the rest of the control-plane CLI

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    team_id = "af27a03a-48d4-451c-aaf4-6d5aa44733f1"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith(
            f"/teams/{team_id}/prompts"
        ):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "prompt-1",
                        "name": "Daily brief",
                        "description": "Ops baseline",
                        "created_by": "alice",
                        "created_at": "2026-01-01T10:00:00+00:00",
                        "updated_at": "2026-01-01T10:05:00+00:00",
                    }
                ],
            )
        return httpx.Response(404)

    http_client, ctx = _make_cli_context(
        handler,
        known_teams=[
            Team(
                id=TeamId(team_id),
                name="fredlab",
                member_count=3,
            )
        ],
    )

    assert run_command("/prompts fredlab", ctx=ctx) is True
    output = capsys.readouterr().out
    assert "Prompts" in output
    assert "Daily brief" in output
    http_client.close()


def test_run_command_prompt_crud_uses_current_team(capsys) -> None:
    """
    Verify prompt CRUD commands call the team-scoped HTTP surface and refresh cache.

    Why this test exists:
    - `make cli` must exercise the full prompt-library lifecycle before any UI
      prompt-management page is considered ready

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    seen_requests: list[tuple[str, str, dict[str, object] | None]] = []
    prompts_payload = [
        {
            "id": "prompt-1",
            "name": "Daily brief v2",
            "description": "Refined",
            "created_by": "alice",
            "created_at": None,
            "updated_at": None,
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode("utf-8")) if request.content else None
        seen_requests.append((request.method, request.url.path, body))
        if request.method == "POST" and request.url.path.endswith(
            "/teams/fredlab/prompts"
        ):
            assert isinstance(body, dict)
            return httpx.Response(
                201,
                json={
                    "id": "prompt-1",
                    "name": body["name"],
                    "description": body.get("description"),
                    "created_by": "alice",
                    "created_at": None,
                    "updated_at": None,
                },
            )
        if request.method == "PUT" and request.url.path.endswith(
            "/teams/fredlab/prompts/prompt-1"
        ):
            assert isinstance(body, dict)
            return httpx.Response(
                200,
                json={
                    "id": "prompt-1",
                    "name": body["name"],
                    "description": body.get("description"),
                    "created_by": "alice",
                    "created_at": None,
                    "updated_at": None,
                },
            )
        if request.method == "GET" and request.url.path.endswith(
            "/teams/fredlab/prompts/prompt-1"
        ):
            return httpx.Response(
                200,
                json={
                    "id": "prompt-1",
                    "team_id": "fredlab",
                    "name": "Daily brief v2",
                    "description": "Refined",
                    "text": "Respond in {response_language}.",
                    "created_by": "alice",
                    "created_at": None,
                    "updated_at": None,
                },
            )
        if request.method == "DELETE" and request.url.path.endswith(
            "/teams/fredlab/prompts/prompt-1"
        ):
            return httpx.Response(204)
        if request.method == "GET" and request.url.path.endswith(
            "/teams/fredlab/prompts"
        ):
            return httpx.Response(200, json=prompts_payload)
        return httpx.Response(404)

    http_client, ctx = _make_cli_context(handler, current_team_id="fredlab")

    assert (
        run_command(
            '/prompt-create "Daily brief" "Today is {today}." "Ops baseline"', ctx=ctx
        )
        is True
    )
    assert (
        run_command(
            '/prompt-update prompt-1 "Daily brief v2" "Respond in {response_language}." "Refined"',
            ctx=ctx,
        )
        is True
    )
    assert run_command("/prompt prompt-1", ctx=ctx) is True
    assert run_command("/prompt-delete prompt-1", ctx=ctx) is True

    output = capsys.readouterr().out
    assert "Created Prompt" in output
    assert "Updated Prompt" in output
    assert "Prompt Detail" in output
    assert "Deleted prompt prompt-1." in output
    assert any(
        method == "POST"
        and path.endswith("/teams/fredlab/prompts")
        and body
        == {
            "name": "Daily brief",
            "description": "Ops baseline",
            "category": "other",
            "emoji": None,
            "tags": [],
            "text": "Today is {today}.",
        }
        for method, path, body in seen_requests
    )
    assert any(
        method == "PUT"
        and path.endswith("/teams/fredlab/prompts/prompt-1")
        and body
        == {
            "name": "Daily brief v2",
            "description": "Refined",
            "category": "other",
            "emoji": None,
            "tags": [],
            "text": "Respond in {response_language}.",
        }
        for method, path, body in seen_requests
    )
    http_client.close()


def test_run_command_prepare_prints_execution_preparation(capsys) -> None:
    """
    Verify `/prepare` renders the execution-preparation contract as JSON.

    Why this test exists:
    - execution preparation is the bridge between product and runtime, so the
      CLI must expose its exact typed payload for local debugging

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith(
            "/teams/fredlab/agent-instances/instance-123/prepare-execution"
        ):
            return httpx.Response(
                200,
                json=_execution_preparation_payload(),
            )
        return httpx.Response(404)

    http_client, ctx = _make_cli_context(handler, current_team_id="fredlab")

    assert run_command("/prepare instance-123", ctx=ctx) is True
    output = capsys.readouterr().out
    assert "Execution Preparation" in output
    assert '"/runtime/agents-v2/agents/execute"' in output
    http_client.close()


def test_run_command_policy_resolve_uses_canonical_team_id(capsys) -> None:
    """
    Verify `/policy resolve` canonicalizes one visible team name before POSTing.

    Why this test exists:
    - README and shell completion both advertise readable team selectors for
      policy resolution, so the CLI must resolve them to the canonical id

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    team_id = "af27a03a-48d4-451c-aaf4-6d5aa44733f1"
    seen_requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith(
            "/policies/purge/resolve"
        ):
            seen_requests.append(json.loads(request.read().decode("utf-8")))
            return httpx.Response(
                200,
                json={
                    "mode": "deferred_delete",
                    "retention": "P7D",
                    "retention_seconds": 604800,
                    "cancel_on_rejoin": True,
                    "matched_rule_id": "purge.fredlab",
                    "matched_rule_specificity": 2,
                },
            )
        return httpx.Response(404)

    http_client, ctx = _make_cli_context(
        handler,
        known_teams=[
            Team(
                id=TeamId(team_id),
                name="fredlab",
                member_count=4,
            )
        ],
    )

    assert run_command("/policy resolve fredlab member_rejoined", ctx=ctx) is True
    assert seen_requests == [{"team_id": team_id, "trigger": "member_rejoined"}]
    assert '"matched_rule_id": "purge.fredlab"' in capsys.readouterr().out
    http_client.close()


def test_run_command_lifecycle_run_once_live_uses_requested_batch_size(
    capsys,
) -> None:
    """
    Verify `/lifecycle run-once live` sends the expected dry-run flag and batch.

    Why this test exists:
    - lifecycle triggering is an operator action and the CLI must preserve the
      explicit execution mode chosen in the terminal

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    seen_requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith(
            "/lifecycle/run-once"
        ):
            seen_requests.append(json.loads(request.read().decode("utf-8")))
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "backend": "memory",
                    "workflow_id": None,
                    "run_id": None,
                    "result": {"scanned": 1, "deleted": 0, "dry_run_actions": 1},
                },
            )
        return httpx.Response(404)

    http_client, ctx = _make_cli_context(handler)

    assert run_command("/lifecycle run-once live 12", ctx=ctx) is True
    assert seen_requests == [{"dry_run": False, "batch_size": 12}]
    assert '"backend": "memory"' in capsys.readouterr().out
    http_client.close()


def test_run_command_login_and_logout_manage_cached_session(capsys) -> None:
    """
    Verify `/login` and `/logout` drive the cached auth-session lifecycle.

    Why this test exists:
    - the CLI should expose predictable login/logout ergonomics without needing
      a live Keycloak realm in the default test suite

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    auth_session = _FakeAuthSession()
    http_client, ctx = _make_cli_context(
        lambda request: httpx.Response(404, request=request),
        auth_session=auth_session,
    )

    assert run_command("/login", ctx=ctx) is True
    assert auth_session.pkce_calls == [("127.0.0.1", 8765)]
    assert "Logged in as browser-user." in capsys.readouterr().out

    assert run_command("/logout", ctx=ctx) is True
    assert auth_session.logged_in is False
    assert "Logged out." in capsys.readouterr().out
    http_client.close()


def test_run_command_login_password_prompts_for_missing_username(
    monkeypatch,
    capsys,
) -> None:
    """
    Verify `/login-password` prompts for a username when no cached one exists.

    Why this test exists:
    - the local password fallback should remain usable from a fresh CLI session
      without pre-populated username state

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    auth_session = _FakeAuthSession()
    http_client, ctx = _make_cli_context(
        lambda request: httpx.Response(404, request=request),
        auth_session=auth_session,
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": "alice")
    monkeypatch.setattr(
        cli_main_module.getpass,
        "getpass",
        lambda _prompt="Password: ": "secret-password",
    )

    assert run_command("/login-password", ctx=ctx) is True
    assert auth_session.password_login_calls == [("alice", "secret-password")]
    assert "Logged in as alice." in capsys.readouterr().out
    http_client.close()


def test_main_rejects_mutually_exclusive_login_flags(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """
    Verify `main()` rejects `--login` and `--login-password` together.

    Why this test exists:
    - the CLI should fail fast on conflicting auth modes instead of opening a
      partially configured interactive session

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    config_file = tmp_path / "configuration.yaml"
    config_file.write_text(
        """
app:
  address: "127.0.0.1"
  port: 8222
  base_url: "/control-plane/v1"
security:
  user:
    enabled: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.setattr(
        cli_main_module,
        "load_cli_environment",
        lambda log_prefix="[CONTROL-PLANE CONFIG]": "test.env",
    )
    monkeypatch.setattr(
        cli_main_module,
        "resolve_keycloak_login_config",
        lambda **_kwargs: None,
    )

    assert main(["--login", "--login-password"]) == 1
    assert (
        "Choose only one login mode: `--login` or `--login-password`."
        in capsys.readouterr().out
    )


def test_main_login_requires_configured_auth(tmp_path, monkeypatch, capsys) -> None:
    """
    Verify `main()` reports missing auth configuration for `--login`.

    Why this test exists:
    - browser login should fail with one clear message when the local project is
      not configured for Keycloak-backed user security

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_cli.py -q`
    """

    config_file = tmp_path / "configuration.yaml"
    config_file.write_text(
        """
app:
  address: "127.0.0.1"
  port: 8222
  base_url: "/control-plane/v1"
security:
  user:
    enabled: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_FILE", str(config_file))
    monkeypatch.setattr(
        cli_main_module,
        "load_cli_environment",
        lambda log_prefix="[CONTROL-PLANE CONFIG]": "test.env",
    )
    monkeypatch.setattr(
        cli_main_module,
        "resolve_keycloak_login_config",
        lambda **_kwargs: None,
    )

    assert main(["--login"]) == 1
    assert "Login is not configured." in capsys.readouterr().out
