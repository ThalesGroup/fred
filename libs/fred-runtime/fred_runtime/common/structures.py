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

from collections.abc import Sequence
from typing import Protocol

from fred_sdk.contracts.models import AgentTuning, MCPServerRef


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
