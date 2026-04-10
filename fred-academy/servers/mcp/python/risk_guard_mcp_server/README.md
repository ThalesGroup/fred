# Risk Guard MCP Server

Mock advisory server for transfer risk and compliance checks.

This server never moves money. It only returns advisory decisions used by
graph routing and approvals.

## Tools

- `evaluate_transfer_risk(source_id, destination_id, amount)`
  - Risk score logic:
    - `amount > 2000` => +40
    - `destination_id` starts with `EXT-` => +50
  - Returns:
    - `risk_score`
    - `requires_validation`
    - `reason`

- `check_kyc_compliance(account_id)`
  - Returns:
    - `status`: `VALID` or `EXPIRED`

## Run

```bash
make run
```

Or manually:

```bash
python -m venv .venv
. .venv/bin/activate
pip install fastapi uvicorn "mcp[fastapi]"
uvicorn risk_guard_mcp_server.server_mcp:app --host 127.0.0.1 --port 9802 --reload
```

Endpoint: `http://127.0.0.1:9802/mcp`
