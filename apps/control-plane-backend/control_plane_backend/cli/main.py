from __future__ import annotations

import argparse
import getpass
import os
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from fred_core.cli.auth import (
    KeycloakUserSessionManager,
    build_cli_token_provider,
    default_configuration_file,
    default_keycloak_token_file,
    default_pkce_callback_host,
    default_pkce_callback_port,
    load_cli_environment,
    load_configuration_yaml,
    resolve_keycloak_login_config,
)
from fred_core.cli.ui import (
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_YELLOW,
    colorize,
    colors_enabled,
    complete_slash_commands,
    install_readline_completion,
)

from control_plane_backend.cli.client import (
    ControlPlaneApiClient,
    ControlPlanePolicySummary,
    ControlPlaneUserDetails,
    ControlPlaneWorkflowStartResponse,
)
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    ExecutionPreparation,
    FrontendBootstrap,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    PromptDetail,
    PromptSummary,
    SessionListItem,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger,
    PolicyEvaluationResult,
)
from control_plane_backend.teams.schemas import Team, TeamMember, TeamWithPermissions

DEFAULT_CONTROL_PLANE_BASE_URL = "http://127.0.0.1:8222/control-plane/v1"
_COMMANDS: tuple[str, ...] = (
    "/help",
    "/bootstrap",
    "/members",
    "/instances",
    "/enroll",
    "/lifecycle",
    "/login",
    "/login-password",
    "/logout",
    "/policy",
    "/prompt",
    "/prompt-create",
    "/prompt-delete",
    "/prompt-update",
    "/prompts",
    "/prepare",
    "/quit",
    "/runtime",
    "/sessions",
    "/team",
    "/team-info",
    "/teams",
    "/templates",
    "/unbind",
    "/whoami",
)


@dataclass(slots=True)
class ControlPlaneShellState:
    """
    Keep the interactive control-plane shell state in one typed object.

    Why this class exists:
    - the REPL needs one place to store the current team context and completion
      caches
    - keeping the mutable state explicit makes command handling easier to test

    How to use it:
    - create one instance when the CLI starts
    - update it as `/team`, `/teams`, `/templates`, and `/instances` run

    Example:
    - `state = ControlPlaneShellState(current_team_id="personal")`
    """

    current_team_id: str | None = None
    known_teams: list[Team] = field(default_factory=list)
    known_templates: list[AgentTemplateSummary] = field(default_factory=list)
    known_instances: list[ManagedAgentInstanceSummary] = field(default_factory=list)
    known_prompts: list[PromptSummary] = field(default_factory=list)


@dataclass(slots=True)
class ControlPlaneCommandContext:
    """
    Group the control-plane CLI runtime dependencies for one command execution.

    Why this class exists:
    - command handlers need the same handful of collaborators repeatedly:
      client, shell state, colors, and auth session
    - passing one typed bundle keeps the function signatures short and explicit

    How to use it:
    - build it once in `main()` or before entering the REPL
    - pass it to `run_command(...)`

    Example:
    - `ctx = ControlPlaneCommandContext(client=client, state=state, color_enabled=True, auth_session=auth, callback_host="127.0.0.1", callback_port=8765)`
    """

    client: ControlPlaneApiClient
    state: ControlPlaneShellState
    color_enabled: bool
    auth_session: KeycloakUserSessionManager | None
    callback_host: str
    callback_port: int


def normalize_base_url(base_url: str) -> str:
    """
    Normalize one control-plane base URL for consistent request construction.

    Why this function exists:
    - manual input often carries a trailing slash
    - the CLI should build relative endpoint paths without accidental double
      slashes

    How to use it:
    - pass any non-empty control-plane base URL before storing it in the client

    Example:
    - `normalize_base_url("http://localhost:8222/control-plane/v1/")`
    """

    cleaned = base_url.strip()
    if not cleaned:
        raise ValueError("base_url cannot be empty.")
    return cleaned.rstrip("/")


def default_control_plane_base_url() -> str:
    """
    Resolve the default local control-plane base URL from config when possible.

    Why this function exists:
    - the CLI should target the same app profile as the backend by default
    - developers should not need to pass `--base-url` in the common local case

    How to use it:
    - export `FRED_CONTROL_PLANE_URL` to override the detected value
    - otherwise the function tries `CONFIG_FILE`, then falls back to localhost

    Example:
    - `base_url = default_control_plane_base_url()`
    """

    env_value = os.getenv("FRED_CONTROL_PLANE_URL")
    if env_value:
        return normalize_base_url(env_value)

    payload = load_configuration_yaml(default_configuration_file())
    if isinstance(payload, dict):
        app = payload.get("app")
        if isinstance(app, dict):
            raw_address = str(app.get("address", "127.0.0.1")).strip()
            any_ipv4_bind_host = ".".join(["0", "0", "0", "0"])
            host = (
                "127.0.0.1"
                if raw_address in {any_ipv4_bind_host, "::"}
                else raw_address
            )
            port = int(app.get("port", 8222))
            base_path = str(app.get("base_url", "/control-plane/v1")).strip()
            if not base_path.startswith("/"):
                base_path = "/" + base_path
            return f"http://{host}:{port}{base_path}".rstrip("/")

    return DEFAULT_CONTROL_PLANE_BASE_URL


def build_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser for the control-plane shell.

    Why this function exists:
    - argument parsing should stay centralized and testable
    - one parser supports both interactive and one-shot command usage

    How to use it:
    - call from `main()` and parse the process argv

    Example:
    - `parser = build_parser()`
    """

    parser = argparse.ArgumentParser(
        description="Inspect and manage a running Fred control-plane backend."
    )
    parser.add_argument(
        "--base-url",
        default=default_control_plane_base_url(),
        help=(
            "Control-plane base URL. Defaults to app.address/app.port/app.base_url "
            "from configuration.yaml."
        ),
    )
    parser.add_argument(
        "--team-id",
        default=os.getenv("FRED_CONTROL_PLANE_TEAM_ID"),
        help="Optional initial team context used by team-scoped commands.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser-based Keycloak PKCE login before running commands.",
    )
    parser.add_argument(
        "--login-password",
        action="store_true",
        help="Use direct username/password login as a local fallback.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("FRED_CONTROL_PLANE_USERNAME"),
        help="Optional default username used by `--login-password` and `/login-password`.",
    )
    parser.add_argument(
        "--keycloak-realm-url",
        default=os.getenv("FRED_CONTROL_PLANE_KEYCLOAK_REALM_URL"),
        help="Optional Keycloak realm URL for CLI login discovery.",
    )
    parser.add_argument(
        "--keycloak-client-id",
        default=os.getenv("FRED_CONTROL_PLANE_KEYCLOAK_CLIENT_ID"),
        help="Optional Keycloak client id for CLI login discovery.",
    )
    parser.add_argument(
        "--keycloak-client-secret",
        default=os.getenv("FRED_CONTROL_PLANE_KEYCLOAK_CLIENT_SECRET"),
        help="Optional Keycloak client secret for confidential login clients.",
    )
    parser.add_argument(
        "--keycloak-callback-host",
        default=default_pkce_callback_host(
            env_var_name="FRED_CONTROL_PLANE_KEYCLOAK_CALLBACK_HOST"
        ),
        help="Loopback host used for browser PKCE login callbacks.",
    )
    parser.add_argument(
        "--keycloak-callback-port",
        type=int,
        default=default_pkce_callback_port(
            env_var_name="FRED_CONTROL_PLANE_KEYCLOAK_CALLBACK_PORT"
        ),
        help="Loopback port used for browser PKCE login callbacks.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI terminal colors in the control-plane CLI output.",
    )
    parser.add_argument(
        "command",
        nargs="*",
        help="Optional one-shot command. Omit it to start the interactive shell.",
    )
    return parser


def print_help() -> None:
    """
    Print the supported interactive control-plane commands.

    Why this function exists:
    - the shell intentionally stays explicit and typed, so discoverability
      should live in one short built-in help block

    How to use it:
    - call when the user types `/help`

    Example:
    - `print_help()`
    """

    print("Commands:")
    print("  /help                       Show this help")
    print(
        "  /login                      Log in through browser PKCE and cache the user session"
    )
    print(
        "  /login-password [user]      Use direct username/password login as a local fallback"
    )
    print(
        "  /whoami                     Show the current login state and personal-team helper info"
    )
    print("  /logout                     Clear the cached login session")
    print("  /bootstrap                  Show the current frontend bootstrap summary")
    print("  /teams                      List visible teams")
    print(
        "  /team [team_id|team_name|clear] Show, set, or clear the current team context"
    )
    print("  /team-info [team_id|team_name] Show one team's metadata and permissions")
    print("  /members [team_id|team_name] List team members")
    print("  /templates [team_id|team_name] List agent templates for a team")
    print("  /instances [team_id|team_name] List managed agent instances for a team")
    print("  /prompts [team_id|team_name]   List saved prompts for a team")
    print(
        "  /prompt <prompt_id>            Inspect one saved prompt from the current team"
    )
    print("  /prompt-create <name> <text> [description]")
    print("                              Create one saved prompt in the current team")
    print("  /prompt-update <prompt_id> <name> <text> [description]")
    print("                              Replace one saved prompt in the current team")
    print(
        "  /prompt-delete <prompt_id>     Delete one saved prompt from the current team"
    )
    print("  /enroll <template_id> [display_name]")
    print("                              Enroll one template for the current team")
    print(
        "  /unbind <agent_instance_id> Delete one managed agent instance from the current team"
    )
    print("  /runtime <agent_instance_id>")
    print("                              Inspect one agent-instance runtime binding")
    print("  /sessions [team_id|team_name] List session metadata for a team")
    print("  /prepare <agent_instance_id>")
    print(
        "                              Prepare execution for the current team and inspect the grant"
    )
    print("  /policy summary             Show the current purge-policy summary")
    print("  /policy resolve [team_id|team_name] [member_removed|member_rejoined]")
    print("                              Resolve policy for one request context")
    print("  /lifecycle run-once [dry-run|live] [batch_size]")
    print("                              Trigger one lifecycle run-once request")
    print("  /quit                       Exit the control-plane CLI")


def format_http_error(exc: httpx.HTTPError) -> str:
    """
    Convert one HTTPX exception into a concise user-facing CLI message.

    Why this function exists:
    - terminal workflows need short, actionable error summaries instead of raw
      exception repr output

    How to use it:
    - call from command handlers when one API request fails

    Example:
    - `print(format_http_error(exc))`
    """

    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            raw_detail = payload.get("detail")
            if raw_detail is not None:
                detail = f" detail={raw_detail}"
        return f"HTTP {response.status_code} {response.request.method} {response.request.url}{detail}"
    return str(exc)


def _truncate(value: str | None, width: int) -> str:
    """Return one terminal-friendly string truncated to the requested width."""

    raw = (value or "").strip()
    if len(raw) <= width:
        return raw
    if width <= 3:
        return raw[:width]
    return raw[: width - 3] + "..."


def _print_section(title: str, *, color_enabled: bool) -> None:
    """Print one dim section header used consistently across the CLI."""

    print(colorize(title, color=ANSI_DIM, enabled=color_enabled, bold=True))
    print(colorize("  " + "-" * 88, color=ANSI_DIM, enabled=color_enabled))


def _print_model_json(
    title: str,
    *,
    json_text: str,
    color_enabled: bool,
) -> None:
    """
    Print one titled JSON block with the CLI's shared visual style.

    Why this function exists:
    - several commands inspect complex typed payloads best shown as formatted
      JSON

    How to use it:
    - pass a pre-rendered JSON string from the typed API client

    Example:
    - `_print_model_json("Runtime binding", json_text=client.dump_model_json(binding), color_enabled=True)`
    """

    _print_section(title, color_enabled=color_enabled)
    print(json_text)


@dataclass(frozen=True)
class ColumnSpec:
    """One column definition used by the generic _print_table renderer."""

    header: str
    width: int
    getter: Callable[..., str]
    color: str | None = None
    align: str = "<"


def _print_table(
    title: str,
    rows: list[Any],
    columns: list[ColumnSpec],
    *,
    color_enabled: bool,
) -> None:
    """Render a titled, aligned table from a list of ColumnSpec definitions."""

    _print_section(title, color_enabled=color_enabled)
    header_parts = [
        colorize(
            f"{col.header:{col.align}{col.width}}",
            color=ANSI_DIM,
            enabled=color_enabled,
            bold=True,
        )
        for col in columns
    ]
    print("  " + "  ".join(header_parts))
    for row in rows:
        row_parts = []
        for col in columns:
            value = _truncate(col.getter(row), col.width)
            cell = f"{value:{col.align}{col.width}}"
            if col.color:
                cell = colorize(cell, color=col.color, enabled=color_enabled)
            row_parts.append(cell)
        print("  " + "  ".join(row_parts))


def _print_bootstrap_summary(
    bootstrap: FrontendBootstrap,
    *,
    color_enabled: bool,
) -> None:
    """Render a compact human-readable frontend bootstrap summary."""

    _print_section("Frontend Bootstrap", color_enabled=color_enabled)
    permission_flags = [
        name
        for name, held in (
            ("platform_admin", bootstrap.permissions.is_platform_admin),
            ("platform_observer", bootstrap.permissions.is_platform_observer),
        )
        if held
    ]
    permissions = ", ".join(permission_flags) or "none"
    print(
        "  User:      "
        + colorize(
            bootstrap.current_user.username or "unknown-user",
            color=ANSI_GREEN,
            enabled=color_enabled,
            bold=True,
        )
    )
    print(
        "  Team:      "
        + colorize(
            bootstrap.active_team.id,
            color=ANSI_CYAN,
            enabled=color_enabled,
            bold=True,
        )
        + "  "
        + _truncate(bootstrap.active_team.name, 40)
    )
    print(f"  Teams:     {len(bootstrap.available_teams)} visible team(s)")
    print(f"  GCU:       {bootstrap.gcu_version or 'not enforced'}")
    print(f"  Features:  {bootstrap.feature_flags.model_dump(mode='json')}")
    print(f"  Perms:     {permissions}")


def _print_team_table(teams: list[Team], *, color_enabled: bool) -> None:
    """Render the team list in a compact table."""

    _print_table(
        "Teams",
        teams,
        [
            ColumnSpec("id", 20, lambda t: str(t.id), color=ANSI_CYAN),
            ColumnSpec("name", 32, lambda t: t.name),
            ColumnSpec("members", 7, lambda t: str(t.member_count or 0), align=">"),
            ColumnSpec("joining", 12, lambda t: str(t.joining_mode.value), align=">"),
        ],
        color_enabled=color_enabled,
    )
    if teams:
        print("  Tip: use `/team <id or visible name>`.")


def _normalized_team_selector(selector: str | None) -> str:
    """
    Normalize one team selector for case-insensitive CLI matching.

    Why this function exists:
    - operators should be able to type one visible team name such as `fredlab`
      without worrying about case differences
    - the CLI still needs deterministic matching against cached team metadata

    How to use it:
    - pass one raw team selector from command input or cached team metadata

    Example:
    - `_normalized_team_selector("Fredlab")`
    """

    return (selector or "").strip().casefold()


def _preferred_team_selector(team: Team) -> str:
    """
    Return the most human-friendly selector for one team.

    Why this function exists:
    - prompts and completion should prefer readable names over raw UUIDs when a
      visible name exists
    - the personal team should keep the stable short selector `personal`

    How to use it:
    - pass one cached `Team` model and use the returned selector in prompts or
      completion candidates

    Example:
    - `_preferred_team_selector(team)`
    """

    team_id = str(team.id).strip()
    if team_id.startswith("personal-"):
        return "personal"

    team_name = team.name.strip()
    if team_name and _normalized_team_selector(team_name) != _normalized_team_selector(
        team_id
    ):
        return team_name
    return team_id


def _team_selector_candidates(
    teams: list[Team],
    *,
    include_clear: bool = False,
) -> list[str]:
    """
    Return the accepted CLI selectors for the currently visible teams.

    Why this function exists:
    - completion should expose both readable team names and canonical ids
    - selector ordering should stay stable and deduplicated across commands

    How to use it:
    - pass the cached team list from shell state
    - set `include_clear=True` for `/team`

    Example:
    - `_team_selector_candidates(state.known_teams, include_clear=True)`
    """

    candidates: list[str] = ["clear"] if include_clear else []
    for team in teams:
        for candidate in (_preferred_team_selector(team), str(team.id)):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _matching_team_candidates(prefix: str, *, teams: list[Team]) -> list[str]:
    """
    Return team selector completions matching one typed prefix.

    Why this function exists:
    - team completion should accept the same readable selectors that command
      resolution accepts
    - matching should stay case-insensitive for visible team names

    How to use it:
    - pass the typed prefix after `/team`, `/team-info`, or another
      team-scoped command

    Example:
    - `_matching_team_candidates("fr", teams=state.known_teams)`
    """

    normalized_prefix = _normalized_team_selector(prefix)
    return [
        candidate
        for candidate in _team_selector_candidates(teams)
        if _normalized_team_selector(candidate).startswith(normalized_prefix)
    ]


def _resolve_team_selector(
    ctx: ControlPlaneCommandContext,
    selector: str,
) -> str:
    """
    Resolve one CLI team selector into the canonical control-plane team id.

    Why this function exists:
    - operators should be able to use either a raw team id or the visible team
      name shown by `/teams`
    - all team-scoped commands should share one consistent resolution rule

    How to use it:
    - pass the typed selector from `/team`, `/team-info`, `/sessions`, or any
      other team-scoped command
    - the function returns the canonical team id accepted by the backend

    Example:
    - `team_id = _resolve_team_selector(ctx, "fredlab")`
    """

    stripped_selector = selector.strip()
    if not stripped_selector:
        return stripped_selector

    def _matches_name(candidate_team: Team) -> bool:
        return _normalized_team_selector(
            candidate_team.name
        ) == _normalized_team_selector(stripped_selector)

    for team in ctx.state.known_teams:
        if str(team.id) == stripped_selector:
            return str(team.id)

    matches = [team for team in ctx.state.known_teams if _matches_name(team)]
    if not matches:
        known_teams = refresh_known_teams(ctx, silent=True)
        for team in known_teams:
            if str(team.id) == stripped_selector:
                return str(team.id)
        matches = [team for team in known_teams if _matches_name(team)]

    if len(matches) == 1:
        return str(matches[0].id)
    if len(matches) > 1:
        conflicting_ids = ", ".join(str(team.id) for team in matches)
        raise ValueError(
            f"Ambiguous team selector {selector!r}. Use one explicit team id: {conflicting_ids}"
        )
    return stripped_selector


def _display_team_reference(
    state: ControlPlaneShellState,
    team_id: str | None,
) -> str:
    """
    Return one prompt-friendly label for the current team context.

    Why this function exists:
    - the shell prompt and `/whoami` should stay readable even when the
      canonical team id is a UUID
    - the CLI already caches visible teams, so it can reuse that metadata for a
      friendlier label

    How to use it:
    - pass the current team id stored in shell state
    - the function falls back to the raw id when no cached team metadata exists

    Example:
    - `label = _display_team_reference(state, state.current_team_id)`
    """

    if not team_id:
        return "not set"
    team = next(
        (candidate for candidate in state.known_teams if str(candidate.id) == team_id),
        None,
    )
    if team is None:
        return team_id
    return _preferred_team_selector(team)


def _print_team_details(team: TeamWithPermissions, *, color_enabled: bool) -> None:
    """Render one team metadata block."""

    _print_section("Team", color_enabled=color_enabled)
    print(
        "  id:         "
        + colorize(team.id, color=ANSI_CYAN, enabled=color_enabled, bold=True)
    )
    print(f"  name:       {team.name}")
    print(
        f"  description:{' ' if team.description else ''}{team.description or 'none'}"
    )
    print(f"  joining:    {team.joining_mode.value}")
    print(f"  members:    {team.member_count or 0}")
    print(
        "  admins:     "
        + (", ".join((admin.username or admin.id) for admin in team.admins) or "none")
    )
    print(
        "  permissions:"
        f" {', '.join(permission.value for permission in team.permissions) or 'none'}"
    )


def _print_members_table(members: list[TeamMember], *, color_enabled: bool) -> None:
    """Render the team-member list in a compact table."""

    _print_table(
        "Members",
        members,
        [
            ColumnSpec(
                "roles",
                34,
                lambda m: ", ".join(relation.value for relation in m.relations),
            ),
            ColumnSpec(
                "username", 28, lambda m: m.user.username or "", color=ANSI_GREEN
            ),
            ColumnSpec("email", 32, lambda m: m.user.email or ""),
        ],
        color_enabled=color_enabled,
    )


def _print_template_table(
    templates: list[AgentTemplateSummary],
    *,
    color_enabled: bool,
) -> None:
    """Render the template list in a compact table."""

    _print_table(
        "Templates",
        templates,
        [
            ColumnSpec("template_id", 36, lambda t: t.template_id, color=ANSI_CYAN),
            ColumnSpec("display_name", 30, lambda t: t.display_name),
            ColumnSpec("status", 10, lambda t: t.status),
        ],
        color_enabled=color_enabled,
    )


def _print_instance_table(
    instances: list[ManagedAgentInstanceSummary],
    *,
    color_enabled: bool,
) -> None:
    """Render the managed-agent instance list in a compact table."""

    _print_table(
        "Instances",
        instances,
        [
            ColumnSpec(
                "instance_id", 32, lambda i: i.agent_instance_id, color=ANSI_CYAN
            ),
            ColumnSpec("display_name", 30, lambda i: i.display_name),
            ColumnSpec("status", 10, lambda i: i.status),
        ],
        color_enabled=color_enabled,
    )


def _print_sessions_table(
    sessions: list[SessionListItem],
    *,
    color_enabled: bool,
) -> None:
    """Render the session metadata list in a compact table."""

    _print_table(
        "Sessions",
        sessions,
        [
            ColumnSpec("session_id", 34, lambda s: s.session_id, color=ANSI_CYAN),
            ColumnSpec("title", 30, lambda s: s.title or ""),
            ColumnSpec(
                "updated_at",
                24,
                lambda s: (
                    s.updated_at.isoformat(timespec="seconds") if s.updated_at else "-"
                ),
            ),
        ],
        color_enabled=color_enabled,
    )


def _print_prompt_table(
    prompts: list[PromptSummary],
    *,
    color_enabled: bool,
) -> None:
    """Render the prompt-library list in a compact table."""

    _print_table(
        "Prompts",
        prompts,
        [
            ColumnSpec("prompt_id", 36, lambda p: p.id, color=ANSI_CYAN),
            ColumnSpec("name", 26, lambda p: p.name),
            ColumnSpec(
                "updated_at",
                24,
                lambda p: (
                    p.updated_at.isoformat(timespec="seconds") if p.updated_at else "-"
                ),
            ),
        ],
        color_enabled=color_enabled,
    )


def refresh_known_teams(
    ctx: ControlPlaneCommandContext,
    *,
    silent: bool = False,
) -> list[Team]:
    """
    Refresh the cached team list from control-plane.

    Why this function exists:
    - both command execution and autocompletion need one shared team cache

    How to use it:
    - call before rendering `/teams` or when you need fresh team ids for the
      interactive shell

    Example:
    - `teams = refresh_known_teams(ctx)`
    """

    try:
        teams = ctx.client.list_teams()
    except httpx.HTTPError:
        if silent:
            return ctx.state.known_teams
        raise
    ctx.state.known_teams = teams
    return teams


def refresh_team_scoped_caches(
    ctx: ControlPlaneCommandContext,
    team_id: str,
    *,
    silent: bool = False,
) -> None:
    """
    Refresh the cached templates and instances for one team context.

    Why this function exists:
    - the shell should autocomplete and display team-scoped resources without
      refetching them redundantly in multiple places

    How to use it:
    - call after changing the current team or before running team-scoped
      inspection commands

    Example:
    - `refresh_team_scoped_caches(ctx, "fredlab")`
    """

    try:
        ctx.state.known_templates = ctx.client.list_agent_templates(team_id)
        ctx.state.known_instances = ctx.client.list_agent_instances(team_id)
        ctx.state.known_prompts = ctx.client.list_prompts(team_id)
    except httpx.HTTPError:
        if not silent:
            raise


def completion_candidates(
    line_buffer: str,
    *,
    state: ControlPlaneShellState,
) -> list[str]:
    """
    Return tab-completion candidates for one control-plane shell prompt line.

    Why this function exists:
    - the control-plane CLI should match `fred-agent-chat` in discoverability
      and terminal ergonomics

    How to use it:
    - pass the current prompt line plus the current shell state caches

    Example:
    - `matches = completion_candidates("/team fr", state=state)`
    """

    stripped = line_buffer.lstrip()
    template_ids = [template.template_id for template in state.known_templates]
    instance_ids = [instance.agent_instance_id for instance in state.known_instances]
    prompt_ids = [prompt.id for prompt in state.known_prompts]

    if stripped.startswith("/team-info "):
        prefix = stripped.removeprefix("/team-info ").strip()
        return _matching_team_candidates(prefix, teams=state.known_teams)
    if stripped.startswith("/team "):
        prefix = stripped.removeprefix("/team ").strip()
        return [
            candidate
            for candidate in _team_selector_candidates(
                state.known_teams, include_clear=True
            )
            if _normalized_team_selector(candidate).startswith(
                _normalized_team_selector(prefix)
            )
        ]
    if stripped.startswith("/members "):
        prefix = stripped.removeprefix("/members ").strip()
        return _matching_team_candidates(prefix, teams=state.known_teams)
    if stripped.startswith("/templates "):
        prefix = stripped.removeprefix("/templates ").strip()
        return _matching_team_candidates(prefix, teams=state.known_teams)
    if stripped.startswith("/instances "):
        prefix = stripped.removeprefix("/instances ").strip()
        return _matching_team_candidates(prefix, teams=state.known_teams)
    if stripped.startswith("/sessions "):
        prefix = stripped.removeprefix("/sessions ").strip()
        return _matching_team_candidates(prefix, teams=state.known_teams)
    if stripped.startswith("/prompts "):
        prefix = stripped.removeprefix("/prompts ").strip()
        return _matching_team_candidates(prefix, teams=state.known_teams)
    if stripped.startswith("/enroll "):
        prefix = stripped.removeprefix("/enroll ").strip()
        return [
            template_id
            for template_id in template_ids
            if template_id.startswith(prefix)
        ]
    if stripped.startswith("/prompt "):
        prefix = stripped.removeprefix("/prompt ").strip()
        return [prompt_id for prompt_id in prompt_ids if prompt_id.startswith(prefix)]
    if stripped.startswith("/prompt-update "):
        prefix = stripped.removeprefix("/prompt-update ").strip()
        first_token = prefix.split(" ", 1)[0]
        return [
            prompt_id for prompt_id in prompt_ids if prompt_id.startswith(first_token)
        ]
    if stripped.startswith("/prompt-delete "):
        prefix = stripped.removeprefix("/prompt-delete ").strip()
        return [prompt_id for prompt_id in prompt_ids if prompt_id.startswith(prefix)]
    if stripped.startswith("/unbind "):
        prefix = stripped.removeprefix("/unbind ").strip()
        return [
            instance_id
            for instance_id in instance_ids
            if instance_id.startswith(prefix)
        ]
    if stripped.startswith("/runtime "):
        prefix = stripped.removeprefix("/runtime ").strip()
        return [
            instance_id
            for instance_id in instance_ids
            if instance_id.startswith(prefix)
        ]
    if stripped.startswith("/prepare "):
        prefix = stripped.removeprefix("/prepare ").strip()
        return [
            instance_id
            for instance_id in instance_ids
            if instance_id.startswith(prefix)
        ]
    if stripped.startswith("/policy resolve "):
        suffix = stripped.removeprefix("/policy resolve ").strip()
        if " " not in suffix:
            return _matching_team_candidates(suffix, teams=state.known_teams)
        team_part, trigger_prefix = suffix.split(" ", 1)
        valid_team_selectors = _team_selector_candidates(state.known_teams)
        if team_part and not any(
            _normalized_team_selector(candidate) == _normalized_team_selector(team_part)
            for candidate in valid_team_selectors
        ):
            return []
        return [
            trigger.value
            for trigger in LifecycleTrigger
            if trigger.value.startswith(trigger_prefix.strip())
        ]
    if stripped.startswith("/lifecycle run-once "):
        prefix = stripped.removeprefix("/lifecycle run-once ").strip()
        return [option for option in ("dry-run", "live") if option.startswith(prefix)]
    if stripped.startswith("/lifecycle "):
        prefix = stripped.removeprefix("/lifecycle ").strip()
        return ["run-once"] if "run-once".startswith(prefix) else []
    if stripped.startswith("/policy "):
        prefix = stripped.removeprefix("/policy ").strip()
        return [sc for sc in ("summary", "resolve") if sc.startswith(prefix)]
    if stripped.startswith("/"):
        return complete_slash_commands(stripped, commands=_COMMANDS)
    return []


def _resolve_team_id(
    ctx: ControlPlaneCommandContext,
    explicit_team_id: str | None,
) -> str:
    """
    Resolve the team id for one team-scoped command.

    Why this function exists:
    - the shell supports a persistent team context, but commands may also
      override it explicitly

    How to use it:
    - pass the parsed explicit team id or `None`

    Example:
    - `team_id = _resolve_team_id(ctx, None)`
    """

    team_id = explicit_team_id or ctx.state.current_team_id
    if not team_id:
        raise ValueError(
            "No team context is set. Use /team <team_id> first or pass an explicit team id."
        )
    return _resolve_team_selector(ctx, team_id)


def _split_command_arguments(command_line: str) -> list[str]:
    """Split one slash command line using shell-style quoting rules."""

    try:
        return shlex.split(command_line)
    except ValueError as exc:
        raise ValueError(f"Could not parse command line: {exc}") from exc


def run_command(
    command_line: str,
    *,
    ctx: ControlPlaneCommandContext,
) -> bool:
    """
    Execute one control-plane shell command.

    Why this function exists:
    - interactive mode and one-shot mode should share the same command
      implementation

    How to use it:
    - pass one slash command line such as `/teams` or `/prepare abc`
    - returns `False` when the shell should exit

    Example:
    - `keep_running = run_command("/teams", ctx=ctx)`
    """

    parts = _split_command_arguments(command_line)
    if not parts:
        return True

    command = parts[0]
    args = parts[1:]
    color_enabled = ctx.color_enabled

    if command == "/help":
        print_help()
        return True

    if command in {"/quit", "/exit"}:
        return False

    if command == "/login":
        if ctx.auth_session is None:
            raise ValueError(
                "Login is not configured. Provide Keycloak settings or run from a control-plane project with configuration.yaml."
            )
        ctx.auth_session.login_with_pkce(
            callback_host=ctx.callback_host,
            callback_port=ctx.callback_port,
        )
        print(f"Logged in as {ctx.auth_session.current_username()}.")
        return True

    if command == "/login-password":
        if ctx.auth_session is None:
            raise ValueError(
                "Login is not configured. Provide Keycloak settings or run from a control-plane project with configuration.yaml."
            )
        username = args[0] if args else (ctx.auth_session.current_username() or "")
        if not username:
            username = input("Username: ").strip()
        if not username:
            raise ValueError("Username cannot be empty.")
        password = getpass.getpass("Password: ")
        ctx.auth_session.login(username=username, password=password)
        print(f"Logged in as {ctx.auth_session.current_username()}.")
        return True

    if command == "/logout":
        if ctx.auth_session is None or not ctx.auth_session.is_logged_in():
            print("No cached login session to clear.")
            return True
        ctx.auth_session.logout()
        print("Logged out.")
        return True

    if command == "/whoami":
        details: ControlPlaneUserDetails = ctx.client.get_user_details()
        auth_desc = (
            ctx.auth_session.describe()
            if ctx.auth_session is not None
            else "security disabled"
        )
        _print_section("Who Am I", color_enabled=color_enabled)
        print(f"  Auth:          {auth_desc}")
        if details.currentUser is not None:
            print(
                "  User id:       "
                + colorize(
                    details.currentUser.id,
                    color=ANSI_CYAN,
                    enabled=color_enabled,
                    bold=True,
                )
            )
        print(
            "  Current team:  "
            + colorize(
                _display_team_reference(ctx.state, ctx.state.current_team_id),
                color=ANSI_CYAN if ctx.state.current_team_id else ANSI_YELLOW,
                enabled=color_enabled,
                bold=bool(ctx.state.current_team_id),
            )
        )
        print(
            "  Personal team: "
            + colorize(
                details.personalTeam.id,
                color=ANSI_GREEN,
                enabled=color_enabled,
                bold=True,
            )
            + f"  {details.personalTeam.name}"
        )
        print(f"  GCU:           {details.cguValidated or 'not recorded'}")
        return True

    if command == "/bootstrap":
        bootstrap = ctx.client.get_frontend_bootstrap()
        _print_bootstrap_summary(bootstrap, color_enabled=color_enabled)
        return True

    if command == "/teams":
        teams = refresh_known_teams(ctx)
        _print_team_table(teams, color_enabled=color_enabled)
        return True

    if command == "/team":
        if not args:
            label = _display_team_reference(ctx.state, ctx.state.current_team_id)
            print(
                "Current team: "
                + colorize(
                    label,
                    color=ANSI_CYAN if ctx.state.current_team_id else ANSI_YELLOW,
                    enabled=color_enabled,
                    bold=bool(ctx.state.current_team_id),
                )
            )
            return True
        candidate = args[0]
        if candidate == "clear":
            ctx.state.current_team_id = None
            ctx.state.known_templates = []
            ctx.state.known_instances = []
            ctx.state.known_prompts = []
            print("Cleared the current team context.")
            return True
        team = ctx.client.get_team(_resolve_team_selector(ctx, candidate))
        ctx.state.current_team_id = team.id
        refresh_known_teams(ctx, silent=True)
        refresh_team_scoped_caches(ctx, team.id, silent=True)
        _print_team_details(team, color_enabled=color_enabled)
        return True

    if command == "/team-info":
        team_id = _resolve_team_id(ctx, args[0] if args else None)
        team = ctx.client.get_team(team_id)
        _print_team_details(team, color_enabled=color_enabled)
        return True

    if command == "/members":
        team_id = _resolve_team_id(ctx, args[0] if args else None)
        members = ctx.client.list_team_members(team_id)
        _print_members_table(members, color_enabled=color_enabled)
        return True

    if command == "/templates":
        team_id = _resolve_team_id(ctx, args[0] if args else None)
        templates = ctx.client.list_agent_templates(team_id)
        ctx.state.known_templates = templates
        _print_template_table(templates, color_enabled=color_enabled)
        return True

    if command == "/instances":
        team_id = _resolve_team_id(ctx, args[0] if args else None)
        instances = ctx.client.list_agent_instances(team_id)
        ctx.state.known_instances = instances
        _print_instance_table(instances, color_enabled=color_enabled)
        return True

    if command == "/prompts":
        team_id = _resolve_team_id(ctx, args[0] if args else None)
        prompts = ctx.client.list_prompts(team_id)
        ctx.state.known_prompts = prompts
        _print_prompt_table(prompts, color_enabled=color_enabled)
        return True

    if command == "/prompt":
        if not args:
            raise ValueError("Usage: /prompt <prompt_id>")
        team_id = _resolve_team_id(ctx, None)
        prompt: PromptDetail = ctx.client.get_prompt(team_id, args[0])
        _print_model_json(
            "Prompt Detail",
            json_text=ctx.client.dump_model_json(prompt),
            color_enabled=color_enabled,
        )
        return True

    if command == "/prompt-create":
        if len(args) < 2:
            raise ValueError("Usage: /prompt-create <name> <text> [description]")
        team_id = _resolve_team_id(ctx, None)
        created = ctx.client.create_prompt(
            team_id,
            name=args[0],
            text=args[1],
            description=args[2] if len(args) > 2 else None,
        )
        ctx.state.known_prompts = ctx.client.list_prompts(team_id)
        _print_model_json(
            "Created Prompt",
            json_text=ctx.client.dump_model_json(created),
            color_enabled=color_enabled,
        )
        return True

    if command == "/prompt-update":
        if len(args) < 3:
            raise ValueError(
                "Usage: /prompt-update <prompt_id> <name> <text> [description]"
            )
        team_id = _resolve_team_id(ctx, None)
        updated = ctx.client.update_prompt(
            team_id,
            args[0],
            name=args[1],
            text=args[2],
            description=args[3] if len(args) > 3 else None,
        )
        ctx.state.known_prompts = ctx.client.list_prompts(team_id)
        _print_model_json(
            "Updated Prompt",
            json_text=ctx.client.dump_model_json(updated),
            color_enabled=color_enabled,
        )
        return True

    if command == "/prompt-delete":
        if not args:
            raise ValueError("Usage: /prompt-delete <prompt_id>")
        team_id = _resolve_team_id(ctx, None)
        ctx.client.delete_prompt(team_id, args[0])
        ctx.state.known_prompts = ctx.client.list_prompts(team_id)
        print(
            "Deleted prompt "
            + colorize(args[0], color=ANSI_CYAN, enabled=color_enabled, bold=True)
            + "."
        )
        return True

    if command == "/enroll":
        if not args:
            raise ValueError(
                "Usage: /enroll <template_id> [display_name] [usage_statement]"
            )
        team_id = _resolve_team_id(ctx, None)
        template_id = args[0]
        templates = ctx.state.known_templates or ctx.client.list_agent_templates(
            team_id
        )
        ctx.state.known_templates = templates
        template = next(
            (item for item in templates if item.template_id == template_id), None
        )
        if template is None:
            raise ValueError(
                f"Unknown template_id {template_id!r}. Run /templates first for the current team."
            )
        display_name = args[1] if len(args) > 1 else template.display_name
        usage_statement = args[2] if len(args) > 2 else template.description
        created = ctx.client.enroll_agent_instance(
            team_id,
            template_id=template.template_id,
            display_name=display_name,
            description=template.description,
            usage_statement=usage_statement,
        )
        ctx.state.known_instances = ctx.client.list_agent_instances(team_id)
        _print_model_json(
            "Enrolled Agent Instance",
            json_text=ctx.client.dump_model_json(created),
            color_enabled=color_enabled,
        )
        return True

    if command == "/unbind":
        if not args:
            raise ValueError("Usage: /unbind <agent_instance_id>")
        team_id = _resolve_team_id(ctx, None)
        ctx.client.unenroll_agent_instance(team_id, args[0])
        ctx.state.known_instances = ctx.client.list_agent_instances(team_id)
        print(
            "Deleted managed instance "
            + colorize(args[0], color=ANSI_CYAN, enabled=color_enabled, bold=True)
            + "."
        )
        return True

    if command == "/runtime":
        if not args:
            raise ValueError("Usage: /runtime <agent_instance_id>")
        team_id = _resolve_team_id(ctx, None)
        binding: ManagedAgentRuntimeBinding = ctx.client.get_runtime_binding(
            team_id, args[0]
        )
        _print_model_json(
            "Runtime Binding",
            json_text=ctx.client.dump_model_json(binding),
            color_enabled=color_enabled,
        )
        return True

    if command == "/sessions":
        team_id = _resolve_team_id(ctx, args[0] if args else None)
        sessions = ctx.client.list_sessions(team_id)
        _print_sessions_table(sessions, color_enabled=color_enabled)
        return True

    if command == "/prepare":
        if not args:
            raise ValueError("Usage: /prepare <agent_instance_id>")
        team_id = _resolve_team_id(ctx, None)
        preparation: ExecutionPreparation = ctx.client.prepare_execution(
            team_id, args[0]
        )
        _print_model_json(
            "Execution Preparation",
            json_text=ctx.client.dump_model_json(preparation),
            color_enabled=color_enabled,
        )
        return True

    if command == "/policy":
        if not args:
            raise ValueError(
                "Usage: /policy summary | /policy resolve [team_id] [trigger]"
            )
        subcommand = args[0]
        if subcommand == "summary":
            summary: ControlPlanePolicySummary = ctx.client.get_policy_summary()
            _print_section("Policy Summary", color_enabled=color_enabled)
            print(f"  mode:            {summary.mode}")
            print(
                f"  retention:       {summary.retention} ({summary.retention_seconds}s)"
            )
            print(
                f"  cancel_on_rejoin:{' ' if summary.cancel_on_rejoin else ''}{summary.cancel_on_rejoin}"
            )
            print(f"  default_rules:   {summary.default_rule_count}")
            print(f"  matched_rule_id: {summary.matched_rule_id or 'none'}")
            print(f"  catalog_path:    {summary.catalog_path}")
            return True
        if subcommand == "resolve":
            team_id = args[1] if len(args) > 1 else ctx.state.current_team_id
            resolved_team_id = (
                _resolve_team_selector(ctx, team_id) if team_id is not None else None
            )
            trigger = (
                LifecycleTrigger(args[2])
                if len(args) > 2
                else LifecycleTrigger.MEMBER_REMOVED
            )
            policy_result: PolicyEvaluationResult = ctx.client.resolve_policy(
                team_id=resolved_team_id,
                trigger=trigger,
            )
            _print_model_json(
                "Policy Resolution",
                json_text=ctx.client.dump_model_json(policy_result),
                color_enabled=color_enabled,
            )
            return True
        raise ValueError("Usage: /policy summary | /policy resolve [team_id] [trigger]")

    if command == "/lifecycle":
        if not args or args[0] != "run-once":
            raise ValueError("Usage: /lifecycle run-once [dry-run|live] [batch_size]")
        mode = args[1] if len(args) > 1 else "dry-run"
        dry_run = True
        if mode == "live":
            dry_run = False
        elif mode != "dry-run":
            raise ValueError("Usage: /lifecycle run-once [dry-run|live] [batch_size]")
        batch_size = int(args[2]) if len(args) > 2 else 100
        result: ControlPlaneWorkflowStartResponse = ctx.client.run_lifecycle_once(
            dry_run=dry_run,
            batch_size=batch_size,
        )
        _print_model_json(
            "Lifecycle Run Once",
            json_text=ctx.client.dump_model_json(result),
            color_enabled=color_enabled,
        )
        return True

    raise ValueError(
        f"Unknown command: {command!r}. Type /help for available commands."
    )


def run_interactive_shell(ctx: ControlPlaneCommandContext) -> int:
    """
    Run the interactive control-plane shell loop.

    Why this function exists:
    - developers need a first-class terminal console for product/admin flows
      without depending on the frontend

    How to use it:
    - call from `main()` when no one-shot command was provided

    Example:
    - `exit_code = run_interactive_shell(ctx)`
    """

    install_readline_completion(
        lambda line: completion_candidates(line, state=ctx.state)
    )
    print(
        "Connected to "
        + colorize(ctx.client.base_url, color=ANSI_DIM, enabled=ctx.color_enabled)
    )
    if ctx.auth_session is not None:
        print(
            "Auth: "
            + colorize(
                ctx.auth_session.describe(),
                color=ANSI_DIM,
                enabled=ctx.color_enabled,
            )
        )
    else:
        print("Auth: security disabled")
    if ctx.state.current_team_id:
        print(
            "Current team: "
            + colorize(
                _display_team_reference(ctx.state, ctx.state.current_team_id),
                color=ANSI_GREEN,
                enabled=ctx.color_enabled,
                bold=True,
            )
        )
    print("Type /help for available commands.")

    while True:
        team_fragment = _display_team_reference(ctx.state, ctx.state.current_team_id)
        if team_fragment == "not set":
            team_fragment = "-"
        prompt = f"control-plane[{team_fragment}]> "
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not line:
            continue
        if not line.startswith("/"):
            line = "/" + line

        try:
            keep_running = run_command(line, ctx=ctx)
        except ValueError as exc:
            print(exc)
            continue
        except httpx.HTTPError as exc:
            print(format_http_error(exc))
            continue
        if not keep_running:
            return 0


def main(argv: list[str] | None = None) -> int:
    """
    Run the Fred control-plane developer/operator CLI.

    Why this function exists:
    - it gives the control-plane surface the same first-class terminal entry
      point that `fred-agent-chat` already gives to runtime execution

    How to use it:
    - run `fred-control-plane-cli` for interactive mode
    - pass one command such as `teams` or `/teams` for one-shot usage

    Example:
    - `main(["--team-id", "fredlab", "templates"])`
    """

    env_file = load_cli_environment(log_prefix="[CONTROL-PLANE CONFIG]")
    parser = build_parser()
    args = parser.parse_args(argv)
    base_url = normalize_base_url(args.base_url)
    color_enabled_flag = colors_enabled(no_color=args.no_color)

    config_file = default_configuration_file()
    print(f"[control-plane] env file  : {env_file}")
    print(f"[control-plane] config    : {config_file} (exists={config_file.exists()})")
    print(f"[control-plane] api url   : {base_url}")

    http_client = httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0, read=60.0))
    auth_session = None
    client_secret_env_var_name = "_".join(
        ["FRED", "CONTROL", "PLANE", "KEYCLOAK", "CLIENT", "SECRET"]
    )
    login_config = resolve_keycloak_login_config(
        realm_url=args.keycloak_realm_url,
        client_id=args.keycloak_client_id,
        client_secret=args.keycloak_client_secret,
        realm_env_var="FRED_CONTROL_PLANE_KEYCLOAK_REALM_URL",
        client_id_env_var="FRED_CONTROL_PLANE_KEYCLOAK_CLIENT_ID",
        client_secret_env_var=client_secret_env_var_name,
    )
    if login_config is not None:
        print(
            f"[control-plane] auth      : keycloak realm={login_config.realm_url}"
            f"  client={login_config.client_id}"
        )
        auth_session = KeycloakUserSessionManager(
            config=login_config,
            cache_file=default_keycloak_token_file(
                env_var_name="FRED_CONTROL_PLANE_TOKEN_FILE",
                default_path="~/.config/fred/control-plane-cli-session.json",
            ),
            log_prefix="[control-plane]",
        )
    else:
        print("[control-plane] auth      : none  (security disabled)")

    if args.team_id:
        print(f"[control-plane] team      : {args.team_id}")

    static_token = os.getenv("FRED_CONTROL_PLANE_TOKEN")
    client = ControlPlaneApiClient(
        base_url=base_url,
        http_client=http_client,
        token_provider=build_cli_token_provider(
            auth_session=auth_session,
            static_token=static_token,
            log_prefix="[control-plane]",
        )
        if auth_session is not None or static_token
        else None,
    )
    state = ControlPlaneShellState(current_team_id=args.team_id)
    ctx = ControlPlaneCommandContext(
        client=client,
        state=state,
        color_enabled=color_enabled_flag,
        auth_session=auth_session,
        callback_host=args.keycloak_callback_host,
        callback_port=args.keycloak_callback_port,
    )

    try:
        if args.login and args.login_password:
            print("Choose only one login mode: `--login` or `--login-password`.")
            return 1
        if args.login:
            if auth_session is None:
                print(
                    "Login is not configured. Provide Keycloak settings or run from a control-plane project with configuration.yaml."
                )
                return 1
            auth_session.login_with_pkce(
                callback_host=args.keycloak_callback_host,
                callback_port=args.keycloak_callback_port,
            )
            print(f"Logged in as {auth_session.current_username()}.")
        if args.login_password:
            if auth_session is None:
                print(
                    "Login is not configured. Provide Keycloak settings or run from a control-plane project with configuration.yaml."
                )
                return 1
            username = args.username or input("Username: ").strip()
            if not username:
                print("Username cannot be empty.")
                return 1
            password = getpass.getpass("Password: ")
            auth_session.login(username=username, password=password)
            print(f"Logged in as {auth_session.current_username()}.")

        if args.command:
            raw_command = " ".join(args.command).strip()
            if raw_command and not raw_command.startswith("/"):
                raw_command = "/" + raw_command
            try:
                run_command(raw_command, ctx=ctx)
                return 0
            except ValueError as exc:
                print(exc)
                return 1
            except httpx.HTTPError as exc:
                print(format_http_error(exc))
                return 1

        refresh_known_teams(ctx, silent=True)
        if state.current_team_id:
            state.current_team_id = _resolve_team_selector(ctx, state.current_team_id)
            refresh_team_scoped_caches(ctx, state.current_team_id, silent=True)

        return run_interactive_shell(ctx)
    finally:
        if auth_session is not None:
            auth_session.close()
        http_client.close()


if __name__ == "__main__":
    raise SystemExit(main())
