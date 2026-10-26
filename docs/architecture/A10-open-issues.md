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
folder lifecycle ordering (I22), alongside SQL constraints and OpenFGA guards.
The protocol protects durable outcomes; removing it is not equivalent to
accepting a temporarily stale display. SQL and OpenFGA remain separate systems.

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
small sections can create a queue without any unusually large query. OpenFGA
calls and SQL quota calculations occur within the document write sections.
The five-second acquisition limit in `authorized_write` bounds waiting to enter,
not the duration of the acquired section or of the entire request. A saturated
path can return 503; no strict acquisition fairness is promised.

Assess a representative mix of ingestion, folder edits, reads and authorization
checks, with one and four Control Plane replicas. The discussion's reference
scenario is 100 teams and 2,000 people in one organization, with rare role changes;
actual simultaneous writers and request rates matter more than registered users
or total batch size. Compare same-organization and different-organization traffic.
Record holding and waiting time distributions, publication throughput, request
latency and timeout/503 rates, together with SQL pool and OpenFGA latency.
Separate ordinary load, bursts and degraded dependencies. No new measurement or
performance campaign accompanies this documentation change.

### Alternatives only if the evidence warrants them

A lock per space could let independent teams publish concurrently. It would
still need coordination for ancestor revocations, team/project shared quotas,
space retirement and cross-organization membership rules. Optimistic version
checks or a hybrid with a shorter final coordination step are other possibilities.
They must preserve the named guarantees across SQL and OpenFGA, including failed
or delayed remote operations, rather than just move waiting into repeated retries.

The existing OpenFGA guard is not a switch to optimistic-only execution: ordinary
content writes also advance the organization's guard revision. Removing the SQL
lock alone would create competing revisions and leave the SQL/OpenFGA publication
ordering unresolved. No alternative or weaker guarantee is selected here.

### Implementation references

- [Organization write boundary](../../apps/control-plane/src/spaces.rs):
  `authorized_write`, `authorize_locked`, `lock_organization`.
- [Original reservation and publication](../../apps/control-plane/src/documents/upload.rs):
  `reserve`, `publish`; [final indexing publication](../../apps/control-plane/src/processing/publication.rs): `commit`.
- [OpenFGA version guards](../../apps/control-plane/src/fga.rs): `guard`, `write_guarded`, `fence`.
- [Shared processing capacity](../../apps/control-plane/src/processing/store.rs):
  `admit`, `claim`; [administrative import](../../apps/control-plane/src/provisioning.rs): `reconcile`.
- [Security ordering](A6-security.md#mutation-ordering-and-revocation) and
  [runtime write boundary](A1-manager-runtime.md#folder-mutations-from-resources).
