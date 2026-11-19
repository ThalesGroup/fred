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

Apply the Control Plane migrations through `83adb40b71f5`. They add terminal incident metadata, restricted consent notes, deployment limits, the storage ledger, the owner-removal state, and consent-scoped title revisions. Existing grants without a verified title revision keep their titles masked. Update the OpenFGA model using the standard deployment process. Deploy Fred Agents, Knowledge Flow, and the frontend alongside the Control Plane API and its lifecycle worker. The runtime uses its existing history table to save the support references for new terminal errors. Existing captures and grants keep their previous evidence. Runtime replicas measure previously indexed evidence before new payload writes resume. During reconciliation the settings panel reports degraded storage.

Upgrade the Control Plane API before the runtime replicas so the managed owner visibility check is available. Enable the updated owner removal UI after all runtime replicas enforce it.

## Validation

Open Conversation traces as a platform admin or trace reader and verify capture is off. Enable it, run a managed chat turn, and confirm its masked entry appears under All. Disable capture and verify a subsequent unshared conversation does not appear. From the owner's Debug panel, share through a saved turn, confirm support can read that turn, then withdraw access and verify it is denied.

With capture off, trigger a terminal error and dismiss the sharing dialog. Check that no entry appears. Share the error and verify the failed catalog lists it as History only with the same support reference. Record consent received outside Fred for a retained turn and verify the audit event identifies the operator and grant without the source note.

Confirm a sampled conversation receives the same decision on two replicas, and that an excluded conversation has no payload writes. Increase and then reduce the limits using Admin. Under pressure, retained and reserved bytes remain charged until cleanup succeeds. A slow or unavailable artifact backend leaves chat running and reports degraded capture.

For a captured streaming turn, open the model attempt's SSE tab. Verify the provider and Fred lanes, the shared zoom window, and the consent requirement for original frames.

Open the LangChain tab on a shared turn and verify the invocation, bound tools, and output availability. For a known correction, follow its link to the original provider frame and verify the literal tool-call ID there.

For a shared turn with remote tool evidence, select the tool and open its HTTP tab. Verify the individual tool outcome, HTTP status, and turn outcome. Check that the raw response is readable only through consent.

Delete selected diagnostics in Admin and confirm the ordinary chat can still continue. Remove a shared chat from the owner's list while keeping diagnostics, then confirm the cutoff is frozen and the old owner history route is closed. Remove its remaining diagnostics and watch the lifecycle worker complete session erasure. Flush while a managed turn is in flight. The turn can finish and later eligible turns can be captured. Verify that a standalone history-only share still appears.

Open the failed catalog after a failed turn followed by a successful one. The conversation keeps its latest failed badge. Search by the support reference, combine filters, and check that renaming a shared conversation hides its title from search until consent covers the new title.

Export a mixed selection in both modes. Metadata only should contain the manifest alone. Shared content should contain files for the covered turns and metadata for the others. Withdraw one grant and verify a fresh download omits that conversation's previously shared content.

## Rollback

Switch capture off before rolling back. An older runtime does not write trace summaries. Leave the additive catalog tables in place if the evidence must be retained during rollback. The migration downgrades drop the catalog, its settings, and consent records.

## Limitations

Capture starts at turn admission. Running turns admitted before disable can finalize. Masked views show diagnostic metadata. HTTP bytes are collected through the shared model, MCP, and direct Knowledge Flow clients within the runtime buffer budget. Slow, unavailable, or oversized evidence can be partial. Ordinary session erasure includes the private trace prefix. Capture retention and eviction erase only diagnostics and revoke their grants. Abandoned publications stay charged through the object-store retry window. Runtime replicas retry physical cleanup under shared leases.
