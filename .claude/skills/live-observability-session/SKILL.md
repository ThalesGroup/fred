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

Retain unfiltered local logs for owned processes and read new lines with cursors.
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
