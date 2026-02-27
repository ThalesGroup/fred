# Simulated IoT Tracking MCP Server

Small MCP server for demoing agent orchestration with live-ish telemetry:

- hub congestion alerts
- vehicle position tracking
- parcel sensor snapshots
- pickup locker occupancy
- deterministic event timelines you can advance step-by-step

This is designed to complement the academy postal business MCP server.

## Run

```bash
make run
```

Or manually:

```bash
python -m venv .venv
. .venv/bin/activate
pip install fastapi uvicorn "mcp[fastapi]"
uvicorn iot_tracking_mcp_server.server_mcp:app --host 127.0.0.1 --port 9798 --reload
```

Endpoint: `http://127.0.0.1:9798/mcp`

## Suggested Demo Flow (with postal business MCP)

1. Call `seed_demo_parcel_exception` on the postal MCP server and capture `tracking_id`.
2. Call `seed_demo_tracking_incident(tracking_id=...)` on this IoT MCP server.
3. Call `get_live_tracking_snapshot(tracking_id=...)`.
4. Call `list_tracking_events(tracking_id=...)`.
5. Call `advance_simulation_tick(tracking_id=...)` to simulate incident evolution.
6. Poll `get_hub_status(...)`, `get_vehicle_position(...)`, and `get_locker_occupancy(...)` as needed.

