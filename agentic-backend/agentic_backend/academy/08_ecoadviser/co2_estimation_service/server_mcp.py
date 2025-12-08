from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx
from fastapi import FastAPI, HTTPException
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel, Field, ValidationError, field_validator

from .base_carbone_client import (
    BaseCarboneClient,
    BaseCarboneQuery,
    DEFAULT_TRANSPORT_QUERIES,
)
from .data import DEFAULT_EMISSION_FACTORS

logger = logging.getLogger(__name__)


class EmissionFactor(BaseModel):
    mode: str = Field(..., description="Canonical identifier of the transport mode.")
    label: str = Field(..., description="Human readable label for the transport mode.")
    category: str = Field(..., description="Semantic category (road, rail, active, etc.).")
    factor_kg_per_km: float = Field(
        ..., ge=0.0, description="Kg CO₂ equivalent emitted per passenger-km."
    )
    unit: str = Field(default="kgCO2e/km", description="Unit of the emission factor.")
    source: str = Field(..., description="Name of the upstream reference (ADEME, SYTRAL...).")
    source_url: Optional[str] = Field(
        default=None, description="URL pointing to the official methodology."
    )
    last_update: date = Field(..., description="Date of the latest refresh of this factor.")
    geography: Optional[str] = Field(
        default=None, description="Geographical scope (France, Rhône, EU27...)."
    )
    notes: Optional[str] = Field(
        default=None, description="Any caveats or assumptions associated with the factor."
    )
    aliases: List[str] = Field(
        default_factory=list,
        description="List of free-form aliases pointing to this canonical mode.",
    )

    @field_validator("last_update", mode="before")
    @classmethod
    def _parse_date(cls, value: Any) -> date:
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        raise ValueError("last_update must be ISO date or datetime.")


class EmissionModeSummary(BaseModel):
    mode: str
    label: str
    category: str
    factor_kg_per_km: float
    source: str
    last_update: date

    @classmethod
    def from_factor(cls, factor: EmissionFactor) -> "EmissionModeSummary":
        return cls(
            mode=factor.mode,
            label=factor.label,
            category=factor.category,
            factor_kg_per_km=factor.factor_kg_per_km,
            source=factor.source,
            last_update=factor.last_update,
        )


class TripComparisonItem(BaseModel):
    mode: str
    label: str
    weekly_emissions_kg: float
    factor_kg_per_km: float
    source: str
    source_url: Optional[str] = None
    last_update: date
    notes: Optional[str] = None


class TripComparisonRequest(BaseModel):
    distance_km: float = Field(
        ...,
        gt=0.0,
        description="One-way distance in kilometers for the studied trip.",
    )
    frequency_days: int = Field(
        default=5,
        gt=0,
        le=14,
        description="How many days per week the trip is performed.",
    )
    round_trips_per_day: float = Field(
        default=2.0,
        gt=0.0,
        le=6.0,
        description="Number of one-way legs per day (2.0 for commute).",
    )
    modes: Optional[List[str]] = Field(
        default=None,
        description="Optional subset of modes to compare. If omitted all modes are returned.",
    )


class TripComparisonResponse(BaseModel):
    distance_km: float
    weekly_distance_km: float
    frequency_days: int
    round_trips_per_day: float
    results: List[TripComparisonItem]
    methodology: str


def _load_json_payload(path: str) -> List[Dict[str, Any]]:
    fpath = Path(path).expanduser()
    if not fpath.exists():
        logger.warning("CO₂ dataset override does not exist: %s", fpath)
        return []
    try:
        payload = json.loads(fpath.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        logger.warning("CO₂ dataset override %s is not a list.", fpath)
    except Exception:
        logger.exception("Unable to parse CO₂ dataset override at %s", fpath)
    return []


def _extract_list_from_payload(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Accept both raw lists and the typical dict wrappers returned by French open-data
    APIs (e.g. data-fair) where rows live under 'results' or 'records'.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("results", "records", "data", "items", "lines"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
    return None


def _fetch_remote_payload(url: str) -> List[Dict[str, Any]]:
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()
            rows = _extract_list_from_payload(payload)
            if rows is not None:
                logger.info("Loaded %d emission factors from %s", len(rows), url)
                return rows
            logger.warning("Remote CO₂ dataset at %s is not a list.", url)
    except Exception:
        logger.exception("Unable to fetch CO₂ dataset from %s", url)
    return []


def _load_dynamic_dataset() -> List[Dict[str, Any]]:
    dataset: List[Dict[str, Any]] = []
    file_path = os.getenv("CO2_REFERENCE_DATA")
    if file_path:
        dataset.extend(_load_json_payload(file_path))
    url = os.getenv("CO2_REFERENCE_URL")
    if url:
        dataset.extend(_fetch_remote_payload(url))
    return dataset


class EmissionFactorStore:
    REQUIRED_FIELDS = {
        "mode",
        "label",
        "category",
        "factor_kg_per_km",
        "source",
        "last_update",
    }

    def __init__(
        self,
        initial_dataset: Sequence[Dict[str, Any]],
        base_carbone_client: Optional[BaseCarboneClient] = None,
        base_carbone_queries: Optional[Sequence[BaseCarboneQuery]] = None,
    ):
        self._raw_dataset = list(initial_dataset)
        self._records: Dict[str, EmissionFactor] = {}
        self._alias_index: Dict[str, str] = {}
        self._base_carbone_client = base_carbone_client
        self._base_carbone_queries = list(base_carbone_queries or [])
        self.reload()

    def reload(self) -> None:
        dataset = list(DEFAULT_EMISSION_FACTORS)
        dataset.extend(self._raw_dataset)
        dataset.extend(_load_dynamic_dataset())
        if self._base_carbone_client and self._base_carbone_queries:
            dataset.extend(
                self._base_carbone_client.fetch_all(self._base_carbone_queries)
            )
        normalized: Dict[str, EmissionFactor] = {}
        aliases: Dict[str, str] = {}
        skipped = 0
        for entry in dataset:
            missing_fields = self.REQUIRED_FIELDS.difference(entry.keys())
            if missing_fields:
                skipped += 1
                logger.debug(
                    "Skipping emission factor entry missing required fields %s: %s",
                    sorted(missing_fields),
                    entry,
                )
                continue
            try:
                record = EmissionFactor(**entry)
            except ValidationError as exc:
                logger.debug(
                    "Invalid emission factor payload skipped: %s", entry, exc_info=exc
                )
                continue
            key = record.mode.lower()
            normalized[key] = record
            for alias in record.aliases:
                aliases[alias.lower()] = key
        self._records = normalized
        self._alias_index = aliases
        if skipped:
            logger.info(
                "EmissionFactorStore: skipped %d dynamic entries missing required fields.",
                skipped,
            )
        logger.info("CO₂ reference now tracks %d canonical modes.", len(self._records))

    def _resolve_mode(self, mode: str) -> str:
        key = mode.strip().lower()
        if key in self._records:
            return key
        if key in self._alias_index:
            return self._alias_index[key]
        raise KeyError(mode)

    def list_modes(self) -> List[EmissionFactor]:
        return sorted(self._records.values(), key=lambda r: r.label)

    def get_factor(self, mode: str) -> EmissionFactor:
        resolved = self._resolve_mode(mode)
        return self._records[resolved]

    def compare_modes(
        self,
        *,
        distance_km: float,
        frequency_days: int,
        round_trips_per_day: float,
        modes: Optional[Iterable[str]] = None,
    ) -> List[TripComparisonItem]:
        if modes:
            resolved_modes = [self.get_factor(mode) for mode in modes]
        else:
            resolved_modes = self.list_modes()

        weekly_distance = distance_km * frequency_days * round_trips_per_day
        results: List[TripComparisonItem] = []
        for record in resolved_modes:
            weekly_emissions = round(
                record.factor_kg_per_km * weekly_distance,
                4,
            )
            results.append(
                TripComparisonItem(
                    mode=record.mode,
                    label=record.label,
                    weekly_emissions_kg=weekly_emissions,
                    factor_kg_per_km=record.factor_kg_per_km,
                    source=record.source,
                    source_url=record.source_url,
                    last_update=record.last_update,
                    notes=record.notes,
                )
            )
        results.sort(key=lambda item: item.weekly_emissions_kg)
        return results


app = FastAPI(
    title="EcoAdvisor CO₂ Reference Service",
    version="0.1.0",
    description=(
        "Lightweight reference service returning ADEME-sourced emission factors. "
        "Designed to be exposed via MCP so EcoAdvisor can cite verifiable sources."
    ),
)

base_carbone_client = BaseCarboneClient.from_env()

store = EmissionFactorStore(
    initial_dataset=[],
    base_carbone_client=base_carbone_client,
    base_carbone_queries=DEFAULT_TRANSPORT_QUERIES,
)


@app.get(
    "/co2/emission-modes",
    response_model=List[EmissionModeSummary],
    tags=["CO2"],
    operation_id="list_emission_modes",
)
async def list_emission_modes() -> List[EmissionModeSummary]:
    return [EmissionModeSummary.from_factor(factor) for factor in store.list_modes()]


@app.get(
    "/co2/emission-factor/{mode}",
    response_model=EmissionFactor,
    tags=["CO2"],
    operation_id="get_emission_factor",
)
async def get_emission_factor(mode: str) -> EmissionFactor:
    try:
        return store.get_factor(mode)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown mode '{mode}'.")


@app.post(
    "/co2/compare-trip-modes",
    response_model=TripComparisonResponse,
    tags=["CO2"],
    operation_id="compare_trip_modes",
)
async def compare_trip_modes(request: TripComparisonRequest) -> TripComparisonResponse:
    results = store.compare_modes(
        distance_km=request.distance_km,
        frequency_days=request.frequency_days,
        round_trips_per_day=request.round_trips_per_day,
        modes=request.modes,
    )
    weekly_distance = request.distance_km * request.frequency_days * request.round_trips_per_day
    methodology = (
        "Weekly emissions = factor_kg_per_km × distance_km (one-way) × "
        "round_trips_per_day × frequency_days."
    )
    return TripComparisonResponse(
        distance_km=request.distance_km,
        weekly_distance_km=weekly_distance,
        frequency_days=request.frequency_days,
        round_trips_per_day=request.round_trips_per_day,
        results=results,
        methodology=methodology,
    )


@app.post(
    "/co2/reload",
    tags=["CO2"],
    operation_id="reload_emission_cache",
)
async def reload_reference_dataset() -> Dict[str, Any]:
    store.reload()
    return {"modes": len(store.list_modes())}


mcp = FastApiMCP(
    app,
    name="EcoAdvisor CO₂ Reference MCP",
    description=(
        "Expose ADEME and SYTRAL CO₂ factors along with comparison utilities "
        "so EcoAdvisor agents can cite verifiable references."
    ),
    include_tags=["CO2"],
    describe_all_responses=True,
    describe_full_response_schema=True,
)
mcp.mount_http(mount_path="/mcp")

__all__ = ["app"]
