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
    "/inspect",
    "/purge-session",
    "/execution-context",
    "/history",
    "/kpi",
    "/login",
    "/login-password",
    "/mode",
    "/run",
    "/session",
    "/session-info",
    "/session-new",
    "/sessions",
    "/stats",
    "/team",
    "/tune",
    "/tuning",
    "/logout",
    "/quit",
    "/whoami",
)

# Scenario keywords for fred.github.test_assistant — used for /run tab-completion.
_TEST_ASSISTANT_SCENARIOS: tuple[str, ...] = (
    "echo",
    "error",
    "hitl choice",
    "hitl text",
    "long",
    "model planning",
    "model routing",
    "trace",
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
        return [mode for mode in ("eval", "final", "stream") if mode.startswith(prefix)]
    if stripped.startswith("/run "):
        prefix = stripped.removeprefix("/run ").strip()
        return [s for s in _TEST_ASSISTANT_SCENARIOS if s.startswith(prefix)]
    if stripped.startswith("/"):
        return complete_slash_commands(stripped, commands=_COMMANDS)
    return []
