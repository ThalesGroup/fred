"""
eco_co2_mcp_server/server_mcp.py
--------------------------------
Minimal MCP server using the current `mcp` Python SDK.

This exposes the Streamable HTTP transport at `/mcp` and is compatible with
modern MCP clients (including Fred agents via MCP).

Run (from project root):
  uvicorn eco_co2_mcp_server.server_mcp:app --host 127.0.0.1 --port 9898 --reload
  or: make server

Tools implemented (Étape 2 roadmap):
  - list_emission_modes()
  - get_emission_factor(mode)
  - estimate_trip_emissions(distance_km, frequency_days, mode)
  - compare_trip_modes(distance_km, frequency_days, current_mode, alternatives)

Fred rationale:
- Au lieu de hardcoder les facteurs CO₂ dans EcoAdvisor,
  on centralise la "connaissance CO₂" dans un service MCP dédié.
- EcoAdvisor devient un simple client de ce serveur:
  il appelle des tools de haut niveau et reste focalisé sur le dialogue.
- Cette séparation simplifie:
  - les démos (on peut brancher/débrancher le serveur),
  - les évolutions (changer les facteurs / la source de données),
  - la compréhension par les développeurs (1 fichier = 1 responsabilité).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
import time

try:
    # Use FastMCP (ergonomic server with @tool decorator) and build a Starlette app
    from mcp.server import FastMCP
except Exception as e:  # pragma: no cover - helpful error at import time
    raise ImportError(
        "The 'mcp' package is required for eco_co2_mcp_server.server_mcp.\n"
        "Install it via: pip install \"mcp[fastapi]\"\n"
        f"Import error: {e}"
    )


# ---------------------------------------------------------------------------
# In-memory "reference" emission factors
# ---------------------------------------------------------------------------
# Fred rationale:
# - Pour la démo, on utilise une petite table en mémoire.
# - Plus tard, on pourra:
#   - la remplir à partir d'un CSV ADEME,
#   - la rafraîchir périodiquement,
#   - ou appeler une vraie API externe.
# - L'API MCP ne change pas: EcoAdvisor continue d'appeler ces tools.
# ---------------------------------------------------------------------------

# Facteurs d'émission simplifiés, inspirés de valeurs ADEME (DEMO ONLY, not official)
# Units: kg CO2 per km (well-to-wheel approximations)
_EMISSION_FACTORS: Dict[str, Dict[str, Any]] = {
    "car_thermal": {
        "label": "Voiture thermique (moyenne)",
        "mode": "car_thermal",
        "factor_kg_per_km": 0.192,
        "source": "Demo factor inspired by ADEME car average (approximate)",
        "source_url": "https://base-empreinte.ademe.fr/ (not queried live in this demo)",
        "last_update": "2024-01-01",
    },
    "public_transport": {
        "label": "Transport en commun urbain (moyenne)",
        "mode": "public_transport",
        "factor_kg_per_km": 0.01,
        "source": "Demo factor inspired by ADEME urban public transport (approximate)",
        "source_url": "https://base-empreinte.ademe.fr/ (not queried live in this demo)",
        "last_update": "2024-01-01",
    },
    "bike": {
        "label": "Vélo",
        "mode": "bike",
        "factor_kg_per_km": 0.0,
        "source": "No CO₂ tailpipe emissions (manufacturing not considered here)",
        "source_url": "",
        "last_update": "2024-01-01",
    },
    "walk": {
        "label": "Marche à pied",
        "mode": "walk",
        "factor_kg_per_km": 0.0,
        "source": "No CO₂ tailpipe emissions (manufacturing not considered here)",
        "source_url": "",
        "last_update": "2024-01-01",
    },
}


# Create a FastMCP server (provides @tool and compatible transports)
server = FastMCP(name="eco-co2-mcp")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@server.tool()
async def list_emission_modes() -> Dict[str, Any]:
    """List available transport modes and their demo emission factors.

    EcoAdvisor usage:
    - Découvrir dynamiquement quels modes sont connus (car_thermal, public_transport, bike, walk...).
    - Afficher des explications à l'utilisateur (labels + sources).
    """
    return {
        "modes": [
            {
                "mode": data["mode"],
                "label": data["label"],
                "factor_kg_per_km": data["factor_kg_per_km"],
                "source": data["source"],
                "source_url": data["source_url"],
                "last_update": data["last_update"],
            }
            for data in _EMISSION_FACTORS.values()
        ],
        "units": "kg_CO2_per_km",
        "note": "Demo emission factors only. For production, connect to an official database (e.g., ADEME Base Carbone).",
    }


@server.tool()
async def get_emission_factor(
    mode: Literal["car_thermal", "public_transport", "bike", "walk"]
) -> Dict[str, Any]:
    """Return the emission factor for a given transport mode.

    EcoAdvisor usage:
    - Ne plus hardcoder les facteurs dans le prompt.
    - Demander au serveur MCP: 'donne-moi le facteur pour car_thermal'.
    """
    data = _EMISSION_FACTORS.get(mode)
    if not data:
        return {
            "ok": False,
            "error": f"Unknown mode: {mode}",
            "known_modes": list(_EMISSION_FACTORS.keys()),
        }

    return {
        "ok": True,
        "mode": data["mode"],
        "label": data["label"],
        "factor_kg_per_km": data["factor_kg_per_km"],
        "source": data["source"],
        "source_url": data["source_url"],
        "last_update": data["last_update"],
        "units": "kg_CO2_per_km",
    }


@server.tool()
async def estimate_trip_emissions(
    distance_km: float,
    frequency_days_per_week: int,
    mode: Literal["car_thermal", "public_transport", "bike", "walk"],
    weeks_per_year: Optional[int] = 47,
) -> Dict[str, Any]:
    """Estimate weekly and yearly CO₂ emissions for a repeated trip.

    Parameters:
      - distance_km: total distance per day (typically round-trip).
      - frequency_days_per_week: how many days per week (e.g. 5).
      - mode: transport mode (must be one of the known modes).
      - weeks_per_year: number of commuting weeks per year (default 47).

    EcoAdvisor usage:
      - Convert a description '10 km AR, 5 jours/semaine, voiture'
        en chiffres: kg CO₂ / semaine et / an.
    """
    factor_data = _EMISSION_FACTORS.get(mode)
    if not factor_data:
        return {
            "ok": False,
            "error": f"Unknown mode: {mode}",
            "known_modes": list(_EMISSION_FACTORS.keys()),
        }

    factor = float(factor_data["factor_kg_per_km"])
    weekly_distance = distance_km * float(frequency_days_per_week)
    weekly_kg = weekly_distance * factor
    yearly_kg = weekly_kg * float(weeks_per_year or 47)

    # Petit timestamp pour tracer quand l'estimation a été faite
    now_ts = int(time.time())

    return {
        "ok": True,
        "mode": mode,
        "label": factor_data["label"],
        "factor_kg_per_km": factor,
        "distance_km_per_day": distance_km,
        "frequency_days_per_week": frequency_days_per_week,
        "weeks_per_year": weeks_per_year,
        "weekly_kg_co2": round(weekly_kg, 3),
        "yearly_kg_co2": round(yearly_kg, 3),
        "units": {
            "factor": "kg_CO2_per_km",
            "weekly": "kg_CO2_per_week",
            "yearly": "kg_CO2_per_year",
        },
        "source": factor_data["source"],
        "source_url": factor_data["source_url"],
        "last_update": factor_data["last_update"],
        "computed_at": now_ts,
        "assumptions": [
            "Emissions are estimated using simplified demo factors.",
            "Manufacturing and infrastructure emissions are not included.",
            "Distance_km is assumed to be total daily distance (e.g. round-trip).",
        ],
    }


@server.tool()
async def compare_trip_modes(
    distance_km: float,
    frequency_days_per_week: int,
    current_mode: Literal["car_thermal", "public_transport", "bike", "walk"],
    alternatives: Optional[List[Literal["car_thermal", "public_transport", "bike", "walk"]]] = None,
    weeks_per_year: Optional[int] = 47,
) -> Dict[str, Any]:
    """Compare CO₂ emissions between current_mode and alternative modes.

    EcoAdvisor usage:
      - Construire un tableau de comparaison prêt à être rendu en Markdown:
        voiture vs TCL vs vélo, pour une distance donnée.

    Returns:
      - current: détail des émissions pour current_mode
      - alternatives: liste des autres modes avec leurs émissions
      - savings: différences (kg CO₂/an) par rapport au mode actuel
    """
    if alternatives is None:
        # By default, compare with all other modes
        alternatives = [
            m for m in _EMISSION_FACTORS.keys() if m != current_mode
        ]

    # Helper: reuse estimate_trip_emissions logic
    async def _estimate(mode: str) -> Dict[str, Any]:
        return await estimate_trip_emissions(
            distance_km=distance_km,
            frequency_days_per_week=frequency_days_per_week,
            mode=mode,  # type: ignore[arg-type]
            weeks_per_year=weeks_per_year,
        )

    current_est = await _estimate(current_mode)
    if not current_est.get("ok"):
        return {
            "ok": False,
            "error": f"Unknown current_mode: {current_mode}",
            "known_modes": list(_EMISSION_FACTORS.keys()),
        }

    alt_results = []
    for m in alternatives:
        est = await _estimate(m)
        if est.get("ok"):
            alt_results.append(est)

    current_yearly = float(current_est["yearly_kg_co2"])
    savings = []
    for alt in alt_results:
        alt_yearly = float(alt["yearly_kg_co2"])
        delta = current_yearly - alt_yearly
        savings.append(
            {
                "from_mode": current_mode,
                "to_mode": alt["mode"],
                "delta_yearly_kg_co2": round(delta, 3),
            }
        )

    return {
        "ok": True,
        "distance_km_per_day": distance_km,
        "frequency_days_per_week": frequency_days_per_week,
        "weeks_per_year": weeks_per_year,
        "current": current_est,
        "alternatives": alt_results,
        "savings": savings,
        "note": (
            "All values are approximate demo estimates based on simplified factors. "
            "For real audits, connect this MCP server to an official emissions database."
        ),
    }


# ---------------------------------------------------------------------------
# Expose the Streamable HTTP transport under /mcp
# ---------------------------------------------------------------------------
# This returns a Starlette app that uvicorn can serve directly.
# Fred rationale:
# - Côté agent (EcoAdvisor), on ne voit que 'un serveur MCP avec des tools'.
# - La mécanique FastAPI/Starlette/HTTP est complètement encapsulée ici.
app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "eco_co2_mcp_server.server_mcp:app",
        host="127.0.0.1",
        port=9898,
        reload=False,
    )
