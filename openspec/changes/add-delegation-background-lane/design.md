## Context

The pod already carries a generic scheduler configuration with a Temporal backend.
That setting alone does not opt a pod into agent-run background execution. The shared task service starts, cancels, acknowledges,
lists and reconciles Temporal-backed tasks with an event stream, and the control
plane exposes start, list, events, cancel and acknowledge routes, today gated to
platform administrators for platform tasks. Schedule support exists in the shared
scheduler package. The typed terminal outcome and the run ceiling exist. A run's
record is pod-local for attended runs. See proposal.md — Why.

## Goals / Non-Goals

**Goals**

- Leaving is a stated rule, not a credential accident.
- Background work is opted into, recorded durably, re-checked at start, budgeted,
  visible and cancellable.

**Non-goals**

- Any stored credential of the person's; a durable record is data, not a key.
- Resuming a foreground run after its grace has elapsed.

## Decisions

### D1 — Presence rule

A foreground run has one active stream attachment. On disconnect its execution
continues for a configurable reconnect grace (default 60 s), then the runtime
cancels the run and its children with reason `cancelled`. The original wall-clock
ceiling continues through detachment and reconnect. Execution ownership is
separate from the HTTP response generator so closing the socket does not destroy
the run before its grace expires. Nothing promotes it to background work.

Extend the existing `POST /execute/stream` contract with a mutually exclusive
reconnect request containing `reconnect.run_id` and optional
`reconnect.after_sequence`. It contains no prompt, execution context or grant.
Initial stream responses expose the server-generated run id in `X-Fred-Run-Id`
(including CORS exposure). SSE `id` uses the existing event `sequence`, monotonic
within that run. The client retains the run handle and last received sequence.
An absent cursor means no event was received; no new secret or signed handle is
introduced, and knowing a run id grants no access.

The admitting runtime verifies the reconnecting person's current token, matches
the recorded owner and re-checks standing and agent/team permission. It attaches
to the same execution, replays events strictly after the supplied cursor, then
streams live. A bounded buffer holds events across a disconnect; configured count
and byte bounds prevent unbounded growth. Reconnection neither repeats tools nor
creates admission/registration records, changes the person, or resets the budget.
Only one stream can be attached; concurrent reconnects are resolved atomically,
with a competing attachment refused. A rejected request never extends the grace.

The deployment keeps runtime routing affine to the admitting pod. A replica
without the run returns 404 and never starts or forwards an execution. A known
run cancelled after grace returns 410; an unavailable replay cursor (evicted or
ahead of the emitted sequence) returns 409 without partial success or attachment.
Missing/invalid credentials return 401; another person or a revoked permission
returns 403. Another person's attempt cannot cancel or alter the owner's run;
lost authority established for the owner ends it. Clients do not turn a reconnect
failure into an automatic execute request. The control plane routes no reconnect,
checks no credential on behalf of the runtime and stores no replay buffer.

A human-in-the-loop pause follows the same presence rule. Once its stream has
closed past grace, resuming requires the person's current token and a new
admission, never execution under the cancelled run's record.
Alternative rejected: keeping foreground runs alive until the ceiling — a flaky
network would silently grant work permission to outlive the person.

The reconnect request continues to require the directly authenticated owner;
a workload grant cannot attach to an existing foreground stream. Owner checks
and single attachment apply to every reconnect.

### D2 — Background runs are tasks

A new task kind carries the admission record as payload: person, roles, team,
agent, prompt, scope, mode, creator and creation time. Starting one is a
team-scoped endpoint requiring the same permission as running the agent
interactively; the platform-administrator task endpoint is unchanged.
Alternative rejected: a runtime-local queue — no durability across restarts and
no existing listing, cancellation or reconciliation.

The control plane keeps the private admission payload in its own agent-run task
storage linked to the existing task summary and event tables. Generic task
responses expose bounded status detail, not prompts or credentials. Start uses
`POST /teams/{team_id}/agent-instances/{agent_instance_id}/tasks`; input contains
only prompt and document/library scope. Target, person, creator, mode, runtime,
run identifier and limits are server-derived. Existing task list, event and
cancel routes apply creator or team-admin access to this kind, including mixed
kind lists. The runtime's configured workload client/subject and task queue come
from the trusted runtime catalog source configuration.

Background and schedule admission hold the common cross-replica lifecycle lock
through a fresh standing check and persistence of the task/private payload. The
same ordering applies to each scheduled occurrence. Personal-team access does not
bypass standing. Deletion cannot finish its purge and then have an older admission
recreate private state. Independent occurrence locks use a consistent ordering.

A cancellation received before workflow binding persists `cancelling` in the
existing task state, which subsequent nonterminal agent-run events cannot overwrite.
Binding, event updates and cancellation serialize on the task row; whichever
finishes second sends cancellation once an execution exists. A retried schedule
occurrence repairs a missing binding on its existing task before returning; it
never recreates a purged task or resets a terminal state. Scheduled task cancellation
targets the already-running occurrence parent, which owns and awaits its child;
the admission retains the child execution identity. Cancellation can therefore
arrive before child creation and still stop the occurrence.

### D3 — Execution under the pod scheduler

The task's workflow runs an activity on the agent pod's scheduler worker. The
activity re-checks standing and the agent permission for the recorded person,
fails closed, registers the execution through the foundation's workload-report
API, takes the grant parameters from the record, runs with the job's own budget,
and writes task events naming the mode. A delayed or scheduled start needs no
person token or active session. Registration and downstream request context identify
the runtime whose workload bearer they verify, with the recorded person as subject.
Delegation logs exclude identifiers under the foundation policy.
The credential provider
reads a durable record as well as a pod-local one; both are records written by
the platform.

The execution activity uses one attempt; a crash after side effects cannot repeat
tools through a default retry. Cancellation waits for activity cleanup and reaches
the execution task through heartbeats. A workload-only task-event receiver feeds
the existing task service and checks the recorded runtime's client and subject;
workers never write another service's tables. Reports contain bounded state and
reason, with event ordering and terminal idempotency enforced by the receiver.

Starting an agent-run worker requires `scheduler.agent_runs_enabled: true`,
which defaults to false independently of the existing `scheduler.enabled` setting.
Explicit opt-in validates the enabled Temporal scheduler, delegation, standing and
control-plane prerequisites and fails startup if they are missing. Existing
configurations that only enable the generic scheduler retain their startup behavior.

The background executor explicitly awaits closure of its nested runtime event
iterator in the consuming task. Terminal task reporting and activity completion
wait for run-scope, descendant and lifecycle-report cleanup, including early stops
on final, error, human-pause and cancellation paths.

### D4 — Schedules

A schedule is created with an explicit opt-in and the same record; each tick
starts one task and performs the same re-check. Removing standing or the
permission stops the next tick from running.

Schedule creation is a separate explicit `task-schedules` operation beside task
start. Schedule definitions have private control-plane metadata and owner/team
admin list and delete operations; cancelling an occurrence does not silently
cancel its schedule. Each tick creates one ordinary task occurrence through an
idempotent lifecycle operation using its deterministic workflow identity, then
executes the same fresh permission checks. Only a configured Temporal backend
admits durable work; a disabled scheduler has no memory-queue fallback.

### D5 — Visibility

Listing and cancellation are scoped: a person to their own runs, a team admin to
the team's. Results are task records; a produced conversation is attributed to
the person, never to the workload.

## Risks / Trade-offs

- [Reconnect grace hides a real departure] → bounded, configurable; the ceiling
  still applies.
- [Pod loss or replay-buffer eviction prevents reconnect] → explicit 404/409/410;
  no silent execution restart. Pod affinity is required for the successful
  reconnect path; cross-pod continuation is outside this lane.
- [Durable record tampered] → restrict server-side writes and protected fields;
  validate the record and re-check authority at start; audit changes under the
  foundation's data policy.
- [Roles in the record go stale] → refreshed at every start from the person's
  current state.

## Migration Plan

1. Complete the foundation's lifecycle-report contract and the single-subject
   model/standing rollout before admitting sessionless work.
2. Update the runtime contract and generated clients, then implement the presence
   rule, attachment lifecycle and replay behind the delegation flag. Enable after
   the frontend reconnect flow and deployment affinity pass the two-replica test.
3. Task kind, endpoint and activity with the pod scheduler disabled by default.
4. Verify reconnect, task and schedule authorization before shared enablement
   using synthetic test data.
5. Enable the pod scheduler per deployment; schedules last.

## Open Questions

- Per-job budget defaults; settled at implementation using the existing budget
  configuration. The attended reconnect grace defaults to 60 s.
