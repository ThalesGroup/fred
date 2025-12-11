# EcoAdvisor - Mobility & CO2 demo

EcoAdvisor is the Academy showcase for a Fred agent that guides employees through low-carbon commuting options around Lyon. It pairs a lightweight LangGraph flow (`reasoner` <-> tools) with a bundle of local MCP services so the agent can cite real datasets instead of hallucinating factors.

---

## Quick start

1. **Load the demo CSVs** into the Knowledge Flow tabular server (DuckDB). Import the two files from `data/` with the same table names: `bike_infra_demo` and `tcl_stops_demo`.
2. **Launch the stack** with `./start.sh`. The script already runs Agentic Backend, Knowledge Flow, the front-end, and the three MCP FastAPI services (CO2, geo, TCL).
3. **Pick the "EcoAdvisor" agent** in the UI. The agent inspects the datasets, calls the MCP tools as needed, and outputs a Markdown summary (comparison table, assumptions, low-carbon hints).

---

## What lives in this folder

| Path | Purpose |
| --- | --- |
| `eco_adviser.py` | Main LangGraph agent (`AgentFlow`) + tuning metadata. |
| `co2_estimation_service/` | FastAPI+MCP service exposing ADEME emission factors and helpers such as `compare_trip_modes`. |
| `geo_distance_service/` | FastAPI+MCP wrapper for Nominatim + OSRM distance estimations. |
| `tcl_transit_service/` | FastAPI+MCP wrapper for the Grand Lyon SYTRAL WFS, with a CSV fallback for offline demos. |
| `data/` | Two cleaned CSV extracts that can be imported into DuckDB for the demo. |
| `reference_api/` | Default JSON payload for the CO2 service fallback (`CO2_REFERENCE_DATA`). |

The previous sprawl of auxiliary docs (`TECH_DOC.md`, `ROADMAP.md`) and bulky CSVs has been folded back into this README to keep the directory self-contained.

---

## Datasets

Only the two curated tables needed for the demo are versioned:

- `data/bike_infra_demo.csv` - handcrafted slice of the Lyon cycling infrastructure feed.  
- `data/tcl_stops_demo.csv` - subset of TCL stops with readable names.

If you need complementary material (energy consumption per parcel, historic travel times, ...), fetch the authoritative files directly from:

- https://data.grandlyon.com  
- https://transport.data.gouv.fr

This keeps the repository small while still documenting where the extra data lives.

---

## Local MCP services

| Service | Port | Tool operations | Notes |
| --- | --- | --- | --- |
| `co2_estimation_service` | `9798` | `list_emission_modes`, `get_emission_factor`, `compare_trip_modes`, `reload_emission_cache` | Pulls ADEME Base Carbone factors (with fallback JSON + `DEFAULT_EMISSION_FACTORS`). |
| `geo_distance_service` | `9801` | `geocode_location`, `compute_trip_distance`, `estimate_trip_between_addresses` | Mix of Nominatim + OSRM with haversine fallback. |
| `tcl_transit_service` | `9802` | `search_tcl_stops`, `find_nearby_tcl_stops`, `list_tcl_lines`, `get_tcl_metadata`, `reload_tcl_stops_cache` | Queries the SYTRAL/TCL stop feed (Grand Lyon WFS) with CSV fallback when offline. |

Update the corresponding environment variables (see `.env` or `start.sh`) to wire in your credentials. Each service is exported as an MCP server in `config/configuration*.yaml`.

---

## Agent behavior in a nutshell

- **State**: minimal LangGraph state with `messages` and `database_context`.  
- **Loop**: `reasoner -> tools -> reasoner` until `tools_condition` indicates the LLM is done with tool calls.  
- **Prompt**: the system prompt is tunable; it is automatically enriched with the list of tables returned by the tabular MCP (`get_context`).  
- **Output**: Markdown summary with a comparison table, weekly CO2 totals, explicit assumptions, plus everyday equivalents (vacuum hours, heating days).

---

## Maintenance tips

- `reference_api/co2_reference_dataset.json` acts as the default payload for `CO2_REFERENCE_DATA`. Override the env var if you want to inject another JSON file or HTTP endpoint.  
- Optional ADEME live fetch can be toggled with `ADEME_BASECARBONE_ENABLED=false` if your environment forbids outbound HTTP.  
- The TCL transit MCP honors `TCL_WFS_BASE_URL`, `TCL_WFS_TYPENAME`, `TCL_WFS_SRSNAME`, `TCL_WFS_PAGE_SIZE`, `TCL_WFS_MAX_FEATURES`, and `TCL_STOPS_CACHE_TTL_SEC` to adapt to custom datasets; it automatically falls back to `data/tcl_stops_demo.csv` when the WFS cannot be reached.  
- Keep an eye on `MAX_TOOL_MESSAGE_CHARS` and `ECO_RECENT_MESSAGES` (env vars read by `eco_adviser.py`) to avoid oversized tool payloads.  
- When adding new MCP endpoints, extend `ECO_TUNING.mcp_servers` and the global `config/configuration*.yaml` files in sync.

---

## Cleanup log (2024-12)

- Removed stray `__pycache__` folders and unused CSV dumps to shrink the repo footprint.  
- Consolidated documentation in this single README so newcomers only have one entry point.  
- The remaining files are the ones actually exercised by the demo (agent + two services + curated datasets).

Add content sparingly: new docs or datasets should land here only if they are actively used in the demo.
