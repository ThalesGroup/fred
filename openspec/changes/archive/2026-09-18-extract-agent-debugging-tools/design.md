# Design

## Context

See proposal.md. The POC helper used custom delegation and printed arbitrary tool data.
The shared skills directory already serves both assistant integrations.

## Goals / Non-Goals

Capture managed execution evidence without changing runtime behavior or implementing a
new trace backend. Native child visibility depends on the running runtime and exporter.

## Decisions

Reuse `fred_core.cli.auth` and `AgentPodClient`. Preserve decoded SSE event payloads in
private files; print identifiers/counts only. The final event is authoritative; deltas
remain evidence and are never silently substituted for a missing final answer.
Use observed call IDs and trace parent IDs for attribution, not arrival-time heuristics.

## Risks / Trade-offs

- Event payloads can contain user or tool secrets → private output directory, redact known
  authentication secrets before writing, and review content before sharing.
- SSE omits some native child activity → report observed calls only; consult configured tracing.
- Live tests incur model spend → one short harmless turn against an authorized existing instance.
