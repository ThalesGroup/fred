---
schema: 1
title: "Capture managed conversation traces for Fred support"
impact: minor
configuration: production
configuration_reason: "The Fred chart disables local trace access and labels model HTTP evidence with the Fred Agents image tag."
---

## Applicability

Fred deployments with a registered Fred Agents runtime. Capture starts off in shared deployments.

## Prerequisites

Control Plane must be able to migrate PostgreSQL and install the current OpenFGA authorization model. Fred Agents must use its registered workload client when calling Control Plane and have read, write, and delete access to its private runtime object storage.

The existing Control Plane lifecycle worker's machine account needs its configured `service_agent` role and an explicit OpenFGA grant that confers `organization.can_manage_platform`. The worker uses this authorization to erase a removed conversation when its retained diagnostics end, including its Runtime history and Knowledge Flow attachments.

## Configuration

Existing deployments can keep their configured values. The chart and backend schema default `conversation_trace_local_development` to false. Use Admin > Conversation traces to operate capture and grant the Trace reader role from Platform roles.

The explicit loopback-only, unsecured developer profile starts capture on and allows local content inspection. Shared profiles retain normal authentication and consent enforcement. An enabled deployment samples 100% of conversations by default, retains captures for 30 days, and caps artifact payloads at 20 GB (decimal).

## Upgrade

1. Apply the Control Plane migrations through `2da6fa199e5e` and update the
   OpenFGA model using the standard deployment process.
2. Upgrade all Control Plane API replicas and the lifecycle worker.
3. Apply the Fred Runtime migrations through `d37ac41af81b` before starting
   the updated Fred Agents runtime. Include the updated Knowledge Flow in
   the rollout.
4. Deploy the updated frontend after all runtime replicas are upgraded.

Keep capture off for the standard upgrade. Enable it optionally from Admin >
Conversation traces after validating the rollout, and grant the Trace reader
role to operators who need access.

Existing captures and grants retain their evidence. Existing grants without
a verified title revision keep their titles masked. Runtime replicas measure
previously indexed evidence before new payload writes resume. During
reconciliation the settings panel reports degraded storage.

Revision `4eea63270bc1` adds an indexed row per explicit incident report to
support search, expiry, and deletion through the existing session lifecycle.
It backfills reports present on active grants. If upgrading an earlier
unreleased trace build, stop its Control Plane writers during the upgrade.
The legacy grant field still carries the latest report for that build.

Revision `6cb9e24a813d` adds a nullable checkpoint status to the capture catalog.
Older captures show an unknown status.

Revision `c1a4bf6de820` adds nullable segment receipts to the existing capture
catalog for independent pause and resume publications. Older clients retain
the combined finalization protocol during rollout.

Revision `3fa0e47d652c` builds an index of opaque invalid tool fingerprints
from retained model calls on PostgreSQL and SQLite. Apply it before starting
the updated Control Plane API. The PostgreSQL migration locks the trace turn
table against concurrent writes during the backfill. After upgrade, writes from
older Control Plane replicas also maintain the index.

Control Plane revision `60cbb822db04` adds a partial index and two nullable
columns for recent degradation on captured turns. A replica can report
degradation even when another replica holds the storage accounting row.

Revision `2da6fa199e5e` adds nullable OTLP span metadata to existing trace
turns. Existing captures need no backfill.

The upgraded Runtime uses the caller's credential with the product lifecycle
API for managed history. Managed history fails closed while that API is
unreachable. Control Plane still accepts the prior trace workload visibility
request during the rollout.

Runtime revision `b34a0d59ef71` adds a table for terminal support references and their immutable cutoffs
with the same session erasure lifecycle as chat history. Ordinary history
rows and earlier terminal references remain readable without backfill.
This migration also applies to local SQLite databases.

Runtime revision `d37ac41af81b` adds the managed session write fence. It keeps
an opaque digest after erasure so a delayed Runtime cannot recreate deleted
transcripts or checkpoints. It stores no chat content or owner identity.

## Validation

Open Conversation traces as a platform admin or trace reader and verify capture is off. Enable it, run a managed chat turn, and confirm its masked entry appears under All. Disable capture and verify a subsequent unshared conversation does not appear. From the owner's Debug panel, share through a saved turn, confirm support can read that turn, then withdraw access and verify it is denied.

In Administration, run **Test roles and isolation** from Self-test with a
dedicated account. The trace reader should be able to read conversation trace
settings, and access to platform Analytics and user administration should be
denied. The normal report has 154 steps, including recovery, with at most one
extra interruption step (155 total). Recovery restores the test account's
original grants, including any Platform Access Manager grant.

With capture off, trigger a terminal error and dismiss the sharing dialog. Check that no entry appears. Share the error and verify the failed catalog lists it as History only with the same support reference. Record consent received outside Fred for a retained turn and verify the audit event identifies the operator and grant without the source note.

On an isolated runtime, fail the terminal transcript insert and share the
error. Verify that the failed turn's transcript is unavailable, earlier
shared history remains available, and subsequent turns stay outside the grant.

Share a second terminal error in the same conversation. Check that the catalog finds the conversation under either support reference and that the inspector shows both reports on their respective turns. Withdraw consent and check that the history-only reports disappear.

Confirm a sampled conversation receives the same decision on two replicas, and that an excluded conversation has no payload writes. Increase and then reduce the limits using Admin. Under pressure, retained and reserved bytes remain charged until cleanup succeeds. A slow or unavailable artifact backend leaves chat running and reports degraded capture.

For a captured streaming turn, open the model attempt's SSE tab. Verify the provider and Fred lanes, the shared zoom window, and the consent requirement for headers and original frames. An early provider rejection can have recorded headers without frames. Run a managed JSON turn and check that it appears in the catalog. When the provider streams, the inspector shows its lane without a Fred SSE lane. Confirm the checkpoint status reflects writes observed during the exchange.

For a shared OpenAI-compatible attempt with an HTTP 400 and a complete request
body, copy the request in each format from the HTTP tab. Supply a test key for
the captured endpoint and check that the status and response body are printed.
In Windows PowerShell, the copied command uses the Windows curl executable.

Pause a captured turn and resume it on another runtime replica while storage
writes are delayed. Verify the terminal status appears first and both timeline
segments appear after storage recovers. A grant through the pause can read its
evidence while the resumed segment stays masked.

With Langfuse export disabled, run a captured Deep turn that starts two
parallel `task` calls, each invoking the same tool. Verify each tool appears
under its own task in the inspector and the existing call links still open
their evidence. With export enabled for the turn, verify the exported spans
use the same span and parent IDs. Older captures remain readable.

Open the LangChain tab on a shared turn and verify the invocation, bound tools, and output availability. For a known correction, follow its link to the original provider frame and verify the literal tool-call ID there. If upgrading from an earlier trace build, verify that an earlier invalid occurrence retained before the upgrade still links from a later shared call.

For a shared turn with remote tool evidence, select the tool and open its HTTP tab. Verify the individual tool outcome, HTTP status, and turn outcome. Check that the raw response is readable only through consent.

Delete selected diagnostics in Admin and confirm the ordinary chat can still continue. Remove a shared chat from the owner's list while keeping diagnostics, then confirm the cutoff is frozen and the old owner history route is closed. Remove its remaining diagnostics and watch the lifecycle worker complete session erasure. Flush while a managed turn is in flight. The turn can finish and later eligible turns can be captured. Verify that a standalone history-only share still appears.

Open the failed catalog after a failed turn followed by a successful one. The conversation keeps its latest failed badge. Search by the support reference, combine filters, and check that renaming a shared conversation hides its title from search until consent covers the new title.

Export a mixed selection in both modes. Metadata only should contain the manifest alone. Shared content should contain files for the covered turns and metadata for the others. Withdraw one grant and verify a fresh download omits that conversation's previously shared content.

## Rollback

Switch capture off before rolling back. An older runtime does not write trace summaries. Leave the additive catalog and terminal reference tables in place if the evidence must be retained during rollback. The Control Plane migration downgrades drop the catalog, its settings, and consent records. Downgrading the runtime migration drops independently saved terminal references and preserves the conversation messages.

## Limitations

Capture starts at turn admission. Running turns admitted before disable can finalize. Masked views show diagnostic metadata. HTTP bytes are collected through the shared model, MCP, and direct Knowledge Flow clients within the runtime buffer budget. Slow, unavailable, or oversized evidence can be partial. Ordinary session erasure includes the private trace prefix. Capture retention and eviction erase only diagnostics and revoke their grants. Abandoned publications stay charged through the object-store retry window. Runtime replicas retry physical cleanup under shared leases.

Deployments forwarding end-user bearers can obtain a fresh prefilter on the
same runtime binding request using the configured runtime machine identity.
With a trusted negative prefilter, the runtime skips the separate admission
request. Each pod allows 16 in-flight admissions with a 900 ms deadline.
Admission saturation can drop diagnostics. If an admission commits but its
acknowledgement is lost, the runtime reports safe terminal facts for the
existing segment. Its payload evidence is partial. Operational counters
report filtering, admission pressure, and publication and reconciliation results.
While a flush holds the PostgreSQL fence, an eligible turn continues without
capture and reports `flush_in_progress`. Downloads use two slots per Control
Plane replica through assembly and delivery. An export started while both slots
are in use receives a busy response.
