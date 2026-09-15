## Why

The self-test page proves retrieval, prompt delivery and authorization through
the real execution pipeline, but every turn it runs finishes well inside the
lifetime of the credential it was handed. The case that fails in real use stays
unproven: an agent whose work outlives that credential, and whose next call made
as the person is refused. The runtime forwards a turn's credential unchanged for
the whole turn and cannot renew it, so that failure reaches a user as an opaque
mid-stream error. The page needs a repeatable, deployment-local check that is red
while that limitation exists and green once in-turn renewal ships.

## What Changes

- Give the deterministic self-test agent a bounded hold before its call, and an
  authenticated-access mode that makes one metadata call as the person on each
  side of the hold instead of reading documents.
- Add a credential-expiry check to the Self-test page: it captures the signed-in
  session's current access token once, hands that one token to a single agent
  turn, and asserts that the authenticated call made after the token's expiry
  succeeds. The browser keeps refreshing its own session throughout, and the
  captured token never appears in a report.
- Size the hold from the captured token's own remaining lifetime plus a margin,
  bounded to a safe maximum; skip with the reason above that bound and where no
  realm is configured. Report an inconclusive run as a failure, never a pass.
- Record the check beside the existing self-test description in the testing
  guide.

## Capabilities

### New Capabilities

- `admin-self-test`: the in-browser self-test's credential-expiry check — which
  credential the turn runs on, how the harness agent holds before calling as the
  person, and what the verdict proves.

### Modified Capabilities

- Functional self-test: enrolling the harness agent no longer sweeps leftover
  instances of its template first, so concurrent runs keep theirs and each run
  deletes only what it created. Nothing then collects an instance whose run was
  interrupted before teardown — a closed tab, a reload, a crash — so that one
  instance stays until it is deleted by hand.

The authorization self-test keeps its behavior, and runtime token handling is
not changed by this change.

## Impact

- Agent: the harness graph agent gains two tuning fields, a hold ahead of its
  call, and an authenticated metadata call on each side of that hold.
- Frontend: the pipeline gains a turn that streams on a supplied credential; the
  Self-test page gains a sub-section with its own action and step report.
- Fixtures: one temporary agent instance per run, deleted by the run. No
  library, document, prompt or session is created, and no document is read.
- No realm configuration, runtime, execution-contract or authoring-surface
  change.
