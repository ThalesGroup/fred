# MCP Servers (Agentic Demo / Open Tools)

This folder hosts standalone MCP servers that are useful for demos and
general-purpose agent capabilities (web browsing, public APIs, GitHub read-only,
etc.).

Why here (and not `knowledge-flow-backend`)?
- `knowledge-flow-backend` stays focused on protected/internal endpoints and
  enterprise data access.
- `agentic-backend/mcp-servers` contains "open" or demo-oriented tools that can
  be attached to agents for compelling public-facing demos.

Suggested conventions
- One server per subfolder
- Streamable HTTP transport exposed at `/mcp`
- Read-only by default for public internet integrations
- Small `README.md` + `Makefile` in each server folder

