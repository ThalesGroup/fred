---
schema: 1
title: "Weaver: Ralph conversation memory and effective conversation erasure"
impact: minor
configuration: local
configuration_reason: "No new production configuration keys. The preceding Ralph search change enables knowledge_flow_url in the checkout's k3d profile and provisions the Control Plane delegation role. Embedded conversation erasure uses the existing lifecycle settings."
covers:
  - e017f869ea5d5668a47d04da3c2de572e97af8b7
---
## Applicability

Weaver installations adopting embedded Ralph memory and effective erasure of
retired Ralph conversations. Python conversation erasure remains blocked. This
note also covers the preceding extraction of Ralph
into `libs/fred-rust-agent`, its Rig 0.46 transport, fixed document search and
native reasoning trace. It does not migrate Swift history.

## Prerequisites

Back up Control Plane SQL and the matching runtime content stores together.
Inspect the lifecycle policy and outstanding deletion receipts before rollout:
Ralph conversations previously blocked at their retention deadline become eligible
for effective erasure. Purged content cannot be recovered by rolling code back.

Keep external runtime sources and their content stores available while Python
conversations remain retained. Disabling a source is not erasure. No additional
Control Plane workload permission is required for the SQL-owned Ralph purge.

## Configuration

No new production chart values or credentials are introduced. Existing
`scheduler.lifecycle` and `policies.purge_catalog_path` control cleanup. Default
retention is seven days; the checkout's k3d profile uses one minute. The worker
schedule adds delay beyond the retention deadline.

For Ralph document search, the preceding change accepts the optional
`platform.knowledge_flow_url` and uses `security.m2m` to call Knowledge Flow.
Provision the accepted delegation audience and caller role for that identity.
The local k3d preparation performs this provisioning; other deployments must
provide it explicitly. An absent URL keeps Ralph text-only.

## Upgrade

1. Review pending deletions and take the coordinated backup before enabling the
   updated worker. Pause lifecycle cleanup during rollout if that review is not
   complete.
2. Apply additive migrations `0006_embedded_agent_conversations.sql` and
   `0007_session_retirement_queue.sql` using the normal initialization/deployment
   procedure. Keep migrations 0001-0005 and SQLx history unchanged. The second
   migration builds an index on existing session metadata; allow a migration
   window for that index build and its write lock. API startup verifies the schema;
   it does not migrate it.
3. Deploy the updated Control Plane before resuming lifecycle cleanup. This lot
   does not change Python runtime storage or its existing purge endpoints.
4. Deploy the generated frontend client with the Control Plane. Ralph uses the
   existing chat history format and does not require a separate UI or service.

## Validation

With Ralph, ask two related questions, reload the page and check restored answers
and search traces. Delete the conversation: it must disappear immediately and
history reads must return 404. After retention and a worker sweep, check the
completed receipt and absence of its metadata/log while consumption remains.

For Python, verify that removal still hides the conversation and its receipt
remains explicitly blocked with `session_purge_unavailable`, preserving metadata
and runtime storage. These operator checks
are not claimed as completed by the repository's offline/disposable-service tests.

For team/organization deletion, verify immediate history denial and eventual
Ralph child deletion before parent completion. Child receipts are materialized
for one remaining space per visit, in batches of 100 after retention, so large
trees require additional sweeps.
Previously retired sessions retain their own deadlines; Python children keep the
parent pending. Ordinary space documents and pending uploads still require their
existing separate cleanup before accepting space deletion.

## Rollback

Prefer a corrective forward release. Stop lifecycle cleanup before rolling the
application back, and restore mutually compatible components. Do not remove
SQLx migration records to force an older binary to start. If schema verification
requires restoration, restore SQL and runtime content from the coordinated backup.
An old Ralph binary does not use the persisted conversation log. Data already
purged is absent unless restored from backup.

## Limitations

Rig owns a pre-1.0 log format; changing its version can make an existing log
unreadable. Logs are read whole and have no context window or compaction.
Runs interrupted before their final append are not saved; an append already
committed remains saved even if the browser misses `final`. A concurrent writer
or persistence failure can invalidate a response already streamed to the browser. No images or files are
stored in the Ralph log. Restored traces contain reduced source excerpts, without
reasoning or token/model badges. See the agent README for the explicit limits.

Usage delivery retains its existing best-effort contract. Erasure preserves
the usage journal but can remove a deleted agent's fallback display name.
Ralph retains verified admission provenance for late usage reports after session
purge, including title usage; this does not make delivery durable across a crash.
This work does not implement the separate KPI redesign.

Python effective erasure is intentionally not activated. There is no durable
coordination covering all admitted Python turns and their history, checkpoint and
filesystem writes. A turn can outlive retention and recreate content after DELETE.
An increased retention or a process-local lock does not establish final erasure.
The follow-up needs durable execution/erasure coordination and crash recovery
without holding a SQL transaction or a database connection throughout every turn.
