## Context

- `useTaskSseManager` (mounted once in `MainLayout`) opens one streaming `fetch`
  per active task, across every kind (ingestion, migration, erasure).
- `GET /tasks?scope=user` already returns the caller's own tasks as
  `TaskSummary` (state, progress, step, error, target, team, detail). It is one
  SQL query filtered on `created_by`, with no ReBAC call. It hides terminal
  tasks unless a state filter is given, so a task that finished cannot be told
  apart from one that disappeared.
- Every task the store follows was started by the current user: imports,
  reprocessing, chat attachments, migration, and rehydration (which itself
  reads `scope=user`). `scope=user` therefore covers them all.
- A task id reaches the browser only after its task is persisted (ingestion:
  after `submit_documents` returns). The task RFC's guardrail "register before
  dispatch" states the same rule.
- Knowledge Flow runs `run_reconcile_sweeper` every 120 s on tasks idle for at
  least 300 s, which drives a task whose workflow died to a terminal state. Control Plane tasks have no executor
  binding to reconcile.

## Decisions

### 1. A batched read, not a multiplexed stream

One stream for all tasks would still hold a connection, and it needs a new
server-side fan-in over the bus. A periodic read reuses the endpoint, the
generated client and the RTK 401 handling that already exist, and it has no
reconnect logic to get wrong. This is polling and is named as such: progress
appears up to one interval late.

### 2. `task_id` filter on `GET /tasks?scope=user`

- Repeated query parameter, 1 to 50 values, otherwise 422. At about 45 bytes
  per id, 50 ids keep the URL near 2.3 KB, well under nginx's default 8 KB
  request-line buffer.
- Only allowed with `scope=user`, otherwise 422. Ownership stays the rule:
  ids the caller does not own are simply absent. That reveals nothing about
  other users' tasks and needs no new authorization path.
- Terminal tasks are included, because a task that finished must be returned
  with its outcome.
- No read-time reconcile: one executor lookup per task on every poll would be
  far too costly. The sweeper is the correction path, as it already is
  for a stream that stays open while its workflow dies.

### 3. One sequential loop per tab

- The loop does `await` a read, then waits 5 s, and repeats. It is never an
  interval timer, so requests cannot pile up behind a slow backend.
- Each tick reads, for each backend that owns at least one active task, its
  active task ids in chunks of 50. The chunks run one after another, which
  bounds the connections in use to one per backend.
- The loop runs only while the store holds an active, non-local task. It stops
  when there is none and starts again when one is registered.
- A new loop starts only once the previous one has ended. The chain is module
  state, so it also holds when MainLayout unmounts and mounts again (a route
  outside it). Stopping a loop cancels its read in flight, and a stopped loop
  reads no further batch.
- It goes through the generated client (`initiate` with `forceRefetch`, no
  cache subscription), so the token is refreshed before each read and a 401 is
  retried after a forced refresh, exactly as for every other request.
- A read unanswered after 15 s is aborted. Otherwise one hung request would
  hold up every later round.
- A failed read (network, 5xx, timeout) changes nothing in the store. The next tick
  tries again, so a backend outage leaves tasks as they were, never terminal.
- When the tab becomes visible again, it reads right away, since browsers
  throttle timers in background tabs.
- Snapshots can settle many tasks at once. `useRefetchOnTaskSettled` hands the
  newly settled targets to its consumer in one call, so the documents page
  reloads each affected folder, and the usage stats, once per batch rather than
  once per document.

### 3b. Query arrays are sent as repeated keys

`fetchBaseQuery` serializes `{ task_id: ["a", "b"] }` as `task_id=a,b`, which
FastAPI reads as the single id `"a,b"`. `dynamicBaseQuery` now repeats the key,
the OpenAPI default for query arrays. Scalars are serialized as before.

The only other endpoint called with an array is `GET /users/by-ids`
(`useUsersByIdsQuery`, author names on seven screens). Its route documents
`ids=a&ids=b`. With one author both forms are identical; with several, it
received the single id `"a,b"` and every name fell back to a bare uid, which
this change fixes. The two tabular endpoints with array parameters have no
frontend caller.

### 3c. A five-second interval

Extraction phases last from one to twelve minutes per file (measured on the
2026-10-04 test), while indexing takes about a second and is missed at any
interval worth polling at. Five seconds is invisible on the long phases and
cuts reads by 60% against two seconds. Beyond ten, the last file reads as
lagging behind its real end, which is what the user is watching.

### 4. Applying a snapshot

The new reducer `taskSnapshotsReceived({ requestedIds, tasks })` follows three
rules:

- **A terminal task never changes again**, whatever the kind. Following ends
  at the first outcome, as the stream did when it closed on it. Server-side,
  only an ingestion outcome is final; a retried erasure shows its later state
  after a reload, as it does today.
- For a returned task: `state`, `progress`, `step` and `error` are written as
  received; `target` is kept when the snapshot has none; migration warnings
  are read from `detail`; `terminalAt` is stamped on the first terminal state.
  The rule that a sparse field does not erase a known value is the same as
  today's.
- For a requested id the response does not contain, the task is marked
  `untracked`.

Snapshots carry no sequence number and need none: each one is a full current
state, applying one twice is harmless, and terminal states are final.

### 5. `untracked` is a flag, not a server state

`TaskState` is the backend's enum, and adding a value the backend never sends
would blur that contract. Instead, `TaskViewModel` gains `untracked: boolean`:

- `selectActiveTasks` excludes it, so the loop stops reading it;
- `selectActiveTaskForTarget` excludes it, so the document row shows the
  document's own processing status. That status is the truth for the row, and
  the existing settled-task refetch reloads it, since the cached copy may
  predate the task;
- the task card shows it with its own badge state (`untracked`, warning colour,
  no progress bar), so it never reads as pending;
- the import panel shows "Following stopped" with a dismiss action that evicts
  the entry locally;
- `useTaskAcknowledgement` acknowledges an untracked task locally for every
  caller (import panel, migration page, task popover), since the server would
  answer 404. The migration page lists it with the finished tasks.

Absence on a single read is enough. A task id is only ever known after its
task is persisted, and a read sees committed rows only, so absence is a fact,
not a race. A transport error is not absence: it changes nothing.

### 6. What is deleted

`useTaskSseManager.ts`, `parseSseBlock`, `taskEventsBasePath` (routing moves to
`taskBackendFor`, which already exists) and their tests. `taskEventReceived` and `lastSeq` stay: chat attachments dispatch local
events through them. The backend SSE endpoint and `fred_core.tasks.sse` remain: the
admin self-test pipeline (`features/pipeline/actions.ts`) still uses them.
Retiring them is a separate change.

## Risks

- **Latency:** up to 5 s. A task whose workflow died without the backend
  noticing is corrected about 7 minutes after its last update at worst (300 s
  grace plus a 120 s sweep interval).
- **Load:** one indexed SQL read per backend and per batch of 50 every 5 s, per
  tab with active tasks: about 20 reads per second for 100 importing users
  with one tab each. The table is indexed on `created_by`; the `task_id` filter is a
  primary-key lookup.
- **Short phases:** a phase shorter than the interval may never be seen. The
  import stepper already handles skipped phases.

## Deferred

- Retiring the per-task SSE endpoint and `awaitIngestion` in the admin
  self-test pipeline.
- Moving `useTaskRehydration` from raw `fetch` to the generated client. It
  runs once on mount and is not part of this transport.
