"""
iot_tracking_mcp_server/server_mcp.py
-------------------------------------
Simulated IoT MCP server for parcel tracking demos.

This exposes the Streamable HTTP transport at `/mcp` and is compatible with
modern MCP clients.

Run:
  uvicorn iot_tracking_mcp_server.server_mcp:app --host 127.0.0.1 --port 9798 --reload
  or: make run

Tools implemented:
  - seed_demo_tracking_incident(tracking_id, scenario, hub_id, vehicle_id)
  - get_live_tracking_snapshot(tracking_id)
  - list_tracking_events(tracking_id, since_seq, limit)
  - get_hub_status(hub_id, tracking_id)
  - get_vehicle_position(vehicle_id, tracking_id)
  - get_route_geometry(tracking_id)
  - get_locker_occupancy(pickup_point_id)
  - acknowledge_alert(tracking_id, alert_id, operator)
  - advance_simulation_tick(tracking_id, steps)
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
import copy
import time
import uuid

try:
    from mcp.server import FastMCP
except Exception as e:  # pragma: no cover
    raise ImportError(
        "The 'mcp' package is required for iot_tracking_mcp_server.server_mcp.\n"
        "Install it via: pip install \"mcp[fastapi]\"\n"
        f"Import error: {e}"
    )


server = FastMCP(name="iot-tracking-mcp")


_SCENARIOS: Dict[str, Dict[str, Any]] = {}

_HUBS: Dict[str, Dict[str, Any]] = {
    "HUB-PAR-01": {
        "hub_id": "HUB-PAR-01",
        "name": "Paris Distribution Hub",
        "city": "Paris",
        "lat": 48.8566,
        "lon": 2.3522,
        "operational_state": "OPERATIONAL",
        "nominal_throughput_parcels_per_hour": 4200,
        "nominal_queue_depth": 180,
    },
    "HUB-IDF-02": {
        "hub_id": "HUB-IDF-02",
        "name": "Ile-de-France East Hub",
        "city": "Noisy-le-Grand",
        "lat": 48.8464,
        "lon": 2.5486,
        "operational_state": "OPERATIONAL",
        "nominal_throughput_parcels_per_hour": 3100,
        "nominal_queue_depth": 140,
    },
}

_VEHICLES: Dict[str, Dict[str, Any]] = {
    "VAN-17": {
        "vehicle_id": "VAN-17",
        "vehicle_type": "delivery_van",
        "fleet": "Paris Last-Mile",
        "capacity_parcels": 180,
    },
    "VAN-42": {
        "vehicle_id": "VAN-42",
        "vehicle_type": "linehaul_van",
        "fleet": "Paris Linehaul",
        "capacity_parcels": 240,
    },
}

_LOCKERS: Dict[str, Dict[str, Any]] = {
    "PP-PAR-001": {
        "pickup_point_id": "PP-PAR-001",
        "name": "Paris Louvre Locker",
        "kind": "locker",
        "lat": 48.8625,
        "lon": 2.3367,
        "total_cells": 48,
        "occupied_cells": 31,
        "door_health": "OK",
        "power_status": "MAINS",
        "network_status": "ONLINE",
    },
    "PP-ISS-001": {
        "pickup_point_id": "PP-ISS-001",
        "name": "Issy Val de Seine Locker",
        "kind": "locker",
        "lat": 48.8299,
        "lon": 2.2636,
        "total_cells": 36,
        "occupied_cells": 22,
        "door_health": "OK",
        "power_status": "MAINS",
        "network_status": "ONLINE",
    },
}


def _now_ts() -> int:
    return int(time.time())


def _hub_route_polyline(hub_id: str) -> List[Dict[str, float]]:
    hub = _HUBS.get(hub_id, _HUBS["HUB-PAR-01"])
    return [
        {"lat": hub["lat"], "lon": hub["lon"]},
        {"lat": 48.8607, "lon": 2.3451},
        {"lat": 48.8629, "lon": 2.3388},
        {"lat": 48.8625, "lon": 2.3367},
    ]


def _tracking_suffix(tracking_id: str) -> str:
    compact = tracking_id.replace("-", "")
    return compact[-6:].upper() if compact else "DEMO00"


def _build_timeline(
    tracking_id: str,
    hub_id: str,
    vehicle_id: str,
    scenario: str,
    base_ts: int,
) -> Dict[str, Any]:
    suffix = _tracking_suffix(tracking_id)
    hub_alert_id = f"ALT-{suffix}-HUBCONG"
    route_alert_id = f"ALT-{suffix}-ROUTEDELAY"
    sensor_id = f"SNS-{suffix}"

    if scenario != "hub_congestion_delay":
        scenario = "hub_congestion_delay"

    route_polyline = _hub_route_polyline(hub_id)

    tick_templates: List[Dict[str, Any]] = [
        {
            "label": "Hub congestion detected",
            "hub_status": {
                "hub_id": hub_id,
                "operational_state": "DEGRADED",
                "congestion_level": "HIGH",
                "queue_depth": 540,
                "throughput_parcels_per_hour": 2600,
                "processing_delay_minutes": 95,
            },
            "vehicle_position": {
                "vehicle_id": vehicle_id,
                "status": "WAITING_AT_HUB",
                "lat": 48.8568,
                "lon": 2.3519,
                "speed_kmh": 0.0,
                "heading_deg": 0,
            },
            "parcel_sensor": {
                "sensor_id": sensor_id,
                "battery_percent": 87,
                "temperature_c": 21.6,
                "shock_g": 0.2,
                "heartbeat_age_sec": 11,
                "device_status": "OK",
            },
            "active_alerts": [
                {
                    "alert_id": hub_alert_id,
                    "type": "HUB_CONGESTION",
                    "severity": "medium",
                    "source": "hub_ops",
                    "message": "Hub queue depth above threshold for this shipment lane",
                }
            ],
            "events": [
                {
                    "type": "HUB_CONGESTION_ALERT",
                    "severity": "medium",
                    "source": "hub_ops",
                    "message": "Queue depth spike detected on Paris outbound lane",
                    "payload": {"hub_id": hub_id, "queue_depth": 540},
                },
                {
                    "type": "PARCEL_SCAN_CONFIRMED",
                    "severity": "info",
                    "source": "scanner",
                    "message": "Parcel present in staging zone at Paris hub",
                    "payload": {"hub_id": hub_id, "zone": "B-12"},
                },
            ],
            "recommended_actions": [
                "Check business ETA and reroute eligibility",
                "Offer pickup-point reroute if delay exceeds SLA threshold",
            ],
            "route_progress_percent": 5,
        },
        {
            "label": "Prioritized handling and vehicle assignment",
            "hub_status": {
                "hub_id": hub_id,
                "operational_state": "DEGRADED",
                "congestion_level": "MEDIUM",
                "queue_depth": 390,
                "throughput_parcels_per_hour": 3000,
                "processing_delay_minutes": 65,
            },
            "vehicle_position": {
                "vehicle_id": vehicle_id,
                "status": "LOADING",
                "lat": 48.8567,
                "lon": 2.3520,
                "speed_kmh": 0.0,
                "heading_deg": 0,
            },
            "parcel_sensor": {
                "sensor_id": sensor_id,
                "battery_percent": 86,
                "temperature_c": 21.4,
                "shock_g": 0.3,
                "heartbeat_age_sec": 8,
                "device_status": "OK",
            },
            "active_alerts": [
                {
                    "alert_id": hub_alert_id,
                    "type": "HUB_CONGESTION",
                    "severity": "low",
                    "source": "hub_ops",
                    "message": "Congestion improving but parcel still delayed",
                }
            ],
            "events": [
                {
                    "type": "VEHICLE_ASSIGNED",
                    "severity": "info",
                    "source": "dispatch",
                    "message": "Vehicle assigned to delayed parcel recovery route",
                    "payload": {"vehicle_id": vehicle_id},
                },
                {
                    "type": "LOADING_STARTED",
                    "severity": "info",
                    "source": "dock",
                    "message": "Parcel loading started",
                    "payload": {"dock": "D4"},
                },
            ],
            "recommended_actions": [
                "Monitor last-mile route progress",
                "Notify customer only after ETA is recomputed",
            ],
            "route_progress_percent": 12,
        },
        {
            "label": "On route but traffic disruption",
            "hub_status": {
                "hub_id": hub_id,
                "operational_state": "OPERATIONAL",
                "congestion_level": "LOW",
                "queue_depth": 210,
                "throughput_parcels_per_hour": 3800,
                "processing_delay_minutes": 18,
            },
            "vehicle_position": {
                "vehicle_id": vehicle_id,
                "status": "IN_ROUTE",
                "lat": 48.8607,
                "lon": 2.3451,
                "speed_kmh": 18.0,
                "heading_deg": 300,
            },
            "parcel_sensor": {
                "sensor_id": sensor_id,
                "battery_percent": 84,
                "temperature_c": 22.2,
                "shock_g": 0.6,
                "heartbeat_age_sec": 6,
                "device_status": "OK",
            },
            "active_alerts": [
                {
                    "alert_id": route_alert_id,
                    "type": "ROUTE_DELAY",
                    "severity": "low",
                    "source": "traffic",
                    "message": "Temporary urban traffic slowdown on delivery corridor",
                }
            ],
            "events": [
                {
                    "type": "VEHICLE_DEPARTED_HUB",
                    "severity": "info",
                    "source": "dispatch",
                    "message": "Vehicle departed hub with parcel onboard",
                    "payload": {"vehicle_id": vehicle_id, "hub_id": hub_id},
                },
                {
                    "type": "TRAFFIC_SLOWDOWN_ALERT",
                    "severity": "low",
                    "source": "traffic",
                    "message": "Traffic slowdown detected on route segment",
                    "payload": {"segment": "PAR-CENTER-02", "delay_minutes": 14},
                },
            ],
            "recommended_actions": [
                "Re-evaluate customer ETA",
                "Pickup-point reroute remains a valid mitigation if customer requests",
            ],
            "route_progress_percent": 55,
        },
        {
            "label": "Approaching destination corridor",
            "hub_status": {
                "hub_id": hub_id,
                "operational_state": "OPERATIONAL",
                "congestion_level": "LOW",
                "queue_depth": 170,
                "throughput_parcels_per_hour": 4050,
                "processing_delay_minutes": 10,
            },
            "vehicle_position": {
                "vehicle_id": vehicle_id,
                "status": "IN_ROUTE",
                "lat": 48.8629,
                "lon": 2.3388,
                "speed_kmh": 12.0,
                "heading_deg": 280,
            },
            "parcel_sensor": {
                "sensor_id": sensor_id,
                "battery_percent": 83,
                "temperature_c": 22.0,
                "shock_g": 0.4,
                "heartbeat_age_sec": 5,
                "device_status": "OK",
            },
            "active_alerts": [],
            "events": [
                {
                    "type": "TRAFFIC_ALERT_CLEARED",
                    "severity": "info",
                    "source": "traffic",
                    "message": "Traffic disruption cleared",
                    "payload": {"segment": "PAR-CENTER-02"},
                },
            ],
            "recommended_actions": [
                "If rerouted, notify customer of pickup availability ETA",
            ],
            "route_progress_percent": 84,
        },
        {
            "label": "Ready for pickup handoff",
            "hub_status": {
                "hub_id": hub_id,
                "operational_state": "OPERATIONAL",
                "congestion_level": "LOW",
                "queue_depth": 160,
                "throughput_parcels_per_hour": 4100,
                "processing_delay_minutes": 8,
            },
            "vehicle_position": {
                "vehicle_id": vehicle_id,
                "status": "STOPPED",
                "lat": 48.8625,
                "lon": 2.3367,
                "speed_kmh": 0.0,
                "heading_deg": 0,
            },
            "parcel_sensor": {
                "sensor_id": sensor_id,
                "battery_percent": 82,
                "temperature_c": 21.8,
                "shock_g": 0.2,
                "heartbeat_age_sec": 4,
                "device_status": "OK",
            },
            "active_alerts": [],
            "events": [
                {
                    "type": "ARRIVED_DESTINATION_CORRIDOR",
                    "severity": "info",
                    "source": "gps",
                    "message": "Vehicle arrived in destination corridor",
                    "payload": {"vehicle_id": vehicle_id},
                },
            ],
            "recommended_actions": [
                "Confirm business-side reroute and customer notification",
            ],
            "route_progress_percent": 100,
        },
    ]

    next_seq = 1
    for tick_index, tick in enumerate(tick_templates):
        tick_ts = base_ts + tick_index * 180
        tick["tick"] = tick_index
        tick["observed_at_ts"] = tick_ts
        tick["hub_status"]["last_update_ts"] = tick_ts
        tick["vehicle_position"]["last_update_ts"] = tick_ts
        tick["parcel_sensor"]["last_update_ts"] = tick_ts
        tick["parcel_sensor"]["heartbeat_age_sec"] = int(tick["parcel_sensor"]["heartbeat_age_sec"])

        alerts: List[Dict[str, Any]] = []
        for alert in tick["active_alerts"]:
            a = dict(alert)
            a["status"] = "OPEN"
            a["started_at_ts"] = tick_ts
            alerts.append(a)
        tick["active_alerts"] = alerts

        enriched_events: List[Dict[str, Any]] = []
        for event in tick["events"]:
            ev = dict(event)
            ev["seq"] = next_seq
            ev["ts"] = tick_ts
            next_seq += 1
            enriched_events.append(ev)
        tick["events"] = enriched_events

    return {
        "scenario_id": "IOTSCN-" + uuid.uuid4().hex[:10].upper(),
        "scenario_type": scenario,
        "tracking_id": tracking_id,
        "hub_id": hub_id,
        "vehicle_id": vehicle_id,
        "created_at_ts": _now_ts(),
        "base_ts": base_ts,
        "current_tick": 0,
        "timeline": tick_templates,
        "route_geometry": {
            "route_id": f"ROUTE-{suffix}",
            "polyline": route_polyline,
            "pickup_point_hint_id": "PP-PAR-001",
        },
        "alert_acks": {},
        "manual_events": [],
        "next_event_seq": next_seq,
    }


def _scenario_or_error(tracking_id: str) -> Optional[Dict[str, Any]]:
    return _SCENARIOS.get(tracking_id)


def _current_tick(scenario: Dict[str, Any]) -> Dict[str, Any]:
    idx = max(0, min(int(scenario["current_tick"]), len(scenario["timeline"]) - 1))
    tick = copy.deepcopy(scenario["timeline"][idx])
    for alert in tick.get("active_alerts", []):
        ack = scenario.get("alert_acks", {}).get(alert["alert_id"])
        if ack:
            alert["acknowledged"] = True
            alert["acknowledged_by"] = ack["operator"]
            alert["acknowledged_at_ts"] = ack["acknowledged_at_ts"]
            alert["status"] = "ACKNOWLEDGED"
        else:
            alert["acknowledged"] = False
    return tick


def _events_up_to_current_tick(scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    max_idx = max(0, min(int(scenario["current_tick"]), len(scenario["timeline"]) - 1))
    events: List[Dict[str, Any]] = []
    for idx in range(max_idx + 1):
        for event in scenario["timeline"][idx]["events"]:
            events.append(copy.deepcopy(event))
    for event in scenario.get("manual_events", []):
        events.append(copy.deepcopy(event))
    events.sort(key=lambda e: (int(e.get("seq", 0)), int(e.get("ts", 0))))
    return events


def _map_markers(scenario: Dict[str, Any], tick: Dict[str, Any]) -> List[Dict[str, Any]]:
    markers: List[Dict[str, Any]] = []
    hub = _HUBS.get(scenario["hub_id"])
    if hub:
        markers.append(
            {
                "id": hub["hub_id"],
                "kind": "hub",
                "label": hub["name"],
                "lat": hub["lat"],
                "lon": hub["lon"],
            }
        )
    vehicle = tick.get("vehicle_position")
    if vehicle:
        markers.append(
            {
                "id": vehicle["vehicle_id"],
                "kind": "vehicle",
                "label": vehicle["vehicle_id"],
                "lat": vehicle["lat"],
                "lon": vehicle["lon"],
                "status": vehicle.get("status"),
            }
        )
    pp_id = scenario.get("route_geometry", {}).get("pickup_point_hint_id")
    locker = _LOCKERS.get(pp_id) if pp_id else None
    if locker:
        markers.append(
            {
                "id": locker["pickup_point_id"],
                "kind": "pickup_locker",
                "label": locker["name"],
                "lat": locker["lat"],
                "lon": locker["lon"],
            }
        )
    return markers


def _build_snapshot(scenario: Dict[str, Any]) -> Dict[str, Any]:
    tick = _current_tick(scenario)
    events = _events_up_to_current_tick(scenario)
    max_tick = len(scenario["timeline"]) - 1
    return {
        "ok": True,
        "tracking_id": scenario["tracking_id"],
        "scenario_id": scenario["scenario_id"],
        "scenario_type": scenario["scenario_type"],
        "tick": int(scenario["current_tick"]),
        "max_tick": max_tick,
        "phase": tick["label"],
        "observed_at_ts": tick["observed_at_ts"],
        "hub_status": tick["hub_status"],
        "vehicle_position": tick["vehicle_position"],
        "parcel_sensor": tick["parcel_sensor"],
        "active_alerts": tick.get("active_alerts", []),
        "recommended_actions": tick.get("recommended_actions", []),
        "route_progress_percent": tick.get("route_progress_percent", 0),
        "map_overlay": {
            "route_polyline": scenario["route_geometry"]["polyline"],
            "markers": _map_markers(scenario, tick),
        },
        "latest_events": events[-5:],
        "event_cursor": events[-1]["seq"] if events else 0,
    }


def _default_hub_status(hub_id: str) -> Optional[Dict[str, Any]]:
    hub = _HUBS.get(hub_id)
    if not hub:
        return None
    now = _now_ts()
    return {
        "hub_id": hub_id,
        "name": hub["name"],
        "city": hub["city"],
        "operational_state": hub["operational_state"],
        "congestion_level": "LOW",
        "queue_depth": hub["nominal_queue_depth"],
        "throughput_parcels_per_hour": hub["nominal_throughput_parcels_per_hour"],
        "processing_delay_minutes": 10,
        "last_update_ts": now,
        "lat": hub["lat"],
        "lon": hub["lon"],
    }


def _default_vehicle_status(vehicle_id: str) -> Optional[Dict[str, Any]]:
    vehicle = _VEHICLES.get(vehicle_id)
    if not vehicle:
        return None
    now = _now_ts()
    return {
        "vehicle_id": vehicle_id,
        "status": "IDLE",
        "lat": _HUBS["HUB-PAR-01"]["lat"],
        "lon": _HUBS["HUB-PAR-01"]["lon"],
        "speed_kmh": 0.0,
        "heading_deg": 0,
        "last_update_ts": now,
    }


def _find_scenario_for_hub(hub_id: str, tracking_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if tracking_id:
        scenario = _SCENARIOS.get(tracking_id)
        if scenario and scenario.get("hub_id") == hub_id:
            return scenario
        return None
    for scenario in _SCENARIOS.values():
        if scenario.get("hub_id") == hub_id:
            return scenario
    return None


def _find_scenario_for_vehicle(vehicle_id: str, tracking_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if tracking_id:
        scenario = _SCENARIOS.get(tracking_id)
        if scenario and scenario.get("vehicle_id") == vehicle_id:
            return scenario
        return None
    for scenario in _SCENARIOS.values():
        if scenario.get("vehicle_id") == vehicle_id:
            return scenario
    return None


@server.tool()
async def seed_demo_tracking_incident(
    tracking_id: str,
    scenario: Literal["hub_congestion_delay"] = "hub_congestion_delay",
    hub_id: str = "HUB-PAR-01",
    vehicle_id: str = "VAN-17",
) -> Dict[str, Any]:
    """Seed a deterministic IoT incident timeline linked to a business tracking_id."""
    if not tracking_id.strip():
        return {"ok": False, "error": "tracking_id must be non-empty"}
    if hub_id not in _HUBS:
        return {"ok": False, "error": "Unknown hub_id"}
    if vehicle_id not in _VEHICLES:
        return {"ok": False, "error": "Unknown vehicle_id"}

    base_ts = _now_ts() - 7 * 60
    seeded = _build_timeline(
        tracking_id=tracking_id,
        hub_id=hub_id,
        vehicle_id=vehicle_id,
        scenario=scenario,
        base_ts=base_ts,
    )
    _SCENARIOS[tracking_id] = seeded
    snapshot = _build_snapshot(seeded)

    return {
        "ok": True,
        "tracking_id": tracking_id,
        "scenario_id": seeded["scenario_id"],
        "scenario_type": seeded["scenario_type"],
        "hub_id": hub_id,
        "vehicle_id": vehicle_id,
        "summary": "Deterministic IoT incident seeded (hub congestion -> route delay -> recovery)",
        "suggested_next_tools": [
            "get_live_tracking_snapshot",
            "list_tracking_events",
            "get_hub_status",
            "advance_simulation_tick",
        ],
        "initial_snapshot": snapshot,
    }


@server.tool()
async def get_live_tracking_snapshot(tracking_id: str) -> Dict[str, Any]:
    """Return the current telemetry snapshot for a seeded tracking incident."""
    scenario = _scenario_or_error(tracking_id)
    if not scenario:
        return {
            "ok": False,
            "error": "Unknown tracking_id (seed a scenario first with seed_demo_tracking_incident)",
        }
    return _build_snapshot(scenario)


@server.tool()
async def list_tracking_events(tracking_id: str, since_seq: int = 0, limit: int = 20) -> Dict[str, Any]:
    """Return ordered telemetry/incident events with cursor-based polling."""
    scenario = _scenario_or_error(tracking_id)
    if not scenario:
        return {
            "ok": False,
            "error": "Unknown tracking_id (seed a scenario first with seed_demo_tracking_incident)",
        }
    events = _events_up_to_current_tick(scenario)
    capped_limit = max(1, min(limit, 100))
    filtered = [e for e in events if int(e.get("seq", 0)) > int(since_seq)]
    page = filtered[:capped_limit]
    has_more = len(filtered) > capped_limit
    next_cursor = page[-1]["seq"] if page else since_seq
    return {
        "ok": True,
        "tracking_id": tracking_id,
        "events": page,
        "has_more": has_more,
        "next_since_seq": next_cursor,
        "current_tick": scenario["current_tick"],
        "max_tick": len(scenario["timeline"]) - 1,
    }


@server.tool()
async def get_hub_status(hub_id: str, tracking_id: Optional[str] = None) -> Dict[str, Any]:
    """Return hub telemetry; optionally scenario-specific if tracking_id is provided."""
    hub = _HUBS.get(hub_id)
    if not hub:
        return {"ok": False, "error": "Unknown hub_id"}

    scenario = _find_scenario_for_hub(hub_id=hub_id, tracking_id=tracking_id)
    if scenario:
        tick = _current_tick(scenario)
        status = dict(tick["hub_status"])
        status.update({"name": hub["name"], "city": hub["city"], "lat": hub["lat"], "lon": hub["lon"]})
        return {
            "ok": True,
            "hub_id": hub_id,
            "tracking_id": scenario["tracking_id"],
            "scenario_id": scenario["scenario_id"],
            "status": status,
        }

    return {"ok": True, "hub_id": hub_id, "status": _default_hub_status(hub_id)}


@server.tool()
async def get_vehicle_position(vehicle_id: str, tracking_id: Optional[str] = None) -> Dict[str, Any]:
    """Return vehicle GPS/telemetry; optionally scenario-specific if tracking_id is provided."""
    vehicle = _VEHICLES.get(vehicle_id)
    if not vehicle:
        return {"ok": False, "error": "Unknown vehicle_id"}

    scenario = _find_scenario_for_vehicle(vehicle_id=vehicle_id, tracking_id=tracking_id)
    if scenario:
        tick = _current_tick(scenario)
        position = dict(tick["vehicle_position"])
        position.update(
            {
                "vehicle_type": vehicle["vehicle_type"],
                "fleet": vehicle["fleet"],
                "capacity_parcels": vehicle["capacity_parcels"],
            }
        )
        return {
            "ok": True,
            "vehicle_id": vehicle_id,
            "tracking_id": scenario["tracking_id"],
            "scenario_id": scenario["scenario_id"],
            "position": position,
        }

    default = _default_vehicle_status(vehicle_id)
    if not default:
        return {"ok": False, "error": "Unknown vehicle_id"}
    default.update(
        {
            "vehicle_type": vehicle["vehicle_type"],
            "fleet": vehicle["fleet"],
            "capacity_parcels": vehicle["capacity_parcels"],
        }
    )
    return {"ok": True, "vehicle_id": vehicle_id, "position": default}


@server.tool()
async def get_route_geometry(tracking_id: str) -> Dict[str, Any]:
    """Return route polyline and markers for a geo map visualization."""
    scenario = _scenario_or_error(tracking_id)
    if not scenario:
        return {
            "ok": False,
            "error": "Unknown tracking_id (seed a scenario first with seed_demo_tracking_incident)",
        }
    tick = _current_tick(scenario)
    return {
        "ok": True,
        "tracking_id": tracking_id,
        "route_geometry": copy.deepcopy(scenario["route_geometry"]),
        "markers": _map_markers(scenario, tick),
        "route_progress_percent": tick.get("route_progress_percent", 0),
    }


@server.tool()
async def get_locker_occupancy(pickup_point_id: str) -> Dict[str, Any]:
    """Return locker telemetry/occupancy for a pickup point locker."""
    locker = _LOCKERS.get(pickup_point_id)
    if not locker:
        return {"ok": False, "error": "Unknown or non-locker pickup_point_id"}

    now = _now_ts()
    total_cells = int(locker["total_cells"])
    occupied = int(locker["occupied_cells"])
    free_cells = max(0, total_cells - occupied)
    occupancy_ratio = round(occupied / total_cells, 3) if total_cells else 0.0

    status = "AVAILABLE"
    if free_cells <= 2:
        status = "NEAR_CAPACITY"
    if free_cells == 0:
        status = "FULL"

    return {
        "ok": True,
        "pickup_point_id": pickup_point_id,
        "telemetry": {
            "name": locker["name"],
            "kind": locker["kind"],
            "lat": locker["lat"],
            "lon": locker["lon"],
            "total_cells": total_cells,
            "occupied_cells": occupied,
            "free_cells": free_cells,
            "occupancy_ratio": occupancy_ratio,
            "capacity_status": status,
            "door_health": locker["door_health"],
            "power_status": locker["power_status"],
            "network_status": locker["network_status"],
            "last_heartbeat_ts": now,
        },
    }


@server.tool()
async def acknowledge_alert(
    tracking_id: str,
    alert_id: str,
    operator: str = "fred-demo",
) -> Dict[str, Any]:
    """Acknowledge an active IoT alert and append an audit event."""
    scenario = _scenario_or_error(tracking_id)
    if not scenario:
        return {
            "ok": False,
            "error": "Unknown tracking_id (seed a scenario first with seed_demo_tracking_incident)",
        }

    tick = _current_tick(scenario)
    active_alert = None
    for alert in tick.get("active_alerts", []):
        if alert.get("alert_id") == alert_id:
            active_alert = alert
            break
    if not active_alert:
        return {"ok": False, "error": "Alert not active in current simulation tick"}

    existing = scenario["alert_acks"].get(alert_id)
    if existing:
        return {
            "ok": True,
            "tracking_id": tracking_id,
            "alert_id": alert_id,
            "status": "ACKNOWLEDGED",
            **existing,
        }

    ack = {
        "operator": operator,
        "acknowledged_at_ts": _now_ts(),
    }
    scenario["alert_acks"][alert_id] = ack

    seq = int(scenario["next_event_seq"])
    scenario["next_event_seq"] = seq + 1
    scenario["manual_events"].append(
        {
            "seq": seq,
            "ts": ack["acknowledged_at_ts"],
            "type": "ALERT_ACKNOWLEDGED",
            "severity": "info",
            "source": "operator",
            "message": f"Alert {alert_id} acknowledged by {operator}",
            "payload": {"alert_id": alert_id, "operator": operator},
        }
    )

    return {
        "ok": True,
        "tracking_id": tracking_id,
        "alert_id": alert_id,
        "status": "ACKNOWLEDGED",
        **ack,
    }


@server.tool()
async def advance_simulation_tick(tracking_id: str, steps: int = 1) -> Dict[str, Any]:
    """Advance the deterministic IoT scenario by one or more ticks."""
    scenario = _scenario_or_error(tracking_id)
    if not scenario:
        return {
            "ok": False,
            "error": "Unknown tracking_id (seed a scenario first with seed_demo_tracking_incident)",
        }

    max_tick = len(scenario["timeline"]) - 1
    requested_steps = max(1, min(int(steps), 10))
    before = int(scenario["current_tick"])
    scenario["current_tick"] = min(max_tick, before + requested_steps)
    after = int(scenario["current_tick"])

    snapshot = _build_snapshot(scenario)
    return {
        "ok": True,
        "tracking_id": tracking_id,
        "advanced_by": after - before,
        "tick_before": before,
        "tick_after": after,
        "max_tick": max_tick,
        "snapshot": snapshot,
    }


app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("iot_tracking_mcp_server.server_mcp:app", host="127.0.0.1", port=9798, reload=False)
