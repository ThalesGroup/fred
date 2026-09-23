## Context

See proposal.md — Why.

Three constraints shape the approach:

- The typed authorization denial already carries an `unavailable` flag, set at
  eight raise sites. Nothing reads it. The distinction the specs require is
  therefore recoverable without changing any authorization rule.
- The shared handler is registered by every first-party backend, the platform
  backends and the agent runtime. Its behaviour is the single point where all
  of them report a denial, so one change reaches all of them and any regression
  reaches all of them too.
- The refusal must stay fail-closed. An unavailable dependency currently denies
  access; changing only how that denial is *reported* must not turn it into a
  grant.

## Goals / Non-Goals

**Goals:**

- Make the cause of a denial recoverable by an operator from one log record.
- Classify an unavailable dependency as an availability failure.
- Keep the caller-facing detail bounded, so a denial discloses nothing about
  who was denied or what exists.

**Non-Goals:**

- Changing any rule that decides whether access is granted. Every request
  granted today is granted afterwards, and every request denied today is denied
  afterwards.
- Enabling organization standing enforcement anywhere it is not already
  enabled. That activation is owned by the in-flight standing change and
  sequenced after a compatible model and completed seed.
- A metrics or tracing surface. Denials become legible on the existing log and
  audit surfaces; a counter is a separate concern.

## Decisions

**Distinguish at the handler, not at the raise sites.** The flag is already set
correctly at every raise site; the loss happens when the handler rebuilds the
detail from the action and resource and drops the message. Reading the existing
flag in the handler is the smallest change that satisfies the specs, and it
avoids touching eight authorization call paths.
*Alternative considered:* a distinct exception subclass per cause. Rejected —
it multiplies types for a distinction one existing field already carries, and
every handler registration would need to learn the new types.

**Report an undecided denial as a server-side failure.** A dependency outage is
not a statement about the caller, and reporting it as a client refusal hides
outages from availability alerting and invites clients to treat a transient
outage as a permanent refusal.
*Alternative considered:* keep the client-side status and rely on the log line
alone. Rejected — the status is what monitoring and client retry logic consume,
and the log line is not visible to either.

**Carry the cause as fields, not as prose.** The record names the subject type,
action, resource type and whether the decision was reached. Prose that varies by
cause is not machine-separable and tends to accumulate identifiers.

**Keep identifiers out by construction.** The record carries types and actions,
never the person, team or resource identifier, so no redaction step is required
and none can be forgotten.

**Audit a standing refusal on the existing audit surface.** Delegation grant
decisions already emit there, and a standing refusal is the same class of fact:
a decision about whether a named person may act. Reusing that surface avoids a
second audit channel with its own retention and format.

## Risks / Trade-offs

- **A client branching on the client-side refusal status sees a new status for
  the outage case.** → The change is declared breaking in the proposal. The new
  status applies only when the dependency could not be consulted, which today is
  an outage the client cannot act on anyway; a client treating any non-2xx as
  refusal is unaffected.
- **Alerting that counts client-side refusals loses the outage signal it never
  knew it had, while availability alerting gains it.** → Both surfaces change in
  the same release, and the proposal names dashboards as impacted.
- **A cause-bearing detail could become an oracle.** A caller learning
  "standing" rather than "permission" learns something about the account.
  → The detail is bounded to the caller's own account state, which the caller
  may already observe by being unable to sign in; it names no team or resource,
  so it discloses nothing about what exists or who else holds access.
- **The handler is shared, so a defect reaches every backend at once.** → The
  change is confined to reporting, with the deciding paths untouched, and the
  acceptance tests assert the grant/deny outcome is unchanged for each cause.

## Migration Plan

1. Land the handler and error-type changes in the core security library.
2. Release the library and take it up in the platform backends, the agent
   runtime and the first-party application backends. No configuration changes
   and no deployment changes are required: the behaviour follows the library.
3. Update dashboards and alerts so outage-caused denials are counted on the
   server-side failure surface.

Rollback is the previous library version. No data is written and no
configuration is introduced, so a rollback restores prior behaviour exactly.

## Open Questions

- Whether the denial record should also carry the caller's workload client
  identity when the subject is an asserted person. It is useful for tracing a
  delegated call, and it is an identifier, so it needs a privacy decision. It
  can be added later without changing these specs, because the record's required
  fields do not depend on it.
