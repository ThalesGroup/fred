## 1. Preserve the cause through reporting

- [x] 1.1 Make the shared handler read the denial's existing undecided flag
      instead of discarding it; verify a denial raised as undecided and one
      raised as decided are reported differently, and that a test asserting the
      distinction fails when the flag is ignored again.
- [x] 1.2 Separate a refusal on organization standing from a refusal on a
      missing permission at the point the denial is reported; verify each of the
      three causes — standing, permission, unavailable dependency — is
      recoverable from the reported denial alone.
- [x] 1.3 Confirm every raise site sets the flag it means; verify each site that
      denies for an unconsultable dependency is covered by a test, and that a
      site left unflagged is reported as decided rather than silently undecided.
      All eight sites inspected: the five reporting an unconsultable dependency
      are exception or absent-result paths, the three reporting a decision are
      standing checks that returned false. Line coverage measured across the
      library suite shows all five unconsultable-dependency sites exercised --
      transport failure, an error returned for the standing check, an absent
      standing result, and both paths of the template the store-backed engine
      replaces. An unflagged denial is covered by a test proving it reports as
      decided. One decided site remains unexercised, outside this task's clause.

- [x] 1.4 Report a dependency that is already unreachable when its client is
      established as an unconsultable dependency rather than as an unhandled
      failure; verify a call against an unresolvable address raises the undecided
      denial and that its message carries no transport detail.

## 2. Classify an outage as an outage

- [x] 2.1 Report a denial caused by an unconsultable dependency with a
      server-side failure status; verify a decided refusal keeps the
      client-side refusal status unchanged.
- [x] 2.2 Prove the request still fails closed: verify that a request whose
      authorization dependency cannot be consulted is refused, and that no path
      grants access when the dependency is unavailable.

## 3. Make a denial legible

- [x] 3.1 Emit one denial record carrying subject type, action, resource type
      and whether the decision was reached; verify the record's fields separate
      three denials that differ only in cause.
- [x] 3.2 Keep identifiers out of the record by construction; verify no denial
      record contains a person, team or resource identifier, and none contains a
      credential or a fragment of one.
- [x] 3.3 Bound the caller-facing detail so it distinguishes a standing refusal
      from a permission refusal while naming no person, team or resource; verify
      an unavailable dependency produces a detail that does not claim the person
      lacks access.

## 4. Audit a standing refusal

- [x] 4.1 Emit a standing refusal as an audit event on the surface that records
      delegation grant decisions, carrying outcome and reason and no person
      identifier; verify a permission refusal emits no standing refusal event.

## 5. Adoption and regression

- [x] 5.1 Take the library up in the platform backends, the agent runtime and
      each first-party application backend; verify every existing authorization
      test passes unchanged, since no rule that grants or denies access changes.
- [x] 5.2 Verify the grant and deny outcome is unchanged for each cause: a
      request granted before this change is granted after it, and a request
      denied before it is denied after it, with only the report differing.

## 6. Verification

- [x] 6.1 Prove the three causes are distinguishable end to end on a running
      deployment: refuse one request on standing, one on a missing permission,
      and one by making the authorization dependency unreachable; record the
      three resulting statuses and log records. Verified against a deployed
      receiver running with standing enforcement on. A delegated request naming a
      person holding no organization standing returned 403 with the standing
      detail and emitted a standing-refused audit event carrying outcome and
      reason; the same request naming a person who holds standing but is not a
      member of the team returned 403 with the permission detail; a request whose
      store stopped answering after the client was established returned 503 with
      the unavailable detail, and the denial carried no trace of the underlying
      transport error. One limit: the unavailable case was induced inside the
      deployed pod against the deployed engine and handler, because taking the
      shared store down was out of scope. The separate case of a store already
      unreachable when its client is established is covered by task 1.4.
- [x] 6.2 Confirm no deployment change was required: the same configuration
      drives every adopting service, and no new configuration value is
      introduced.
