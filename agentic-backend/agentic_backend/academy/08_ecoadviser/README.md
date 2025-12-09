# EcoAdvisor - Mobility & CO2 demo

EcoAdvisor is the Academy showcase for a Fred agent that guides employees through low-carbon commuting options around Lyon. It pairs a lightweight LangGraph flow (`reasoner` <-> tools) with a bundle of local MCP services so the agent can cite real datasets instead of hallucinating factors.

---

## Quick start

1. **Load the demo CSVs** into the Knowledge Flow tabular server (DuckDB). Import the two files from `data/` with the same table names: `bike_infra_demo` and `tcl_stops_demo`.
2. **Launch the stack** with `./start.sh`. The script already runs Agentic Backend, Knowledge Flow, the front-end, and the four MCP FastAPI services (CO2, traffic, TCL, geo).
3. **Pick the "EcoAdvisor" agent** in the UI. The agent inspects the datasets, calls the MCP tools as needed, and outputs a Markdown summary (comparison table, assumptions, low-carbon hints).

---

## What lives in this folder

| Path | Purpose |
| --- | --- |
| `eco_adviser.py` | Main LangGraph agent (`AgentFlow`) + tuning metadata. |
| `co2_estimation_service/` | FastAPI+MCP service exposing ADEME emission factors and helpers such as `compare_trip_modes`. |
| `traffic_service/` | FastAPI+MCP wrapper around the Grand Lyon WFS traffic feed. |
| `tcl_service/` | FastAPI+MCP wrapper around TCL's RDATA realtime endpoint. |
| `geo_distance_service/` | FastAPI+MCP wrapper for Nominatim + OSRM distance estimations. |
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
| `traffic_service` | `9799` | `get_live_traffic_segments` | Calls Grand Lyon WFS (`pvo_patrimoine_voirie.pvotrafic`). Requires either API key or basic auth. |
| `tcl_service` | `9800` | `get_tcl_realtime_passages` | Queries TCL RDATA (`tcl_sytral.tclpassagesarret_2_0_0`). Needs Grand Lyon credentials. |
| `geo_distance_service` | `9801` | `geocode_location`, `compute_trip_distance`, `estimate_trip_between_addresses` | Mix of Nominatim + OSRM with haversine fallback. |

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
- Keep an eye on `MAX_TOOL_MESSAGE_CHARS` and `ECO_RECENT_MESSAGES` (env vars read by `eco_adviser.py`) to avoid oversized tool payloads.  
- When adding new MCP endpoints, extend `ECO_TUNING.mcp_servers` and the global `config/configuration*.yaml` files in sync.

---

## Cleanup log (2024-12)

- Removed stray `__pycache__` folders and unused CSV dumps to shrink the repo footprint.  
- Consolidated documentation in this single README so newcomers only have one entry point.  
- The remaining files are the ones actually exercised by the demo (agent + four services + curated datasets).

Add content sparingly: new docs or datasets should land here only if they are actively used in the demo.
