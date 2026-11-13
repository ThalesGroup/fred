# Design

## Context

See [proposal.md](proposal.md). The agent form currently holds a `File` until the multipart create/update request. Control Plane then stores an immutable asset and creates a `capability_preparation` row in the agent save transaction. The worker receives a preparation ID through Temporal; it cannot process a browser-only file. Platform template replacement already has a server-side owner before analysis starts. The active `reusable-capability-preparation` change establishes this worker and must be synced before this delta is archived.

## Goals / Non-Goals

**Goals:**

- Reuse the current asset, preparation, dispatch and result machinery for a temporary owner, then transfer the same preparation to an agent without duplicate model work.
- Preserve the form's Save/Cancel boundary: selecting a file may consume temporary storage and worker capacity, but cannot create or mutate an agent.
- Keep transfer and status independent of one browser mount or backend replica, with bounded cleanup of abandoned work.

**Non-Goals:**

- Changing the platform default template flow or the legacy save-time multipart API.
- Automatically creating or saving an agent when the author selects a file.

## Decisions

### Temporary owner in existing preparation tables

Add `draft` to the owner-kind constraints and shared work contract. Store the author's ID and an expiry on a draft preparation; its existing asset associations own the immutable file. This extends `capability_asset` and `capability_preparation` in one migration instead of introducing tables with the same lifecycle. Only capabilities explicitly declaring draft support may use this path; PPT Builder opts in. Ordinary agent and platform paths remain as they are.

The draft ID is an opaque server-generated UUID. Reads and mutations require the author's own credential, team editing permission and matching team, user, runtime and capability. The server resolves the template for creation or the existing agent for editing before accepting bytes. A draft cannot be used to access another team's template or to bypass capability selection on Save.

### Scoped upload and status API

Add a bounded multipart draft upload route under the team, accepting the target template or existing agent, capability ID, preparation settings and one declared asset slot. Return a draft ID and initial status after durable admission. Add scoped status, retry and discard operations. The form starts the request at file selection and displays transfer immediately. Once the server acknowledges the file, the existing dispatcher starts the worker; the form polls the draft status independently of the agent form's saved status. A completed draft shows its summary before Save; slide previews become available after adoption through the existing agent endpoint.

Save includes an optional capability-to-draft ID mapping in the existing create/update request. The legacy multipart route remains valid. Save is unavailable while the selected file is still transferring, but becomes available as soon as the draft is admitted, regardless of whether analysis is running. If transfer fails, the file remains selectable for retry. A closed form can abandon the draft without waiting for the worker.

### Atomic adoption and revision fencing

The save request checks team editing permission and active capability selection. In the agent save transaction, lock the chosen draft preparation and the agent's current preparation, then compare author, team, target, runtime, capability, analysis settings and rules version with the submitted form. Mark the previous agent revision obsolete, then move the draft preparation and its asset ownership to the agent. Keep its preparation ID, state and result reference so a running worker can finish after Save and a succeeded result needs no second analysis. Result publication and adoption serialize on the same preparation row; a stale or duplicate completion remains fenced.

Each file selection or analysis-setting change creates a new current draft revision for that form session and supersedes the prior one. The client keeps the active draft ID above the Simple/Advanced view components so switching views does not restart upload. The server rejects adoption of an obsolete, expired, mismatched or already adopted draft. Changing unrelated agent fields does not restart analysis.

### Expiry and capacity

Drafts expire one hour after admission; expiry marks pending/running work obsolete and the existing cleanup path reclaims assets and result objects after any worker lease ends. A bounded, indexed sweep handles expiration across replicas with idempotent claims. Client discard is best effort; correctness relies on server expiry. Admission limits active draft count and retained draft bytes per author and team, including superseded revisions, as well as the capability's existing 64 MiB input limit. The existing worker concurrency cap remains the execution bound.

## Risks / Trade-offs

- **Work may be wasted when an author cancels** - Short draft expiry, per-author admission limits and bounded worker concurrency constrain cost.
- **Save and worker completion may race** - One preparation ID, row locking and existing attempt fencing keep exactly one publishable result.
- **A file may finish uploading after the form closes** - The server retains it only until expiry; no agent is created or changed without Save.
- **A stale draft may be submitted from another tab or after permissions change** - Check the team grant and capability availability in the save request, then ownership and revision during adoption; return a recoverable form error.

## Migration Plan

1. Deploy the additive owner-kind migration and draft API before enabling the form's selection-time upload. Keep existing multipart saves functional for older frontends.
2. Enable the frontend flow; monitor draft admission, expired-draft cleanup, worker queue depth and adoption failures. A rollback disables the frontend flow while leaving existing agent preparations and legacy uploads usable.
3. Sync and archive the prerequisite `reusable-capability-preparation` change before syncing this delta so its save-time wording is superseded in order.
