from __future__ import annotations

from collections.abc import Sequence

from fred_core.cli.ui import complete_slash_commands

_COMMANDS: tuple[str, ...] = (
    "/audit",
    "/help",
    "/agents",
    "/agent",
    "/checkpoints",
    "/checkpoint",
    "/context",
    "/delete-session",
    "/delete-checkpoint",
    "/purge-session",
    "/execution-context",
    "/history",
    "/kpi",
    "/login",
    "/login-password",
    "/mode",
    "/session",
    "/session-info",
    "/session-new",
    "/sessions",
    "/stats",
    "/team",
    "/logout",
    "/quit",
    "/whoami",
)


def completion_candidates(
    line_buffer: str,
    *,
    agent_ids: Sequence[str],
    session_ids: Sequence[str] = (),
) -> list[str]:
    """Return tab-completion candidates for one chat prompt line."""
    stripped = line_buffer.lstrip()
    if stripped.startswith("/agent "):
        prefix = stripped.removeprefix("/agent ").strip()
        return [agent_id for agent_id in agent_ids if agent_id.startswith(prefix)]
    if stripped.startswith("/session "):
        prefix = stripped.removeprefix("/session ").strip()
        return [sid for sid in session_ids if sid.startswith(prefix)]
    if stripped.startswith("/mode "):
        prefix = stripped.removeprefix("/mode ").strip()
        return [mode for mode in ("final", "stream") if mode.startswith(prefix)]
    if stripped.startswith("/"):
        return complete_slash_commands(stripped, commands=_COMMANDS)
    return []
