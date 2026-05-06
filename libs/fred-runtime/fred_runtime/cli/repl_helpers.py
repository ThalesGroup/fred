from __future__ import annotations

import uuid
from typing import Any, Literal

from fred_core.cli.ui import (
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_WHITE,
    ANSI_YELLOW,
    colorize,
)

from .pod_client import AgentPodClient

ExecutionMode = Literal["stream", "final", "eval"]


def print_help() -> None:
    """Print the supported interactive chat commands."""
    print("Commands:")
    print(
        "  /help [question]          Show this help, or ask a question in natural language"
    )
    print()
    print("  Agent & session:")
    print("  /agents                   Refresh and list available agent ids")
    print("  /agent <agent_id>         Switch the active agent")
    print("  /inspect                  Show current agent fields and tuning surface")
    print(
        "  /run <scenario>           Send scenario keyword (tab-completes for test agent)"
    )
    print(
        "  /session [<N>|<id>]       Show current session, or switch by index / exact id"
    )
    print("  /session-new              Start a fresh session with a generated id")
    print("  /session-info [id]        Session metadata (timestamps, agents, tokens)")
    print("  /sessions                 List sessions with message count and preview")
    print("  /team [team_id|clear]     Show, set, or clear the current team scope")
    print()
    print("  Tuning:")
    print("  /tuning                   Show active in-session tuning overrides")
    print("  /tune key=value           Set a tuning override (clear with key=)")
    print()
    print("  Observability:")
    print("  /history [--raw] [id]     Show conversation history")
    print("  /kpi [limit]              Show recent agent.turn_completed events")
    print("  /kpi prom [pattern]       Show Prometheus metrics snapshot")
    print("  /audit [limit]            Show recent security audit events")
    print("  /checkpoints [limit]      List checkpoint threads with sizes")
    print("  /checkpoint <session_id>  Inspect all checkpoints for one session")
    print("  /stats                    Show aggregate checkpoint storage statistics")
    print("  /context                  Show current execution context summary")
    print()
    print("  Auth:")
    print("  /login                    Browser PKCE login")
    print("  /login-password [user]    Username/password login")
    print(
        "  /whoami                   Show identity, auth, team, agent, session, pod URL"
    )
    print("  /logout                   Clear the cached login session")
    print("  /mode [stream|final|eval] Show or change the execution mode")
    print()
    print("  Cleanup (irreversible — always prompt for confirmation):")
    print("  /delete-session [id]      Delete history rows only (checkpoint kept)")
    print("  /delete-checkpoint [id]   Delete checkpoint only (history kept)")
    print("  /purge-session [id]       Delete BOTH history and checkpoint")
    print("  /quit                     Exit the chat client")


_CLI_HELP_CONTEXT = (
    "You are an interactive help assistant embedded in the Fred CLI chat tool "
    "(fred-agents-cli). Answer the user's question about how to use the CLI. "
    "Respond in the same language as the user's question. Be concise and practical.\n\n"
    "Available commands:\n"
    "  /help [question]          Show command reference or ask a question in natural language\n"
    "  /agents                   Refresh and list available agent ids\n"
    "  /agent <agent_id>         Switch the active agent\n"
    "  /inspect                  Show the current agent template fields and tuning surface\n"
    "  /run <scenario>           Send a scenario keyword directly (tab-completes for test agent)\n"
    "  /tuning                   Show active in-session tuning overrides\n"
    "  /tune key=value           Set a tuning override (clear with key=)\n"
    "  /login                    Log in through browser PKCE and cache the user session\n"
    "  /login-password [user]    Use direct username/password login as a local fallback\n"
    "  /whoami                   Show identity, auth, team, agent, session, pod URL\n"
    "  /logout                   Clear the cached login session\n"
    "  /mode [stream|final|eval] Show or change the execution mode (default: stream)\n"
    "  /session [<N>|<id>]       Show current session, or switch by index / exact id\n"
    "  /session-new              Start a fresh session with a generated id\n"
    "  /session-info [id]        Show session metadata (timestamps, agents, tokens, title)\n"
    "  /team [team_id|clear]     Show, set, or clear the current team scope\n"
    "  /sessions                 List sessions with message count and first/last preview\n"
    "  /history [--raw] [id]     Show conversation history (--raw: full JSON payload)\n"
    "  /kpi [limit]              Show recent agent.turn_completed events from the pod\n"
    "  /kpi prom [pattern]       Show Prometheus metrics snapshot (optional filter)\n"
    "  /audit [limit]            Show recent security audit events from the pod\n"
    "  /checkpoints [limit]      List checkpoint threads with sizes (default limit=20)\n"
    "  /checkpoint <session_id>  Inspect all checkpoints for one session\n"
    "  /stats                    Show aggregate checkpoint storage statistics\n"
    "  /context                  Show current execution context summary\n"
    "  /delete-session [id]      Delete history rows only (checkpoint kept) — irreversible\n"
    "  /delete-checkpoint [id]   Delete checkpoint only (history kept) — irreversible\n"
    "  /purge-session [id]       Delete BOTH history and checkpoint — irreversible\n"
    "  /quit                     Exit the chat client\n\n"
    "Any text that does not start with / is sent as a message to the current agent.\n\n"
    "User question: "
)


def _ask_cli_help(
    *,
    question: str,
    client: AgentPodClient,
    agent_id: str,
    user_id: str,
    team_id: str | None,
    color_enabled: bool,
) -> None:
    compound = _CLI_HELP_CONTEXT + question
    ephemeral_session = f"__help__{uuid.uuid4().hex}"
    try:
        payload: dict[str, Any] = client.execute(
            agent_id=agent_id,
            message=compound,
            session_id=ephemeral_session,
            user_id=user_id,
            team_id=team_id,
        )
    except Exception as exc:
        print(
            colorize(
                f"[help] Pod unavailable ({exc}). Showing command reference instead.",
                color=ANSI_DIM,
                enabled=color_enabled,
            )
        )
        print_help()
        return
    if "error" in payload:
        print(
            colorize(
                f"[help] Agent error: {payload['error']}. Showing command reference.",
                color=ANSI_DIM,
                enabled=color_enabled,
            )
        )
        print_help()
        return
    content = payload.get("content")
    if not isinstance(content, str):
        print_help()
        return
    print(content)


def fmt_bytes(n: int) -> str:
    """Human-readable byte size with one decimal place."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


_MODE_COLORS: dict[str, str] = {
    "stream": ANSI_GREEN,
    "final": ANSI_YELLOW,
    "eval": ANSI_CYAN,
}


def execution_mode_label(mode: ExecutionMode) -> str:
    """Return the human-readable label for the current execution mode."""
    return mode


def execution_mode_color(mode: ExecutionMode) -> str:
    """Return the ANSI color for the given execution mode."""
    return _MODE_COLORS.get(mode, ANSI_DIM)


def parse_mode_command(message: str) -> ExecutionMode | None:
    """
    Parse one `/mode ...` command into the requested execution mode.

    Returns the mode string, or None to display the current mode.
    Raises ValueError on unknown input.
    """
    requested = message.strip().removeprefix("/mode").strip().lower()
    if not requested:
        return None
    if requested in ("stream", "final", "eval"):
        return requested  # type: ignore[return-value]
    raise ValueError(
        f"Unknown mode {requested!r}. Use `/mode stream`, `/mode final`, or `/mode eval`."
    )


def parse_tuning_value(raw: str) -> Any:
    """
    Parse a CLI value string into the most specific scalar type.

    Converts "true"/"false" to bool, integer strings to int, float strings
    to float, and anything else to str.
    """
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def print_inspect(
    templates: list[dict[str, Any]],
    current_agent: str,
    *,
    color_enabled: bool,
) -> None:
    """Render the field table for the current agent template."""
    template = next(
        (t for t in templates if t.get("template_agent_id") == current_agent), None
    )
    if template is None:
        print(
            colorize(
                f"  No template found for {current_agent!r}.",
                color=ANSI_YELLOW,
                enabled=color_enabled,
            )
        )
        return

    kind = template.get("kind", "?")
    description = template.get("description", "")
    default_tuning = template.get("default_tuning") or {}
    tags: list[str] = default_tuning.get("tags") or []
    fields: list[dict[str, Any]] = default_tuning.get("fields") or []
    available_mcp: list[dict[str, Any]] = template.get("available_mcp_servers") or []

    def _h(text: str) -> str:
        return colorize(text, color=ANSI_CYAN, enabled=color_enabled, bold=True)

    def _dim(text: str) -> str:
        return colorize(text, color=ANSI_DIM, enabled=color_enabled)

    def _key(text: str) -> str:
        return colorize(text, color=ANSI_WHITE, enabled=color_enabled, bold=True)

    print()
    print(_h(f"  Template: {current_agent}"))
    print(_dim("  " + "─" * 62))
    print(
        _dim(f"  {'Execution:':12}")
        + colorize(kind, color=ANSI_GREEN, enabled=color_enabled, bold=True)
    )
    if description:
        wrapped = (description[:72] + "…") if len(description) > 72 else description
        print(_dim(f"  {'Description:':12}") + _dim(wrapped))
    if tags:
        print(_dim(f"  {'Tags:':12}") + _dim("  ".join(tags)))

    if not fields:
        print()
        print(_dim("  No tunable fields declared."))
        if available_mcp:
            print()
            print(_h("  Available MCP servers:"))
            print(_dim("  " + "─" * 62))
            for srv in available_mcp:
                print(_dim(f"  {srv.get('id', '?'):<28}") + _dim(srv.get("name", "")))
        print()
        return

    # Group fields
    groups: dict[str, list[dict[str, Any]]] = {}
    ungrouped: list[dict[str, Any]] = []
    for field in fields:
        group = (field.get("ui") or {}).get("group") or ""
        if group:
            groups.setdefault(group, []).append(field)
        else:
            ungrouped.append(field)

    def _render_fields(flist: list[dict[str, Any]]) -> None:
        for f in flist:
            key = f.get("key", "?")
            ftype = f.get("type", "?")
            title = f.get("title", "")
            required = f.get("required", False)
            default = f.get("default")
            fmin = f.get("min")
            fmax = f.get("max")
            fdesc = f.get("description", "")

            fenum: list[str] | None = f.get("enum") or None
            meta_parts = [ftype]
            if fenum:
                meta_parts.append("|".join(fenum))
            if required:
                meta_parts.append("required")
            if default is not None:
                meta_parts.append(f"default={default!r}")
            if fmin is not None and fmax is not None:
                meta_parts.append(f"{fmin}–{fmax}")
            elif fmin is not None:
                meta_parts.append(f"min={fmin}")
            elif fmax is not None:
                meta_parts.append(f"max={fmax}")
            meta = ", ".join(meta_parts)

            print(_dim("    ") + _key(f"{key:<38}") + _dim(f"[{meta}]"))
            if title:
                print(_dim(f"      {title}"))
            if fdesc:
                short = (fdesc[:80] + "…") if len(fdesc) > 80 else fdesc
                print(_dim(f"      {short}"))

    print()
    if ungrouped:
        print(_h("  Fields:"))
        print(_dim("  " + "─" * 62))
        _render_fields(ungrouped)

    for group_name, group_fields in groups.items():
        print()
        print(_h(f"  {group_name}:"))
        print(_dim("  " + "─" * 62))
        _render_fields(group_fields)

    if available_mcp:
        print()
        print(_h("  Available MCP servers:"))
        print(_dim("  " + "─" * 62))
        for srv in available_mcp:
            sid = srv.get("id", "?")
            sname = srv.get("name", "")
            sdesc = srv.get("description", "")
            config_fields: list[dict[str, Any]] = srv.get("config_fields") or []
            print(_dim("    ") + _key(f"{sid:<28}") + _dim(sname))
            if sdesc:
                print(_dim(f"      {sdesc}"))
            if config_fields:
                print(_dim("      config_fields  (tunable via /tune key=value):"))
                _render_fields(config_fields)

    print()


def print_tuning_table(
    inline_tuning: dict[str, Any],
    *,
    color_enabled: bool,
) -> None:
    """Render the active in-session tuning overrides."""
    if not inline_tuning:
        print(
            colorize(
                "  No active tuning overrides. Use /tune key=value to set one.",
                color=ANSI_DIM,
                enabled=color_enabled,
            )
        )
        return

    def _dim(text: str) -> str:
        return colorize(text, color=ANSI_DIM, enabled=color_enabled)

    print()
    print(
        colorize(
            "  Active tuning overrides  (session-local, not persisted)",
            color=ANSI_CYAN,
            enabled=color_enabled,
            bold=True,
        )
    )
    print(_dim("  " + "─" * 56))
    for key, val in inline_tuning.items():
        val_str = repr(val) if not isinstance(val, str) else f'"{val}"'
        if len(val_str) > 60:
            val_str = val_str[:57] + '…"'
        print(
            _dim(f"  {key:<36}")
            + colorize(val_str, color=ANSI_GREEN, enabled=color_enabled, bold=True)
        )
    print()
    print(
        _dim(
            "  Use /tune key=value to change  ·  /tune key= to clear  ·  "
            "/tune to refresh"
        )
    )
