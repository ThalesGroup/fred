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
  - list_my_active_parcels()
  - track_package(tracking_id)
  - seed_demo_parcel_exception(...)
  - get_pickup_points_nearby(city, postal_code, limit)
  - reroute_package_to_pickup_point(tracking_id, pickup_point_id, reason)
  - reschedule_delivery(tracking_id, requested_date, time_window)
  - notify_customer(tracking_id, channel, message)
  - estimate_compensation(tracking_id)
  - open_claim(tracking_id, reason, description)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import types
from functools import lru_cache
from typing import Dict, Any, Literal, List, Optional
import time
import uuid

try:
    # Use FastMCP (ergonomic server with @tool decorator) and build a Starlette app
    from mcp.server import FastMCP
    from mcp.server.fastmcp import Context
except Exception as e:  # pragma: no cover - helpful error at import time
    raise ImportError(
        "The 'mcp' package is required for postal_service_mcp_server.server_mcp.\n"
        "Install it via: pip install \"mcp[fastapi]\"\n"
        f"Import error: {e}"
    )

logger = logging.getLogger(__name__)

_TERMINAL_PACKAGE_STATUSES = {"DELIVERED", "CANCELLED", "LOST"}


def _load_fred_oidc_helpers():
    """
    Best-effort import of fred_core.security.oidc without importing the heavy
    `fred_core.__init__` aggregator.
    """
    repo_root = Path(__file__).resolve().parents[3]
    fred_core_pkg = repo_root / "fred-core" / "fred_core"
    if not fred_core_pkg.exists():
        return None, None, None

    if "fred_core" not in sys.modules:
        pkg = types.ModuleType("fred_core")
        pkg.__path__ = [str(fred_core_pkg)]  # type: ignore[attr-defined]
        sys.modules["fred_core"] = pkg

    try:
        from fred_core.security.oidc import decode_jwt, initialize_user_security
        from fred_core.security.structure import UserSecurity

        return decode_jwt, initialize_user_security, UserSecurity
    except Exception as exc:  # pragma: no cover - demo fallback
        logger.warning(
            "Could not import fred_core OIDC helpers; falling back to mock caller: %s",
            exc,
        )
        return None, None, None


_FRED_DECODE_JWT, _FRED_INIT_USER_SECURITY, _FRED_USER_SECURITY_CLS = (
    _load_fred_oidc_helpers()
)


@lru_cache(maxsize=1)
def _init_demo_oidc_from_env_once() -> None:
    if not (_FRED_INIT_USER_SECURITY and _FRED_USER_SECURITY_CLS):
        return

    enabled = os.getenv("DEMO_MCP_OIDC_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    realm_url = os.getenv("DEMO_MCP_KEYCLOAK_REALM_URL", "").strip()
    client_id = os.getenv("DEMO_MCP_KEYCLOAK_CLIENT_ID", "").strip()

    if not enabled:
        logger.info(
            "Demo OIDC disabled for postal MCP (set DEMO_MCP_OIDC_ENABLED=true to validate Bearer tokens)."
        )
        return

    if not realm_url or not client_id:
        logger.warning(
            "Demo OIDC enabled but realm/client env vars are missing. Falling back to mock caller."
        )
        return

    try:
        cfg = _FRED_USER_SECURITY_CLS(
            enabled=True,
            realm_url=realm_url,
            client_id=client_id,
        )
        _FRED_INIT_USER_SECURITY(cfg)
        logger.info(
            "Demo OIDC initialized for postal MCP (realm=%s client_id=%s)",
            realm_url,
            client_id,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Demo OIDC initialization failed: %s", exc)


def _extract_bearer_token_from_ctx(ctx: Optional[Context]) -> Optional[str]:
    if not ctx:
        return None
    try:
        req = ctx.request_context.request
        if req is None:
            return None
        headers = getattr(req, "headers", None)
        auth = headers.get("authorization") if headers else None
        if not auth and headers:
            auth = headers.get("Authorization")
        if not isinstance(auth, str) or not auth.lower().startswith("bearer "):
            return None
        token = auth[7:].strip()
        return token or None
    except Exception:
        return None


def _user_to_demo_profile(user: Any, *, source: str) -> Dict[str, Any]:
    uid = str(getattr(user, "uid", "") or "admin")
    username = str(getattr(user, "username", "") or "admin")
    email = getattr(user, "email", None)
    email_str = email if isinstance(email, str) and email else None

    if username and username != "admin":
        display_name = username.replace(".", " ").replace("_", " ").title()
    elif email_str and "@" in email_str and not email_str.startswith("admin@"):
        display_name = email_str.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
    else:
        # Stable demo alias when auth is disabled locally.
        display_name = "Alice Martin"

    return {
        "uid": uid,
        "username": username,
        "email": email_str,
        "display_name": display_name,
        "demo_customer_ref": f"CUST-DEMO-{uid.upper().replace('-', '')[:12]}",
        "source": source,
    }


def _resolve_demo_caller(ctx: Optional[Context]) -> Dict[str, Any]:
    _init_demo_oidc_from_env_once()
    token = _extract_bearer_token_from_ctx(ctx)

    if token and _FRED_DECODE_JWT:
        try:
            user = _FRED_DECODE_JWT(token)
            return _user_to_demo_profile(user, source="bearer_token")
        except Exception as exc:
            logger.warning("Bearer token decode failed in postal MCP: %s", exc)

    mock_user = types.SimpleNamespace(
        uid="admin",
        username="admin",
        email="admin@mail.com",
        roles=["admin"],
        groups=["admins"],
    )
    return _user_to_demo_profile(mock_user, source="mock")


def _norm_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _attach_owner_metadata_to_package(pkg: Dict[str, Any], caller: Dict[str, Any]) -> None:
    """Persist a compact caller identity on the package for later lookups."""
    pkg["owner"] = {
        "uid": caller.get("uid"),
        "username": caller.get("username"),
        "email": caller.get("email"),
        "display_name": caller.get("display_name"),
        "demo_customer_ref": caller.get("demo_customer_ref"),
        "source": caller.get("source"),
    }


def _caller_matches_package(caller: Dict[str, Any], pkg: Dict[str, Any]) -> bool:
    owner = pkg.get("owner") or {}
    if isinstance(owner, dict):
        caller_uid = _norm_text(caller.get("uid"))
        caller_ref = _norm_text(caller.get("demo_customer_ref"))
        caller_email = _norm_text(caller.get("email"))
        if caller_uid and _norm_text(owner.get("uid")) == caller_uid:
            return True
        if caller_ref and _norm_text(owner.get("demo_customer_ref")) == caller_ref:
            return True
        if caller_email and _norm_text(owner.get("email")) == caller_email:
            return True

    # Fallback for older seeded packages without owner metadata.
    caller_name = _norm_text(caller.get("display_name"))
    receiver_name = _norm_text(pkg.get("receiver"))
    return bool(caller_name and receiver_name and caller_name == receiver_name)


# In-memory stores (tutorial-grade persistence)
_ADDRESSES: Dict[str, Dict[str, str]] = {}
_PACKAGES: Dict[str, Dict[str, Any]] = {}
_CLAIMS: Dict[str, Dict[str, Any]] = {}


# Static pickup points (demo-grade data for rerouting scenarios)
_PICKUP_POINTS: Dict[str, Dict[str, Any]] = {
    "PP-PAR-001": {
        "pickup_point_id": "PP-PAR-001",
        "name": "Paris Louvre Locker",
        "type": "locker",
        "city": "Paris",
        "postal_code": "75001",
        "street": "12 Rue de l'Oratoire",
        "lat": 48.8625,
        "lon": 2.3367,
        "available_slots": 14,
        "opening_hours": "24/7",
        "distance_hint_km": 1.2,
    },
    "PP-PAR-002": {
        "pickup_point_id": "PP-PAR-002",
        "name": "Bastille Relay",
        "type": "partner_shop",
        "city": "Paris",
        "postal_code": "75011",
        "street": "41 Boulevard Richard-Lenoir",
        "lat": 48.8593,
        "lon": 2.3701,
        "available_slots": 7,
        "opening_hours": "Mon-Sat 08:30-20:00",
        "distance_hint_km": 2.9,
    },
    "PP-PAR-003": {
        "pickup_point_id": "PP-PAR-003",
        "name": "La Poste Montparnasse",
        "type": "post_office",
        "city": "Paris",
        "postal_code": "75015",
        "street": "38 Rue du Depart",
        "lat": 48.8414,
        "lon": 2.3209,
        "available_slots": 21,
        "opening_hours": "Mon-Fri 08:00-19:00, Sat 09:00-12:30",
        "distance_hint_km": 3.4,
    },
    "PP-ISS-001": {
        "pickup_point_id": "PP-ISS-001",
        "name": "Issy Val de Seine Locker",
        "type": "locker",
        "city": "Issy-les-Moulineaux",
        "postal_code": "92130",
        "street": "7 Rue Rouget de Lisle",
        "lat": 48.8299,
        "lon": 2.2636,
        "available_slots": 9,
        "opening_hours": "24/7",
        "distance_hint_km": 1.8,
    },
    "PP-BOL-001": {
        "pickup_point_id": "PP-BOL-001",
        "name": "Boulogne Centre Relay",
        "type": "partner_shop",
        "city": "Boulogne-Billancourt",
        "postal_code": "92100",
        "street": "102 Avenue Jean Baptiste Clement",
        "lat": 48.8369,
        "lon": 2.2402,
        "available_slots": 5,
        "opening_hours": "Mon-Sat 09:00-19:30",
        "distance_hint_km": 3.8,
    },
}


# Create a FastMCP server (provides @tool and compatible transports)
server = FastMCP(name="postal-mcp")


@server.tool()
async def who_am_i_demo(ctx: Context) -> Dict[str, Any]:
    """Return the caller identity as seen by the postal demo MCP server."""
    return {"ok": True, "caller": _resolve_demo_caller(ctx)}


def _now_ts() -> int:
    return int(time.time())


def _record_event(pkg: Dict[str, Any], event: str, **details: Any) -> None:
    item: Dict[str, Any] = {"ts": _now_ts(), "event": event}
    if details:
        item["details"] = details
    pkg.setdefault("history", []).append(item)


def _ensure_package_defaults(tracking_id: str, pkg: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_ts()
    pkg.setdefault("tracking_id", tracking_id)
    pkg.setdefault("status", "CREATED")
    pkg.setdefault("history", [])
    pkg.setdefault("created_at_ts", now)
    pkg.setdefault("flags", [])
    pkg.setdefault("notifications", [])
    pkg.setdefault("claims", [])
    pkg.setdefault(
        "current_location",
        {
            "kind": "hub",
            "hub_id": "HUB-PAR-01",
            "label": "Paris Distribution Hub",
            "lat": 48.8566,
            "lon": 2.3522,
        },
    )

    if "eta" not in pkg:
        promised_days = 2 if pkg.get("service") == "express" else 5
        promised_ts = now + promised_days * 24 * 3600
        pkg["eta"] = {
            "promised_ts": promised_ts,
            "estimated_ts": promised_ts,
            "delay_minutes": 0,
        }
    else:
        eta = pkg["eta"]
        promised_days = 2 if pkg.get("service") == "express" else 5
        eta.setdefault("promised_ts", now + promised_days * 24 * 3600)
        eta.setdefault("estimated_ts", eta["promised_ts"])
        eta.setdefault("delay_minutes", 0)

    if "delivery" not in pkg:
        pkg["delivery"] = {
            "mode": "home",
            "address": dict(pkg.get("address", {})),
            "pickup_point_id": None,
            "pickup_point_name": None,
            "scheduled_date": None,
            "time_window": None,
            "reroute_eligible": True,
        }
    else:
        delivery = pkg["delivery"]
        delivery.setdefault("mode", "home")
        delivery.setdefault("address", dict(pkg.get("address", {})))
        delivery.setdefault("pickup_point_id", None)
        delivery.setdefault("pickup_point_name", None)
        delivery.setdefault("scheduled_date", None)
        delivery.setdefault("time_window", None)
        delivery.setdefault("reroute_eligible", True)

    return pkg


def _recompute_delay_minutes(pkg: Dict[str, Any]) -> None:
    eta = pkg.get("eta", {})
    delay_seconds = max(0, int(eta.get("estimated_ts", 0)) - int(eta.get("promised_ts", 0)))
    eta["delay_minutes"] = delay_seconds // 60


def _package_actions_available(pkg: Dict[str, Any]) -> List[str]:
    status = pkg.get("status")
    if status in _TERMINAL_PACKAGE_STATUSES:
        return []

    delivery = pkg.get("delivery", {})
    actions = ["notify_customer"]
    if delivery.get("mode") == "home":
        actions.append("reschedule_delivery")
        if delivery.get("reroute_eligible", True):
            actions.append("reroute_package_to_pickup_point")
    if pkg.get("eta", {}).get("delay_minutes", 0) >= 60:
        actions.extend(["estimate_compensation", "open_claim"])
    return actions


def _find_pickup_point(pickup_point_id: str) -> Optional[Dict[str, Any]]:
    return _PICKUP_POINTS.get(pickup_point_id)


def _score_pickup_point(city: str, postal_code: str, point: Dict[str, Any]) -> float:
    score = float(point.get("distance_hint_km", 10.0))
    if point.get("city", "").lower() != city.lower():
        score += 20.0
    if postal_code and point.get("postal_code", "")[:2] != postal_code[:2]:
        score += 3.0
    if point.get("available_slots", 0) <= 0:
        score += 100.0
    return score


def _pickup_points_nearby(city: str, postal_code: str, limit: int) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for point in _PICKUP_POINTS.values():
        item = dict(point)
        item["distance_km"] = round(_score_pickup_point(city, postal_code, point), 1)
        candidates.append(item)
    candidates.sort(key=lambda p: (p["distance_km"], -p.get("available_slots", 0)))
    return candidates[: max(1, min(limit, 10))]


def _estimate_compensation_amount(pkg: Dict[str, Any]) -> Dict[str, Any]:
    delay_minutes = int(pkg.get("eta", {}).get("delay_minutes", 0))
    service = pkg.get("service", "standard")
    amount = 0.0
    policy_code = "DEMO-NO-COMP"
    reason = "Delay below compensation threshold"

    if service == "express" and delay_minutes >= 24 * 60:
        amount = 8.0
        policy_code = "DEMO-EXPRESS-24H"
        reason = "Express shipment delayed by at least 24h"
    elif service == "standard" and delay_minutes >= 48 * 60:
        amount = 4.0
        policy_code = "DEMO-STANDARD-48H"
        reason = "Standard shipment delayed by at least 48h"

    return {
        "eligible": amount > 0,
        "estimated_amount_eur": amount,
        "delay_minutes": delay_minutes,
        "policy_code": policy_code,
        "reason": reason,
    }


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
    pkg = {
        "tracking_id": tracking_id,
        "receiver": receiver_name,
        "address": addr,
        "service": service,
        "status": "CREATED",
        "history": [
            {"ts": _now_ts(), "event": "LABEL_CREATED"},
        ],
    }
    _ensure_package_defaults(tracking_id, pkg)
    _PACKAGES[tracking_id] = pkg
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
    _ensure_package_defaults(tracking_id, pkg)

    # Simulate a tiny progression over time (illustrative only)
    if len(pkg["history"]) == 1 and pkg["status"] == "CREATED":
        pkg["status"] = "IN_TRANSIT"
        pkg["current_location"] = {
            "kind": "vehicle",
            "vehicle_id": "VAN-42",
            "label": "Linehaul vehicle VAN-42",
            "lat": 48.8722,
            "lon": 2.3470,
        }
        _record_event(pkg, "PICKED_UP")
    elif len(pkg["history"]) == 2 and pkg["status"] == "IN_TRANSIT":
        pkg["status"] = "OUT_FOR_DELIVERY"
        pkg["current_location"] = {
            "kind": "vehicle",
            "vehicle_id": "VAN-17",
            "label": "Delivery route VAN-17",
            "lat": 48.8580,
            "lon": 2.3415,
        }
        _record_event(pkg, "HUB_DEPARTURE")

    _recompute_delay_minutes(pkg)
    return {
        "ok": True,
        "tracking_id": tracking_id,
        "status": pkg["status"],
        "receiver": pkg.get("receiver"),
        "service": pkg.get("service"),
        "history": pkg["history"],
        "current_location": pkg.get("current_location"),
        "delivery": pkg.get("delivery"),
        "eta": pkg.get("eta"),
        "flags": pkg.get("flags", []),
        "actions_available": _package_actions_available(pkg),
        "notifications_count": len(pkg.get("notifications", [])),
        "claims_count": len(pkg.get("claims", [])),
    }


@server.tool()
async def list_my_active_parcels(
    ctx: Context,
    include_terminal: bool = False,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    List parcels linked to the current caller identity in the demo environment.

    Use this when the user asks questions such as:
    - "Ai-je un colis en cours ?"
    - "Y a-t-il un colis pour moi en attente ou en livraison ?"
    - "Montre mes colis actifs"

    This is the missing "find my parcels" capability used by generic tool agents.
    """
    caller = _resolve_demo_caller(ctx)
    try:
        limit_i = int(limit)
    except (TypeError, ValueError):
        limit_i = 10
    limit_i = max(1, min(limit_i, 20))

    parcels: List[Dict[str, Any]] = []
    for tracking_id, pkg in _PACKAGES.items():
        _ensure_package_defaults(tracking_id, pkg)
        if not _caller_matches_package(caller, pkg):
            continue
        status = str(pkg.get("status") or "UNKNOWN")
        if not include_terminal and status in _TERMINAL_PACKAGE_STATUSES:
            continue
        _recompute_delay_minutes(pkg)
        delivery = pkg.get("delivery") or {}
        eta = pkg.get("eta") or {}
        current_location = pkg.get("current_location") or {}
        parcels.append(
            {
                "tracking_id": tracking_id,
                "status": status,
                "service": pkg.get("service"),
                "receiver": pkg.get("receiver"),
                "created_at_ts": pkg.get("created_at_ts"),
                "updated_event_count": len(pkg.get("history", [])),
                "actions_available": _package_actions_available(pkg),
                "delay_minutes": eta.get("delay_minutes"),
                "delivery_mode": delivery.get("mode"),
                "pickup_point_id": delivery.get("pickup_point_id"),
                "pickup_point_name": delivery.get("pickup_point_name"),
                "scheduled_date": delivery.get("scheduled_date"),
                "time_window": delivery.get("time_window"),
                "current_location": {
                    "kind": current_location.get("kind"),
                    "label": current_location.get("label"),
                },
            }
        )

    parcels.sort(
        key=lambda p: (
            p.get("status") in _TERMINAL_PACKAGE_STATUSES,
            -(int(p.get("created_at_ts") or 0)),
        )
    )
    visible = parcels[:limit_i]

    return {
        "ok": True,
        "caller": caller,
        "has_active_parcels": bool(visible),
        "count": len(visible),
        "total_matched": len(parcels),
        "parcels": visible,
        "suggested_next_tools": ["track_package"] if visible else [],
    }


@server.tool()
async def seed_demo_parcel_exception(
    receiver_name: str = "Claire Martin",
    city: str = "Paris",
    postal_code: str = "75015",
    street: str = "85 Rue de Vaugirard",
    service: Literal["standard", "express"] = "express",
) -> Dict[str, Any]:
    """Create a repeatable delayed parcel scenario for demos."""
    addr = {
        "country": "FR",
        "city": city,
        "postal_code": postal_code,
        "street": street,
    }
    address_id = str(uuid.uuid4())
    _ADDRESSES[address_id] = addr

    tracking_id = "PKG-DEMO-" + uuid.uuid4().hex[:8].upper()
    now = _now_ts()
    promised_hours = 2 if service == "express" else 24
    delay_hours = 27 if service == "express" else 55
    promised_ts = now + promised_hours * 3600
    estimated_ts = promised_ts + delay_hours * 3600
    pkg: Dict[str, Any] = {
        "tracking_id": tracking_id,
        "receiver": receiver_name,
        "address": addr,
        "service": service,
        "status": "DELAYED_AT_HUB",
        "history": [
            {"ts": now - 8 * 3600, "event": "LABEL_CREATED"},
            {"ts": now - 7 * 3600, "event": "PICKED_UP"},
            {"ts": now - 5 * 3600, "event": "ARRIVED_AT_HUB", "details": {"hub_id": "HUB-PAR-01"}},
            {
                "ts": now - 20 * 60,
                "event": "DELAY_ALERT",
                "details": {"reason": "Hub congestion", "severity": "medium"},
            },
        ],
        "eta": {
            "promised_ts": promised_ts,
            "estimated_ts": estimated_ts,
            "delay_minutes": (estimated_ts - promised_ts) // 60,
        },
        "flags": ["DELAYED", "HUB_CONGESTION", "REROUTE_ELIGIBLE"],
        "current_location": {
            "kind": "hub",
            "hub_id": "HUB-PAR-01",
            "label": "Paris Distribution Hub",
            "lat": 48.8566,
            "lon": 2.3522,
        },
        "delivery": {
            "mode": "home",
            "address": dict(addr),
            "pickup_point_id": None,
            "pickup_point_name": None,
            "scheduled_date": None,
            "time_window": None,
            "reroute_eligible": True,
        },
        "notifications": [],
        "claims": [],
    }
    _ensure_package_defaults(tracking_id, pkg)
    _PACKAGES[tracking_id] = pkg

    nearby = _pickup_points_nearby(city=city, postal_code=postal_code, limit=3)
    return {
        "ok": True,
        "scenario": "parcel_exception_reroute",
        "address_id": address_id,
        "tracking_id": tracking_id,
        "status": pkg["status"],
        "summary": "Parcel delayed at hub; reroute to pickup point is eligible",
        "suggested_next_tools": [
            "track_package",
            "get_pickup_points_nearby",
            "reroute_package_to_pickup_point",
            "notify_customer",
        ],
        "nearby_pickup_points": nearby,
    }


@server.tool()
async def seed_demo_parcel_exception_for_current_user(
    ctx: Context,
    city: str = "Paris",
    postal_code: str = "75015",
    street: str = "85 Rue de Vaugirard",
    service: Literal["standard", "express"] = "express",
) -> Dict[str, Any]:
    """
    Create a delayed parcel scenario personalized to the caller identity.

    If no Bearer token is available (or OIDC is not configured), the server falls
    back to a stable demo identity ("Alice Martin").
    """
    caller = _resolve_demo_caller(ctx)
    seeded = await seed_demo_parcel_exception(
        receiver_name=str(caller.get("display_name") or "Alice Martin"),
        city=city,
        postal_code=postal_code,
        street=street,
        service=service,
    )
    if isinstance(seeded, dict):
        seeded["caller"] = caller
        tracking_id = str(seeded.get("tracking_id") or "")
        if tracking_id and tracking_id in _PACKAGES:
            _attach_owner_metadata_to_package(_PACKAGES[tracking_id], caller)
        seeded["summary"] = (
            f"Parcel delayed at hub for caller '{caller.get('display_name', 'Alice Martin')}' "
            f"(identity source={caller.get('source', 'unknown')})"
        )
    return seeded


@server.tool()
async def get_pickup_points_nearby(city: str, postal_code: str, limit: int = 3) -> Dict[str, Any]:
    """Return nearby pickup points for rerouting options."""
    results = _pickup_points_nearby(city=city, postal_code=postal_code, limit=limit)
    return {
        "ok": True,
        "search": {"city": city, "postal_code": postal_code, "limit": max(1, min(limit, 10))},
        "pickup_points": results,
    }


@server.tool()
async def reroute_package_to_pickup_point(
    tracking_id: str,
    pickup_point_id: str,
    reason: str = "customer_request",
) -> Dict[str, Any]:
    """Reroute a parcel from home delivery to a pickup point."""
    pkg = _PACKAGES.get(tracking_id)
    if not pkg:
        return {"ok": False, "error": "Unknown tracking_id"}
    _ensure_package_defaults(tracking_id, pkg)

    terminal_statuses = {"DELIVERED", "CANCELLED", "LOST"}
    if pkg["status"] in terminal_statuses:
        return {"ok": False, "error": f"Cannot reroute package in status {pkg['status']}"}

    delivery = pkg["delivery"]
    if not delivery.get("reroute_eligible", True):
        return {"ok": False, "error": "Package not eligible for reroute"}

    point = _find_pickup_point(pickup_point_id)
    if not point:
        return {"ok": False, "error": "Unknown pickup_point_id"}
    if int(point.get("available_slots", 0)) <= 0:
        return {"ok": False, "error": "Pickup point has no available capacity"}

    previous_pickup_id = delivery.get("pickup_point_id")
    if previous_pickup_id and previous_pickup_id in _PICKUP_POINTS:
        _PICKUP_POINTS[previous_pickup_id]["available_slots"] += 1

    point["available_slots"] -= 1
    delivery.update(
        {
            "mode": "pickup_point",
            "pickup_point_id": point["pickup_point_id"],
            "pickup_point_name": point["name"],
            "pickup_point_address": {
                "city": point["city"],
                "postal_code": point["postal_code"],
                "street": point["street"],
            },
            "time_window": None,
            "scheduled_date": None,
        }
    )
    pkg["status"] = "REROUTED_TO_PICKUP_POINT"
    if "REROUTED" not in pkg["flags"]:
        pkg["flags"].append("REROUTED")

    pkg["eta"]["estimated_ts"] = int(pkg["eta"]["estimated_ts"]) + 8 * 3600
    _recompute_delay_minutes(pkg)
    _record_event(
        pkg,
        "REROUTED_TO_PICKUP_POINT",
        pickup_point_id=point["pickup_point_id"],
        pickup_point_name=point["name"],
        reason=reason,
    )

    return {
        "ok": True,
        "tracking_id": tracking_id,
        "status": pkg["status"],
        "delivery": pkg["delivery"],
        "eta": pkg["eta"],
        "next_recommended_action": "notify_customer",
    }


@server.tool()
async def reschedule_delivery(
    tracking_id: str,
    requested_date: str,
    time_window: Literal["morning", "afternoon", "evening"],
) -> Dict[str, Any]:
    """Reschedule home delivery to a new date/time window."""
    pkg = _PACKAGES.get(tracking_id)
    if not pkg:
        return {"ok": False, "error": "Unknown tracking_id"}
    _ensure_package_defaults(tracking_id, pkg)

    delivery = pkg["delivery"]
    if delivery.get("mode") != "home":
        return {"ok": False, "error": "Reschedule applies only to home delivery"}

    delivery["scheduled_date"] = requested_date
    delivery["time_window"] = time_window
    pkg["status"] = "DELIVERY_RESCHEDULED"
    _record_event(pkg, "DELIVERY_RESCHEDULED", requested_date=requested_date, time_window=time_window)

    return {
        "ok": True,
        "tracking_id": tracking_id,
        "status": pkg["status"],
        "delivery": pkg["delivery"],
    }


@server.tool()
async def notify_customer(
    tracking_id: str,
    channel: Literal["sms", "email"],
    message: str,
) -> Dict[str, Any]:
    """Log a customer notification (demo stub for CRM/notification integration)."""
    pkg = _PACKAGES.get(tracking_id)
    if not pkg:
        return {"ok": False, "error": "Unknown tracking_id"}
    _ensure_package_defaults(tracking_id, pkg)

    notification_id = "NTF-" + uuid.uuid4().hex[:10].upper()
    notification = {
        "notification_id": notification_id,
        "channel": channel,
        "message": message,
        "sent_at_ts": _now_ts(),
    }
    pkg["notifications"].append(notification)
    _record_event(pkg, "CUSTOMER_NOTIFIED", channel=channel, notification_id=notification_id)

    return {
        "ok": True,
        "tracking_id": tracking_id,
        "notification_id": notification_id,
        "channel": channel,
        "message_preview": message[:160],
    }


@server.tool()
async def estimate_compensation(tracking_id: str) -> Dict[str, Any]:
    """Estimate compensation eligibility for a delayed parcel (demo logic)."""
    pkg = _PACKAGES.get(tracking_id)
    if not pkg:
        return {"ok": False, "error": "Unknown tracking_id"}
    _ensure_package_defaults(tracking_id, pkg)
    _recompute_delay_minutes(pkg)

    estimate = _estimate_compensation_amount(pkg)
    return {
        "ok": True,
        "tracking_id": tracking_id,
        "service": pkg.get("service"),
        **estimate,
    }


@server.tool()
async def open_claim(
    tracking_id: str,
    reason: Literal["delay", "damage", "loss"] = "delay",
    description: str = "Customer reported issue",
) -> Dict[str, Any]:
    """Open a basic customer claim linked to a shipment."""
    pkg = _PACKAGES.get(tracking_id)
    if not pkg:
        return {"ok": False, "error": "Unknown tracking_id"}
    _ensure_package_defaults(tracking_id, pkg)

    claim_id = "CLM-" + uuid.uuid4().hex[:10].upper()
    compensation = _estimate_compensation_amount(pkg)
    claim = {
        "claim_id": claim_id,
        "tracking_id": tracking_id,
        "reason": reason,
        "description": description,
        "status": "OPEN",
        "created_at_ts": _now_ts(),
        "estimated_compensation_eur": compensation["estimated_amount_eur"],
    }
    _CLAIMS[claim_id] = claim
    pkg["claims"].append(claim_id)
    _record_event(pkg, "CLAIM_OPENED", claim_id=claim_id, reason=reason)

    return {
        "ok": True,
        "claim_id": claim_id,
        "tracking_id": tracking_id,
        "status": "OPEN",
        "estimated_compensation_eur": compensation["estimated_amount_eur"],
    }


# Expose the Streamable HTTP transport under /mcp
# This returns a Starlette app that uvicorn can serve directly
app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("postal_service_mcp_server.server_mcp:app", host="127.0.0.1", port=9797, reload=False)
