## Context

See proposal.md for motivation. The branch already carries a Python
implementation (`fred_sdk/knowledge_base/telemetry.py`, commit `d2e5b9aef`)
whose series were never written down as a contract: `KNOWLEDGE-BASE.md` refers
to an *Operational metrics* section that does not exist. This change makes the
contract normative (specs/knowledge-base-pod-metrics/spec.md) and audits the
implementation against it.

Native Fred backends emit KPIs through `fred_core.kpi` (`BaseKPIWriter` with
log, OpenSearch and Prometheus sinks). A Knowledge Base pod never depends on
`fred-core`; its shared floor is `fred-pod` (pydantic, httpx, pyyaml, dotenv).

## Goals / Non-Goals

**Goals:**
- A contract another language can implement from the spec alone.
- No metrics API in the SDK: instrumentation lives in the seams the SDK
  already owns.
- Same configuration keys and label discipline as native backends.

**Non-Goals:**
- Business statistics for Fred's UI (document counts, volumes). The run result
  already carries an opaque `metrics` dict; whether Fred stores and shows it is
  a separate change.
- Per-team or per-instance metrics (Stream 2).
- A Rust SDK. The spec only has to make one possible.

## Decisions

**D1. The contract is the exposition format, not a Fred KPI library.**
OpenMetrics text over HTTP has a mature client in every language and is read
by Prometheus, the OpenTelemetry Collector and managed scrapers alike, so
"Prometheus" stays an implementation choice of the platform, not of the pod.
Alternatives: reuse `fred_core.kpi` (pulls the agents platform into every pod,
Python-only); push OTLP (needs a collector address in every pod's config and an
SDK per language for little gain over a scrape).

**D2. Configuration through `fred-pod`'s `KpiPrometheusSinkConfig`.** Same key
path (`observability.kpi.prometheus`) and same model as every backend, from the
light shared floor. Only the Prometheus half is modelled: a pod writes no KPI
events, so the log and OpenSearch sinks would be read by nobody. Another
language's SDK mirrors the three fields.

**D3. Instrumentation at the SDK's seams.** The run activity wraps context
fetch, library declaration and handler (`observing_run`); every HTTP call to
Fred goes through one measured helper per client (`observing_request`); the
ingestion wait observes its own end. The author's code is never asked to
call anything. Author-specific series use the language's default metrics
registry, which the same endpoint serves.

**D4. One identity label: the definition id.** Mirrors Stream 1's rule that a
configured copy (an instance) is a Stream 2 question. Scrape-time labels
(`job`, `namespace`, `pod`) still identify the replica.

**D5. Loopback by default, enabled by default.** The endpoint exists in every
pod so `kubectl port-forward` always works, but nothing is reachable until the
deployment binds it outward. Consequence: the `PodObservability` docstring
"Nothing listens unless enabled" is wrong and must say "nothing is reachable
from outside unless bound outward".

**D6. Engine metrics on their own port.** The workflow engine's core exports
through its own runtime, not through the language metrics library, so it
cannot share the `/metrics` registry. Tagging it with `knowledge_base` keeps
both joinable.

**D7. Absent metrics library is a no-op.** `prometheus-client` ships in the
`knowledge-base` extra; without it every observation does nothing and a
warning says how to install it. A developer calling the document client from a
script is not broken by metrics.

**D8. `sdk` and `sdk_version` as two labels on `fred_kb_info`.** Today
`sdk_version` is the bare package version (`4.4.2`), ambiguous once a second
implementation numbers its own releases. A separate `sdk` label
(`fred-sdk-python`) filters without a regex and keeps `sdk_version` a plain
version. Alternative rejected: one combined `fred-sdk-python/4.4.2` value,
which every query would have to split.

**D9. The pod's identity is `app.runtime_id`, chosen at deployment.** Agent
pods already identify themselves this way (`fred_runtime.app.config`): a
required slug, used as the `service` KPI label and as the `service` field of
every log record, as OBSERVABILITY-AND-AUDIT.md §3 requires. A Knowledge Base
pod takes the same key, the same pattern and the same meaning, so one
`service="…"` filter works for every kind of component. The pattern and the
small `app` model move to `fred-pod`, the floor both pod kinds share;
`fred-runtime` reuses them unchanged in behaviour. The definition id stays a
separate `knowledge_base` label: it is the *what* (fixed by the author in
code, like an agent type), `runtime_id` is the *which deployment* (fixed by
whoever deploys). Alternatives rejected: deriving the slug from the definition
id (hard-coded in the image, so two deployments of one image cannot be told
apart); the Kubernetes pod name (changes on every rollout, invisible outside
the cluster).

**D10. Logs are JSON lines on standard output.** A Knowledge Base pod has no
log store, so stdout is the only log channel; cluster log pipelines (Cloud
Logging and its sovereign equivalents) parse JSON lines into fields, which is
what makes `service` filterable. Field names follow `fred_core`'s
`CompactJsonFormatter` (`ts`, `level`, `logger`, `msg`, `service`) so one
query reads both; the formatter is re-implemented in the SDK in a few lines
rather than imported from `fred-core`. `observability.logs.format: text`
keeps local work readable. Records emitted while the configuration loads are
held and replayed once the pod knows its `runtime_id`, so the stream is JSON
from its first line; if loading fails they are written as text on stderr, so
the reason is never lost. Note, out of scope: native backends' console output
is text without `service` — only their store handler writes it — a divergence
for a separate change.

**D11. Reconciliation is three-valued in the result itself.** A boolean
`reconciliation_complete` could not say "nothing to do": an incremental source
whose revision did not move had to answer `False`, so a perfectly synchronized
Knowledge Base read as one doing partial passes on most runs. The result now
carries `reconciliation: complete | partial | up_to_date`, and the metric label
reports it as is. **BREAKING** for Knowledge Base code (the field is renamed);
Fred's applications never read it — only the run outcome reaches the workflow.
Alternative rejected: keeping the boolean and adding an `up_to_date` flag, two
fields whose combinations would need rules an enum makes impossible.

## Risks / Trade-offs

- [The spec and the Python code drift] → a contract test asserts every series
  name, label set and closed value set from the spec against a live registry.
- [An author's own series carry team or instance labels] → the spec forbids it
  but cannot enforce it outside the SDK; the authoring guide says so plainly.
- [`exception_type` is open-ended] → bounded in practice by the code's own
  exception classes; acceptable, and the message is never a label.
- [Throughput is read at run end] → `fred_kb_items_total` moves only when a run
  reports. Real-time document throughput is
  `rate(fred_kb_requests_total{operation="publish",target="knowledge_flow"})`
  and `rate(fred_kb_ingestion_wait_seconds_count)` by `state`; the guide gives
  these queries.
- [Two pods on one host] → distinct ports per pod; documented in the migration
  note.
- [**BREAKING** for existing Knowledge Base configurations: `app.runtime_id`
  is required, so a pod rebuilt on this SDK with an unchanged configuration
  refuses to start] → the error names the key; the migration note and every
  sample (`webdav-knowledge-base`, `fred-samples/knowledge-bases`) set it.
  Making it optional with a derived default was rejected: a wrong identity that
  starts silently is the exact mistake this change exists to prevent.
- [JSON logs are harder to read locally] → `observability.logs.format: text`.

## Migration Plan

Covered by `docs/swift/ops/migrations/knowledge-base-pod-metrics.md`: set
`app.runtime_id` in the pod configuration (chart values), rebuild the image on
`fred-sdk[knowledge-base]>=4.4.2`, bind the endpoints outward, expose the
ports and add a scrape target. No Fred redeployment. Rollback: redeploy the
previous image; the extra configuration keys are ignored by older SDKs.
