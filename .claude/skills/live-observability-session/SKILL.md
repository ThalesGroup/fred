---
name: live-observability-session
description: Observe Fred logs, audit events and metrics while the developer reproduces a local scenario. Use for an explicitly requested live observability session; ordinary development does not start services or a campaign.
---

# Live observability session

Read the active checkout's `AGENTS.md`, current component READMEs and the relevant
arc42 operations references. Establish the developer's scenario, environment and
expected evidence. Do not assume a Swift stack, fixed ports, a Python Control
Plane, OpenFGA or the presence/absence of a central Prometheus.

Use the repository `fred` skill for requested startup, process ownership, logs
and shutdown. Existing authorization applies to its stated scope. Observe running
services when startup is unnecessary. Infrastructure remains developer-managed;
do not start, reset or reconfigure it implicitly. Never replace an unknown process
because its port is occupied.

The developer drives the UI. Do not invoke business actions or mutate data to
manufacture evidence unless explicitly requested. Inspect actual configuration
and source emitters to locate the signals needed for this scenario:

- stdout/stderr and structured audit events, including their actual routing;
- application metrics, exporter endpoints and any configured Prometheus targets;
- configured log/search sinks and dashboard queries, when relevant.

## Quality review during every session

Challenge the signals as well as application behavior, using observed events and
targeted source inspection. Report concrete defects without launching a separate
audit or changing code outside the agreed scope. Use the current
[logging contract](../../../docs/architecture/A3-manager-operations.md#logging)
as evidence, not as proof that emitted logs meet these requirements:

- INFO must be concise and useful for operating Fred: meaningful lifecycle,
  outcomes and bounded diagnostic context. Flag repetitive polling/health success,
  duplicate access logs, configuration dumps and per-item/token chatter. Check
  disabled-log formatting, payload serialization and synchronous I/O on hot paths
  when implicated; do not claim a measured performance cost without measurements.
  Keep required security audit events; do not globally raise severity to hide noise.
- No secrets or personal data in emitted application/dependency logs, audit
  payloads or metric labels. Check free text and exception chains, not only field
  names: credentials, headers/cookies, signed URLs, prompts, responses, document
  contents, filenames and paths can disclose sensitive information. Sanitizing a
  chat excerpt does not fix disclosure at the emitter or in the collected index.
  Flag a leak immediately without reproducing its value. Opaque person IDs are
  pseudonymous, not anonymous; flag conflicts between existing audit identity
  fields and the confidentiality requirement instead of silently removing audits.
- Events must identify the service/role, time, severity, operation, outcome and
  necessary non-sensitive correlation IDs consistently across Rust and Python.
  Flag missing terminal outcomes, misleading severity and unstructured/multiline
  output that breaks collection. Never add payloads merely to improve correlation.
- Review available KPI semantics, units, labels, cardinality, duplication and
  collection cost. Distinguish an unwired Weaver metric from a measured zero or a
  broken collector. Swift KPI parity is not assumed; report the scenario's missing
  evidence without restoring retired metrics or starting a benchmark campaign.

## Verify the collection path

For a Fluent Bit -> OpenSearch deployment, verify the actual input (container
stdout or mounted host files), parser, metadata, output/index and recent arrival
of this session's events. Observe collected logs through bounded queries when
available, and compare local output to distinguish an emitter defect from lost,
duplicated, delayed or misparsed events. Do not assume that a Compose collector
exists because k3d has one, that `make run` logs are mounted into it, or that a KPI
index contains application logs. Report an absent or unverified collection path
and explicitly identify local-file observation as the fallback. This verification
does not authorize infrastructure changes or artificial business events.

Retain unfiltered local logs for owned processes and read new lines with cursors.
Keep raw captures private; never attach a raw log containing sensitive values.
Use a streaming monitor only if the current tool supports one; otherwise poll
bounded batches during active turns and on developer signals. Do not claim
continuous observation when inactive. Query only the required time window and
aggregation, with bounded result sizes. Keep tokens, credentials, personal data
and document contents out of messages and shared artifacts.

Correlate timestamps and existing request/task/run identifiers across relevant
components. Distinguish an absent event from an unavailable exporter, failed scrape,
wrong label, wrong time window or a path the developer did not execute. A healthy
HTTP response does not prove the metric, audit event or authorization behavior.
Likewise a synthetic observation does not prove production capacity.

Report observed facts, missing evidence, plausible explanation and the next
bounded check. Use current component behavior as evidence; do not turn historical
metric names into requirements. Code/configuration fixes, independent reviews,
tests and load campaigns require that work to be in the authorized scope.
Finish with the observed result, evidence limits and which owned processes remain
running; stop only those covered by a shutdown request.
