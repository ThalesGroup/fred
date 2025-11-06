"""
postal_service_mcp_server/server_mcp.py
---------------------------------
Minimal MCP server using the current `mcp` Python SDK.

This exposes the Streamable HTTP transport at `/mcp` and is compatible with
modern MCP clients.

Run:
  uvicorn postal_service_mcp_server.server_mcp:app --host 127.0.0.1 --port 9797 --reload
  or: make server

Tools implemented:
  - validate_address(country, city, postal_code, street)
  - quote_shipping(weight_kg, distance_km, speed)
  - create_label(receiver_name, address_id, service)
  - track_package(tracking_id)
"""

from __future__ import annotations

from typing import Dict, Any, Literal
import time
import uuid

try:
    # Use FastMCP (ergonomic server with @tool decorator) and build a Starlette app
    from mcp.server import FastMCP
except Exception as e:  # pragma: no cover - helpful error at import time
    raise ImportError(
        "The 'mcp' package is required for postal_service_mcp_server.server_mcp.\n"
        "Install it via: pip install \"mcp[fastapi]\"\n"
        f"Import error: {e}"
    )


# In-memory stores (tutorial-grade persistence)
_ADDRESSES: Dict[str, Dict[str, str]] = {}
_PACKAGES: Dict[str, Dict[str, Any]] = {}


# Create a FastMCP server (provides @tool and compatible transports)
server = FastMCP(name="postal-mcp")


@server.tool()
async def validate_address(country: str, city: str, postal_code: str, street: str) -> Dict[str, Any]:
    """Validate and register a postal address; returns an address_id.

    Business value: normalize and persist an address so that later tools
    (e.g., create_label) can reference it by ID.
    """
    if len(postal_code) < 4:
        return {"valid": False, "reason": "postal_code too short"}
    if not street.strip():
        return {"valid": False, "reason": "street must be non-empty"}

    addr = {
        "country": country,
        "city": city,
        "postal_code": postal_code,
        "street": street,
    }
    addr_id = str(uuid.uuid4())
    _ADDRESSES[addr_id] = addr
    return {"valid": True, "address_id": addr_id, "normalized": addr}


@server.tool()
async def quote_shipping(
    weight_kg: float,
    distance_km: float,
    speed: Literal["standard", "express"],
) -> Dict[str, Any]:
    """Quote a shipment price and ETA."""
    base = 2.0
    per_km = 0.01
    per_kg = 0.5
    speed_multiplier = 1.0 if speed == "standard" else 1.8
    price = round((base + distance_km * per_km + weight_kg * per_kg) * speed_multiplier, 2)
    eta_days = 5 if speed == "standard" else 2
    return {"currency": "EUR", "price": price, "eta_days": eta_days}


@server.tool()
async def create_label(
    receiver_name: str,
    address_id: str,
    service: Literal["standard", "express"],
) -> Dict[str, Any]:
    """Create a shipping label and a tracking_id for a validated address."""
    addr = _ADDRESSES.get(address_id)
    if not addr:
        return {"ok": False, "error": "Unknown address_id"}

    tracking_id = "PKG-" + uuid.uuid4().hex[:12].upper()
    _PACKAGES[tracking_id] = {
        "receiver": receiver_name,
        "address": addr,
        "service": service,
        "status": "CREATED",
        "history": [
            {"ts": int(time.time()), "event": "LABEL_CREATED"},
        ],
    }
    return {
        "ok": True,
        "tracking_id": tracking_id,
        "label": {
            "format": "ZPL",
            "payload": f"^XA^FO50,50^ADN,36,20^FDTo:{receiver_name}^FS^XZ",
        },
    }


@server.tool()
async def track_package(tracking_id: str) -> Dict[str, Any]:
    """Return current package status + history."""
    pkg = _PACKAGES.get(tracking_id)
    if not pkg:
        return {"ok": False, "error": "Unknown tracking_id"}

    # Simulate a tiny progression over time (illustrative only)
    if len(pkg["history"]) == 1:
        pkg["status"] = "IN_TRANSIT"
        pkg["history"].append({"ts": int(time.time()), "event": "PICKED_UP"})
    elif len(pkg["history"]) == 2:
        pkg["status"] = "OUT_FOR_DELIVERY"
        pkg["history"].append({"ts": int(time.time()), "event": "HUB_DEPARTURE"})
    return {"ok": True, "status": pkg["status"], "history": pkg["history"]}


# Expose the Streamable HTTP transport under /mcp
# This returns a Starlette app that uvicorn can serve directly
app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("postal_service_mcp_server.server_mcp:app", host="127.0.0.1", port=9797, reload=False)
