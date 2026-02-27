# Postal Demo Integration (Fred runtime agent)

This use case documents a runtime agent that currently remains in the product codebase.

## Agent class used by the demo

- Class path: `agentic_backend.agents.postal.tracking.TrackingAgent`
- Source file: `agentic-backend/agentic_backend/agents/postal/tracking.py`

## Why it is not moved into `fred-academy` (for now)

- It is executed through the normal Fred runtime
- Keeping it in `agentic-backend` reduces setup friction for developers running the demo
- The academy documents the scenario and dependencies without changing runtime integration

## Academy-side dependencies for this demo

- `fred-academy/servers/mcp/python/postal-service-mcp-server`
- `fred-academy/servers/mcp/python/iot-tracking-mcp-server`
- `fred-academy/use-cases/postal/knowledge/*`
- `fred-academy/use-cases/postal/demos/parcel-ops/*`
