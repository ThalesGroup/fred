## Why

With grants, a run no longer dies with the person's credential, so what happens
when the person leaves must be a deliberate rule rather than an accident — and
work meant to run without the person needs its own admission, its own record and
its own place to land.

## What Changes

- Presence rule: an attended run is bound to its stream and is cancelled after a
  reconnect grace when the stream closes. A dropped connection never promotes a
  run to background work.
- Reconnection reattaches the authenticated owner to the same run through the
  existing execution-stream endpoint, replaying buffered events by sequence.
  Pod affinity keeps attended state local; another replica refuses attachment
  without starting a replacement run or consulting the control plane.
- Background runs are tasks of a new kind, started explicitly through a
  team-scoped endpoint by a person who may use the agent there. The task payload
  is the durable, server-written admission record.
- The pod's scheduler executes the task; the grant parameters are taken from the
  record, which carries `mode = background`; every start re-checks standing and
  permission and fails closed; each job has its own budget. Registration uses
  the runtime workload report and requires no person token or active session.
- Scheduled runs create the same task kind on a schedule, with an explicit opt-in
  at creation and a re-check at every tick.
- Results land as task records and, where a conversation is produced, it is
  attributed to the person. People see and cancel their own background runs; team
  admins see and cancel their team's.

## Capabilities

### New Capabilities

- `delegation-background-runs`: the presence rule, explicit background admission,
  execution from a durable record, and the visibility and cancellation of
  background and scheduled runs.

### Modified Capabilities

None. Builds on `delegated-execution-grant` and `delegation-subject-and-standing`.

## Impact

- Runtime: presence rule in the stream lifecycle; the credential provider reading
  durable records; reconnect request and bounded replay on the execution stream;
  a task-kind activity executed under the pod scheduler.
- Control plane: team-scoped start endpoint; task kind, listing and cancellation
  by person and team; schedule creation with opt-in.
- Shared libraries: task detail model for agent runs; schedule support reuse.
- SDK and generated clients: reconnect request, exposed run handle and event cursor
  on the existing streaming contract, with its dated contract entry.
- Frontend: reconnect to the existing run; list and cancel background runs;
  results surfaced as tasks.
- Deployment tooling (separate repository): pod scheduler enabled where the lane
  is used; runtime routing preserves pod affinity for reconnection.
- Sequencing: after `add-delegation-single-subject`.
