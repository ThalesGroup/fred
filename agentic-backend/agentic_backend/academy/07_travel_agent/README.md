# 🗺️ Travel Agent – OpenStreetMap Demo

This academy sample shows how to build a **minimal LangGraph agent** that uses **OpenStreetMap / Overpass** to answer travel‑style questions, e.g.:

> “Nice vegetarian restaurants near Bordeaux?”  
> “Museums around Lyon?”  

The goal is to give developers a **small, realistic example** of:

- Using `AgentFlow` + `StateGraph` (`MessagesState` as state)
- Calling external HTTP APIs (`Nominatim`, `Overpass`) from a node
- Encoding simple **natural‑language → OSM tag** logic
- Returning only **delta state** per node to avoid history replay
- Emitting **thought traces** so the UI can show the internal steps

---

## 🧠 Agent Structure

File: `travel_agent.py`

- **State**: `TravelAgentState(MessagesState + city/coords/pois/geo_error)`
- **Nodes pipeline**:
  1. `parse_city_and_category_node` – extract city and derive OSM filters from the user query
  2. `osm_search_node` – geocode the city via Nominatim (`lat`, `lon`)
  3. `fetch_pois_node` – query Overpass for nearby POIs (e.g. restaurants, vegetarian options)
  4. `format_pois_node` – render a short Markdown answer or fall back to LLM if APIs fail

Each node returns a **partial update** (no full state overwrite) and can add a `mk_thought(...)` message so the Fred UI displays step‑by‑step reasoning.

---

## 🌍 External APIs & User‑Agent

The agent calls public OSM services:

- `https://nominatim.openstreetmap.org/search` – city → coordinates
- `https://overpass-api.de/api/interpreter` – coordinates + tags → POIs

To respect OSM policies and avoid 403s, the agent sends a custom `User-Agent`.  
You can override it via environment variable:

```bash
export TRAVEL_AGENT_USER_AGENT="FredTravelAgent/1.0 (https://your-url; contact: you@example.com)"
```

---

## ✅ What This Sample Illustrates

For developers, this academy step is a good starting point to learn how to:

- Wire a **tool‑using agent** without a full tool abstraction (direct HTTP calls)
- Implement **error‑tolerant flows** with a graceful LLM fallback
- Add **UX‑friendly traces** (Thoughts) for debugging and demo purposes
- Adapt the pattern to other domains (hotels, monuments, local services, etc.)

It is intentionally small and opinionated so you can easily copy/paste and adapt it for your own agents.

