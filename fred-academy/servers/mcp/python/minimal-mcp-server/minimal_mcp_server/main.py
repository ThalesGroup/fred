"""
postal_service_mcp_server/main.py (compat wrapper)
-----------------------------------
Simple entrypoint for the standard MCP server.
Use:
  - Server: uvicorn postal_service_mcp_server.server:app --reload  (or `make server`)
"""

from __future__ import annotations
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9797)
    args = parser.parse_args()

    uvicorn.run("postal_service_mcp_server.server_mcp:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
