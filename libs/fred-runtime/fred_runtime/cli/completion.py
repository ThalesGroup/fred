from __future__ import annotations

import glob as _glob
import os
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
    "/scenario",
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
    if stripped.startswith("/scenario "):
        partial = stripped.removeprefix("/scenario ").strip()
        return _complete_scenario_path(partial)
    if stripped.startswith("/"):
        return complete_slash_commands(stripped, commands=_COMMANDS)
    return []


def _complete_scenario_path(partial: str) -> list[str]:
    """
    Return YAML file paths that complete the partial path typed after /scenario.

    Why this function exists:
    - scenario files live in a subdirectory, not the cwd root
    - two levels of glob depth covers the typical tests/scenarios/ layout
      without listing the entire filesystem
    """
    expanded = os.path.expanduser(partial)

    candidates: list[str] = sorted(_glob.glob(expanded + "*.yaml"))

    if not partial or partial.endswith("/"):
        candidates += sorted(_glob.glob(expanded + "*/*.yaml"))
        candidates += sorted(_glob.glob(expanded + "*/*/*.yaml"))

    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result
