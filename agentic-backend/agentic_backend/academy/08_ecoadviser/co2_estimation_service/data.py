"""Default emission factors referenced by the CO₂ MCP service."""

from __future__ import annotations

from typing import List, TypedDict


class EmissionFactorDict(TypedDict, total=False):
    """Serialized representation of an emission factor."""

    mode: str
    label: str
    category: str
    factor_kg_per_km: float
    unit: str
    source: str
    source_url: str
    last_update: str
    geography: str
    notes: str
    aliases: List[str]


DEFAULT_EMISSION_FACTORS: List[EmissionFactorDict] = [
    {
        "mode": "car_thermal",
        "label": "Voiture thermique (segment C)",
        "category": "road_private",
        "factor_kg_per_km": 0.192,
        "unit": "kgCO2e/km",
        "source": "ADEME Base Carbone 2024",
        "source_url": "https://data.ademe.fr/datasets/base-carbone",
        "last_update": "2024-02-15",
        "geography": "France métropolitaine",
        "notes": "Mix essence/diesel WLTP. Inclut valeurs amont carburant.",
        "aliases": [
            "voiture",
            "car",
            "auto",
            "voiture_thermique",
            "car_ice",
            "voiture thermique",
        ],
    },
    {
        "mode": "car_electric",
        "label": "Voiture électrique",
        "category": "road_private",
        "factor_kg_per_km": 0.012,
        "unit": "kgCO2e/km",
        "source": "ADEME Base Carbone 2024",
        "source_url": "https://data.ademe.fr/datasets/base-carbone",
        "last_update": "2024-02-15",
        "geography": "Mix électrique français 2023",
        "notes": "Berline électrique ~15 kWh/100km. Inclut production électricité.",
        "aliases": [
            "voiture_electrique",
            "voiture électrique",
            "car_ev",
            "ev",
        ],
    },
    {
        "mode": "tramway",
        "label": "Tramway urbain (TCL)",
        "category": "public_transport",
        "factor_kg_per_km": 0.004,
        "unit": "kgCO2e/km",
        "source": "SYTRAL Mobilités 2023 + ADEME",
        "source_url": "https://sytral.fr",
        "last_update": "2023-12-01",
        "geography": "Réseau TCL",
        "notes": "Consommation électrique ramenée au voyageur moyen.",
        "aliases": [
            "tram",
            "tcl_tram",
            "tramway tcl",
        ],
    },
    {
        "mode": "metro",
        "label": "Métro (TCL)",
        "category": "public_transport",
        "factor_kg_per_km": 0.003,
        "unit": "kgCO2e/km",
        "source": "SYTRAL Mobilités 2023 + ADEME",
        "source_url": "https://sytral.fr",
        "last_update": "2023-12-01",
        "geography": "Réseau TCL",
        "notes": "Facteur par passager pour les lignes A/B/D.",
        "aliases": ["tcl_metro", "metro tcl"],
    },
    {
        "mode": "tcl_bus_hybrid",
        "label": "Bus urbain hybride (TCL)",
        "category": "public_transport",
        "factor_kg_per_km": 0.089,
        "unit": "kgCO2e/km",
        "source": "SYTRAL Mobilités 2023",
        "source_url": "https://sytral.fr",
        "last_update": "2023-12-01",
        "geography": "Réseau TCL",
        "notes": "Equivalent passager moyen. Inclut exploitation et carburant.",
        "aliases": [
            "bus",
            "tcl_bus",
            "bus_tcl",
            "tcl",
        ],
    },
    {
        "mode": "regional_train",
        "label": "TER / Train régional",
        "category": "rail",
        "factor_kg_per_km": 0.006,
        "unit": "kgCO2e/km",
        "source": "ADEME / SNCF 2024",
        "source_url": "https://www.sncf.com/fr/empreinte",
        "last_update": "2024-01-20",
        "geography": "France",
        "notes": "Valeur moyenne par passager (mix électrique + diesel).",
        "aliases": [
            "train",
            "ter",
            "sncf",
        ],
    },
    {
        "mode": "bike",
        "label": "Vélo / VAE",
        "category": "active",
        "factor_kg_per_km": 0.0,
        "unit": "kgCO2e/km",
        "source": "ADEME Base Carbone 2024",
        "source_url": "https://data.ademe.fr/datasets/base-carbone",
        "last_update": "2024-02-15",
        "geography": "Usage urbain",
        "notes": "Émissions directes nulles.",
        "aliases": [
            "velo",
            "vélo",
            "bicycle",
        ],
    },
    {
        "mode": "walking",
        "label": "Marche",
        "category": "active",
        "factor_kg_per_km": 0.0,
        "unit": "kgCO2e/km",
        "source": "ADEME Base Carbone 2024",
        "source_url": "https://data.ademe.fr/datasets/base-carbone",
        "last_update": "2024-02-15",
        "geography": "Usage urbain",
        "notes": "Émissions directes nulles.",
        "aliases": [
            "marche",
            "walk",
            "walking_mode",
            "a_pied",
        ],
    },
]

