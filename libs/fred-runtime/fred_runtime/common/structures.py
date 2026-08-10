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
"""
Minimal contracts for runtime helpers that need agent settings.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from fred_sdk.contracts.models import AgentTuning, MCPServerRef

logger = logging.getLogger(__name__)

# Awaited, never called inline: the Keycloak exchange behind it is network I/O
# on paths that already run inside the pod's event loop (issue #2125). Lives
# here rather than beside one consumer so the KF clients and the MCP
# interceptor share one definition without importing each other.
TokenRefreshCallback = Callable[[], Awaitable[str]]


class AgentSettingsLike(Protocol):
    """
    Minimal agent settings contract needed by runtime adapters.

    Why this exists:
    - fred-runtime must not depend on agentic-backend settings models
    - only a few identity/tuning fields are required by shared helpers

    How to use it:
    - pass any object exposing `id`, `team_id`, `tuning`, and
      `active_mcp_servers`

    Example:
        >>> class SimpleAgentSettings:
        ...     id = "agent.demo"
        ...     team_id = None
        ...     tuning = None
        ...     active_mcp_servers = ()
        >>> settings: AgentSettingsLike = SimpleAgentSettings()
    """

    id: str
    team_id: str | None
    tuning: AgentTuning | None
    # The MCP servers active for this request (#1978). The MCP tuning trio was
    # retired, so the live MCP tool provider reads the active server refs here
    # instead of from `tuning.mcp_servers`.
    active_mcp_servers: Sequence[MCPServerRef]


async def resolve_refresh_result(result: object, hook_owner: object) -> str:
    """Await a token-refresh hook's result, tolerating a legacy synchronous one.

    Why it exists:
    - `TokenRefreshCallback` and `KnowledgeFlowAgentContext` are typing-only, so
      an out-of-tree agent can still supply the pre-#2125 SYNCHRONOUS hook.
    - Whether a hook is async CANNOT be decided statically:
      `lambda: self._refresh()` and an object with `async def __call__` are both
      legal `Callable[[], Awaitable[str]]`, and `inspect.iscoroutinefunction` is
      False for both. A static guard is therefore either too narrow (rejects
      valid agents and disables their 401 recovery) or too loose (admits sync
      ones and `await`s a `str`). An earlier version managed to be both.
    - So the shape is decided from the RESULT. A sync hook has, by then, blocked
      the event loop once — bad, and loudly logged — but its token is valid, and
      discarding a refresh that actually succeeded turns one slow call into a
      permanently broken recovery path.

    How to use it:
    - `token = await resolve_refresh_result(hook(), self._agent)`
    """
    if inspect.isawaitable(result):
        resolved = await result
    else:
        logger.error(
            "%s supplied a SYNCHRONOUS token-refresh hook; it must be `async def` "
            "(RUNTIME-EXECUTION-CONTRACT.md §8.45). It has just run blocking "
            "network I/O on the event loop, stalling every other turn on this "
            "pod. Using its result this once — fix the hook.",
            type(hook_owner).__name__,
        )
        resolved = result

    if isinstance(resolved, str):
        return resolved
    # Degraded, not raised: a TypeError here would be swallowed by the callers'
    # `except Exception` and reported as a Keycloak failure — the misdiagnosis
    # this helper exists to stop. An empty token is what every caller already
    # treats as "refresh produced nothing".
    logger.error(
        "%s's token-refresh hook returned %s, expected a token string.",
        type(hook_owner).__name__,
        type(resolved).__name__,
    )
    return ""
