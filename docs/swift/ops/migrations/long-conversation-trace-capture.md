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

Apply the Control Plane migration through `8a49f3ac2e6b`, then deploy the
updated Control Plane, Fred Agents, and frontend. The Runtime negotiates
incremental storage with Control Plane at segment admission. Existing traces
remain readable after the upgrade. Capture needs no additional bucket privileges.

The existing storage quota charges compressed bytes. Payload writes can start
while the chat streams. The catalog publishes protected evidence references
after the execution segment has a saved rank.

## Validation

Capture a long managed turn with a provider stream that fails near the end.
After publishing completes, open its final attempt, page through the HTTP
response and inspect the last SSE page. Verify that withdrawing consent blocks
body and frame reads. With trace object storage unavailable, verify that chat
continues and that the inspector reports incomplete evidence.

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
