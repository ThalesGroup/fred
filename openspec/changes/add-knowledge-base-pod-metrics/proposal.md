## Why

A Knowledge Base pod is opaque to Fred: it may pull documents from an outside
source, or embed its own retrieval stack and expose it through capabilities.
Either way it runs in production next to Fred's own components and must be
operable like them — error rates, throughput and latencies visible in the same
Grafana, under the same rules about what a metric may carry. Today the series a
pod exports exist only as Python code in the SDK, so no other implementation
(a future Rust SDK, a hand-written pod) can honour them, and no dashboard or
alert can rely on them.

## What Changes

- Define a **language-neutral metrics contract** for Knowledge Base pods: the
  exposition endpoint, its configuration keys, every series name, its labels and
  their closed value sets, and what is structurally excluded from labels.
- The contract is the **OpenMetrics text exposition** over HTTP. Prometheus is
  one consumer; any scraper (OpenTelemetry Collector, Managed Prometheus) reads
  the same endpoint. No Fred KPI library is required to honour it.
- Every series is produced by the SDK's own seams — the run activity and the
  clients that call Fred — so an author who writes only a handler is measured
  completely, with **zero metrics API** in the SDK.
- An author MAY add domain series of their own on the same endpoint, with the
  implementation language's ordinary metrics library.
- The Python SDK (`fred-sdk[knowledge-base]` 4.4.3)
  becomes the reference implementation, checked against the contract.
- Pod configuration keys reuse `fred-pod`'s `observability.kpi.prometheus`, the
  path every Fred backend reads; the workflow engine's own exporter sits under
  `observability.temporal.prometheus`.
- **BREAKING** (Knowledge Base pod configurations only): a pod identifies
  itself with the required `app.runtime_id`, chosen at deployment exactly as
  agent pods do. It is the `service` label of every series and the `service`
  field of every log record, so metrics and logs join on one value for every
  kind of component.
- Knowledge Base pods write **JSON log lines** on standard output, with the
  same field names as Fred's own structured logs.

Out of scope: per-team or per-instance follow-up inside Fred (Stream 2), and
business statistics shown in Fred's UI (document counts, data volume). Those
are a separate change and SHALL NOT add to the SDK's surface.

## Capabilities

### New Capabilities
- `knowledge-base-pod-metrics`: the operational metrics a Knowledge Base pod
  exposes — endpoint, configuration, series, labels, exclusions and stability.

### Modified Capabilities
<!-- none -->

## Impact

- `libs/fred-sdk/fred_sdk/knowledge_base/` — `telemetry.py`, and the seams that
  call it (`worker.py`, `documents.py`, `client.py`, `configuration.py`).
- `libs/fred-pod` gains the shared `app.runtime_id` model and pattern;
  `libs/fred-runtime` reuses them with no behaviour change.
- `libs/fred-sdk` gains the optional `prometheus-client` dependency in the
  `knowledge-base` extra; dependent lockfiles pick up the 4.4.3 patch version.
- Docs: `docs/swift/design/KNOWLEDGE-BASE.md` (its dangling *Operational
  metrics* reference), `docs/swift/ops/migrations/knowledge-base-pod-metrics.md`.
- Fred's own applications, chart and schemas are unchanged. Knowledge Base
  images expose the endpoints once rebuilt and bound outward by their own chart.
