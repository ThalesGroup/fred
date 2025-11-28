from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

DEFAULT_WFS_URL = "https://data.grandlyon.com/geoserver/metropole-de-lyon/ows"
DEFAULT_TYPENAME = "metropole-de-lyon:pvo_patrimoine_voirie.pvotrafic"


class LiveTrafficRequest(BaseModel):
    origin_lat: float = Field(..., description="Latitude of the trip origin (WGS84).")
    origin_lng: float = Field(..., description="Longitude of the trip origin (WGS84).")
    destination_lat: float = Field(..., description="Latitude of the trip destination (WGS84).")
    destination_lng: float = Field(..., description="Longitude of the trip destination (WGS84).")
    buffer_deg: float = Field(
        default=0.02,
        description="Extra margin (degrees) added around the bounding box.",
        ge=0.001,
        le=0.5,
    )
    max_features: int = Field(default=200, description="Maximum WFS features to retrieve.", ge=1, le=500)

    @field_validator("buffer_deg")
    @classmethod
    def _validate_buffer(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("buffer_deg must be positive.")
        return value


class TrafficFeature(BaseModel):
    gid: Optional[int]
    name: Optional[str]
    commune: Optional[str]
    average_speed_kmh: Optional[float]
    traffic_state: Optional[str]
    last_update: Optional[str]
    geometry_type: Optional[str]
    coordinates_preview: Optional[List[float]]
    raw_properties: Dict[str, Any]


class LiveTrafficResponse(BaseModel):
    provider: str
    bbox: List[float]
    fetched_at: datetime
    feature_count: int
    features: List[TrafficFeature]


class GrandLyonWFSClient:
    def __init__(self):
        self.base_url = os.getenv("GRANDLYON_WFS_URL", DEFAULT_WFS_URL)
        self.typename = os.getenv("GRANDLYON_WFS_TYPENAME", DEFAULT_TYPENAME)
        self.api_key = os.getenv("GRANDLYON_WFS_API_KEY")
        self.username = os.getenv("GRANDLYON_WFS_USERNAME")
        self.password = os.getenv("GRANDLYON_WFS_PASSWORD")
        self.timeout = float(os.getenv("GRANDLYON_WFS_TIMEOUT", "10.0"))
        if not any([self.api_key, self.username and self.password]):
            logger.warning(
                "GRANDLYON_WFS_API_KEY or GRANDLYON_WFS_USERNAME/GRANDLYON_WFS_PASSWORD not set. "
                "The WFS endpoint may reject unauthenticated requests."
            )

    def fetch_features(self, bbox: Tuple[float, float, float, float], max_features: int) -> Dict[str, Any]:
        min_lng, min_lat, max_lng, max_lat = bbox
        params: Dict[str, Any] = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "request": "GetFeature",
            "typename": self.typename,
            "outputFormat": "application/json",
            "SRSNAME": "EPSG:4171",
            "bbox": f"{min_lng},{min_lat},{max_lng},{max_lat}",
            "sortby": "gid",
            "startIndex": 0,
            "count": max_features,
        }
        if self.api_key:
            params["apikey"] = self.api_key

        auth = None
        if self.username and self.password:
            auth = httpx.BasicAuth(self.username, self.password)

        with httpx.Client(timeout=self.timeout, auth=auth) as client:
            response = client.get(self.base_url, params=params)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.exception("GrandLyon WFS error: %s", exc)
                raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
            payload = response.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail="Invalid WFS response (not JSON).")
        if "features" not in payload:
            message = payload.get("message") or payload.get("error") or "Unknown WFS error"
            raise HTTPException(status_code=502, detail=message)
        return payload


def _compute_bbox(request: LiveTrafficRequest) -> Tuple[float, float, float, float]:
    min_lat = min(request.origin_lat, request.destination_lat) - request.buffer_deg
    max_lat = max(request.origin_lat, request.destination_lat) + request.buffer_deg
    min_lng = min(request.origin_lng, request.destination_lng) - request.buffer_deg
    max_lng = max(request.origin_lng, request.destination_lng) + request.buffer_deg
    return (min_lng, min_lat, max_lng, max_lat)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_feature(feature: Dict[str, Any]) -> TrafficFeature:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coords_preview: Optional[List[float]] = None
    coords = geometry.get("coordinates")
    if isinstance(coords, list):
        if geometry.get("type") == "LineString" and coords:
            coords_preview = coords[0]
        elif geometry.get("type") == "Point":
            coords_preview = coords
        elif geometry.get("type") == "MultiLineString" and coords and coords[0]:
            coords_preview = coords[0][0]

    candidate_names = [
        "libelle",
        "nom",
        "libellecommune",
        "libelleaxe",
    ]
    name = next((properties.get(key) for key in candidate_names if properties.get(key)), None)
    commune = properties.get("commune") or properties.get("ville") or properties.get("libellecommune")
    speed = (
        properties.get("vitesse")
        or properties.get("vitesse_moyenne")
        or properties.get("vitesse_kmh")
    )
    state = properties.get("etat_trafic") or properties.get("etat") or properties.get("niveau")
    last_update = (
        properties.get("date_maj")
        or properties.get("derniere_maj")
        or properties.get("timestamp")
    )

    return TrafficFeature(
        gid=properties.get("gid"),
        name=name,
        commune=commune,
        average_speed_kmh=_coerce_float(speed),
        traffic_state=state,
        last_update=last_update,
        geometry_type=geometry.get("type"),
        coordinates_preview=coords_preview,
        raw_properties=properties,
    )


client = GrandLyonWFSClient()

app = FastAPI(
    title="EcoAdvisor Grand Lyon Traffic Service",
    version="0.2.0",
    description=(
        "Query the Métropole de Lyon WFS (pvo_patrimoine_voirie.pvotrafic) to obtain live traffic segments "
        "matching an origin/destination bounding box."
    ),
)


@app.post(
    "/traffic/live",
    response_model=LiveTrafficResponse,
    tags=["Traffic"],
    operation_id="get_live_traffic_segments",
)
async def get_live_traffic_segments(request: LiveTrafficRequest) -> LiveTrafficResponse:
    bbox = _compute_bbox(request)
    logger.info("Querying Grand Lyon WFS for bbox=%s count=%s", bbox, request.max_features)
    payload = client.fetch_features(bbox, request.max_features)
    features_payload = payload.get("features", [])
    features = [_build_feature(feature) for feature in features_payload]

    return LiveTrafficResponse(
        provider="Grand Lyon WFS",
        bbox=list(bbox),
        fetched_at=datetime.now(timezone.utc),
        feature_count=len(features),
        features=features,
    )


@app.get("/traffic/health", tags=["Traffic"])
async def healthcheck() -> Dict[str, Any]:
    return {
        "status": "ok",
        "base_url": client.base_url,
        "typename": client.typename,
        "auth": "api_key" if client.api_key else "basic" if client.username else "none",
    }


mcp = FastApiMCP(
    app,
    name="EcoAdvisor Live Traffic MCP",
    description="Expose live traffic data from the Métropole de Lyon WFS endpoint.",
    include_tags=["Traffic"],
    describe_all_responses=True,
    describe_full_response_schema=True,
)
mcp.mount_http(mount_path="/mcp")

__all__ = ["app"]
