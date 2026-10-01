# Proposal

## Why

Operators cannot reliably follow one chat exchange or document upload across Fred API and worker logs. Implement the agreed local structured logging specification (`docs/design/STRUCTURED-LOGGING-SPEC.md`, retained locally) through five sequential delivery slices, tracked by [issue #2906](https://github.com/ThalesGroup/fred/issues/2906).

## What Changes

- Standard-library events use shared structlog processing, explicit JSON/readable output selection, cloud-compatible severity/time, and the existing optional generic-store representation.
- Each HTTP request receives local identity, one stream-aware completion event, and scoped authenticated/journey context; successful probes are suppressed while failures remain visible.
- Safe context crosses first-party REST/MCP calls only through existing delegated credentials and successful receiver admission, with bounded encoding and protected local fields.
- Trusted ingestion submissions carry optional durable context into worker activities and retries; older queued jobs continue to execute.
- Frontend-pod nginx access output becomes escaped JSON; document native error/startup parsing limits.
- Intentionally replace the existing neutral-access restriction with admitted metadata-only diagnostic context. Preserve audit isolation, metrics label restrictions, sanitized exception diagnostics, and delegation defaults.

## Capabilities

### New Capabilities

- `structured-logging`: shared output, scoped diagnostic context, trusted propagation, worker handoff, and nginx access output as one coherent observability capability.

### Modified Capabilities

None of the shipped capability specs cover generic logging. The active `add-delegated-agent-execution` change contains the neutral-access restriction; reconcile that requirement and its scenarios in slice 2 rather than creating a second authentication capability or changing grant admission.

## Impact

- `libs/fred-core/fred_core/logs`, shared security admission and scheduler seams; `libs/fred-pod` configuration ownership.
- `libs/fred-runtime` ingress, run/tool orchestration, existing SDK traceability binding, delegated REST/MCP adapters and hosted runtime setup.
- Control Plane and Knowledge Flow API startup, conversation/attachment/upload orchestration, existing worker entrypoints and ingestion scheduling/activity boundaries.
- Local examples, `deploy/charts/fred/values.yaml` and generated schemas, frontend container nginx configuration, operator migration notes, observability and runtime contracts.
- Add structlog through existing uv projects/locks. No collector SDK, infrastructure service, deployment, frontend product feature, authorization redesign, or content capture.
- Output fields and HTTP diagnostic headers are additive; reference deployments explicitly select JSON, while omitted format settings retain local readable defaults. Existing stdout parsers need the documented migration.
