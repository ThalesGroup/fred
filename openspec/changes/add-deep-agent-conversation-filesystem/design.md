# Design

## Context

See `proposal.md` for motivation and `specs/deep-agent-conversation-filesystem/spec.md` for the behavioral contract.

Deep Agents 0.6.12 currently receives no explicit backend, so its filesystem middleware uses state held in the LangGraph checkpoint. Fred's SQL checkpointer makes that state available across turns, but it is not an independently addressable filesystem for capability code and parallel children only exchange file changes when their state is merged. Fred Runtime already depends on `fred-core`, whose `BaseFilesystem` protocol has local, MinIO/S3-compatible, and GCS implementations. The cloud implementations expose async methods but currently perform synchronous SDK calls inside some of them.

`deep-agent-runtime-baseline` is a related in-flight OpenSpec change. It intentionally left `backend=` and `CompositeBackend` out of scope and guards Deep's built-in filesystem tool names unless Fred binds them. This change follows that baseline: the runtime-provided conversation filesystem becomes the standard binding for the safe filesystem operations, while `execute` remains disabled.

Conversation erasure already resolves the runtime that owns a session, deletes its checkpoint before its history, and retains session metadata when any store fails so retries remain possible. The filesystem must join that existing lifecycle rather than establish a second retention mechanism.

## Goals / Non-Goals

**Goals:**

- Keep storage scoping, path normalization, text handling, quota accounting, and mutation semantics behind one conversation-filesystem module.
- Give Deep's parent and native subagents the same shared backend scope, including future independently scheduled children.
- Keep capability callers independent of both Deep Agents and the object-store abstraction.
- Reuse one generic Deep backend adapter for both mounted namespaces.
- Preserve the existing conversation erasure ordering and retry guarantees.

**Non-Goals:**

- Consolidating Fred's four storage abstractions. A later change may remove the unused Knowledge Flow `BaseFileStore`, introduce a shared lower-level object-store seam, and rebuild the remaining higher-level interfaces on it.
- Migrating corpus, attachment, or skill access to filesystem mounts.
- Adding a public scratchpad API, UI editor, M2M flow, or Knowledge Flow dependency.
- Hard distributed quota transactions, binary scratchpad files, file version history, merge conflict UX, or a sandbox/code-execution tool.
- Migrating files already embedded in active LangGraph checkpoints.

## Decisions

### D1 — Fred Runtime owns one bucket and code-owned conversation prefixes

Fred Runtime talks directly to the configured object store through `BaseFilesystem`; Knowledge Flow is not in the request path. Infrastructure configuration selects the provider, endpoint/credentials or workload identity, and one Fred Runtime bucket. Feature code owns all prefixes beneath that bucket; scratchpad and `.deep` do not add separately configurable bucket or prefix settings.

The physical layout is:

```text
<fred-runtime-bucket>/
  conversations/<session_id>/
    scratchpad/
    .deep/
```

`session_id` is the sole ownership key because the conversation identifier is assumed to be globally unique. Adding `team_id` would not repair a conversation-identity defect and would complicate every caller. The scoping layer treats the identifier as one path segment and rejects identifiers or virtual paths that could traverse out of the conversation prefix.

One bucket is appropriate because both areas have the same owner, access policy, encryption/residency requirements, recovery lifecycle, and operational boundary. A later feature should use another prefix by default and a separate bucket only when IAM, lifecycle, exposure, replication, or blast-radius requirements differ.

Alternative rejected: feature-specific buckets and configuration. They multiply deployment settings without adding isolation while the policies remain identical.

### D2 — One deep conversation-filesystem module owns policy; adapters stay thin

A conversation-bound service above `BaseFilesystem` owns:

- safe path normalization and physical prefixing;
- UTF-8 text validation for scratchpad operations;
- list/read/write/edit/delete semantics;
- independent namespace quota accounting;
- storage-error translation and observability;
- idempotent namespace purge.

Two thin outward adapters use that service:

1. `ConversationScratchpadPort`, added to `RuntimeServices`, exposes conversation-bound text operations to trusted runtime and capability code. Its contract covers read, write/replace, expected-text edit, list, exists, and delete. Paths are scratchpad-relative; callers cannot select a bucket, conversation, or `.deep` namespace.
2. One generic Deep `BackendProtocol` implementation adapts a configured namespace of the service to the Deep Agents filesystem contract. It is instantiated for both `/scratchpad/` and `/.deep/` instead of duplicating backend code.

The port belongs at the SDK/runtime-service seam because capability authors need a stable product operation, not Fred's storage interface. `BaseFilesystem` remains an internal implementation seam and is not exposed through capability contexts.

Alternative rejected: make `BaseFilesystem` the capability contract. That would leak bytes, physical-storage behavior, and namespace selection into capability code and make future storage consolidation harder.

### D3 — Composite routing exposes two mounts and rejects everything else

Deep Runtime constructs one composite backend per conversation:

```text
default: reject
/scratchpad/ -> conversation scratchpad backend
/.deep/      -> Deep internal backend
artifacts_root: /.deep
```

The same composite backend and conversation service are supplied to the parent and its native subagents. This replaces checkpoint-state copy/merge behavior with ordinary shared-storage visibility: once an operation succeeds, later operations observe it directly.

The standard model-visible surface enables `ls`, `read_file`, `write_file`, `edit_file`, `glob`, and `grep`; `execute` stays guarded. Runtime filesystem-tool guards regard these standard safe operations as bound even when no optional capability is selected.

The `.deep` backend must be writable by trusted Deep middleware because it stores `large_tool_results/` and `conversation_history/`. The model-facing validation layer rejects `write_file` and `edit_file` paths under `/.deep/`, while allowing its read-only browsing operations. Capability code receives only `ConversationScratchpadPort`, so it has no route to `.deep`.

Alternative rejected: a physically read-only `.deep` backend. Deep middleware and the model use the same backend contract, so making the backend itself read-only would also prevent the framework from persisting its artifacts.

### D4 — `BaseFilesystem` is retained for this slice and may receive compatible fixes

`BaseFilesystem` is the only shared abstraction that already provides the operations needed by a filesystem-shaped feature and has local, MinIO/S3-compatible, and GCS implementations. `fred-core.store.ContentStore` is limited to put plus signed URL, Knowledge Flow's `BaseContentStore` is document-domain-specific, and Knowledge Flow's `BaseFileStore` has no production caller and lives in the wrong dependency direction.

This change may make small backward-compatible `BaseFilesystem` corrections needed by the conversation service, including safe recursive prefix deletion, consistent metadata/list behavior, and ensuring synchronous MinIO/GCS SDK work is offloaded from the async event loop. It must not perform the broader storage-abstraction consolidation.

Alternative rejected: introduce the future generic `ObjectStore` abstraction now. That would turn a bounded Deep-agent feature into a cross-application migration.

### D5 — Edits provide lightweight conflict detection; full writes remain explicit replacement

`edit_file` and the port's edit operation read the latest stored text and apply only when the requested old text matches with the Deep Agents edit semantics. A stale edit therefore fails without overwriting newer content. Creating an absent path succeeds. A full write is an explicit replacement and uses last-successful-write-wins behavior.

This is intentionally better than today's unconditional document overwrite without introducing ETags, draft reconciliation, merge UI, or a requirement that every code caller retain a read token. A future human editor can add conditional writes without changing the basic scratchpad scope.

Alternative rejected: mandatory ETags for every mutation. They add state and UI/API complexity before a human editor exists and do not match the current Deep tool contract.

### D6 — Quotas are local-accounted soft safety limits

Default safety limits are:

| Namespace | Total bytes | Files | Per-file limit |
|---|---:|---:|---:|
| `/scratchpad/` | 100 MiB | 1,000 | none |
| `/.deep/` | 1 GiB | 10,000 | none |

These four values are code defaults in one grouped conversation-filesystem runtime setting. Each value can be overridden independently through the runtime's normal settings/environment mechanism, so an operator can adjust a limit without rebuilding the image. This change does not add quota values to checked-in configuration files or Helm charts; deployments that need an override supply it through their existing runtime-configuration mechanism, while all others inherit the defaults.

The conversation service obtains actual count and byte totals from the namespace on its first mutation in a process, serializes same-process mutations with a per-conversation async lock, applies replacement deltas, and updates its local accounting after successful operations. A new process starts by recounting storage. Rejections produce a stable domain error plus a metric and structured log without logging file content.

This is not a distributed transaction. Two replicas can observe the same remaining capacity and both approve a mutation, temporarily exceeding the nominal limit. A single turn/tool call normally runs on one replica; this race needs overlapping turns, retries, or future independently scheduled child work. The accepted trade-off is bounded operational overshoot rather than a database counter or distributed lock. Subsequent fresh accounting uses actual stored totals.

There is no per-file limit: any one text file may consume the remaining namespace budget. `.deep` receives a much larger independent ceiling so long conversations are unlikely to fail because of internal artifact retention.

Alternative rejected: a hard distributed quota. It adds a shared transactional coordinator for a safety control whose cross-replica race is expected to be rare.

### D7 — Storage failures are explicit and never fall back locally

A failed object-store operation is translated into a stable filesystem/tool error and recorded with the conversation identifier, operation, namespace, and error category, but never file contents or credentials. The runtime does not write a replica-local or checkpoint copy after failure because reporting success would create divergent views across replicas and capability callers.

Filesystem failure does not make unrelated non-filesystem tool calls unavailable. Deep internal persistence may still cause the current graph operation to fail when the framework requires that artifact; the error remains visible rather than silently losing data.

### D8 — Standard erasure calls the owning runtime before deleting history metadata

The Control Plane continues to resolve the runtime from server-side conversation metadata. Runtime cleanup gains an authenticated, internal operation that purges `conversations/<session_id>/scratchpad/` and `conversations/<session_id>/.deep/` idempotently. It is not a general file API.

Erasure ordering becomes:

1. resolve and authorize the conversation and its owning runtime;
2. delete the runtime checkpoint;
3. delete the runtime conversation-filesystem prefixes;
4. delete runtime history;
5. delete conversation metadata only after every store reports success.

Keeping filesystem cleanup before history preserves the history-backed ownership proof needed by runtime cleanup and retains the existing retry strategy. A partial filesystem failure is represented in the erasure receipt and prevents metadata deletion.

Alternative rejected: bucket lifecycle rules as the only cleanup. They cannot provide prompt explicit erasure, per-conversation receipts, or retry visibility.

### D9 — Test through the runtime boundary, with focused adapter and lifecycle contracts

The primary acceptance seam is a compiled Deep runtime using a deterministic model and an in-memory `BaseFilesystem` implementation. It proves the model-visible mounts and permissions, live sharing by parent and native subagents, later-turn visibility through a fresh runtime instance, and continued blocking of `execute`. Tests should assert externally visible files and tool results rather than middleware lists or constructor call shapes.

Focused contract tests below that seam cover path traversal, UTF-8 enforcement, expected-text edit failure, replacement semantics, namespace quotas, storage failures, and idempotent purge. The same filesystem contract suite runs against the supported local, MinIO, and GCS adapters where existing test infrastructure permits. Control Plane erasure tests extend the existing receipt/order/retry suite with the new runtime filesystem store.

No live cloud system is required for unit acceptance. A later manual deployment check may confirm two runtime pods observe one conversation's files, but it does not replace deterministic automated coverage.

## Risks / Trade-offs

- **[Soft quota overshoot]** Concurrent replicas may temporarily exceed a namespace quota. → Keep same-process serialization, recount on new executors, emit usage/rejection metrics, and introduce a distributed counter only if observed concurrency makes the risk material.
- **[Event-loop blocking]** Existing cloud filesystem implementations call synchronous SDKs from async methods. → Offload those calls or otherwise make them non-blocking before placing them on the per-tool hot path.
- **[Existing active conversations]** Checkpoint-contained Deep files and internal artifacts are not migrated, so an active conversation may not resolve an old artifact reference after rollout. → Roll out at an agreed boundary, communicate that active Deep conversations may need a new conversation, and retain checkpoint cleanup for old state.
- **[Storage outage]** A shared-store outage makes filesystem operations fail across replicas. → Fail explicitly, preserve other tools when possible, and add operation-level metrics; do not create divergent local state.
- **[Identifier assumption]** Physical isolation relies on `session_id` being globally unique. → Validate it as one safe opaque segment here; fix any conversation-ID generation defect at its source rather than adding a team prefix in this feature.
- **[Pending spec interaction]** The in-flight `deep-agent-runtime-baseline` delta currently describes filesystem names as capability/toolset-bound. → Reconcile its wording so the standard runtime-provided backend counts as the binding before archiving either change.

## Migration Plan

1. Provision one private Fred Runtime bucket and grant runtime workloads list/read/write/delete access; configure the provider and bucket once per deployment. Override quota defaults through runtime settings only when needed, without adding quota entries to the checked-in configuration or chart.
2. Deploy the backward-compatible core filesystem fixes and Fred Runtime support, including the internal purge operation, before Control Plane starts requiring the new erasure receipt entry.
3. Deploy Control Plane erasure fan-out for the runtime filesystem store.
4. Exercise a new Deep conversation through parent/child sharing and erase it through the standard recovery/erasure flow.
5. Do not copy checkpoint-held files. Existing checkpoints remain governed by their current deletion path.

Rollback may restore the previous checkpoint backend for new turns, but externally stored objects must remain discoverable by the erasure endpoint until their conversations are purged. Do not remove bucket credentials or cleanup support while such objects remain.
