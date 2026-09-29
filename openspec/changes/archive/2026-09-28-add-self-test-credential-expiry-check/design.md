## Context

See [proposal.md](proposal.md) for scope. Verified constraints:

- With delegated execution off, a turn runs on the credential its execution
  request carried, and nothing in the runtime replaces that credential while the
  turn is in flight. With it on, that credential authenticates admission only;
  the turn holds no person credential and every call carries the platform's
  workload credential and a grant naming the person.
- The page can read the signed-in session's current access token and its
  remaining lifetime. Reading the value does not pin the session to it: the
  browser keeps refreshing the session on its own schedule, so a captured value
  ages out while the person stays signed in.
- The graph runtime imposes no per-node or per-turn duration cap.
- An authenticated metadata call made as the person is meaningful on an empty
  result as much as on a populated one, so it needs no library or document to
  prove that the credential was accepted.
- A refused call inside a graph node does not surface as an error event: the
  turn ends with a final answer carrying the error text, so the check
  classifies that answer without ever echoing it.
- Status and thought events stream live as a node emits them, and a node that
  raises keeps what it already emitted. The hold keeps the stream alive with
  periodic thoughts and emits one status at its end, whose arrival marks when
  the post-hold call began.
- Enrolling an agent instance grants no access of its own, and an instance is
  addressable only by its owner, so a run-scoped instance is a safe fixture.

## Goals / Non-Goals

**Goals:** a real expiry on any deployment that has a realm, with no realm
change, no password and no document; a verdict that cannot go green by
accident; no change to runtime token handling.

**Non-Goals:** renewing the credential (a separate change); running the check as
another account; simulating expiry inside the runtime; changing the functional
or authorization self-tests.

## Decisions

### The turn runs on the session's own token, captured once

The check reads the signed-in session's current access token once, after
ensuring the session is fresh, and hands that single value to the one turn under
test. Nothing else in the run uses it: preparation, enrollment and cleanup go
through the live session, which the browser keeps refreshing as usual. The
captured value is therefore a credential that genuinely expires mid-turn while
the person remains signed in, and it never reaches a step report.

### Hold sized from the captured lifetime, bounded

The hold is the captured token's own remaining lifetime plus a margin, so the
wait is as short as the deployment's token lifetime allows and the post-hold
call always lands after expiry. It is bounded to a safe maximum on both sides:
the agent clamps the configured hold, and the check skips with the reason rather
than starting a run it would have to clamp. The verdict then compares the
recorded expiry against the observed end of the hold instead of trusting the
configured number, so an enrollment that silently dropped the hold cannot pass.

### An authenticated metadata call, not a document read

The harness calls the metadata service as the person on each side of the hold.
The first call establishes that the captured credential was accepted at all, so
a run that never had working access reads as inconclusive instead of as an
expiry. The second is the call under test. Neither reads a document, which is
what lets the check run with no library, document, prompt or session fixture —
and keeps a failing run from leaving corpus state behind.

### One temporary agent instance as the only fixture

Each run enrolls its own instance, carrying the hold and the access-check mode
as tuning, and deletes it in a `finally`, tolerating an instance that is already
gone. Enrollment removes no other instance of the same template, so a second run
elsewhere keeps its own. Cancellation takes the same teardown path as a finished
run, and a cancelled creation is reported as cancelled rather than as a creation
that failed.

### Renewal-marker contract

The harness reports renewal when the credential it holds changes between the
start of the post-hold call and its completion: it reads the runtime context's
access token on each side of that call and emits the renewal marker only when
the two differ. A renewal mechanism that replaces the credential at admission —
before the node runs — leaves both reads equal, so the harness observes no
renewal and the check reads inconclusive rather than green. Any mechanism that
renews a delegated credential must therefore make the replacement observable to
the harness.

### Absent-credential marker

In access-check mode the harness also reports when the post-hold call succeeded
while it held no person credential on either side of that call. In the runtime a
turn without a person credential is a delegated turn: without delegation the
request's credential is always stamped into the turn, and a call with neither a
person credential nor a delegated provider is refused before it is sent. The
marker states only what was observed — no person token was held — so the page's
wording claims no more than that.

### Verdict

Pass requires all of: the first authenticated call observed, the hold observed
to end at least a tolerance after the captured expiry, the post-hold call
reported as succeeded after that, and either renewal or the absent-credential
marker observed. Anything short of that
fails — as inconclusive where the run proved nothing, so a misconfigured hold,
an older agent build or a credential that outlived the wait cannot pass. A
refusal fails with one fixed explanation whether it arrives as an execution
error or as the turn's final text; upstream response text and credential values
never reach the report. A turn refused before it started is reported as such,
never as expiry during execution.

## Risks / Trade-offs

- The wait is the deployment's own token lifetime, so a realm with a long
  lifetime pushes the check past the bound and it skips — visible, but proving
  nothing there.
- Heartbeats keep the stream alive through the hold; a proxy whose idle timeout
  is shorter than the heartbeat interval would still cut the run.
- The renewal marker is an observation of the harness's own credential, not of
  the renewal mechanism itself, which is why the contract above has to be
  stated rather than inferred from a green run.
