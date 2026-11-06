"""Tiny wire peer for a v2 stdio client transport test."""

from __future__ import annotations

import json
import os
import sys

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    result: dict[str, object]
    if method == "server/discover":
        result = {
            "supportedVersions": ["2026-07-28"],
            "capabilities": {"tools": {}},
            "resultType": "complete",
            "ttlMs": 0,
            "cacheScope": "private",
        }
    elif method == "initialize":
        result = {
            "protocolVersion": "2025-11-25",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "Stdio test", "version": "1"},
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "current_bearer",
                    "description": "Return the subprocess bearer.",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]
        }
    elif method == "tools/call":
        result = {
            "content": [{"type": "text", "text": os.environ.get("AUTHORIZATION", "")}],
            "isError": False,
        }
    else:
        continue
    result.setdefault("resultType", "complete")
    result.setdefault("ttlMs", 0)
    result.setdefault("cacheScope", "private")
    print(
        json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}),
        flush=True,
    )
