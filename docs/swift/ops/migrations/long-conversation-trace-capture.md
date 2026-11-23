---
schema: 1
title: "Retain long conversation trace evidence during execution"
impact: minor
configuration: none
configuration_reason: "The existing runtime bucket, trace consent, retention, and storage quota settings apply to compressed trace blocks."
---

## Applicability

Fred deployments with managed conversation trace capture.

## Prerequisites

Control Plane must be able to apply its PostgreSQL migrations. Fred Agents
must have read, write, and delete access to the configured private trace bucket.

## Configuration

The existing trace settings apply. The default deployment-wide quota is 20 GB
and the default retention period is 30 days. No chart values or bucket
permissions change.

## Upgrade

Disable trace capture and let active captures finish before a mixed-version
rollout. Apply the Control Plane migration through `8a49f3ac2e6b`, deploy the
updated Control Plane, Fred Agents, and frontend, then re-enable capture.
Reload any open trace inspector tabs after rollout. The migration adds
PostgreSQL bookkeeping columns. Fred Agents use compressed
blocks once Control Plane advertises incremental storage at segment admission.
Traces already recorded in the compressed format remain readable.

Payloads in the earlier format become unavailable. The catalog can retain their
summaries until normal retention expires. To remove them from the catalog,
select affected conversations for diagnostic deletion or use
**Delete all captures** in conversation trace settings. Both actions also clear any
compressed captures in the selected scope and revoke its diagnostic grants.
The trace cleanup worker removes the associated objects from the private bucket
asynchronously. Ordinary chat history remains available.

The existing storage quota charges compressed bytes. Payload writes can start
while the chat streams. The catalog publishes protected evidence references
after the execution segment has a saved rank.

## Validation

Capture a long managed turn with a provider stream that fails near the end.
After publishing completes, open its final attempt, page through the HTTP
response and select the last event in the SSE timeline. Verify that withdrawing
consent blocks body and frame reads. With trace object storage unavailable,
verify that chat continues and that the inspector reports incomplete evidence.

## Rollback

Disable trace capture before rolling back the Runtime or Control Plane. The
new Runtime is required to inspect paged trace content captured after the
upgrade. Retain the additive storage ledger migration so upgraded maintenance
can settle or remove compressed trace artifacts when re-enabled.

## Limitations

A saturated background queue, interrupted Runtime, or unavailable artifact
store can leave incomplete trace evidence. Chat continues. The inspector
reports capture loss when known, and the final failed provider bytes receive
priority where capacity permits. Run a managed streaming comparison before
enabling high-volume capture on a shared deployment.
