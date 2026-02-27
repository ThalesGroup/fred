# Fred Academy

`fred-academy` is a developer playground for demos, experiments, and example integrations around Fred.

Read this first:

- `fred-academy/DISCLAIMER.md`

## What belongs here

- Demo use-cases and presenter material
- Example MCP servers (Python samples)
- Exploration labs and sample documents
- Integration notes that point to runtime code living elsewhere in the repo

## What does not belong here

- Production guarantees / stable APIs
- Long-term supported components without explicit promotion

## Folder Layout

- `fred-academy/use-cases/`: runnable demo scenarios (what to play)
- `fred-academy/servers/`: reusable demo backend components (what powers demos)
- `fred-academy/labs/`: exploratory material and exercises

## Demo Script Pattern (copy/paste friendly)

For every runnable demo, the human-friendly script should be here:

`fred-academy/use-cases/<domain>/demos/<demo-name>/RUN_DEMO.md`

Machine-readable or structured specifications can live next to it (YAML/JSON), but `RUN_DEMO.md` is the entrypoint during a live demo.

## Current Entry Points

- Postal demo playbook: `fred-academy/use-cases/postal/demos/parcel-ops/RUN_DEMO.md`
- Postal demo spec (YAML): `fred-academy/use-cases/postal/demos/parcel-ops/LAPOSTE_PARCEL_OPS_DEMO_SCRIPT_V2.yaml`
- Postal use-case overview: `fred-academy/use-cases/postal/README.md`
- Agile use-case: `fred-academy/use-cases/agility/README.md`
- IoT use-case: `fred-academy/use-cases/iot/README.md`

## Important Note (runtime agent location)

Some demos use runtime agents that intentionally stay in product code paths for now.

Example: the LaPoste tracking agent remains in:

`agentic-backend/agentic_backend/agents/postal/tracking.py`

The academy documents how to use it, but does not move product runtime code.
