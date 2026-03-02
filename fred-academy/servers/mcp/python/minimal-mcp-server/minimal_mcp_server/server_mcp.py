"""
minimal_mcp_server/server_mcp.py
---------------------------------
Minimal MCP server using the current `mcp` Python SDK.

This exposes the Streamable HTTP transport at `/mcp` and is compatible with
modern MCP clients.

Run:
  uvicorn minimal_mcp_server.server_mcp:app --host 127.0.0.1 --port 9797 --reload
  or: make server

Tools implemented:
  - validate_address(country, city, postal_code, street)
  - quote_shipping(weight_kg, distance_km, speed)
  - create_label(receiver_name, address_id, service)
  - track_package(tracking_id)
"""

from __future__ import annotations

from typing import Dict, Any
import random

try:
    # Use FastMCP (ergonomic server with @tool decorator) and build a Starlette app
    from mcp.server import FastMCP
except Exception as e:  # pragma: no cover - helpful error at import time
    raise ImportError(
        "The 'mcp' package is required for minimal_mcp_server.server_mcp.\n"
        "Install it via: pip install \"mcp[fastapi]\"\n"
        f"Import error: {e}"
    )


# In-memory stores (tutorial-grade persistence)
_ADDRESSES: Dict[str, Dict[str, str]] = {}
_PACKAGES: Dict[str, Dict[str, Any]] = {}


# Create a FastMCP server (provides @tool and compatible transports)
server = FastMCP(name="postal-mcp")


@server.tool()
async def random_numbers(
    count: int,
    min_value: int = 0,
    max_value: int = 100
) -> Dict[str, Any]:
    """
    Generate a list of random integers.

    Parameters:
      - count: number of random numbers to generate
      - min_value: minimum integer value (inclusive)
      - max_value: maximum integer value (inclusive)

    Returns:
      { "numbers": [ ... ] }
    """
    if count <= 0:
        return {"error": "count must be > 0"}

    if min_value > max_value:
        return {"error": "min_value must be <= max_value"}

    nums = [random.randint(min_value, max_value) for _ in range(count)]
    return {"numbers": nums}



# Expose the Streamable HTTP transport under /mcp
# This returns a Starlette app that uvicorn can serve directly
app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("minimal_mcp_server.server_mcp:app", host="127.0.0.1", port=9797, reload=False)
