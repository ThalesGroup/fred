from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)


DEFAULT_API_BASE = "https://data.ademe.fr/data-fair/api/v1/datasets/base-carboner"
DEFAULT_SELECT_FIELDS: Sequence[str] = (
    "Nom_base_français",
    "Nom_poste_français",
    "Nom_poste_anglais",
    "Unité_français",
    "Unité_anglais",
    "Source",
    "Programme",
    "Commentaire_français",
    "Commentaire_anglais",
    "Date_de_modification",
    "Date_de_création",
    "Période_de_validité",
    "Total_poste_non_décomposé",
    "CO2f",
    "Localisation_géographique",
    "Url_du_programme",
)


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_float(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_int(value: Optional[str], default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", ".").strip()
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _coerce_iso_date(*candidates: Any) -> str:
    for candidate in candidates:
        if isinstance(candidate, date) and not isinstance(candidate, datetime):
            return candidate.isoformat()
        if isinstance(candidate, datetime):
            return candidate.date().isoformat()
        if isinstance(candidate, str):
            text = candidate.strip()
            if not text:
                continue
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
                try:
                    return datetime.strptime(text, fmt).date().isoformat()
                except ValueError:
                    continue
    # Fallback to current date for traceability
    return datetime.utcnow().date().isoformat()


@dataclass(frozen=True)
class BaseCarboneQuery:
    mode: str
    label: str
    category: str
    query: str
    aliases: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    unit_hint: Optional[str] = None


DEFAULT_TRANSPORT_QUERIES: Sequence[BaseCarboneQuery] = (
    BaseCarboneQuery(
        mode="car_thermal",
        label="Voiture particulière (thermique)",
        category="road_private",
        query='"voiture" AND "particulière" AND thermique',
        aliases=[
            "voiture",
            "car",
            "auto",
            "voiture_thermique",
            "car_ice",
            "voiture thermique",
        ],
        notes="Facteur ADEME Base Carbone pour un véhicule particulier thermique (passager.km).",
    ),
    BaseCarboneQuery(
        mode="car_electric",
        label="Voiture particulière (électrique)",
        category="road_private",
        query='"voiture" AND "particulière" AND électrique',
        aliases=[
            "voiture_electrique",
            "voiture électrique",
            "car_ev",
            "ev",
        ],
        notes="Facteur ADEME Base Carbone pour un véhicule particulier électrique (passager.km).",
    ),
    BaseCarboneQuery(
        mode="tramway",
        label="Tramway urbain",
        category="public_transport",
        query="tramway",
        aliases=["tram", "tcl_tram", "tramway tcl"],
        notes="Facteur par voyageur-km pour un tramway urbain.",
    ),
    BaseCarboneQuery(
        mode="metro",
        label="Métro",
        category="public_transport",
        query='métro OR "transport métropolitain"',
        aliases=["tcl_metro", "metro tcl"],
        notes="Facteur par voyageur-km pour un métro urbain.",
    ),
    BaseCarboneQuery(
        mode="tcl_bus_hybrid",
        label="Bus urbain / hybride",
        category="public_transport",
        query="bus urbain",
        aliases=["bus", "tcl_bus", "bus_tcl", "tcl"],
        notes="Facteur par voyageur-km pour un autobus urbain.",
    ),
    BaseCarboneQuery(
        mode="regional_train",
        label="Train régional / TER",
        category="rail",
        query="train régional OR TER",
        aliases=["train", "ter", "sncf"],
        notes="Facteur par voyageur-km pour un service régional ferroviaire.",
    ),
    BaseCarboneQuery(
        mode="bike",
        label="Vélo / VAE",
        category="active",
        query="vélo",
        aliases=["velo", "vélo", "bicycle"],
        notes="Émissions directes nulles pour les modes actifs.",
        unit_hint="kgCO2e/km",
    ),
    BaseCarboneQuery(
        mode="walking",
        label="Marche",
        category="active",
        query="marche",
        aliases=["marche", "walk", "walking_mode", "a_pied"],
        notes="Émissions directes nulles pour la marche.",
        unit_hint="kgCO2e/km",
    ),
)


class BaseCarboneClient:
    """
    Thin helper querying ADEME's Base Carbone dataset to retrieve transport emission factors.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_API_BASE,
        api_key: Optional[str] = None,
        timeout: float = 8.0,
        max_results: int = 5,
        enabled: bool = True,
        select_fields: Sequence[str] = DEFAULT_SELECT_FIELDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.lines_url = f"{self.base_url}/lines"
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max_results
        self.enabled = enabled
        self.select_fields = select_fields

    @classmethod
    def from_env(cls) -> "BaseCarboneClient":
        enabled = _parse_bool(os.getenv("ADEME_BASECARBONE_ENABLED"), True)
        base_url = os.getenv("ADEME_BASECARBONE_URL", DEFAULT_API_BASE)
        timeout = _parse_float(os.getenv("ADEME_BASECARBONE_TIMEOUT"), 8.0)
        max_results = _parse_int(os.getenv("ADEME_BASECARBONE_MAX_RESULTS"), 5)
        api_key = os.getenv("ADEME_BASECARBONE_API_KEY")
        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_results=max_results,
            enabled=enabled,
        )

    def fetch_all(self, queries: Sequence[BaseCarboneQuery]) -> List[Dict[str, Any]]:
        if not self.enabled:
            logger.info("Base Carbone client disabled via configuration.")
            return []

        factors: List[Dict[str, Any]] = []
        for spec in queries:
            record = self.fetch_factor(spec)
            if record:
                factors.append(record)
        return factors

    def fetch_factor(self, spec: BaseCarboneQuery) -> Optional[Dict[str, Any]]:
        params = {
            "size": self.max_results,
            "sort": "-Date_de_modification",
            "select": ",".join(self.select_fields),
            "filters[Type_de_l'élément_eq]": "Facteur d'émission",
            "filters[Statut_de_l'élément_eq]": "Valide générique",
            "filters[Type_poste_eq]": "Total poste non décomposé",
            "q": spec.query,
        }

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        try:
            with httpx.Client(timeout=self.timeout, headers=headers) as client:
                response = client.get(self.lines_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("ADEME Base Carbone request failed for %s: %s", spec.mode, exc)
            return None
        except json.JSONDecodeError:
            logger.warning("ADEME Base Carbone returned invalid JSON for mode %s", spec.mode)
            return None

        results = payload.get("results") if isinstance(payload, dict) else None
        if not results:
            logger.info("No ADEME entry matched query '%s' for mode %s.", spec.query, spec.mode)
            return None

        for entry in results:
            factor_value = _coerce_float(entry.get("Total_poste_non_décomposé"))
            if factor_value is None:
                factor_value = _coerce_float(entry.get("CO2f"))
            if factor_value is None:
                continue
            return {
                "mode": spec.mode,
                "label": entry.get("Nom_poste_français") or entry.get("Nom_base_français") or spec.label,
                "category": spec.category,
                "factor_kg_per_km": factor_value,
                "unit": spec.unit_hint or entry.get("Unité_français") or "kgCO2e/km",
                "source": entry.get("Source") or "ADEME Base Carbone",
                "source_url": entry.get("Url_du_programme") or DEFAULT_API_BASE,
                "last_update": _coerce_iso_date(
                    entry.get("Date_de_modification"),
                    entry.get("Date_de_création"),
                    entry.get("Période_de_validité"),
                ),
                "geography": entry.get("Localisation_géographique"),
                "notes": spec.notes
                or entry.get("Commentaire_français")
                or entry.get("Programme"),
                "aliases": spec.aliases,
            }

        logger.info(
            "ADEME Base Carbone did not provide a numeric factor for mode %s despite %d hits.",
            spec.mode,
            len(results),
        )
        return None


__all__ = [
    "BaseCarboneClient",
    "BaseCarboneQuery",
    "DEFAULT_TRANSPORT_QUERIES",
]
