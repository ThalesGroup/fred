# Bank Core MCP Server

Mock banking ledger server used for transfer demos.

This server is the "execution arm":
- it stores account balances,
- prepares pending transfers,
- commits approved transfers.

## Tools

- `get_account_details(account_id)`
- `prepare_transfer(source_id, destination_id, amount)`
- `commit_transfer(transaction_id)`

## Mock state

- Accounts:
  - `ACC-001`: 5000 EUR
  - `ACC-002`: 150 EUR
- Transactions:
  - In-memory register with pending/completed status.

## Run

```bash
make run
```

Or manually:

```bash
python -m venv .venv
. .venv/bin/activate
pip install fastapi uvicorn "mcp[fastapi]"
uvicorn bank_core_mcp_server.server_mcp:app --host 127.0.0.1 --port 9801 --reload
```

Endpoint: `http://127.0.0.1:9801/mcp`
