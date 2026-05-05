from __future__ import annotations

import uuid
from typing import Any, Literal

from fred_core.cli.ui import ANSI_CYAN, ANSI_DIM, ANSI_GREEN, ANSI_YELLOW, colorize

from .pod_client import AgentPodClient

ExecutionMode = Literal["stream", "final", "eval"]


def print_help() -> None:
    """Print the supported interactive chat commands."""
    print("Commands:")
    print(
        "  /help [question]         Show this help, or ask a question in natural language"
    )
    print("  /agents                  Refresh and list available agent ids")
    print("  /agent <agent_id>        Switch the active agent")
    print(
        "  /login                   Log in through browser PKCE and cache the user session"
    )
    print(
        "  /login-password [user]   Use direct username/password login as a local fallback"
    )
    print(
        "  /whoami                  Show identity, auth, team, agent, session, pod URL"
    )
    print("  /logout                  Clear the cached login session")
    print("  /mode [stream|final|eval] Show or change the execution mode")
    print(
        "  /session [<N>|<id>]      Show current session, or switch by index / exact id"
    )
    print("  /session-new             Start a fresh session with a generated id")
    print(
        "  /session-info [id]       Show session metadata (timestamps, agents, tokens, title)"
    )
    print("  /team [team_id|clear]    Show, set, or clear the current team scope")
    print(
        "  /sessions                List sessions with message count and first/last preview"
    )
    print(
        "  /history [--raw] [id]    Show conversation history (--raw: full JSON payload)"
    )
    print(
        "  /kpi [limit]             Show recent agent.turn_completed events from the pod"
    )
    print(
        "  /kpi prom [pattern]      Show Prometheus metrics snapshot (optional filter)"
    )
    print("  /audit [limit]           Show recent security audit events from the pod")
    print(
        "  /checkpoints [limit]     List checkpoint threads with sizes (default limit=20)"
    )
    print("  /checkpoint <session_id> Inspect all checkpoints for one session")
    print("  /stats                   Show aggregate checkpoint storage statistics")
    print("  /context                 Show current execution context summary")
    print()
    print("Cleanup commands (irreversible — always prompt for confirmation):")
    print("  /delete-session [id]     Delete history rows only (checkpoint kept)")
    print("  /delete-checkpoint [id]  Delete checkpoint only (history kept)")
    print("  /purge-session [id]      Delete BOTH history and checkpoint")
    print("  /quit                    Exit the chat client")


_CLI_HELP_CONTEXT = (
    "You are an interactive help assistant embedded in the Fred CLI chat tool "
    "(fred-agents-cli). Answer the user's question about how to use the CLI. "
    "Respond in the same language as the user's question. Be concise and practical.\n\n"
    "Available commands:\n"
    "  /help [question]         Show command reference or ask a question in natural language\n"
    "  /agents                  Refresh and list available agent ids\n"
    "  /agent <agent_id>        Switch the active agent\n"
    "  /login                   Log in through browser PKCE and cache the user session\n"
    "  /login-password [user]   Use direct username/password login as a local fallback\n"
    "  /whoami                  Show identity, auth, team, agent, session, pod URL\n"
    "  /logout                  Clear the cached login session\n"
    "  /mode [stream|final|eval] Show or change the execution mode (default: stream)\n"
    "  /session [<N>|<id>]      Show current session, or switch by index / exact id\n"
    "  /session-new             Start a fresh session with a generated id\n"
    "  /session-info [id]       Show session metadata (timestamps, agents, tokens, title)\n"
    "  /team [team_id|clear]    Show, set, or clear the current team scope\n"
    "  /sessions                List sessions with message count and first/last preview\n"
    "  /history [--raw] [id]    Show conversation history (--raw: full JSON payload)\n"
    "  /kpi [limit]             Show recent agent.turn_completed events from the pod\n"
    "  /kpi prom [pattern]      Show Prometheus metrics snapshot (optional filter)\n"
    "  /audit [limit]           Show recent security audit events from the pod\n"
    "  /checkpoints [limit]     List checkpoint threads with sizes (default limit=20)\n"
    "  /checkpoint <session_id> Inspect all checkpoints for one session\n"
    "  /stats                   Show aggregate checkpoint storage statistics\n"
    "  /context                 Show current execution context summary\n"
    "  /delete-session [id]     Delete history rows only (checkpoint kept) — irreversible\n"
    "  /delete-checkpoint [id]  Delete checkpoint only (history kept) — irreversible\n"
    "  /purge-session [id]      Delete BOTH history and checkpoint — irreversible\n"
    "  /quit                    Exit the chat client\n\n"
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
