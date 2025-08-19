# Copyright Thales 2025
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

from langchain_mcp_adapters.client import MultiServerMCPClient
from app.common.structures import AgentSettings
from app.common.error import UnsupportedTransportError
from builtins import ExceptionGroup

SUPPORTED_TRANSPORTS = ["sse", "stdio", "streamable_http", "websocket"]


async def get_mcp_client_for_agent(
    agent_settings: AgentSettings,
) -> MultiServerMCPClient:
    client = MultiServerMCPClient()
    exceptions = []
    if not agent_settings.mcp_servers:
        raise ValueError("no mcp server configuration")

    for server in agent_settings.mcp_servers:
        if server.transport not in SUPPORTED_TRANSPORTS:
            raise UnsupportedTransportError(
                f"Unsupported transport: {server.transport}"
            )
        try:
            await client.connect_to_server(
                server_name=server.name,
                url=server.url,
                transport=server.transport,
                command=server.command,
                args=server.args,
                env=server.env,
                sse_read_timeout=server.sse_read_timeout,
            )
        except Exception as eg:
            exceptions.extend(getattr(eg, "exceptions", [eg]))

    if exceptions:
        raise ExceptionGroup("Some MCP connections failed", exceptions)

    return client
