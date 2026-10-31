# A10. Open Issues

This annex records unresolved quality questions about the current architecture.
It separates retained decisions from evidence still needed; alternatives below
are considerations for a later decision, not planned implementation.

## OI-1. Document write concurrency

**Decision retained, 2026-10-25:** keep the organization-wide write lock for now.
Its presence is established by the code; a material performance problem under
the intended workload has not been established by this discussion. Short critical
sections are a design intent, not a measured latency guarantee.

### Guarantee and scope

The [system overview](01-system-overview.md#13-coordinating-document-writes) and
[document journey](02.2-document-journey.md#concurrent-imports-and-publication)
explain the check-and-record boundary. It supports the existing invariants in
[chapter 9](09-quality.md#invariants), including authorization ordering (I5) and
folder lifecycle ordering (I22), alongside SQL constraints and transaction-local permission checks.
The protocol protects durable outcomes; removing it is not equivalent to
accepting a temporarily stale display. Permissions and durable outcomes share PostgreSQL.

Ordinary ingestion releases the organization lock between upload reservation,
original publication and final indexing publication. File transfer, object
verification, extraction and embeddings are outside it. Folder mutations and
other participating organization mutations share this boundary. Rare revocations
do not eliminate contention between ordinary writes.

With four Control Plane replicas sharing the same stores, only one participating
section per organization holds that lock at a time. Reads and standalone
authorization checks do not acquire it; four Agent Pods requesting such checks
do not themselves create four exclusive writers. Their dependency load can still
affect latency. Organizations have distinct locks, but not complete performance
isolation: processing admission and stage claims share a storage-capacity row,
and administrative operations also use platform-wide coordination. Provisioning
an organization/role bundle holds locks across multiple changes, unlike a
document batch's separate reservation and publication steps.

### Evidence needed before changing the design

The useful distinction is lock **holding time** versus **waiting time**. Many
small sections can create a queue without any unusually large query. SQL permission checks and quota calculations occur within the document write sections.
The five-second acquisition limit in `authorized_write` bounds waiting to enter,
not the duration of the acquired section or of the entire request. A saturated
path can return 503; no strict acquisition fairness is promised.

Assess a representative mix of ingestion, folder edits, reads and authorization
checks, with one and four Control Plane replicas. The discussion's reference
scenario is 100 teams and 2,000 people in one organization, with rare role changes;
actual simultaneous writers and request rates matter more than registered users
or total batch size. Compare same-organization and different-organization traffic.
Record holding and waiting time distributions, publication throughput, request
latency and timeout/503 rates, together with SQL pool and query latency.
Separate ordinary load, bursts and degraded dependencies. No new measurement or
performance campaign accompanies this documentation change.

### Alternatives only if the evidence warrants them

A lock per space could let independent teams publish concurrently. It would
still need coordination for ancestor revocations, team/project shared quotas,
space retirement and cross-organization membership rules. Optimistic version
checks or a hybrid with a shorter final coordination step are other possibilities.
They must preserve transaction ordering with role changes and retirement.
No alternative or weaker guarantee is selected here.

### Implementation references

- [Organization write boundary](../../apps/control-plane/src/spaces.rs):
  `authorized_write`, `authorize_locked`, `lock_organization`.
- [Original reservation and publication](../../apps/control-plane/src/documents/upload.rs):
  `reserve`, `publish`; [final indexing publication](../../apps/control-plane/src/processing/publication.rs): `commit`.
- [Shared processing capacity](../../apps/control-plane/src/processing/store.rs):
  `admit`, `claim`; [administrative import](../../apps/control-plane/src/provisioning.rs): `reconcile`.
- [Security ordering](A6-security.md#mutation-ordering-and-revocation) and
  [runtime write boundary](A1-manager-runtime.md#folder-mutations-from-resources).

## OI-2. Where to retain computed conversation controls

**Decision deferred, 2026-10-29:** make no further implementation change for now.
Choose whether to retain computed interface controls in the Control Plane, in
the browser, or to keep evaluating them on each preparation. This entry records
an open question from the `gap/picker` working branch, not an end-to-end validated
Weaver journey or a decision to remove server-side authorization.

### Observed call path and cost

The browser calls Control Plane `prepare-execution` when opening a conversation
and before each message, even a second "hello" after the first answer. In the
current working change, Control Plane then asks the configured Agent Pod to
compute the selected capabilities' interface controls in one batched request.
Control Plane returns the descriptors to the browser, which can then send the
message to the Agent Pod. The control calculation calls no LLM. The Agent Pod's
subsequent trusted turn-context resolution from Control Plane is a separate
admission exchange and is not the subject of this cache discussion.

The working change adds one pod request per preparation with evaluable selected
capabilities, even when the person never opens the document picker. The request
uses a shared HTTP client, a ten-second timeout and no open SQL transaction.
Its latency and load impact have not been measured. A failed evaluation omits
the affected controls from that preparation response and logs the failure.

Swift's **Python Control Plane process** held a bounded in-memory cache of these
computed controls, keyed by capability, manifest version and configuration hash.
Neither the browser nor the Agent Pod owned that cache. Each Control Plane
process had its own entries, lost on restart; cache hits avoided asking the pod
again. The working Rust Control Plane implementation currently has no such cache.

### Alternatives and evidence needed

A Control Plane cache could avoid repeated pod evaluation while keeping the
existing browser preparation flow. A browser cache could retain controls in the
conversation page and refresh them when the relevant configuration or capability
version changes. Browser retention alone would not avoid the current pod call:
Control Plane would still recompute controls inside every preparation. That
option therefore also needs a way to separate control refresh from preparation
or tell the server which revision the browser already has.

Before choosing, compare the frequency and latency of preparations, configuration
changes and pod calls against the complexity of cache invalidation. Establish
how updates, pod deployments, navigation between instances/spaces, account changes
and dependency failures affect freshness. Any reuse must distinguish the owning
pod, capability version and effective configuration, with appropriate browser
account/instance scope. Keeping the uncached batch is also an option if its
measured cost is acceptable. No measurement campaign is requested by this entry.

Only interface descriptors are candidates for reuse. Cached controls never confer
permission: trusted turn admission and resource-specific authorization retain
their existing server-side boundaries, even if the browser displays old controls.
No cache location or invalidation protocol is selected here.

### Implementation references

- [Browser preparation and send](../../apps/frontend/src/rework/core/hooks/useChatSse.ts):
  `prepareChatControls`, `applyPreparation` and the preparation before sending.
- [Control Plane preparation](../../apps/control-plane/src/agent_instances/preparation.rs):
  `prepare_execution`; [pod control evaluation](../../apps/control-plane/src/agent_instances/chat_controls.rs): `resolve`, `fetch`.
- [Pod evaluation and wire contract](../../libs/fred-sdk/fred_sdk/contracts/capability/chat_controls.py),
  [capability evaluation](../../libs/fred-runtime/fred_runtime/capabilities/assembly.py): `evaluate_chat_controls_batch`.
- Swift branch reference: `apps/control-plane-backend/control_plane_backend/product/service.py`,
  `_chat_controls_cache`, `_resolve_chat_controls` (historical comparison only).
