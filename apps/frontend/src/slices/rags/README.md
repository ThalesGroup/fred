# rags-services API — RTK Query

RTK Query configuration for `rags-services` (Information Systems CRUD), a
standalone FastAPI+MCP backend that lives in the sibling `fred-rags` repo
(`~/Fred/fred-rags/apps/rags-services`), not in this monorepo (#2307).

## Files

- **ragsApi.ts** — base API configuration with tag types
- **ragsOpenApi.ts** — auto-generated endpoints from the OpenAPI spec (DO NOT EDIT MANUALLY)
- **openapi.json** — local snapshot copied from `rags-services` at generation time (gitignored)

## Regenerating

`rags-services` is out-of-repo, so `make update-rags-api` (from `apps/frontend`)
first runs `make generate-openapi` in the sibling checkout, copies the
resulting `openapi.json` into this directory as a snapshot, then generates the
RTK Query hooks from that local copy — same codegen mechanism as every other
backend, just sourced across the repo boundary:

```bash
make update-rags-api  # from apps/frontend
```

The sibling checkout path defaults to `~/Fred/fred-rags/apps/rags-services`;
override with `RAGS_SERVICES_DIR=/path/to/rags-services make update-rags-api`
if your checkout lives elsewhere.

**⚠️ Never edit `ragsOpenApi.ts` manually** — your changes will be overwritten
on next generation.
