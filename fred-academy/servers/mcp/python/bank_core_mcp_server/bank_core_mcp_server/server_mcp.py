"""
bank_core_mcp_server/server_mcp.py
----------------------------------
Simulated banking core MCP server for transfer workflows.

This exposes the Streamable HTTP transport at `/mcp` and is compatible with
modern MCP clients.

Run:
  uvicorn bank_core_mcp_server.server_mcp:app --host 127.0.0.1 --port 9801 --reload
  or: make run

Tools implemented:
  - get_account_details(account_id)
  - prepare_transfer(source_id, destination_id, amount)
  - commit_transfer(transaction_id)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
import copy
import uuid

try:
    from mcp.server import FastMCP
except Exception as e:  # pragma: no cover
    raise ImportError(
        "The 'mcp' package is required for bank_core_mcp_server.server_mcp.\n"
        "Install it via: pip install \"mcp[fastapi]\"\n"
        f"Import error: {e}"
    )


server = FastMCP(name="bank-core-mcp")


_ACCOUNTS: Dict[str, Dict[str, Any]] = {
    "ACC-001": {
        "account_id": "ACC-001",
        "holder_name": "Alice Martin",
        "currency": "EUR",
        "balance": 5000.00,
    },
    "ACC-002": {
        "account_id": "ACC-002",
        "holder_name": "Bob Lambert",
        "currency": "EUR",
        "balance": 150.00,
    },
}

_TRANSACTIONS: Dict[str, Dict[str, Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _money(value: float) -> float:
    return round(float(value), 2)


def _account_exists(account_id: str) -> bool:
    return account_id in _ACCOUNTS


def _destination_kind(destination_id: str) -> str:
    if _account_exists(destination_id):
        return "INTERNAL"
    if destination_id.startswith("EXT-"):
        return "EXTERNAL"
    return "UNKNOWN"


@server.tool()
async def get_account_details(account_id: str) -> Dict[str, Any]:
    """Return account holder, currency and current balance."""
    account = _ACCOUNTS.get(account_id)
    if not account:
        return {
            "ok": False,
            "error": f"Unknown account_id: {account_id}",
        }
    return {"ok": True, "account": copy.deepcopy(account)}


@server.tool()
async def prepare_transfer(
    source_id: str,
    destination_id: str,
    amount: float,
) -> Dict[str, Any]:
    """
    Validate transfer feasibility and create a pending transaction.

    Money is not moved here. The transaction remains PENDING_APPROVAL until
    commit_transfer is called.
    """
    if amount <= 0:
        return {"ok": False, "error": "amount must be > 0"}

    source = _ACCOUNTS.get(source_id)
    if not source:
        return {"ok": False, "error": f"Unknown source account_id: {source_id}"}

    destination_kind = _destination_kind(destination_id)
    if destination_kind == "UNKNOWN":
        return {
            "ok": False,
            "error": (
                "Unknown destination account_id. Use an internal account like ACC-002 "
                "or an external account id starting with EXT-."
            ),
        }

    normalized_amount = _money(amount)
    source_balance = _money(source["balance"])
    if source_balance < normalized_amount:
        return {
            "ok": False,
            "status": "REJECTED",
            "reason": "INSUFFICIENT_FUNDS",
            "source_id": source_id,
            "available_balance": source_balance,
            "requested_amount": normalized_amount,
            "currency": source["currency"],
        }

    transaction_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
    _TRANSACTIONS[transaction_id] = {
        "transaction_id": transaction_id,
        "source_id": source_id,
        "destination_id": destination_id,
        "destination_kind": destination_kind,
        "amount": normalized_amount,
        "currency": source["currency"],
        "status": "PENDING_APPROVAL",
        "created_at": _utc_now_iso(),
    }

    return {
        "ok": True,
        "transaction_id": transaction_id,
        "status": "PENDING_APPROVAL",
        "source_id": source_id,
        "destination_id": destination_id,
        "destination_kind": destination_kind,
        "amount": normalized_amount,
        "currency": source["currency"],
    }


@server.tool()
async def commit_transfer(transaction_id: str) -> Dict[str, Any]:
    """
    Execute a previously prepared transfer.

    This debits the source account and credits destination account when it is
    internal (ACC-*). For external destinations (EXT-*), only the source is
    debited.
    """
    tx = _TRANSACTIONS.get(transaction_id)
    if not tx:
        return {"ok": False, "error": f"Unknown transaction_id: {transaction_id}"}

    if tx["status"] == "COMPLETED":
        source = _ACCOUNTS.get(tx["source_id"], {})
        destination = (
            _ACCOUNTS.get(tx["destination_id"], {})
            if tx["destination_kind"] == "INTERNAL"
            else {}
        )
        return {
            "ok": True,
            "transaction_id": transaction_id,
            "status": "COMPLETED",
            "message": "Transfer already committed",
            "source_balance": _money(source.get("balance", 0.0)),
            "destination_balance": _money(destination.get("balance", 0.0))
            if destination
            else None,
        }

    if tx["status"] != "PENDING_APPROVAL":
        return {
            "ok": False,
            "error": (
                f"Transaction {transaction_id} is not committable "
                f"(status={tx['status']})."
            ),
        }

    source = _ACCOUNTS.get(tx["source_id"])
    if not source:
        return {
            "ok": False,
            "error": f"Source account missing for transaction {transaction_id}",
        }

    amount = _money(tx["amount"])
    source_balance = _money(source["balance"])
    if source_balance < amount:
        tx["status"] = "FAILED"
        tx["failure_reason"] = "INSUFFICIENT_FUNDS_AT_COMMIT"
        tx["updated_at"] = _utc_now_iso()
        return {
            "ok": False,
            "transaction_id": transaction_id,
            "status": "FAILED",
            "reason": tx["failure_reason"],
            "source_balance": source_balance,
            "required_amount": amount,
        }

    source["balance"] = _money(source_balance - amount)

    destination_balance = None
    if tx["destination_kind"] == "INTERNAL":
        destination = _ACCOUNTS.get(tx["destination_id"])
        if not destination:
            tx["status"] = "FAILED"
            tx["failure_reason"] = "MISSING_INTERNAL_DESTINATION"
            tx["updated_at"] = _utc_now_iso()
            # rollback debit
            source["balance"] = _money(source["balance"] + amount)
            return {
                "ok": False,
                "transaction_id": transaction_id,
                "status": "FAILED",
                "reason": tx["failure_reason"],
            }
        destination["balance"] = _money(destination["balance"] + amount)
        destination_balance = _money(destination["balance"])

    tx["status"] = "COMPLETED"
    tx["committed_at"] = _utc_now_iso()
    tx["updated_at"] = tx["committed_at"]

    return {
        "ok": True,
        "transaction_id": transaction_id,
        "status": "COMPLETED",
        "amount": amount,
        "currency": tx["currency"],
        "source_id": tx["source_id"],
        "destination_id": tx["destination_id"],
        "destination_kind": tx["destination_kind"],
        "source_balance": _money(source["balance"]),
        "destination_balance": destination_balance,
    }


app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "bank_core_mcp_server.server_mcp:app",
        host="127.0.0.1",
        port=9801,
        reload=False,
    )
