# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Manual reception peer shared by Rust discovery and Python tool execution."""

import argparse

from fastmcp import FastMCP


def add(a: int, b: int) -> int:
    print("MCP call: add", flush=True)
    return a + b


def add_with_offset(a: int, b: int, offset: int = 0) -> int:
    print("MCP call: add (changed contract)", flush=True)
    return a + b + offset


def multiply(a: int, b: int) -> int:
    print("MCP call: multiply", flush=True)
    return a * b


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8333)
    parser.add_argument("--changed-contract", action="store_true")
    args = parser.parse_args()
    server = FastMCP("Managed MCP reception")
    # Deliberately no tool docstrings/descriptions; identical initial arguments.
    server.tool(name="add")(add_with_offset if args.changed_contract else add)
    server.tool(name="multiply")(multiply)
    server.run(transport="streamable-http", host=args.host, port=args.port, path="/mcp")
