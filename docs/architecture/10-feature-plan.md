# 10. Feature plan

Which control-plane slices exist, and which are agreed or proposed next? Each slice
has a stable ID, a user outcome, its boundary and its acceptance scenario. A
proposed slice does not authorize implementation: Dimi orders and accepts slices.
Execution status and review notes stay in the [working journal](../WORKING-JOURNAL.md).

States: **proposed** (described, not agreed), **agreed** (scope and acceptance
accepted), **implemented** (code and dossier match the slice), **verified** (Dimi's
explicit acceptance of the implemented slice).

| Id | Outcome | State |
| --- | --- | --- |
| [S01](#s01-processing-starts-on-admission-commit) | Processing starts as soon as its admission commits, without throttling large batches | implemented |
| [S02](#s02-separate-api-and-worker-roles) | Production runs API replicas apart from a background worker; a small installation keeps one process | proposed |
| [S03](#s03-processing-capacity-and-admission-horizon) | A large batch is queued rather than refused after its originals are stored | proposed |
| [S04](#s04-direct-to-storage-upload) | Original bytes no longer transit through API pods | proposed |
| [S05](#s05-content-purge-on-space-deletion) | Deleting a space that holds documents eventually removes its content | proposed |
| [S06](#s06-worker-callback-routing) | Worker callbacks and original streaming do not compete with user and agent traffic | proposed |

## S01 Processing starts on admission commit

- **Scope:** the admission transaction notifies the dispatcher; a tick leases
  never-delivered intents first, runs bounded concurrent Temporal RPCs and repeats
  while batches are full; running work is described again every two minutes.
- **Excludes:** capacity and admission horizon (S03), process roles (S02).
- **Prerequisites:** original storage, processing configuration, Temporal and the
  existing KF worker.
- **Acceptance:** a committed admission is delivered well before the safety-net
  poll; a new intent is leased ahead of running work due for reconciliation; an
  intent whose notification was missed is delivered at startup or by the poll; no
  intent starts twice ([I28](09-quality.md#invariants)).
- **Implementation:** `processing::dispatch::{run, tick}`, `processing::store::Processing::admit`;
  `processing_dispatch_wakes_on_commit_and_prefers_new_intents`. Decision D22 in the
  [runtime reference](A1-manager-runtime.md#design-rationale).

## S02 Separate API and worker roles

- **Scope:** `control-plane api` serves HTTP only and needs no Temporal connection;
  `control-plane worker` runs the processing dispatcher, the lifecycle worker and
  original-storage cleanup; `serve` keeps both roles in one process. The chart's
  `control-plane-worker` application invokes this command.
- **Excludes:** replacing Temporal.
- **Prerequisites:** S01.
- **Acceptance:** an API-only process answers every route without Temporal
  settings; a worker-only process delivers committed intents and runs lifecycle
  sweeps; `serve` behaves as today.
- **Implementation:** today `main.rs` `serve` supervises every role; the chart's
  `control-plane-worker` entry names a command the binary does not provide.

## S03 Processing capacity and admission horizon

- **Scope:** decide what replaces the global `limits.pending` refusal, which today
  answers 429 after the original is stored, and the admission-time storage lock that
  only serves that count; decide whether `queue_seconds` still expires intents already
  delivered to Temporal but not yet claimed by a worker; define the frontend's
  response to capacity.
- **Excludes:** S04.
- **Prerequisites:** a design decision; acceptance is not yet defined.
- **Implementation:** `processing::store::Processing::admit`, `processing::dispatch::expire`,
  `rework/features/imports/managerImportRun.ts`.

## S04 Direct-to-storage upload

- **Scope:** the browser writes the original to object storage through a presigned
  request; the manager keeps reservation, quota, checksum verification and
  publication guarantees ([I25](09-quality.md#invariants)).
- **Prerequisites:** a design decision on verification and failure handling.
- **Implementation:** today `documents::upload` spools and writes every original.

## S05 Content purge on space deletion

- **Scope:** after its retention, a retired space's originals, derived artifacts,
  chunks and vectors are removed, with coordination by the KF cleanup consumer.
  Today the API refuses to retire a space that holds documents.
- **Excludes:** data owned outside the control-plane, which needs its own decision.
- **Prerequisites:** a design decision on ownership of each store's cleanup.
- **Implementation:** `lifecycle::store` (refusal), `lifecycle::cleanup`; KF
  `features/manager_processing/cleanup.py`.

## S06 Worker callback routing

- **Scope:** serve the `/document-processing/*` worker callbacks, including original
  streaming, from an internal service or the worker role instead of the user-facing
  API replicas.
- **Prerequisites:** S02.
- **Implementation:** `processing::http::routes`.
