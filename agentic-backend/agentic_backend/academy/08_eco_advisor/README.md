# EcoAdvisor - Mobility & CO2 demo

EcoAdvisor is the Academy showcase that walks a Fred agent through low-carbon commute ideas around Lyon. The flow is intentionally lean: LangGraph (`reasoner ↔ tools`) plus two local MCP micro-services so the agent can cite real datasets instead of inventing numbers.

## Demo flow
1. Import the demo CSVs from `data/` into the Knowledge Flow tabular server: `bike_infra_demo`, `tcl_stops_demo`, plus `co2_emission_factors` (seeded from `data/Base_Carbone_V23.6.csv` or your trimmed ADEME export). The UI now owns CO₂ factors, no extra MCP service required. Upload any PDF resources you want the agent to cite (ADEME guides, Plan de Mobilité, subsidies, …) through **Knowledge → Documents** and drop them in a document library you will select for the chat session.
2. Launch each service with its Makefile (separate terminals recommended):
   - Agentic Backend API: `cd agentic-backend && make run`
   - Knowledge Flow tabular backend: `cd knowledge-flow-backend && make run`
   - Agentic UI: `cd frontend && make run`
   - EcoAdvisor MCP micro-services: `cd agentic-backend/agentic_backend/academy/08_eco_advisor && make run`
3. In the Agentic UI, go to **Tools → MCP servers → Add server** and register the remaining local services (configs no longer autoload them):
   | Alias in UI | URL |
   | --- | --- |
   | `mcp-geo-service` | `http://localhost:9801/mcp` |
   | `mcp-tcl-service` | `http://localhost:9802/mcp` |
   | `mcp-knowledge-flow-mcp-text` | `http://localhost:8111/knowledge-flow/v1/mcp-text` |
4. Pick the **EcoAdvisor** agent, point it at a commute scenario, and let it call the MCP tools plus the tabular datasets. The agent responds with a Markdown brief (comparison table + CO₂ totals + assumptions).

## Repo tour
| Path | Purpose |
| --- | --- |
| `eco_adviser.py` | LangGraph agent + tuning metadata. |
| `geo_distance_service/` | FastAPI MCP for Nominatim/OSRM distance estimates with a haversine fallback. |
| `tcl_transit_service/` | FastAPI MCP for SYTRAL/TCL stops, with CSV fallback for offline demos. |
| `data/` | Curated CSVs (bike infra, TCL stops, ADEME CO₂ factors, etc.) ready to import via the UI. |

Old side documents (`TECH_DOC.md`, `ROADMAP.md`, …) were merged into this single README so every required instruction lives here.

## Demo datasets
- `data/bike_infra_demo.csv` – curated slice of the Lyon cycling infrastructure feed.
- `data/tcl_stops_demo.csv` – readable subset of TCL stops.
- `data/Base_Carbone_V23.6.csv` – ADEME emission factors: import it (or a trimmed version) as the `co2_emission_factors` table inside Knowledge Flow so EcoAdvisor can query it like any other dataset.

Need more context (energy mix, historic traffic, etc.)? Pull it from https://data.grandlyon.com or https://transport.data.gouv.fr directly—the repo purposely stays light.

## PDF resources
1. Upload the PDF playbooks you need (regulation summaries, company plans, subsidy sheets, etc.) in the Knowledge Flow UI and assign them to one or more document libraries.
2. Register the `mcp-knowledge-flow-mcp-text` server in the UI (see table above) so EcoAdvisor can hit the vector search MCP.
3. In the chat sidebar, select the document library you created. EcoAdvisor will now pull short snippets from those PDFs, cite the document title/page, and surface them alongside the tabular CO₂ comparisons.

## Local MCP services
| Service | Port | Key tools | Notes |
| --- | --- | --- | --- |
| `geo_distance_service` | `9801` | `geocode_location`, `compute_trip_distance`, `estimate_trip_between_addresses` | Wraps Nominatim + OSRM; falls back to simple haversine math offline. |
| `tcl_transit_service` | `9802` | `search_tcl_stops`, `find_nearby_tcl_stops`, `list_tcl_lines`, `get_tcl_metadata`, `reload_tcl_stops_cache` | Pulls SYTRAL/TCL WFS with a CSV fallback (`data/tcl_stops_demo.csv`). |

CO₂ computation is now fully tabular: load the emission CSV into Knowledge Flow and EcoAdvisor will query it through `mcp-knowledge-flow-mcp-tabular`. Because the UI owns MCP registration, `config/configuration*.yaml` only contains global defaults (no ECO-specific entries). If you run another instance, repeat the UI step above.

## How the agent reasons
- Minimal LangGraph state (`messages`, `database_context`).
- Loop pattern: `reasoner → tools → reasoner` until `tools_condition` says no more calls.
- System prompt automatically lists the DuckDB tables returned by the tabular MCP `get_context` call.
- Output: Markdown recap with a comparison table, total weekly CO₂, explicit assumptions, and tangible equivalents (vacuum hours, heating days, …).
