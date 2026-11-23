# Migration guide - v3.15.0

Upgrade from: `code/v3.14.0`
Operational impact: **minor** (minimum version: `3.15.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Render tabular query results as native chat charts

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.15.0/docs/swift/ops/migrations/3592-native-chat-charts.md)

Existing conversations and agent configurations remain valid; normal agent-pod and frontend deployment supplies the tool and renderer.

See the source note for applicability, validation and rollback.

## Reduce the advanced home greeting logo

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.15.0/docs/swift/ops/migrations/advanced-home-logo-size.md)

The CSS update takes effect with a normal frontend deployment; data and APIs are unchanged.

See the source note for applicability, validation and rollback.

## Keep Deep child deliverables with the parent

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.15.0/docs/swift/ops/migrations/deep-child-parent-deliverables.md)

Existing data and APIs are unchanged; the child tool filtering and evidence aggregation take effect on normal deployment.

See the source note for applicability, validation and rollback.

## Retain long conversation trace evidence during execution

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.15.0/docs/swift/ops/migrations/long-conversation-trace-capture.md)

### Applicability

All Fred deployments apply the Control Plane migration. The capture pause,
evidence compatibility and cleanup steps apply to deployments using managed
conversation trace capture.

### Prerequisites

Control Plane must be able to apply its PostgreSQL migrations. When capture is
enabled, Fred Agents must have read, write, and delete access to the configured
private trace bucket.

### Configuration

The existing trace settings apply. The default deployment-wide quota is 20 GB
and the default retention period is 30 days. No chart values or bucket
permissions change.

### Upgrade

1. If trace capture is enabled, turn it off in Admin > Conversation traces and
   let active captures finish before starting the mixed-version rollout.
2. Apply the Control Plane migration through `8a49f3ac2e6b` and deploy the
   updated Control Plane, Fred Agents, and frontend in that order. The migration
   adds PostgreSQL bookkeeping columns.
3. After all replicas are upgraded, restore capture if it was enabled before
   rollout and reload any open trace inspector tabs. Fred Agents use compressed
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

### Validation

Capture a long managed turn with a provider stream that fails near the end.
After publishing completes, open its final attempt, page through the HTTP
response and select the last event in the SSE timeline. Verify that withdrawing
consent blocks body and frame reads. With trace object storage unavailable,
verify that chat continues and that the inspector reports incomplete evidence.

### Rollback

Disable trace capture before rolling back the Runtime or Control Plane. The
new Runtime is required to inspect paged trace content captured after the
upgrade. Retain the additive storage ledger migration so upgraded maintenance
can settle or remove compressed trace artifacts when re-enabled.

### Limitations

A saturated background queue, interrupted Runtime, or unavailable artifact
store can leave incomplete trace evidence. Chat continues. The inspector
reports capture loss when known, and the final failed provider bytes receive
priority where capacity permits. Run a managed streaming comparison before
enabling high-volume capture on a shared deployment.

## Prepare the Fred v3.15.0 release

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.15.0/docs/swift/ops/migrations/release-v3-15-0-preparation.md)

Normal deployment installs the prepared package versions. The trace storage note records the database and rollout steps for this release.

See the source note for applicability, validation and rollback.

## Select resource rows and open folders or files with a double-click

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.15.0/docs/swift/ops/migrations/resource-name-copy-folder-row-open.md)

Existing data and APIs are unchanged; the interactions become available after normal deployment.

See the source note for applicability, validation and rollback.

## Place MCP tools in their conversation trace branches

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.15.0/docs/swift/ops/migrations/mcp-conversation-trace-order.md)

The runtime writes the existing evidence reference on new spans during normal operation. No data migration is needed.

See the source note for applicability, validation and rollback.
