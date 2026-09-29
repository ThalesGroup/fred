---
schema: 1
title: "Replace the legacy Graph executor with native LangGraph execution"
impact: major
configuration: local
configuration_reason: "Local fred-agents configuration changes logging and adds the test mock model profile. The chart only documents that optional test profile as a commented example; no production setting is activated."
---

## Applicability

Deployments and external agent pods upgrading to the native Graph runtime.
Graph, ReAct and Deep now share capability tool authorization, observability
and approval handling. This change does not enable token delegation.

The four Python libraries (`fred-pod`, `fred-core`, `fred-sdk`, `fred-runtime`)
are prepared for coordinated publication as 4.4.0, with aligned internal
dependency minimums. This package version does not remove the incompatible
SDK and checkpoint changes below. Publish in the documented order: pod,
core, SDK, then runtime.

## Prerequisites

Review external SDK consumers before upgrading:

- `GraphWorkflow.parallel` and `GraphDefinition.parallel_groups` are removed.
  The legacy implementation supported concurrent branches. Adapt affected
  agents before upgrading; a sequential rewrite requires a review of its
  behavior and performance and is not an equivalent automatic migration.
- `ThoughtRecord` and `GraphExecutionOutput.thought_trace` are removed.
  Consumers needing authored thought events must use the existing streamed events.
- Graph approval clients must use `interrupt_id` and, when supplied,
  `occurrence_id`, instead of `checkpoint_id`. Old request/history keys may
  still parse, but this does not make old Graph pauses resumable.
- Custom session IDs must not contain `:`; the runtime rejects them with 422.

## Configuration

No production configuration activation is required. The bundled test mock
model is optional and intended only for Test Assistant checks. Local settings
are not a production model or observability recommendation.

## Upgrade

1. Stop admitting new Graph runs and finish or explicitly abandon pending
   Graph approvals on the old deployment. Record any business work to restart.
2. Back up runtime checkpoint and session-history storage using the deployment's
   normal backup procedure. Do not delete old checkpoints as part of this upgrade.
3. Upgrade the SDK, runtime, agent pods, frontend and custom approval clients
   together. Avoid mixed runtime versions serving the same Graph session.
4. Start fresh Graph sessions. Legacy Graph checkpoints use a different layout
   and are not migrated: old paused runs cannot resume, and their business state
   is not automatically restored on a new turn. Reconstruct required business
   state explicitly and check previous side effects before rerunning work.

PostgreSQL checkpoint initialization also installs two session lookup indexes on
existing tables. Their equality lookup covers both ReAct/Deep session threads
and every `session:agent` Graph thread, including dynamic children, under
non-C collations and generic prepared plans. SQLite keeps its existing lookup.

For large live checkpoint tables, prebuild these indexes **before rollout** to
avoid the write-blocking build during the first checkpoint request. Run each
statement outside a transaction; adjust `v2_` if using a custom table prefix:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS v2_langgraph_checkpoint_session_idx
    ON v2_langgraph_checkpoint (split_part(thread_id, ':', 1));
CREATE INDEX CONCURRENTLY IF NOT EXISTS v2_langgraph_checkpoint_write_session_idx
    ON v2_langgraph_checkpoint_write (split_part(thread_id, ':', 1));
```

Confirm both indexes are valid before upgrading; a failed concurrent build can
leave an invalid index that must be dropped and rebuilt. Otherwise, allow the
runtime to create them during a maintenance window. Existing indexes and data
are retained; rollback can leave these additional indexes in place.

## Validation

Verify pod template discovery and external agent imports. In a new Graph session,
exercise a capability approval, reload while paused, accept and confirm one tool
execution and a terminal response. In a separate session, reject and confirm
zero execution. Check ReAct and Deep approval/refusal behavior as well.

## Rollback

Stop new runs before reverting pods and clients together. The old Graph runtime
cannot consume the new native checkpoints. Restore a consistent pre-upgrade
backup only through the normal recovery procedure; this can discard intervening
history. Neither rollback nor checkpoint restoration reverses external tool
effects. Reconcile those effects before restarting business work.

## Limitations

No automatic legacy Graph checkpoint conversion is provided. Native parallel
authoring, per-node retry/timeout configuration, automatic node progress and
model-native reasoning visibility remain outside this change. Node error routes
use the Fred wrapper because the native LangGraph 1.2.12 error handler does not
recover correctly with the required custom stream mode.

The upgrade procedure is an operational requirement, not evidence that legacy
checkpoints can be resumed. Existing ReAct/Deep source aggregation may attach
retrieved documents to an abstention; relevance filtering is a separate follow-up.
