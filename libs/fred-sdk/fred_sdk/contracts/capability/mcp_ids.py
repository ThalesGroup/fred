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
The `mcp:<server>` capability-id contract (#1978, RFC §3.8).

An MCP server surfaces as a capability whose id is `mcp:<catalog server id>`.
This tiny module owns that namespace so every layer agrees on it without a
duplicated prefix string: fred-runtime builds the capabilities and derives the
active server set, and control-plane maps the retired MCP trio into
`selected_capability_ids` / `capability_config` slices.
"""

from __future__ import annotations

# Capability-id namespace for catalog MCP servers. A server with catalog id
# `mcp-knowledge-flow-fs` becomes the capability `mcp:mcp-knowledge-flow-fs`.
MCP_CAPABILITY_PREFIX = "mcp:"


def mcp_capability_id(server_id: str) -> str:
    """Return the capability id for one catalog MCP server id."""

    return f"{MCP_CAPABILITY_PREFIX}{server_id}"


def is_mcp_capability_id(capability_id: str) -> bool:
    """Tell whether a capability id names an MCP-server capability."""

    return capability_id.startswith(MCP_CAPABILITY_PREFIX)


def mcp_server_id_of(capability_id: str) -> str:
    """Return the catalog server id behind one `mcp:<server>` capability id."""

    return capability_id[len(MCP_CAPABILITY_PREFIX) :]
