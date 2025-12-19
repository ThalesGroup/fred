# EcoAdvisor - Mobility & CO₂ Demo

EcoAdvisor is the Academy showcase that walks a Fred agent through low-carbon commute ideas around Lyon.

Before you start, make sure you are on the branch `826-create-eco-adviser-academy-agent`.

## Repository Overview
| Path | Purpose |
| --- | --- |
| `eco_adviser.py` | LangGraph agent + tuning metadata. |
| `geo_distance_service/` | FastAPI MCP for Nominatim/OSRM distance estimates with a haversine fallback. |
| `tcl_transit_service/` | FastAPI MCP for SYTRAL/TCL stops location, with CSV fallback for offline demos. |
| `data/` | Curated CSVs (bike infra, TCL stops, ADEME CO₂ factors, etc.) ready to import via the UI. |

## External API Calls
| Service | Default endpoint | Why EcoAdvisor calls it | Configuration & fallback |
| --- | --- | --- | --- |
| Nominatim (OpenStreetMap) | `https://nominatim.openstreetmap.org/search` | `geo_distance_service` geocodes the origin/destination text entered in the UI before running CO₂ math. | Override with `ECO_GEO_NOMINATIM_URL`, set `ECO_GEO_USER_AGENT`, and throttle via `ECO_GEO_ATTEMPT_DELAY`/cache settings. If disabled (`ECO_GEO_GEOCODING_ENABLED=false`), the service returns an error and the demo cannot resolve addresses. |
| OSRM public router | `https://router.project-osrm.org/route/v1/{profile}/{lon},{lat};{lon},{lat}` | Provides precise distance/duration for car/bike/walk profiles. | Override with `ECO_GEO_OSRM_URL`. If routing is disabled (`ECO_GEO_ROUTING_ENABLED=false`) or the endpoint fails, EcoAdvisor falls back to a haversine estimate and flags the response as approximate. |
| Grand Lyon SYTRAL WFS | `https://data.grandlyon.com/geoserver/sytral/ows` (`sytral:tcl_sytral.tclarret`) | `tcl_transit_service` refreshes stop metadata (lines, coordinates, zones) so the agent can surface nearby transit options. | All request details are driven by the `TCL_WFS_*` env vars (URL, credentials, pagination). If the feed is unreachable, the service automatically reloads the local CSV `data/tcl_stops_demo.csv`. |

## Demo Setup
1. Create and fill `agentic-backend/config/.env`.
2. Launch each service with its Makefile:
   - Agentic Backend API: `cd agentic-backend && make run`
   - Knowledge Flow tabular backend: `cd knowledge-flow-backend && make run`
   - Agentic UI: `cd frontend && make run`
   - EcoAdvisor MCP micro-services: `cd agentic-backend/agentic_backend/academy/08_eco_advisor && make run`
3. In **Fred UI (http://localhost:5173) → Ressources**, import every files from `agentic_backend/academy/08_eco_advisor/data`.
4. In **Fred UI (http://localhost:5173) → MCP servers** register the MCP:
   | Alias in UI | URL |
   | --- | --- |
   | `mcp-geo-service` | `http://localhost:9801/mcp` |
   | `mcp-tcl-service` | `http://localhost:9802/mcp` |

## Demo Questions
In **Fred UI (http://localhost:5173) → Chat** pick the **Eco** agent and ask the following questions:
   1. Quel est le bilan carbone (en kg CO₂) de mon trajet quotidien entre les locaux de la CNR 2 rue André Bonin, Lyon et mon domicile au 44 boulevard marius vivier merle, Lyon en voiture essence ?
   2. Pour ce même trajet, quelle serait la différence d’émissions CO₂ si je prenais :
      - Les transports en commun (métro D + bus C7) ?
      - Un vélo personnel ou un Vélov’ (location) ?
      - Une trottinette électrique en free-floating (ex : Lime) ?
   3. Montres moi les arrêts de transport en commun les plus proche de chez moi.
   4. Quelles bonnes pratiques sont proposées pour les trajets domicile‑école des enfants ?
   5. Quels sont les dispositifs d’aides financières (ex : prime à la conversion, forfait mobilité durable) auxquels je pourrais prétendre à Lyon ?
