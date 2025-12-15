from __future__ import annotations

import csv
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

os.environ.setdefault("TCL_WFS_BASE_URL", "https://data.grandlyon.com/geoserver/sytral/ows")
os.environ.setdefault("TCL_WFS_TYPENAME", "sytral:tcl_sytral.tclarret")
os.environ.setdefault("TCL_WFS_SRSNAME", "EPSG:4171")
os.environ.setdefault("TCL_WFS_PAGE_SIZE", "200")
os.environ.setdefault("TCL_WFS_MAX_FEATURES", "5000")
os.environ.setdefault("TCL_WFS_TIMEOUT_SEC", "10")
os.environ.setdefault("TCL_STOPS_CACHE_TTL_SEC", "900")
os.environ.setdefault("TCL_WFS_SORT_BY", "gid")
_fallback_default = Path(__file__).resolve().parent.parent / "data" / "tcl_stops_demo.csv"
os.environ.setdefault("TCL_STOPS_FALLBACK_CSV", str(_fallback_default))


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def _safe_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
        if math.isfinite(parsed):
            return parsed
    except (TypeError, ValueError):
        pass
    return None


def _split_lines(value: Any) -> List[str]:
    tokens: List[str] = []
    if isinstance(value, str):
        chunks = re.split(r"[;,/|]", value)
        for chunk in chunks:
            token = chunk.strip().upper()
            if token:
                tokens.append(token)
    elif isinstance(value, Iterable):
        for item in value:
            if not item:
                continue
            tokens.append(str(item).strip().upper())
    return tokens


def _extract_coordinates(geometry: Any, properties: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    coords: Optional[Sequence[Any]] = None
    if isinstance(geometry, dict):
        coords = geometry.get("coordinates")
    elif isinstance(geometry, (list, tuple)):
        coords = geometry
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        lon = _safe_float(coords[0])
        lat = _safe_float(coords[1])
        if lon is not None and lat is not None:
            return lon, lat
    lon = _safe_float(
        properties.get("lon")
        or properties.get("longitude")
        or properties.get("x")
        or properties.get("coordonneex")
    )
    lat = _safe_float(
        properties.get("lat")
        or properties.get("latitude")
        or properties.get("y")
        or properties.get("coordonneey")
    )
    if lon is not None and lat is not None:
        return lon, lat
    return None


def _choose(properties: Dict[str, Any], keys: Sequence[str]) -> Optional[str]:
    for key in keys:
        value = properties.get(key)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
        elif value is not None:
            return str(value)
    return None


def _guess_line_label(properties: Dict[str, Any]) -> Optional[str]:
    return _choose(
        properties,
        (
            "libelleligne",
            "ligne_libelle",
            "ligne_longue",
            "nom_ligne",
            "ligne_nom",
        ),
    )


def _simplify_props(properties: Dict[str, Any]) -> Dict[str, Any]:
    simplified: Dict[str, Any] = {}
    for key, value in properties.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            simplified[key] = value
        else:
            simplified[key] = str(value)
    return simplified


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c * 1000.0


@dataclass
class TCLStopRecord:
    stop_id: str
    name: str
    lat: float
    lon: float
    lines: set[str] = field(default_factory=set)
    line_labels: Dict[str, str] = field(default_factory=dict)
    city: Optional[str] = None
    district: Optional[str] = None
    zone: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def cache_key(self) -> str:
        return f"{self.stop_id.lower()}|{round(self.lat, 5)}|{round(self.lon, 5)}"

    def as_payload(
        self,
        source: str,
        *,
        include_raw: bool,
        distance_m: Optional[float] = None,
    ) -> "StopPayload":
        return StopPayload(
            stop_id=self.stop_id,
            name=self.name,
            city=self.city,
            district=self.district,
            zone=self.zone,
            lat=self.lat,
            lon=self.lon,
            lines=sorted(self.lines),
            line_labels={code: label for code, label in self.line_labels.items() if label},
            distance_m=None if distance_m is None else round(distance_m, 2),
            source=source,
            attributes=dict(self.raw) if include_raw else {},
        )

    @staticmethod
    def from_feature(feature: Dict[str, Any]) -> Optional["TCLStopRecord"]:
        if not isinstance(feature, dict):
            return None
        properties = feature.get("properties") or {}
        coordinates = _extract_coordinates(feature.get("geometry"), properties)
        if not coordinates:
            return None
        lon, lat = coordinates
        stop_id = _choose(
            properties,
            (
                "code",
                "mnemo",
                "mnemoarret",
                "objectid",
                "id_arret",
                "stop_id",
                "gid",
            ),
        )
        if not stop_id:
            stop_id = feature.get("id")
        if not stop_id:
            stop_id = f"{lon:.6f},{lat:.6f}"
        name = _choose(
            properties,
            (
                "nom",
                "nomlong",
                "nom_long",
                "nom_arret",
                "libelle",
                "libellearret",
                "name",
            ),
        ) or str(stop_id)
        lines = set(
            _split_lines(
                properties.get("ligne")
                or properties.get("lignes")
                or properties.get("code_ligne")
                or properties.get("codes_lignes")
                or properties.get("mnemo_ligne")
            )
        )
        if not lines:
            line_hint = _choose(properties, ("ligne", "code_ligne", "mnemo_ligne"))
            if line_hint:
                lines.add(line_hint.strip().upper())
        city = _choose(properties, ("commune", "libelle_commune", "nom_commune", "ville"))
        district = _choose(properties, ("arrondissement", "quartier", "secteur_quartier"))
        zone = _choose(properties, ("secteur", "secteurcommercial", "poteau", "pole"))
        line_label = _guess_line_label(properties)
        record = TCLStopRecord(
            stop_id=str(stop_id),
            name=name,
            lat=lat,
            lon=lon,
            city=city,
            district=district,
            zone=zone,
            raw=_simplify_props(properties),
        )
        if not lines:
            record.lines.add("TCL")
        else:
            for code in lines:
                if not code:
                    continue
                record.lines.add(code)
                if line_label:
                    record.line_labels.setdefault(code, line_label)
        return record


class StopPayload(BaseModel):
    stop_id: str
    name: str
    city: Optional[str]
    district: Optional[str]
    zone: Optional[str]
    lat: float
    lon: float
    lines: List[str]
    line_labels: Dict[str, str] = Field(default_factory=dict)
    distance_m: Optional[float] = Field(
        default=None,
        description="Distance from the queried coordinate in meters (nearby search only).",
    )
    source: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class StopSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Search string to match stop names or cities.")
    limit: int = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum number of stops to return.",
    )
    city: Optional[str] = Field(
        default=None,
        description="Optional city filter (case insensitive substring).",
    )
    lines: Optional[List[str]] = Field(
        default=None,
        description="Optional list of TCL line codes to keep.",
    )
    include_raw: bool = Field(
        default=False,
        description="When true, include the raw feature attributes in the response.",
    )

    @field_validator("query")
    @classmethod
    def _trim_query(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Query must contain at least two characters.")
        return cleaned

    @field_validator("city")
    @classmethod
    def _normalize_city(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("lines", mode="before")
    @classmethod
    def _normalize_lines(cls, value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        normalized = []
        for item in candidates:
            if not item:
                continue
            normalized.append(str(item).strip().upper())
        return normalized or None


class StopSearchResponse(BaseModel):
    query: str
    count: int
    limit: int
    city_filter: Optional[str]
    line_filter: Optional[List[str]]
    results: List[StopPayload]
    source: str
    refreshed_at: Optional[datetime]


class NearbyStopsRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees.")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees.")
    radius_m: float = Field(
        default=400.0,
        ge=50.0,
        le=3000.0,
        description="Search radius in meters.",
    )
    limit: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Maximum number of stops to return.",
    )
    include_raw: bool = Field(
        default=False,
        description="When true, include raw attributes for each stop.",
    )


class NearbyStopsResponse(BaseModel):
    origin_lat: float
    origin_lon: float
    radius_m: float
    limit: int
    count: int
    results: List[StopPayload]
    source: str
    refreshed_at: Optional[datetime]


class LineSummary(BaseModel):
    code: str
    label: Optional[str]
    stop_count: int


class LinesResponse(BaseModel):
    count: int
    lines: List[LineSummary]
    source: str
    refreshed_at: Optional[datetime]


class MetadataResponse(BaseModel):
    source: str
    stop_count: int
    line_count: int
    last_refresh_utc: Optional[datetime]
    cache_ttl_sec: int
    wfs_base_url: str
    typename: str
    srs_name: str
    fallback_csv: str


class ReloadResponse(BaseModel):
    stop_count: int
    line_count: int
    source: str
    refreshed_at: Optional[datetime]


class TCLWFSClient:
    def __init__(
        self,
        *,
        base_url: str,
        typename: str,
        srs_name: str,
        username: Optional[str],
        password: Optional[str],
        page_size: int,
        max_features: int,
        timeout: float,
        sort_by: str,
    ) -> None:
        self._base_url = base_url
        self._typename = typename
        self._srs_name = srs_name
        self._auth = (username, password) if username and password else None
        self._page_size = max(1, page_size)
        self._max_features = max(self._page_size, max_features)
        self._timeout = max(3.0, timeout)
        self._sort_by = sort_by

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def typename(self) -> str:
        return self._typename

    @property
    def srs_name(self) -> str:
        return self._srs_name

    def fetch_all(self) -> List[Dict[str, Any]]:
        features: List[Dict[str, Any]] = []
        start_index = 0
        while start_index < self._max_features:
            batch = self._fetch_page(start_index)
            if not batch:
                break
            features.extend(batch)
            if len(batch) < self._page_size:
                break
            start_index += self._page_size
        if features:
            logger.info("Fetched %d TCL stops from WFS.", len(features))
        return features[: self._max_features]

    def _fetch_page(self, start_index: int) -> List[Dict[str, Any]]:
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "typename": self._typename,
            "outputFormat": "application/json",
            "SRSNAME": self._srs_name,
            "startIndex": start_index,
            "count": self._page_size,
            "sortBy": self._sort_by,
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "EcoAdvisor-TCL-MCP/0.1",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(
                    self._base_url,
                    params=params,
                    headers=headers,
                    auth=self._auth,
                )
                response.raise_for_status()
                payload = response.json()
        except Exception:
            logger.exception("Failed to fetch TCL stops page starting at %s", start_index)
            return []
        features = payload.get("features")
        if not isinstance(features, list):
            logger.warning("Unexpected WFS payload format: missing 'features' list.")
            return []
        return features


class TCLStopStore:
    def __init__(self, *, client: TCLWFSClient, fallback_csv: Path, cache_ttl_sec: int) -> None:
        self._client = client
        self._fallback_csv = fallback_csv
        self._cache_ttl = max(60, cache_ttl_sec)
        self._lock = threading.RLock()
        self._expires_at = 0.0
        self._stops: List[TCLStopRecord] = []
        self._line_counts: Dict[str, int] = {}
        self._line_labels: Dict[str, str] = {}
        self._last_refresh: Optional[datetime] = None
        self._source = "uninitialized"

    def ensure_cache(self) -> None:
        with self._lock:
            self._refresh_locked(force=False)

    def reload(self) -> Dict[str, Any]:
        with self._lock:
            return self._refresh_locked(force=True)

    def search(
        self,
        *,
        query: str,
        limit: int,
        city: Optional[str],
        lines: Optional[List[str]],
    ) -> List[TCLStopRecord]:
        self._require_data()
        query_norm = _normalize_text(query)
        city_norm = _normalize_text(city)
        line_filter = {code.upper() for code in lines} if lines else None
        matches: List[Tuple[int, TCLStopRecord]] = []
        for stop in self._stops:
            if city_norm:
                hay_city = _normalize_text(stop.city)
                if city_norm not in hay_city:
                    continue
            if line_filter:
                if not line_filter.intersection({code.upper() for code in stop.lines}):
                    continue
            haystack = _normalize_text(" ".join(part for part in (stop.name, stop.city, stop.zone) if part))
            if query_norm not in haystack:
                continue
            score = self._score_stop(query_norm, stop)
            matches.append((score, stop))
        matches.sort(key=lambda item: (item[0], item[1].name.lower()))
        return [item[1] for item in matches[:limit]]

    def nearby(
        self,
        *,
        lat: float,
        lon: float,
        radius_m: float,
        limit: int,
    ) -> List[Tuple[TCLStopRecord, float]]:
        self._require_data()
        matches: List[Tuple[TCLStopRecord, float]] = []
        for stop in self._stops:
            distance_m = _haversine_m(lat, lon, stop.lat, stop.lon)
            if distance_m <= radius_m:
                matches.append((stop, distance_m))
        matches.sort(key=lambda item: (item[1], item[0].name.lower()))
        return matches[:limit]

    def list_lines(self) -> List[LineSummary]:
        self._require_data()
        summaries: List[LineSummary] = []
        for code in sorted(self._line_counts.keys()):
            summaries.append(
                LineSummary(
                    code=code,
                    label=self._line_labels.get(code),
                    stop_count=self._line_counts[code],
                )
            )
        return summaries

    def metadata(self) -> MetadataResponse:
        return MetadataResponse(
            source=self._source,
            stop_count=len(self._stops),
            line_count=len(self._line_counts),
            last_refresh_utc=self._last_refresh,
            cache_ttl_sec=self._cache_ttl,
            wfs_base_url=self._client.base_url,
            typename=self._client.typename,
            srs_name=self._client.srs_name,
            fallback_csv=str(self._fallback_csv),
        )

    @property
    def source_label(self) -> str:
        return self._source

    @property
    def last_refresh(self) -> Optional[datetime]:
        return self._last_refresh

    def _require_data(self) -> None:
        self.ensure_cache()
        if not self._stops:
            raise RuntimeError(
                "No TCL stops available (WFS unreachable and fallback CSV missing)."
            )

    def _refresh_locked(self, *, force: bool) -> Dict[str, Any]:
        now = time.monotonic()
        if not force and self._stops and now < self._expires_at:
            return self._stats()
        features, source = self._load_features()
        stops = self._normalize_features(features)
        self._stops = stops
        self._line_counts, self._line_labels = self._build_line_metadata(stops)
        self._last_refresh = datetime.now(timezone.utc)
        self._source = source
        self._expires_at = time.monotonic() + self._cache_ttl
        logger.info(
            "TCL stop cache refreshed: %d stops (source=%s).",
            len(stops),
            source,
        )
        return self._stats()

    def _stats(self) -> Dict[str, Any]:
        return {
            "stop_count": len(self._stops),
            "line_count": len(self._line_counts),
            "source": self._source,
            "last_refresh": self._last_refresh,
        }

    def _load_features(self) -> Tuple[List[Dict[str, Any]], str]:
        try:
            features = self._client.fetch_all()
        except Exception:
            logger.exception("Unexpected error while fetching TCL stops from WFS.")
            features = []
        if features:
            return features, "grandlyon_wfs"
        fallback = self._load_csv_fallback()
        if fallback:
            return fallback, "fallback_csv"
        return [], "unavailable"

    def _load_csv_fallback(self) -> List[Dict[str, Any]]:
        path = self._fallback_csv
        if not path.exists():
            logger.warning("TCL fallback CSV missing at %s", path)
            return []
        rows: List[Dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    lon = _safe_float(row.get("lon") or row.get("longitude"))
                    lat = _safe_float(row.get("lat") or row.get("latitude"))
                    geometry = None
                    if lon is not None and lat is not None:
                        geometry = {"type": "Point", "coordinates": [lon, lat]}
                    rows.append({"properties": row, "geometry": geometry})
        except Exception:
            logger.exception("Unable to parse TCL fallback CSV at %s", path)
            return []
        return rows

    def _normalize_features(self, features: Sequence[Dict[str, Any]]) -> List[TCLStopRecord]:
        merged: Dict[str, TCLStopRecord] = {}
        for feature in features:
            record = TCLStopRecord.from_feature(feature)
            if not record:
                continue
            key = record.cache_key()
            existing = merged.get(key)
            if existing:
                existing.lines.update(record.lines)
                for code, label in record.line_labels.items():
                    if label and code not in existing.line_labels:
                        existing.line_labels[code] = label
                if not existing.city and record.city:
                    existing.city = record.city
                if not existing.district and record.district:
                    existing.district = record.district
                if not existing.zone and record.zone:
                    existing.zone = record.zone
            else:
                merged[key] = record
        return sorted(merged.values(), key=lambda stop: stop.name.lower())

    def _build_line_metadata(
        self, stops: Sequence[TCLStopRecord]
    ) -> Tuple[Dict[str, int], Dict[str, str]]:
        counts: Dict[str, int] = {}
        labels: Dict[str, str] = {}
        for stop in stops:
            for code in stop.lines:
                counts[code] = counts.get(code, 0) + 1
                label = stop.line_labels.get(code)
                if label and code not in labels:
                    labels[code] = label
        return counts, labels

    @staticmethod
    def _score_stop(query_norm: str, stop: TCLStopRecord) -> int:
        name_norm = _normalize_text(stop.name)
        if name_norm == query_norm:
            return 0
        if name_norm.startswith(query_norm):
            return 1
        if query_norm in name_norm:
            return 2
        city_norm = _normalize_text(stop.city)
        if city_norm and query_norm in city_norm:
            return 3
        return 4


cache_ttl = int(os.getenv("TCL_STOPS_CACHE_TTL_SEC", "900"))
fallback_csv = Path(os.getenv("TCL_STOPS_FALLBACK_CSV", str(_fallback_default))).expanduser()
client = TCLWFSClient(
    base_url=os.getenv("TCL_WFS_BASE_URL", "https://data.grandlyon.com/geoserver/sytral/ows"),
    typename=os.getenv("TCL_WFS_TYPENAME", "sytral:tcl_sytral.tclarret"),
    srs_name=os.getenv("TCL_WFS_SRSNAME", "EPSG:4171"),
    username=os.getenv("TCL_WFS_USERNAME"),
    password=os.getenv("TCL_WFS_PASSWORD"),
    page_size=int(os.getenv("TCL_WFS_PAGE_SIZE", "200")),
    max_features=int(os.getenv("TCL_WFS_MAX_FEATURES", "5000")),
    timeout=float(os.getenv("TCL_WFS_TIMEOUT_SEC", "10")),
    sort_by=os.getenv("TCL_WFS_SORT_BY", "gid"),
)
store = TCLStopStore(client=client, fallback_csv=fallback_csv, cache_ttl_sec=cache_ttl)

app = FastAPI(
    title="EcoAdvisor TCL Transit Service",
    version="0.1.0",
    description="Expose TCL stop locations via MCP using the Grand Lyon WFS feed.",
)


@app.post(
    "/tcl/stops/search",
    response_model=StopSearchResponse,
    tags=["TCL"],
    operation_id="search_tcl_stops",
)
async def search_tcl_stops(request: StopSearchRequest) -> StopSearchResponse:
    try:
        stops = store.search(
            query=request.query,
            limit=request.limit,
            city=request.city,
            lines=request.lines,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    payloads = [
        stop.as_payload(
            store.source_label,
            include_raw=request.include_raw,
        )
        for stop in stops
    ]
    return StopSearchResponse(
        query=request.query,
        count=len(payloads),
        limit=request.limit,
        city_filter=request.city,
        line_filter=request.lines,
        results=payloads,
        source=store.source_label,
        refreshed_at=store.last_refresh,
    )


@app.post(
    "/tcl/stops/nearby",
    response_model=NearbyStopsResponse,
    tags=["TCL"],
    operation_id="find_nearby_tcl_stops",
)
async def find_nearby_tcl_stops(request: NearbyStopsRequest) -> NearbyStopsResponse:
    try:
        matches = store.nearby(
            lat=request.lat,
            lon=request.lon,
            radius_m=request.radius_m,
            limit=request.limit,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    payloads = [
        stop.as_payload(
            store.source_label,
            include_raw=request.include_raw,
            distance_m=distance,
        )
        for stop, distance in matches
    ]
    return NearbyStopsResponse(
        origin_lat=request.lat,
        origin_lon=request.lon,
        radius_m=request.radius_m,
        limit=request.limit,
        count=len(payloads),
        results=payloads,
        source=store.source_label,
        refreshed_at=store.last_refresh,
    )


@app.get(
    "/tcl/lines",
    response_model=LinesResponse,
    tags=["TCL"],
    operation_id="list_tcl_lines",
)
async def list_tcl_lines() -> LinesResponse:
    try:
        summaries = store.list_lines()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return LinesResponse(
        count=len(summaries),
        lines=summaries,
        source=store.source_label,
        refreshed_at=store.last_refresh,
    )


@app.get(
    "/tcl/metadata",
    response_model=MetadataResponse,
    tags=["TCL"],
    operation_id="get_tcl_metadata",
)
async def get_tcl_metadata() -> MetadataResponse:
    return store.metadata()


@app.post(
    "/tcl/reload",
    response_model=ReloadResponse,
    tags=["TCL"],
    operation_id="reload_tcl_stops_cache",
)
async def reload_tcl_stops_cache() -> ReloadResponse:
    stats = store.reload()
    return ReloadResponse(
        stop_count=stats["stop_count"],
        line_count=stats["line_count"],
        source=stats["source"],
        refreshed_at=stats.get("last_refresh"),
    )


mcp = FastApiMCP(
    app,
    name="EcoAdvisor TCL Transit MCP",
    description=(
        "Provides access to TCL stop locations sourced from the Grand Lyon SYTRAL WFS feed "
        "with an optional CSV fallback for offline demos."
    ),
    include_tags=["TCL"],
    describe_all_responses=True,
    describe_full_response_schema=True,
)
mcp.mount_http(mount_path="/mcp")

__all__ = ["app"]

