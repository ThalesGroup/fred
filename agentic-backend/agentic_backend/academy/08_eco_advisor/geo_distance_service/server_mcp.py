from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import unicodedata
from collections import OrderedDict
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Dict, List, Optional, Set

import httpx
from fastapi import FastAPI, HTTPException
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_OSRM_URL = "https://router.project-osrm.org"
DEFAULT_STREET_TYPES = (
    "rue",
    "avenue",
    "av",
    "boulevard",
    "bd",
    "cours",
    "place",
    "quai",
    "allee",
    "allée",
    "impasse",
    "chemin",
    "route",
    "passage",
    "square",
    "voie",
    "cite",
    "cité",
    "pont",
    "esplanade",
)


def _parse_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bbox(seq: Any) -> Optional[List[float]]:
    if not isinstance(seq, (list, tuple)):
        return None
    coords: List[float] = []
    for value in seq:
        parsed = _parse_float(value)
        if parsed is not None:
            coords.append(parsed)
    return coords or None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


class GeocodeRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Free-text address or place to look up.")
    limit: int = Field(3, ge=1, le=5, description="Maximum number of matches to return.")
    countrycodes: Optional[str] = Field(
        default=None,
        description="Optional ISO country codes filter (comma-separated, e.g., 'fr' or 'fr,be').",
    )
    language: Optional[str] = Field(
        default=None,
        description="Preferred response language (e.g., 'fr' or 'en').",
    )
    allow_default_city: bool = Field(
        default=True,
        description="When true, append the configured default city suffix if the query does not already contain a known city keyword.",
    )

    @field_validator("query")
    @classmethod
    def _trim_query(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Query must contain at least 3 non-whitespace characters.")
        return cleaned


class GeocodeResult(BaseModel):
    label: str = Field(..., description="Display name provided by the geocoder.")
    lat: float
    lon: float
    place_id: Optional[str]
    osm_type: Optional[str]
    osm_id: Optional[int]
    place_class: Optional[str] = Field(None, description="Nominatim 'class' attribute.")
    place_type: Optional[str] = Field(None, description="Nominatim 'type' attribute.")
    importance: Optional[float]
    boundingbox: Optional[List[float]]
    raw: Dict[str, Any]


class GeocodeResponse(BaseModel):
    provider: str
    query: str = Field(..., description="Original query provided by the caller.")
    effective_query: str = Field(..., description="Query actually sent to Nominatim (after fallback logic).")
    count: int
    limit: int
    countrycodes: Optional[str]
    effective_countrycodes: Optional[str]
    language: Optional[str]
    queried_at: datetime
    results: List[GeocodeResult]


class RouteDistanceRequest(BaseModel):
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    profile: str = Field(
        default="driving",
        description="OSRM routing profile (driving, cycling, walking).",
    )

    @field_validator("profile")
    @classmethod
    def _normalize_profile(cls, value: str) -> str:
        allowed = {"driving", "cycling", "walking"}
        mapping = {
            "car": "driving",
            "voiture": "driving",
            "auto": "driving",
            "bike": "cycling",
            "vélo": "cycling",
            "velo": "cycling",
            "bicycle": "cycling",
            "marche": "walking",
            "foot": "walking",
            "walk": "walking",
        }
        profile = mapping.get(value.strip().lower(), value.strip().lower())
        if profile not in allowed:
            raise ValueError(f"Unsupported profile '{value}'. Allowed: {sorted(allowed)}")
        return profile


class RouteDistanceResponse(BaseModel):
    provider: str
    profile: str
    distance_m: float
    distance_km: float
    duration_s: Optional[float]
    duration_min: Optional[float]
    computed_at: datetime
    source: str
    fallback_reason: Optional[str]
    notes: Optional[str]


class TripAddressResolution(BaseModel):
    query: str
    label: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    place_id: Optional[str]
    osm_id: Optional[int]
    boundingbox: Optional[List[float]]
    raw: Dict[str, Any] = Field(default_factory=dict)


class TripEstimateRequest(BaseModel):
    origin_query: str = Field(..., min_length=3, description="Origin address or place.")
    destination_query: str = Field(..., min_length=3, description="Destination address or place.")
    profile: str = Field(
        default="driving", description="Routing profile (driving/cycling/walking, synonyms accepted)."
    )
    countrycodes: Optional[str] = Field(
        default=None,
        description="Optional ISO country codes filter for both lookups.",
    )
    language: Optional[str] = Field(
        default=None,
        description="Preferred response language.",
    )
    allow_default_city: bool = Field(
        default=True,
        description="Append the configured default city suffix when queries lack city hints.",
    )

    @field_validator("profile")
    @classmethod
    def _normalize_profile(cls, value: str) -> str:
        return RouteDistanceRequest._normalize_profile(value)


class TripEstimateResponse(BaseModel):
    provider: str
    profile: str
    distance_m: float
    distance_km: float
    duration_s: Optional[float]
    duration_min: Optional[float]
    geodesic_distance_km: float
    computed_at: datetime
    source: str
    fallback_reason: Optional[str]
    notes: Optional[str]
    origin: TripAddressResolution
    destination: TripAddressResolution


class NominatimClient:
    def __init__(self):
        self.base_url = os.getenv("ECO_GEO_NOMINATIM_URL", DEFAULT_NOMINATIM_URL).rstrip("/")
        self.user_agent = os.getenv(
            "ECO_GEO_USER_AGENT",
            "FredEcoAdvisorGeo/1.0 (+https://fredk8.dev; contact: ecoadvisor@thalesgroup.com)",
        )
        self.timeout = float(os.getenv("ECO_GEO_TIMEOUT", "10.0"))
        self.default_countrycodes = os.getenv("ECO_GEO_DEFAULT_COUNTRIES", "fr")
        self.default_language = os.getenv("ECO_GEO_LANGUAGE", "fr")
        raw_keywords = os.getenv(
            "ECO_GEO_CITY_KEYWORDS",
            "lyon,villeurbanne,venissieux,vaulx-en-velin,oullins,caluire,bron,meyzieu",
        )
        self.city_keywords = [kw.strip().lower() for kw in raw_keywords.split(",") if kw.strip()]
        raw_street_types = os.getenv("ECO_GEO_STREET_TYPES", ",".join(DEFAULT_STREET_TYPES))
        street_types = [token.strip().lower() for token in raw_street_types.split(",") if token.strip()]
        if not street_types:
            street_types = list(DEFAULT_STREET_TYPES)
        street_pattern = r"\b(?:%s)\b" % "|".join(re.escape(token) for token in street_types)
        self.street_type_pattern = re.compile(street_pattern, re.IGNORECASE)
        self.multiword_sequence_pattern = re.compile(
            r"(?:\s+[A-Za-zÀ-ÖØ-öø-ÿ'’-]+){2,}",
            re.IGNORECASE,
        )
        self.default_city_suffix = os.getenv("ECO_GEO_DEFAULT_CITY_SUFFIX", "Lyon, France").strip()
        self.enabled = os.getenv("ECO_GEO_GEOCODING_ENABLED", "true").lower() not in (
            "false",
            "0",
        )
        self.request_delay = max(0.0, float(os.getenv("ECO_GEO_ATTEMPT_DELAY", "0.0")))
        self.max_query_attempts = max(1, int(os.getenv("ECO_GEO_MAX_QUERY_ATTEMPTS", "20")))
        self.cache_ttl = max(0.0, float(os.getenv("ECO_GEO_CACHE_TTL", "30.0")))
        self.cache_max_entries = max(0, int(os.getenv("ECO_GEO_CACHE_MAX", "128")))
        self._cache: OrderedDict[str, tuple[float, List[Dict[str, Any]], str, Optional[str]]] = OrderedDict()
        self._cache_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": self.user_agent})

    def _should_append_city(self, query: str) -> bool:
        if not self.default_city_suffix:
            return False
        normalized = query.lower()
        return not any(keyword in normalized for keyword in self.city_keywords)

    def _enumerate_query_variants(self, query: str) -> List[tuple[str, str]]:
        variants: List[tuple[str, str]] = []
        seen: Set[str] = set()

        def add_variant(value: str, reason: str) -> None:
            normalized = re.sub(r"\s+", " ", value).strip()
            if not normalized:
                return
            key = normalized.lower()
            if key in seen:
                return
            seen.add(key)
            variants.append((normalized, reason))

        add_variant(query, "original")
        base = variants[0][0]
        house_stripped = re.sub(r"^\s*\d+[A-Za-zÀ-ÖØ-öø-ÿ-]*\s+", "", base)
        if house_stripped != base:
            add_variant(house_stripped, "drop_house_number")

        accent_folded = self._strip_accents(base)
        if accent_folded != base:
            add_variant(accent_folded, "strip_accents")

        simplified = self._simplify_punctuation(accent_folded)
        if simplified != accent_folded:
            add_variant(simplified, "simplify_punctuation")

        parts = [segment.strip() for segment in simplified.split(",") if segment.strip()]
        if len(parts) >= 2:
            add_variant(parts[0], "primary_component")
            add_variant(f"{parts[0]}, {parts[-1]}", "poi_plus_city")
        elif parts:
            add_variant(parts[0], "primary_component")

        for current, _ in list(variants):
            for candidate in self._build_proper_noun_variants(current):
                add_variant(candidate, "proper_noun_adjustment")

        return variants

    def _build_proper_noun_variants(self, query: str) -> List[str]:
        head, sep, tail = query.partition(",")
        street_part = head.strip()
        if not street_part:
            return []
        match = self.street_type_pattern.search(street_part)
        if not match:
            return []
        suffix = street_part[match.end():]
        if not suffix.strip():
            return []

        variants: List[str] = []
        for seq_match in self.multiword_sequence_pattern.finditer(suffix):
            seq_text = seq_match.group(0)
            words = [token for token in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’-]+", seq_text)]
            if len(words) < 2:
                continue
            prefix_text = suffix[: seq_match.start()]
            suffix_text = suffix[seq_match.end():]
            normalized_words = [self._normalize_proper_word(token) for token in words]

            def _build_variant(tokens: List[str], joiner: str) -> str:
                tail_segment = f"{prefix_text} {joiner.join(tokens)}{suffix_text}"
                return (street_part[: match.end()] + tail_segment).strip()

            title_variant = _build_variant(normalized_words, " ")
            variants.append(self._reassemble_query(title_variant, sep, tail))

            hyphen_all_tail = _build_variant(normalized_words, "-")
            variants.append(self._reassemble_query(hyphen_all_tail, sep, tail))

            if len(normalized_words) >= 3:
                trimmed = normalized_words[1:]
                hyphen_trim_tail = _build_variant(trimmed, "-")
                variants.append(self._reassemble_query(hyphen_trim_tail, sep, tail))

                drop_first_tail = _build_variant(trimmed, " ")
                variants.append(self._reassemble_query(drop_first_tail, sep, tail))

        return [variant for variant in variants if variant]

    @staticmethod
    def _reassemble_query(street: str, separator: str, remainder: str) -> str:
        if separator:
            remainder_clean = remainder.strip()
            if remainder_clean:
                return f"{street}, {remainder_clean}"
        return street

    @staticmethod
    def _normalize_proper_word(token: str) -> str:
        stripped = token.strip()
        if not stripped:
            return stripped
        lower = stripped.lower()
        return lower[0].upper() + lower[1:]

    @staticmethod
    def _strip_accents(value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @staticmethod
    def _simplify_punctuation(value: str) -> str:
        no_quotes = re.sub(r"[’'`]", " ", value)
        no_hyphen = no_quotes.replace("-", " ")
        collapsed = re.sub(r"\s+", " ", no_hyphen)
        return collapsed.strip()

    def _cache_key(
        self,
        query: str,
        limit: int,
        countrycodes: Optional[str],
        language: Optional[str],
        allow_default_city: bool,
    ) -> str:
        normalized_query = re.sub(r"\s+", " ", query.strip()).lower()
        parts = [
            normalized_query,
            str(limit),
            (countrycodes or "").lower(),
            (language or "").lower(),
            "1" if allow_default_city else "0",
        ]
        return "|".join(parts)

    async def _cache_get(
        self, key: str
    ) -> Optional[tuple[List[Dict[str, Any]], str, Optional[str]]]:
        if self.cache_ttl <= 0 or self.cache_max_entries <= 0:
            return None
        async with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            ts, payload, eff_query, eff_codes = entry
            if monotonic() - ts > self.cache_ttl:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return payload, eff_query, eff_codes

    async def _cache_set(
        self,
        key: str,
        payload: List[Dict[str, Any]],
        effective_query: str,
        effective_codes: Optional[str],
    ) -> None:
        if self.cache_ttl <= 0 or self.cache_max_entries <= 0:
            return
        async with self._cache_lock:
            self._cache[key] = (monotonic(), payload, effective_query, effective_codes)
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_max_entries:
                self._cache.popitem(last=False)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call_nominatim(
        self,
        query: str,
        limit: int,
        countrycodes: Optional[str],
        language: Optional[str],
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "q": query,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 0,
        }
        if countrycodes:
            params["countrycodes"] = countrycodes
        lang = language or self.default_language
        if lang:
            request_headers = {"Accept-Language": lang}
        else:
            request_headers = None

        try:
            response = await self._client.get(self.base_url, params=params, headers=request_headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("Nominatim error: %s", exc)
            status = exc.response.status_code if exc.response else 502
            detail = exc.response.text if exc.response else str(exc)
            raise HTTPException(status_code=status, detail=detail) from exc
        except httpx.RequestError as exc:
            logger.warning("Nominatim request error: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        payload = response.json()

        if not isinstance(payload, list):
            raise HTTPException(status_code=502, detail="Invalid response from Nominatim (expected list).")
        return payload

    async def geocode(
        self,
        query: str,
        limit: int,
        countrycodes: Optional[str],
        language: Optional[str],
        allow_default_city: bool = True,
    ) -> tuple[List[Dict[str, Any]], str, Optional[str]]:
        if not self.enabled:
            raise HTTPException(status_code=503, detail="Nominatim geocoding disabled via configuration.")

        preferred_codes = countrycodes or self.default_countrycodes
        preferred_language = language or self.default_language
        base_query = query.strip()
        cache_key = self._cache_key(base_query, limit, preferred_codes, preferred_language, allow_default_city)
        cached = await self._cache_get(cache_key)
        if cached:
            payload, eff_query, eff_codes = cached
            return payload, eff_query, eff_codes
        query_variants = self._enumerate_query_variants(base_query)

        attempts = self._build_attempts(query_variants, preferred_codes, allow_default_city)
        seen = set()
        last_query = base_query
        last_codes = preferred_codes

        for attempt_query, attempt_codes, appended, attempt_reason in attempts:
            normalized_key = (attempt_query.lower(), attempt_codes or "__none__")
            if normalized_key in seen:
                continue
            seen.add(normalized_key)
            try:
                payload = await self._call_nominatim(
                    attempt_query,
                    limit,
                    attempt_codes,
                    preferred_language,
                )
            except HTTPException as exc:
                logger.warning(
                    "Nominatim attempt failed (%s | reason=%s): %s", attempt_query, attempt_reason, exc.detail
                )
                if attempt_codes is None:
                    last_query = attempt_query
                    last_codes = attempt_codes
                if self.request_delay > 0:
                    await asyncio.sleep(self.request_delay)
                continue

            last_query = attempt_query
            last_codes = attempt_codes
            if payload:
                if appended:
                    logger.info(
                        "Nominatim fallback succeeded with appended city for query=%r (reason=%s)",
                        attempt_query,
                        attempt_reason,
                    )
                elif attempt_reason != "original":
                    logger.info(
                        "Nominatim fallback succeeded using reason=%s for query=%r",
                        attempt_reason,
                        attempt_query,
                    )
                if attempt_codes is None and (countrycodes or self.default_countrycodes):
                    logger.info("Nominatim fallback succeeded without country restriction for query=%r", attempt_query)
                await self._cache_set(cache_key, payload, attempt_query, attempt_codes)
                return payload, attempt_query, attempt_codes
            if self.request_delay > 0:
                await asyncio.sleep(self.request_delay)

        logger.warning(
            "Nominatim returns no result for query=%r even after %d attempts.",
            query,
            len(seen),
        )
        await self._cache_set(cache_key, [], last_query, last_codes)
        return [], last_query, last_codes

    def _build_attempts(
        self,
        query_variants: List[tuple[str, str]],
        preferred_codes: Optional[str],
        allow_default_city: bool,
    ) -> List[tuple[str, Optional[str], bool, str]]:
        attempts: List[tuple[str, Optional[str], bool, str]] = []
        base_attempts: List[tuple[str, Optional[str], bool, str]] = []
        for variant, reason in query_variants:
            entry = (variant, preferred_codes, False, reason)
            attempts.append(entry)
            base_attempts.append(entry)
            if (
                allow_default_city
                and self.default_city_suffix
                and self._should_append_city(variant)
            ):
                appended_query = f"{variant}, {self.default_city_suffix}"
                attempts.append((appended_query, preferred_codes, True, f"{reason}+city_suffix"))

        if preferred_codes:
            for variant, _, flag, reason in base_attempts:
                attempts.append((variant, None, flag, f"{reason}+no_country"))

        if self.max_query_attempts > 0:
            attempts = attempts[: self.max_query_attempts]
        return attempts


class OSRMClient:
    def __init__(self):
        self.base_url = os.getenv("ECO_GEO_OSRM_URL", DEFAULT_OSRM_URL).rstrip("/")
        self.timeout = float(os.getenv("ECO_GEO_OSRM_TIMEOUT", "10.0"))
        self.user_agent = os.getenv(
            "ECO_GEO_USER_AGENT",
            "FredEcoAdvisorGeo/1.0 (+https://fredk8.dev; contact: ecoadvisor@thalesgroup.com)",
        )
        self.enabled = os.getenv("ECO_GEO_ROUTING_ENABLED", "true").lower() not in (
            "false",
            "0",
        )
        self._client = httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": self.user_agent})

    async def route(
        self,
        origin_lat: float,
        origin_lng: float,
        destination_lat: float,
        destination_lng: float,
        profile: str,
    ) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("OSRM routing disabled via configuration.")

        coords = f"{origin_lng},{origin_lat};{destination_lng},{destination_lat}"
        url = f"{self.base_url}/route/v1/{profile}/{coords}"
        params = {
            "overview": "false",
            "alternatives": "false",
            "annotations": "distance,duration",
        }
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            detail = exc.response.text[:200] if exc.response and exc.response.text else str(exc)
            raise RuntimeError(f"OSRM HTTP {status}: {detail}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"OSRM request error: {exc}") from exc

        payload = response.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            message = payload.get("message") or "OSRM did not return a valid route."
            raise RuntimeError(message)
        return payload["routes"][0]

    async def aclose(self) -> None:
        await self._client.aclose()


geocoder = NominatimClient()
router = OSRMClient()

app = FastAPI(
    title="EcoAdvisor Geo Distance Service",
    version="0.1.0",
    description="Provides geocoding (Nominatim) and routing distances (OSRM) for EcoAdvisor.",
)


@app.post(
    "/geo/geocode",
    tags=["Geo"],
    operation_id="geocode_location",
    response_model=GeocodeResponse,
)
async def geocode_location(request: GeocodeRequest) -> GeocodeResponse:
    logger.info("Geo geocoding request q=%r limit=%s", request.query, request.limit)
    raw_results, effective_query, effective_codes = await geocoder.geocode(
        query=request.query,
        limit=request.limit,
        countrycodes=request.countrycodes,
        language=request.language,
        allow_default_city=request.allow_default_city,
    )
    results: List[GeocodeResult] = []
    for entry in raw_results:
        lat = _parse_float(entry.get("lat"))
        lon = _parse_float(entry.get("lon"))
        if lat is None or lon is None:
            continue
        results.append(
            GeocodeResult(
                label=entry.get("display_name", ""),
                lat=lat,
                lon=lon,
                place_id=str(entry.get("place_id") or ""),
                osm_type=entry.get("osm_type"),
                osm_id=_parse_int(entry.get("osm_id")),
                place_class=entry.get("class"),
                place_type=entry.get("type"),
                importance=_parse_float(entry.get("importance")),
                boundingbox=_to_bbox(entry.get("boundingbox")),
                raw=entry,
            )
        )

    return GeocodeResponse(
        provider="Nominatim OpenStreetMap",
        query=request.query,
        effective_query=effective_query,
        count=len(results),
        limit=request.limit,
        countrycodes=request.countrycodes or geocoder.default_countrycodes,
        effective_countrycodes=effective_codes or request.countrycodes or geocoder.default_countrycodes,
        language=request.language or geocoder.default_language,
        queried_at=datetime.now(timezone.utc),
        results=results,
    )


async def _compute_route_metrics(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    profile: str,
) -> RouteDistanceResponse:
    logger.info(
        "Routing lat/lon=(%.5f, %.5f)->(%.5f, %.5f) profile=%s",
        origin_lat,
        origin_lng,
        destination_lat,
        destination_lng,
        profile,
    )
    used_source = "osrm"
    fallback_reason: Optional[str] = None
    notes: Optional[str] = None

    try:
        route = await router.route(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            destination_lat=destination_lat,
            destination_lng=destination_lng,
            profile=profile,
        )
        distance_m = float(route.get("distance") or 0.0)
        duration_s = _parse_float(route.get("duration"))
    except Exception as exc:
        logger.warning("OSRM routing failed (%s). Falling back to haversine.", exc)
        used_source = "haversine"
        fallback_reason = str(exc)
        distance_km = _haversine_km(origin_lat, origin_lng, destination_lat, destination_lng)
        distance_m = distance_km * 1000.0
        duration_s = None
        notes = "Fallback great-circle distance (no live travel time)."

    distance_km = distance_m / 1000.0
    duration_min = (duration_s / 60.0) if duration_s is not None else None

    return RouteDistanceResponse(
        provider="OSRM" if used_source == "osrm" else "Great-circle approximation",
        profile=profile,
        distance_m=distance_m,
        distance_km=distance_km,
        duration_s=duration_s,
        duration_min=duration_min,
        computed_at=datetime.now(timezone.utc),
        source=used_source,
        fallback_reason=fallback_reason,
        notes=notes,
    )


@app.post(
    "/geo/distance",
    tags=["Geo"],
    operation_id="compute_trip_distance",
    response_model=RouteDistanceResponse,
)
async def compute_trip_distance(request: RouteDistanceRequest) -> RouteDistanceResponse:
    return await _compute_route_metrics(
        origin_lat=request.origin_lat,
        origin_lng=request.origin_lng,
        destination_lat=request.destination_lat,
        destination_lng=request.destination_lng,
        profile=request.profile,
    )


def _build_trip_resolution(query: str, payload: Dict[str, Any]) -> TripAddressResolution:
    return TripAddressResolution(
        query=query,
        label=payload.get("display_name"),
        lat=_parse_float(payload.get("lat")),
        lon=_parse_float(payload.get("lon")),
        place_id=str(payload.get("place_id") or ""),
        osm_id=_parse_int(payload.get("osm_id")),
        boundingbox=_to_bbox(payload.get("boundingbox")),
        raw=payload,
    )


@app.post(
    "/geo/trip",
    tags=["Geo"],
    operation_id="estimate_trip_between_addresses",
    response_model=TripEstimateResponse,
)
async def estimate_trip_between_addresses(request: TripEstimateRequest) -> TripEstimateResponse:
    origin_task = geocoder.geocode(
        query=request.origin_query,
        limit=1,
        countrycodes=request.countrycodes,
        language=request.language,
        allow_default_city=request.allow_default_city,
    )
    destination_task = geocoder.geocode(
        query=request.destination_query,
        limit=1,
        countrycodes=request.countrycodes,
        language=request.language,
        allow_default_city=request.allow_default_city,
    )
    (
        (origin_candidates, origin_effective_query, origin_codes),
        (destination_candidates, destination_effective_query, destination_codes),
    ) = await asyncio.gather(origin_task, destination_task)

    if not origin_candidates:
        raise HTTPException(status_code=404, detail=f"Origin '{request.origin_query}' not found.")
    if not destination_candidates:
        raise HTTPException(status_code=404, detail=f"Destination '{request.destination_query}' not found.")

    origin = _build_trip_resolution(request.origin_query, origin_candidates[0])
    destination = _build_trip_resolution(request.destination_query, destination_candidates[0])

    if origin.lat is None or origin.lon is None or destination.lat is None or destination.lon is None:
        raise HTTPException(status_code=502, detail="Failed to resolve coordinates for one of the addresses.")

    route_response = await _compute_route_metrics(
        origin_lat=origin.lat,
        origin_lng=origin.lon,
        destination_lat=destination.lat,
        destination_lng=destination.lon,
        profile=request.profile,
    )
    geodesic_distance = _haversine_km(origin.lat, origin.lon, destination.lat, destination.lon)

    return TripEstimateResponse(
        provider=route_response.provider,
        profile=route_response.profile,
        distance_m=route_response.distance_m,
        distance_km=route_response.distance_km,
        duration_s=route_response.duration_s,
        duration_min=route_response.duration_min,
        geodesic_distance_km=geodesic_distance,
        computed_at=route_response.computed_at,
        source=route_response.source,
        fallback_reason=route_response.fallback_reason,
        notes=route_response.notes,
        origin=origin,
        destination=destination,
    )


@app.get("/geo/health", tags=["Geo"])
async def healthcheck() -> Dict[str, Any]:
    return {
        "nominatim_url": geocoder.base_url,
        "nominatim_enabled": geocoder.enabled,
        "osrm_url": router.base_url,
        "osrm_enabled": router.enabled,
    }


@app.on_event("shutdown")
async def shutdown_clients() -> None:
    await asyncio.gather(geocoder.aclose(), router.aclose())


mcp = FastApiMCP(
    app,
    name="EcoAdvisor Geo MCP",
    description="Expose geocoding (Nominatim) and routing distances (OSRM) to EcoAdvisor.",
    include_tags=["Geo"],
    describe_all_responses=True,
    describe_full_response_schema=True,
)
mcp.mount_http(mount_path="/mcp")

__all__ = ["app"]
