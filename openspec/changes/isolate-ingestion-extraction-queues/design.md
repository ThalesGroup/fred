## Context
The [ingestion architecture](../../../docs/swift/design/INGESTION.md) is the single design reference.

## Goals / Non-Goals
Isolate resource-heavy extraction while preserving the existing stages and shared storage.
No page-level orchestration, new distributed fencing protocol, or in-flight migration support.

## Decisions
See the architecture for routing, admission, process supervision, local/Kubernetes modes and performance diagnosis.
Keep behavioral acceptance in [spec.md](specs/ingestion-extraction-routing/spec.md), outstanding work in [tasks.md](tasks.md).

## Risks / Trade-offs
The architecture's “Robustness and current limits” section records unresolved cleanup, retry and instrumentation risks.
Resource settings remain provisional; the normal-path local test is not a production resilience test.

## Migration Plan
Drain ingestion; deploy API and workers with matching queues and shared stores and consumers for all roles.
