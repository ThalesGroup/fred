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
  - get_maintenance_events(api_url, engine_id, start_at, ...)
  - search_assets(query, model, designation, created_after, ...)
"""

from __future__ import annotations

from typing import Dict, Any, Literal, Optional
import time
import uuid
from datetime import datetime

try:
    # Use FastMCP (ergonomic server with @tool decorator) and build a Starlette app
    from mcp.server import FastMCP
except Exception as e:  # pragma: no cover - helpful error at import time
    raise ImportError(
        "The 'mcp' package is required for postal_service_mcp_server.server_mcp.\n"
        'Install it via: pip install "mcp[fastapi]"\n'
        f"Import error: {e}"
    )

# Import the portable Geosecur API client
from .geosecur_client import create_default_client

# In-memory stores (tutorial-grade persistence)
_ADDRESSES: Dict[str, Dict[str, str]] = {}
_PACKAGES: Dict[str, Dict[str, Any]] = {}

# Create Geosecur API client instance
_geosecur_client = create_default_client()


def serialize_asset_response(kuzzle_document: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a Kuzzle asset document to simplified format.

    Transforms complex Kuzzle document structure to a simplified format
    matching assetsresponse.json structure with French comments.

    Args:
        kuzzle_document: Raw document from Kuzzle search response

    Returns:
        Simplified asset dict with French field comments
    """
    doc_id = kuzzle_document.get("_id", "")
    source = kuzzle_document.get("_source", {})

    # Extract metadata
    metadata = source.get("metadata", {})

    # Extract position data from positionSpeed measure
    measures = source.get("measures", {})
    position_speed = measures.get("positionSpeed", {})
    position_values = position_speed.get("values", {})
    position = position_values.get("position", {})

    # Extract Kuzzle system info
    kuzzle_info = source.get("_kuzzle_info", {})

    return {
        "_id": doc_id,  # asset id is a combination of model and immatriculation
        "model": source.get("model", ""),  # asset model could be Semi or CaisseMobile
        "reference": source.get(
            "reference", ""
        ),  # immatriculation number format nnAAAnn or AAnnnAA for Semi or CMnnnn for CaisseMobile
        "designation": metadata.get("designation", ""),
        "codeInventaire": metadata.get("codeInventaire", ""),
        "platformId": metadata.get(
            "platformId", ""
        ),  # id of platform where asset is presently located
        "lastPlatformId": metadata.get(
            "lastPlatformId", ""
        ),  # id of last platform where asset was located if platformID is empty
        "owner": metadata.get("owner", ""),
        "actif": metadata.get("actif", False),  # if asset is actif or not
        "inOutGeofenceAt": metadata.get(
            "inOutGeofenceAt"
        ),  # timestamp of last in or out geofence event when asset enter platformId geofence or leave it
        "bearing": position_values.get("bearing", 0),
        "speedkmh": position_values.get("speedkmh", 0),  # speed in km/h
        "longitude": position.get("lon", 0),
        "latitude": position.get("lat", 0),
        "speed": position_values.get("speed", 0),  # speed in m/s
        "measuredAt": position_speed.get(
            "measuredAt"
        ),  # timestamp of last positionSpeed measurement
        "type": "positionSpeed",
        "originId": position_speed.get(
            "originId", ""
        ),  # id of device that sent the geolocalization
        "payloadUuids": position_speed.get("payloadUuids", []),
        "author": kuzzle_info.get("author", ""),
        "createdAt": kuzzle_info.get("createdAt"),  # document creation timestamp
        "updatedAt": kuzzle_info.get("updatedAt"),  # document last update timestamp
        "updater": kuzzle_info.get("updater"),
    }


# Create a FastMCP server (provides @tool and compatible transports)
server = FastMCP(name="postal-mcp")


@server.tool()
async def validate_address(
    country: str, city: str, postal_code: str, street: str
) -> Dict[str, Any]:
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
    price = round(
        (base + distance_km * per_km + weight_kg * per_kg) * speed_multiplier, 2
    )
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


@server.tool()
async def get_maintenance_events(
    start_at: str,
    end_at: Optional[str] = None,
    timezone: str = "Europe/Paris",
    size: int = 10000,
    format_type: Literal["json", "csv", "xml"] = "json",
    csv_separator: Literal[",", ";"] = ",",
) -> Dict[str, Any]:
    """Get maintenance events from the géosecur API.

    Retrieves maintenance events within a specified time period from the
    géosecur maintenance API using pre-configured URL and authentication.
    Supports different output formats (JSON, CSV, XML) for analysis and data export.

    Args:
        start_at: Start date in French format (dd-mm-yyyy hh:mm:ss) in local time
        end_at: End date in French format (optional, defaults to 24h after start_at)
        timezone: Timezone for date interpretation (default: Europe/Paris)
        size: Number of results to return (default: 10000)
        format_type: Output format - json, csv, or xml (default: json)
        csv_separator: CSV separator character - comma or semicolon (default: comma)

    Returns:
        Dictionary containing the API response with maintenance events data

    Note:
        Automatically handles JWT authentication using login credentials.
        Uses GEOSECUR_USERNAME and GEOSECUR_PASSWORD environment variables (defaults: geosecur-admin/pass).
        JWT tokens are cached and automatically refreshed when expired.
        Uses pre-configured API URL and engine ID for géosecur service.
    """
    # Validate date format (basic check)
    try:
        datetime.strptime(start_at, "%d-%m-%Y %H:%M:%S")
        if end_at:
            datetime.strptime(end_at, "%d-%m-%Y %H:%M:%S")
    except ValueError as e:
        return {
            "success": False,
            "error": f"Invalid date format. Use dd-mm-yyyy hh:mm:ss format. Error: {str(e)}",
        }

    # Use the portable Geosecur client
    result = await _geosecur_client.get_maintenance_events(
        start_at=start_at,
        end_at=end_at,
        timezone=timezone,
        size=size,
        format_type=format_type,
        csv_separator=csv_separator,
    )

    return result


@server.tool()
async def search_assets(
    query: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    designation: Optional[str] = None,
    actif: bool = True,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    measured_after: Optional[str] = None,
    measured_before: Optional[str] = None,
    size: int = 10000,
    from_: int = 0,
) -> Dict[str, Any]:
    """Search assets in the Kuzzle collection with optional filters.

    Retrieves asset data from the 'assets' collection in Kuzzle v2 database.
    Supports filtering by asset model, immatriculation, actif, creation dates, and position measurement dates. Every filter has a default value

    Args:
        model: Model of asset, exact value could be Semi or CaisseMobile, by default all models. In natural language Semi if for semi-remorque, semi etc.. and CaisseMobile for Caisse Mobile
            Example: "Semi", "CaisseMobile"
        designation: license plate number format nnAAAnn or AAnnnAA for model "Semi" or CMnnnn for model "CaisseMobile, by default all designation
            Example: "428RNK75", "ER193WE", "CM0191
        actif: Filter by asset status - True for active assets, False for inactive assets (default: True)
            Accepts boolean True/False or string "true"/"false"
        created_after: Filter documents created after this date
            Accepts ISO format (2024-01-01T00:00:00Z) or timestamp (1704067200000)
        created_before: Filter documents created before this date
            Accepts ISO format (2024-12-31T23:59:59Z) or timestamp (1735689599000)
        measured_after: Filter by positionSpeed measurement after this date
            Accepts ISO format (2024-01-01T00:00:00Z) or timestamp (1704067200000)
        measured_before: Filter by positionSpeed measurement before this date
            Accepts ISO format (2024-12-31T23:59:59Z) or timestamp (1735689599000)

    Returns:
        Dictionary containing:
        - success: Boolean indicating if the request was successful
        - data: The Kuzzle API response with asset documents
        - error: Error message if the request failed

    Example Response Structure (Simplified Format):
        {
            "success": true,
            "total": 1977000,
            "assets": [
                {
                    "_id": "Semi-428RNK75",  // asset id is a combination of model and immatriculation
                    "model": "Semi",  // asset model could be Semi or CaisseMobile
                    "reference": "428RNK75",  // immatriculation number format nnAAAnn or AAnnnAA for Semi or CMnnnn for CaisseMobile
                    "designation": "428RNK75",
                    "codeInventaire": "L115713946000066",
                    "platformId": "IDF NORD PFC",  // id of platform where asset is presently located
                    "lastPlatformId": "IDF NORD PFC",  // id of last platform where asset was located if platformID is empty
                    "owner": "laposte",
                    "actif": false,  // if asset is actif or not
                    "inOutGeofenceAt": 1715867895000,  // timestamp of last in or out geofence event
                    "bearing": 0,
                    "speedkmh": 0,  // speed in km/h
                    "longitude": 2.4834,
                    "latitude": 49.0065,
                    "speed": 0,  // speed in m/s
                    "measuredAt": 1715925913000,  // timestamp of last positionSpeed measurement
                    "type": "positionSpeed",
                    "originId": "FleetConnected-1911485",  // id of device that sent the geolocalization
                    "payloadUuids": [],
                    "author": "geosecur-admin",
                    "createdAt": 1667325047125,  // document creation timestamp
                    "updatedAt": 1716882183682,  // document last update timestamp
                    "updater": null
                }
            ],
            "metadata": {
                "size": 10000,
                "from": 0,
                "returned": 1
            }
        }

    Note:
        - Automatically handles JWT authentication using GeosecurClient
        - Date filters can use ISO format or Unix timestamps in milliseconds
        - Results include asset metadata, measures, and Kuzzle system information
        - Uses the 'tenant-geosecur-laposte' index and 'assets' collection
    """
    # Validate parameters
    if size > 10000:
        return {"success": False, "error": "Size parameter cannot exceed 10000 results"}

    if from_ < 0:
        return {"success": False, "error": "from_ parameter must be >= 0"}

    # Normalize actif parameter to handle string values from LLM
    def normalize_boolean(value):
        """Convert string 'true'/'false' to boolean, handle existing booleans."""
        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            normalized_str = value.strip().lower()
            if normalized_str == "true":
                return True
            elif normalized_str == "false":
                return False
            else:
                raise ValueError(
                    f"Invalid boolean string: {value}. Expected 'true' or 'false'"
                )
        else:
            raise TypeError(f"actif must be boolean or string, got {type(value)}")

    try:
        actif_normalized = normalize_boolean(actif)
    except (ValueError, TypeError) as e:
        return {"success": False, "error": f"Invalid actif parameter: {str(e)}"}

    # Use the Geosecur client to search assets
    result = await _geosecur_client.search_assets(
        query=query,
        model=model,
        designation=designation,
        actif=actif_normalized,
        created_after=created_after,
        created_before=created_before,
        measured_after=measured_after,
        measured_before=measured_before,
        size=size,
        from_=from_,
    )

    # If successful, serialize the response to simplified format
    if result.get("success") and result.get("data"):
        kuzzle_response = result["data"]
        if "result" in kuzzle_response and "hits" in kuzzle_response["result"]:
            # Serialize each asset hit to simplified format
            simplified_hits = [
                serialize_asset_response(hit)
                for hit in kuzzle_response["result"]["hits"]
            ]
            print(f"Serialized {len(simplified_hits)} assets from Kuzzle response.")

            return {
                "success": True,
                "total": kuzzle_response["result"].get("total", len(simplified_hits)),
                "assets": simplified_hits,
                "metadata": {
                    "size": size,
                    "from": from_,
                    "returned": len(simplified_hits),
                },
            }

    return result


# Expose the Streamable HTTP transport under /mcp
# This returns a Starlette app that uvicorn can serve directly
app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "postal_service_mcp_server.server_mcp:app",
        host="127.0.0.1",
        port=9797,
        reload=False,
    )
