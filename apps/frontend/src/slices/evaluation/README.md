# Evaluation API client — generated, cross-repo

`evaluationOpenApi.ts` is **generated code — do not hand-edit it.** It is the typed
RTK Query client for the evaluation backend.

## ⚠️ Cross-repo provenance (read this)

Unlike the control-plane / knowledge-flow slices — generated from **first-party**
backends in this platform — this slice is generated from **`fred-agent-evaluator`**,
a **separate repository** that lives under `ignored/` and deploys independently
(see [RFC EVAL-02](../../../../../docs/swift/rfc/AGENT-EVALUATION-TASK-EVENT-AMENDMENT-RFC.md)).

The evaluator's OpenAPI is the source of truth. We **vendor a snapshot** of it here as
[`openapi.json`](./openapi.json) and generate the client from that snapshot.

Vendoring is deliberate and the safer choice: generation is reproducible from a pinned
file, and any API change appears as a reviewable `openapi.json` diff in the PR (never
codegen against a live or external path). **But the source of truth is external**, so:

> **Drift risk.** Nothing in this repo's CI verifies that `openapi.json` matches the
> _deployed_ evaluator. If the evaluator API changes and this snapshot is not refreshed,
> the typed client silently goes stale. Refresh on every evaluator API change.

**Ownership:** the evaluator API is owned by the `fred-agent-evaluator` maintainers;
refreshing this snapshot + regenerating is the frontend's responsibility.

**Generated against:** `fred-agent-evaluator` on fred-core 3.2.0 — 2026-06-25.

## Regenerate

1. Produce the evaluator's OpenAPI (the repo's `make generate-openapi` target is
   currently broken — missing `scripts/generate_openapi.py` — so use the inline form):

   ```bash
   cd ignored/fred-agent-evaluator/apps/fred-evaluation-backend
   CONFIG_FILE=./config/configuration.yaml uv run python -c \
     "import json; from fred_evaluation_backend.main import create_app; \
      json.dump(create_app().openapi(), open('openapi.json','w'), indent=2)"
   ```

2. Vendor the snapshot here and regenerate the client:

   ```bash
   cp ignored/fred-agent-evaluator/apps/fred-evaluation-backend/openapi.json \
      apps/frontend/src/slices/evaluation/openapi.json
   cd apps/frontend/src/slices/evaluation
   npx @rtk-query/codegen-openapi evaluationOpenApiConfig.json
   ```

3. Review the `openapi.json` **and** `evaluationOpenApi.ts` diffs, then run
   `make code-quality`.

## Hardening (follow-up, tracked under EVAL-02)

A CI check should assert this vendored `openapi.json` equals the evaluator's published
OpenAPI for the pinned evaluator/fred-core version — turning silent drift into a failing
build. Until then, drift is caught only by manual refresh + PR review.
