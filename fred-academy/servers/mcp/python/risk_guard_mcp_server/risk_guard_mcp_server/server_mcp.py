"""
risk_guard_mcp_server/server_mcp.py
-----------------------------------
Simulated risk and compliance advisory MCP server for transfer workflows.

This server never moves money. It only returns advisory outputs used by
orchestrators for conditional branching.

Run:
  uvicorn risk_guard_mcp_server.server_mcp:app --host 127.0.0.1 --port 9802 --reload
  or: make run

Tools implemented:
  - evaluate_transfer_risk(source_id, destination_id, amount)
  - check_kyc_compliance(account_id)
"""

from __future__ import annotations

from typing import Any, Dict

try:
    from mcp.server import FastMCP
except Exception as e:  # pragma: no cover
    raise ImportError(
        "The 'mcp' package is required for risk_guard_mcp_server.server_mcp.\n"
        "Install it via: pip install \"mcp[fastapi]\"\n"
        f"Import error: {e}"
    )


server = FastMCP(name="risk-guard-mcp")


_KYC_REGISTRY: Dict[str, str] = {
    "ACC-001": "VALID",
    "ACC-002": "EXPIRED",
}


def _risk_reason(reasons: list[str]) -> str:
    if not reasons:
        return "No significant risk signal detected"
    return "; ".join(reasons)


@server.tool()
async def evaluate_transfer_risk(
    source_id: str,
    destination_id: str,
    amount: float,
) -> Dict[str, Any]:
    """
    Return a mock risk score and validation recommendation.

    Scoring rules:
    - amount > 2000 => +40
    - destination_id starts with "EXT-" => +50
    """
    if amount <= 0:
        return {"ok": False, "error": "amount must be > 0"}

    risk_score = 0
    reasons: list[str] = []

    if amount > 2000:
        risk_score += 40
        reasons.append("amount_above_2000")

    if destination_id.startswith("EXT-"):
        risk_score += 50
        reasons.append("external_destination")

    requires_validation = risk_score >= 50

    return {
        "ok": True,
        "source_id": source_id,
        "destination_id": destination_id,
        "amount": round(float(amount), 2),
        "risk_score": risk_score,
        "requires_validation": requires_validation,
        "reason": _risk_reason(reasons),
    }


@server.tool()
async def check_kyc_compliance(account_id: str) -> Dict[str, Any]:
    """
    Return KYC status for an account.

    Known statuses:
    - VALID
    - EXPIRED
    """
    status = _KYC_REGISTRY.get(account_id, "EXPIRED")
    return {
        "ok": True,
        "account_id": account_id,
        "status": status,
    }


app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "risk_guard_mcp_server.server_mcp:app",
        host="127.0.0.1",
        port=9802,
        reload=False,
    )
