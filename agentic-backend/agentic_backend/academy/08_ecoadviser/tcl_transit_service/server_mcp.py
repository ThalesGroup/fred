from __future__ import annotations

import csv
import logging
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_WFS_BASE_URL = os.getenv(
    "TCL_WFS_BASE_URL",
    "https://data.grandlyon.com/geoserver/sytral/ows",
)
DEFAULT_WFS_TYPENAME = os.getenv(
    "TCL_WFS_TYPENAME",
    "sytral:tcl_sytral.tclarret",
)
DEFAULT_WFS_SRSNAME = os.getenv("TCL_WFS_SRSNAME", "EPSG:4326")
DEFAULT_WFS_TIMEOUT = float(os.getenv("TCL_WFS_TIMEOUT_SEC", "10"))
DEFAULT_WFS_PAGE_SIZE = int(os.getenv("TCL_WFS_PAGE_SIZE", "500"))
DEFAULT_WFS_MAX_FEATURES = int(os.getenv("TCL_WFS_MAX_FEATURES", "8000"))
DEFAULT_WFS_SORT_BY = os.getenv("TCL_WFS_SORT_BY", "gid")
DEFAULT_WFS_USERNAME = os.getenv("TCL_WFS_USERNAME")
DEFAULT_WFS_PASSWORD = os.getenv("TCL_WFS_PASSWORD")
CACHE_TTL_SEC = int(os.getenv("TCL_STOPS_CACHE_TTL_SEC", "900"))

FALLBACK_CSV_PATH = Path(
    os.getenv(
        "TCL_STOPS_FALLBACK_CSV",
        str(
            Path(__file__).resolve().parent.parent / "data" / "tcl_stops_demo.csv"
        ),
    )
)

STOP_ID_FIELDS = [
    "stop_id",
    "id",
    "gid",
    "objectid",
    "idarret",
    "id_arret",
    "code_arret",
]
NAME_FIELDS = [
    "stop_name",
    "nom",
    "nomarret",
    "libelle",
    "libelle_arret",
    "nom_arret",
]
CITY_FIELDS = [
    "commune",
    "ville",
    "nomcomm",
    "nom_commune",
    "nom_comm",
]
ADDRESS_FIELDS = [
    "adresse",
    "adresse_arret",
    "adrligne1",
    "adrligne2",
    "libellevoie",
]
LINE_FIELDS = ["served_lines", "lignes", "ligne", "liste_ligne", "dessertes"]
PMR_FIELDS = ["accessible_pmr", "pmr", "accessibilite", "accessibilité"]
ELEVATOR_FIELDS = ["has_elevator", "ascenseur", "elevator"]
ESCALATOR_FIELDS = ["has_escalator", "escalator"]
ZONE_FIELDS = ["zone", "secteur"]
INSEE_FIELDS = ["insee", "codeinsee", "code_insee"]


def _normalize_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "oui", "yes", "y"}:
            return True
        if lowered in {"false", "0", "non", "no", "n"}:
            return False
    return None


def _normalize_lines(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return parts
    if isinstance(value, str):
        raw_parts = value.replace(";", ",").split(",")
        parts = [part.strip() for part in raw_parts if part.strip()]
        return parts
    return [str(value).strip()] if str(value).strip() else []


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def _extract_property(
    props: Dict[str, Any],
    candidates: Sequence[str],
) -> Optional[Any]:
    if not props:
        return None
    lowered = {str(key).lower(): key for key in props.keys()}
    for candidate in candidates:
        key = lowered.get(candidate.lower())
        if key is not None:
            value = props.get(key)
            if value not in (None, ""):
                return value
    return None


def _extract_coordinates(feature: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    geometry = feature.get("geometry") if isinstance(feature, dict) else None
    if not isinstance(geometry, dict):
        return None, None
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coordinates, (list, tuple)):
        if len(coordinates) >= 2:
            lon, lat = coordinates[0], coordinates[1]
            try:
                return float(lon), float(lat)
            except (TypeError, ValueError):
                return None, None
    if geometry.get("type") == "MultiPoint" and isinstance(coordinates, list):
        for entry in coordinates:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    return float(entry[0]), float(entry[1])
                except (TypeError, ValueError):
                    continue
    return None, None


class TCLStop(BaseModel):
    stop_id: str = Field(..., description="Stable identifier from the SYTRAL dataset.")
    name: str = Field(..., description="Published stop name.")
    city: Optional[str] = Field(None, description="City or commune hosting the stop.")
    address: Optional[str] = Field(None, description="Street-level address when available.")
    lines: List[str] = Field(default_factory=list, description="List of TCL lines serving the stop.")
    latitude: Optional[float] = Field(None, description="Latitude in WGS84.")
    longitude: Optional[float] = Field(None, description="Longitude in WGS84.")
    accessible_pmr: Optional[bool] = Field(None, description="True when the stop is declared PMR-friendly.")
    has_elevator: Optional[bool] = Field(None, description="True when an elevator is available.")
    has_escalator: Optional[bool] = Field(None, description="True when an escalator is available.")
    zone: Optional[str] = Field(None, description="Fare zone or TCL sector.")
    insee: Optional[str] = Field(None, description="INSEE commune code.")
    source: str = Field(..., description="Origin dataset (WFS or fallback CSV).")
    raw_properties: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Original WFS/CSV record so the agent can inspect additional attributes.",
    )

    def to_payload(self, include_raw: bool) -> Dict[str, Any]:
        payload = self.model_dump(exclude_none=True)
        if not include_raw:
            payload.pop("raw_properties", None)
        return payload


class TCLStopWithDistance(TCLStop):
    distance_km: float = Field(..., description="Great-circle distance to the requested point.")


class TCLStopSearchResponse(BaseModel):
    query: Optional[str]
    city: Optional[str]
    line: Optional[str]
    limit: int
    count: int
    generated_at: datetime
    source: str
    stops: List[TCLStop]


class TCLStopNearbyResponse(BaseModel):
    latitude: float
    longitude: float
    radius_km: float
    max_results: int
    line: Optional[str]
    count: int
    generated_at: datetime
    source: str
    stops: List[TCLStopWithDistance]


class TCLLineSummary(BaseModel):
    line: str
    stop_count: int
    sample_stop: Optional[str]


class TCLDatasetMetadata(BaseModel):
    stop_count: int
    last_refresh: Optional[datetime]
    cache_ttl_sec: int
    source: str
    wfs_base_url: str
    typename: str
    srs_name: str


class CacheReloadResponse(BaseModel):
    stop_count: int
    refreshed_at: datetime
    source: str


class TCLWFSClient:
    def __init__(
        self,
        base_url: str,
        typename: str,
        srs_name: str,
        timeout: float,
        page_size: int,
        max_features: int,
        sort_by: Optional[str],
        auth: Optional[httpx.Auth],
    ):
        self.base_url = base_url
        self.typename = typename
        self.srs_name = srs_name
        self.timeout = timeout
        self.page_size = page_size
        self.max_features = max_features
        self.sort_by = sort_by
        self._auth = auth

    def fetch_all(self) -> List[Dict[str, Any]]:
        features: List[Dict[str, Any]] = []
        start_index = 0
        logger.info(
            "TCLWFSClient: fetching dataset base_url=%s typename=%s",
            self.base_url,
            self.typename,
        )
        with httpx.Client(timeout=self.timeout, auth=self._auth) as client:
            while start_index < self.max_features:
                page_size = min(self.page_size, self.max_features - start_index)
                params = {
                    "SERVICE": "WFS",
                    "VERSION": "2.0.0",
                    "request": "GetFeature",
                    "typename": self.typename,
                    "outputFormat": "application/json",
                    "SRSNAME": self.srs_name,
                    "startIndex": start_index,
                    "count": page_size,
                }
                if self.sort_by:
                    params["sortby"] = self.sort_by
                response = client.get(self.base_url, params=params)
                response.raise_for_status()
                payload = response.json()
                page_features = self._extract_features(payload)
                if not page_features:
                    logger.info(
                        "TCLWFSClient: stop pagination because page is empty (startIndex=%s).",
                        start_index,
                    )
                    break
                features.extend(page_features)
                logger.info(
                    "TCLWFSClient: fetched %d features (total=%d).",
                    len(page_features),
                    len(features),
                )
                if len(page_features) < page_size:
                    break
                start_index += len(page_features)
        return features

    @staticmethod
    def _extract_features(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            features = payload.get("features")
            if isinstance(features, list):
                return [feature for feature in features if isinstance(feature, dict)]
        return []


class TCLStopStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stops: List[TCLStop] = []
        self._last_refresh: Optional[datetime] = None
        self._source_label: str = "uninitialized"
        self._cache_ttl = timedelta(seconds=CACHE_TTL_SEC)
        auth = None
        if DEFAULT_WFS_USERNAME and DEFAULT_WFS_PASSWORD:
            auth = httpx.BasicAuth(DEFAULT_WFS_USERNAME, DEFAULT_WFS_PASSWORD)

        self._wfs_client = TCLWFSClient(
            base_url=DEFAULT_WFS_BASE_URL,
            typename=DEFAULT_WFS_TYPENAME,
            srs_name=DEFAULT_WFS_SRSNAME,
            timeout=DEFAULT_WFS_TIMEOUT,
            page_size=DEFAULT_WFS_PAGE_SIZE,
            max_features=DEFAULT_WFS_MAX_FEATURES,
            sort_by=DEFAULT_WFS_SORT_BY,
            auth=auth,
        )

    def ensure_loaded(self) -> None:
        if self._stops and not self._is_stale():
            return
        with self._lock:
            if self._stops and not self._is_stale():
                return
            stops, source = self._load_dataset()
            if not stops:
                raise RuntimeError("Unable to load TCL stops from WFS or fallback CSV.")
            self._stops = stops
            self._source_label = source
            self._last_refresh = datetime.now(timezone.utc)
            logger.info(
                "TCLStopStore: loaded %d stops from %s.",
                len(self._stops),
                self._source_label,
            )

    def reload(self) -> Tuple[int, str]:
        with self._lock:
            stops, source = self._load_dataset()
            if not stops:
                raise RuntimeError("Reload failed: dataset is empty.")
            self._stops = stops
            self._source_label = source
            self._last_refresh = datetime.now(timezone.utc)
            logger.info(
                "TCLStopStore: reloaded %d stops from %s.",
                len(self._stops),
                self._source_label,
            )
            return len(self._stops), self._source_label

    def metadata(self) -> TCLDatasetMetadata:
        return TCLDatasetMetadata(
            stop_count=len(self._stops),
            last_refresh=self._last_refresh,
            cache_ttl_sec=int(self._cache_ttl.total_seconds()),
            source=self._source_label,
            wfs_base_url=DEFAULT_WFS_BASE_URL,
            typename=DEFAULT_WFS_TYPENAME,
            srs_name=DEFAULT_WFS_SRSNAME,
        )

    def search(
        self,
        query: Optional[str],
        city: Optional[str],
        line: Optional[str],
        limit: int,
    ) -> List[TCLStop]:
        self.ensure_loaded()
        query_norm = query.lower().strip() if query else None
        city_norm = city.lower().strip() if city else None
        line_norm = line.lower().strip() if line else None
        results: List[TCLStop] = []
        for stop in self._stops:
            if query_norm:
                haystacks = filter(
                    None,
                    [
                        stop.name,
                        stop.address,
                        stop.city,
                        " ".join(stop.lines) if stop.lines else None,
                    ],
                )
                if not any(query_norm in segment.lower() for segment in haystacks):
                    continue
            if city_norm:
                if not stop.city or city_norm not in stop.city.lower():
                    continue
            if line_norm and not self._matches_line(stop, line_norm):
                continue
            results.append(stop)
            if len(results) >= limit:
                break
        return results

    def find_nearby(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        max_results: int,
        line: Optional[str],
    ) -> List[Tuple[TCLStop, float]]:
        self.ensure_loaded()
        line_norm = line.lower().strip() if line else None
        matches: List[Tuple[TCLStop, float]] = []
        for stop in self._stops:
            if stop.latitude is None or stop.longitude is None:
                continue
            if line_norm and not self._matches_line(stop, line_norm):
                continue
            distance = _haversine_km(latitude, longitude, stop.latitude, stop.longitude)
            if distance <= radius_km:
                matches.append((stop, distance))
        matches.sort(key=lambda item: item[1])
        return matches[:max_results]

    def list_lines(self, min_count: int, limit: int) -> List[TCLLineSummary]:
        self.ensure_loaded()
        counters: Dict[str, int] = {}
        samples: Dict[str, str] = {}
        for stop in self._stops:
            for line in stop.lines:
                if not line:
                    continue
                counters[line] = counters.get(line, 0) + 1
                samples.setdefault(line, stop.name)
        summaries = [
            TCLLineSummary(line=line, stop_count=count, sample_stop=samples.get(line))
            for line, count in counters.items()
            if count >= min_count
        ]
        summaries.sort(key=lambda item: (-item.stop_count, item.line))
        return summaries[:limit]

    def _is_stale(self) -> bool:
        if not self._last_refresh:
            return True
        return datetime.now(timezone.utc) - self._last_refresh > self._cache_ttl

    def _load_dataset(self) -> Tuple[List[TCLStop], str]:
        try:
            features = self._wfs_client.fetch_all()
            stops = self._convert_features(features, source_label="grandlyon-wfs")
            if stops:
                return stops, "grandlyon-wfs"
        except Exception:
            logger.exception("TCLStopStore: failed to fetch WFS dataset, falling back to CSV.")
        csv_stops = self._load_from_csv()
        return csv_stops, f"csv:{FALLBACK_CSV_PATH.name}"

    def _convert_features(
        self,
        features: Iterable[Dict[str, Any]],
        source_label: str,
    ) -> List[TCLStop]:
        stops: List[TCLStop] = []
        for feature in features:
            props = feature.get("properties") if isinstance(feature, dict) else None
            if not isinstance(props, dict):
                continue
            stop_id = _normalize_string(
                _extract_property(props, STOP_ID_FIELDS) or feature.get("id")
            )
            name = _normalize_string(_extract_property(props, NAME_FIELDS))
            if not stop_id or not name:
                continue
            city = _normalize_string(_extract_property(props, CITY_FIELDS))
            address = _normalize_string(_extract_property(props, ADDRESS_FIELDS))
            lines = _normalize_lines(_extract_property(props, LINE_FIELDS))
            latitude = longitude = None
            lon, lat = _extract_coordinates(feature)
            if lon is not None and lat is not None:
                longitude, latitude = lon, lat
            elif "lon" in props and "lat" in props:
                try:
                    longitude = float(props["lon"])
                    latitude = float(props["lat"])
                except (TypeError, ValueError):
                    longitude = latitude = None
            accessible = _normalize_bool(_extract_property(props, PMR_FIELDS))
            elevator = _normalize_bool(_extract_property(props, ELEVATOR_FIELDS))
            escalator = _normalize_bool(_extract_property(props, ESCALATOR_FIELDS))
            zone = _normalize_string(_extract_property(props, ZONE_FIELDS))
            insee = _normalize_string(_extract_property(props, INSEE_FIELDS))
            stop = TCLStop(
                stop_id=stop_id,
                name=name,
                city=city,
                address=address,
                lines=lines,
                latitude=latitude,
                longitude=longitude,
                accessible_pmr=accessible,
                has_elevator=elevator,
                has_escalator=escalator,
                zone=zone,
                insee=insee,
                source=source_label,
                raw_properties=props,
            )
            stops.append(stop)
        return stops

    def _load_from_csv(self) -> List[TCLStop]:
        if not FALLBACK_CSV_PATH.exists():
            logger.error(
                "TCLStopStore: fallback CSV does not exist at %s.",
                FALLBACK_CSV_PATH,
            )
            return []
        stops: List[TCLStop] = []
        try:
            with FALLBACK_CSV_PATH.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    stop_id = _normalize_string(row.get("stop_id"))
                    name = _normalize_string(row.get("stop_name"))
                    if not stop_id or not name:
                        continue
                    try:
                        latitude = float(row["stop_lat"]) if row.get("stop_lat") else None
                        longitude = float(row["stop_lon"]) if row.get("stop_lon") else None
                    except (TypeError, ValueError):
                        latitude = longitude = None
                    stop = TCLStop(
                        stop_id=stop_id,
                        name=name,
                        city=_normalize_string(row.get("city")),
                        address=_normalize_string(row.get("address")),
                        lines=_normalize_lines(row.get("served_lines")),
                        latitude=latitude,
                        longitude=longitude,
                        accessible_pmr=_normalize_bool(row.get("accessible_pmr")),
                        has_elevator=_normalize_bool(row.get("has_elevator")),
                        has_escalator=_normalize_bool(row.get("has_escalator")),
                        zone=_normalize_string(row.get("zone")),
                        insee=_normalize_string(row.get("insee")),
                        source=f"csv:{FALLBACK_CSV_PATH.name}",
                        raw_properties=row,
                    )
                    stops.append(stop)
        except Exception:
            logger.exception("TCLStopStore: failed to parse fallback CSV.")
            return []
        return stops

    @staticmethod
    def _matches_line(stop: TCLStop, line_norm: str) -> bool:
        for candidate in stop.lines:
            if line_norm in candidate.lower():
                return True
        return False


app = FastAPI(
    title="EcoAdvisor TCL Transit Service",
    version="0.1.0",
    description=(
        "Expose live TCL stops from data.grandlyon.com (SYTRAL WFS) with fallbacks "
        "so EcoAdvisor agents can locate public transport options."
    ),
)

store = TCLStopStore()


@app.get(
    "/tcl/stops/search",
    response_model=TCLStopSearchResponse,
    tags=["TCL"],
    operation_id="search_tcl_stops",
)
async def search_tcl_stops(
    query: Optional[str] = Query(
        default=None,
        min_length=2,
        description="Partial stop name, address or line identifier.",
    ),
    city: Optional[str] = Query(
        default=None,
        min_length=2,
        description="Filter on the commune label.",
    ),
    line: Optional[str] = Query(
        default=None,
        min_length=1,
        description="Filter stops that serve a given TCL line (e.g. 'C13', 'T1').",
    ),
    limit: int = Query(default=25, ge=1, le=200),
    include_raw: bool = Query(
        default=False,
        description="Include the raw WFS properties in each stop payload.",
    ),
) -> TCLStopSearchResponse:
    try:
        stops = store.search(query=query, city=city, line=line, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    payload = [
        stop.to_payload(include_raw=include_raw)
        for stop in stops
    ]
    return TCLStopSearchResponse(
        query=query,
        city=city,
        line=line,
        limit=limit,
        count=len(payload),
        generated_at=datetime.now(timezone.utc),
        source=store.metadata().source,
        stops=[TCLStop(**item) for item in payload],
    )


@app.get(
    "/tcl/stops/nearby",
    response_model=TCLStopNearbyResponse,
    tags=["TCL"],
    operation_id="find_nearby_tcl_stops",
)
async def find_nearby_tcl_stops(
    latitude: float = Query(..., ge=40.0, le=52.0, description="Latitude in decimal degrees (WGS84)."),
    longitude: float = Query(..., ge=-2.0, le=10.0, description="Longitude in decimal degrees (WGS84)."),
    radius_km: float = Query(1.5, gt=0.1, le=25.0, description="Search radius in kilometers."),
    max_results: int = Query(20, ge=1, le=100),
    line: Optional[str] = Query(
        default=None,
        description="Optional TCL line filter (case-insensitive).",
    ),
    include_raw: bool = Query(
        default=False,
        description="Include raw WFS properties for each stop.",
    ),
) -> TCLStopNearbyResponse:
    try:
        matches = store.find_nearby(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            max_results=max_results,
            line=line,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    stops_with_distance: List[TCLStopWithDistance] = []
    for stop, distance in matches:
        payload = stop.to_payload(include_raw=include_raw)
        stops_with_distance.append(
            TCLStopWithDistance(**payload, distance_km=round(distance, 3))
        )
    return TCLStopNearbyResponse(
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        max_results=max_results,
        line=line,
        count=len(stops_with_distance),
        generated_at=datetime.now(timezone.utc),
        source=store.metadata().source,
        stops=stops_with_distance,
    )


@app.get(
    "/tcl/lines",
    response_model=List[TCLLineSummary],
    tags=["TCL"],
    operation_id="list_tcl_lines",
)
async def list_tcl_lines(
    min_count: int = Query(5, ge=1, le=100),
    limit: int = Query(100, ge=1, le=500),
) -> List[TCLLineSummary]:
    try:
        return store.list_lines(min_count=min_count, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/tcl/metadata",
    response_model=TCLDatasetMetadata,
    tags=["TCL"],
    operation_id="get_tcl_metadata",
)
async def get_tcl_metadata() -> TCLDatasetMetadata:
    try:
        store.ensure_loaded()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return store.metadata()


@app.post(
    "/tcl/reload",
    response_model=CacheReloadResponse,
    tags=["TCL"],
    operation_id="reload_tcl_stops_cache",
)
async def reload_tcl_stops_cache() -> CacheReloadResponse:
    try:
        count, source = store.reload()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CacheReloadResponse(
        stop_count=count,
        refreshed_at=datetime.now(timezone.utc),
        source=source,
    )


mcp = FastApiMCP(
    app,
    name="EcoAdvisor TCL Transit MCP",
    description="Provides TCL stop search, proximity lookups and metadata backed by the Grand Lyon SYTRAL feed.",
    include_tags=["TCL"],
    describe_all_responses=True,
    describe_full_response_schema=True,
)
mcp.mount_http(mount_path="/mcp")

__all__ = ["app"]
