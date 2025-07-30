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
