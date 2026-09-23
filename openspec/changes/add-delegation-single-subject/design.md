## Context

The service role is today an identity marker on the bearer that a dozen call
sites across the runtime, the control plane and Knowledge Flow turn into team,
tag, table or knowledge-base access without a relation, written for one
evaluation worker. The authorization engine exposes `has_permission`,
`has_permissions` and `lookup_resources`; every backend goes through it and no
code talks to the relationship store directly. Tags carry direct per-person
`owner` grants and team read includes `public`, so a gate placed on team relations
alone would not reach them. Personal spaces carry only their owner's editor tuple.
The control plane already runs startup reconciliations over the team registry
before it serves. Deleting a person through the platform today deletes only the
identity-provider account. See proposal.md — Why.

## Goals / Non-Goals

**Goals**

- No access decision without a person, except explicit caller-only policies.
- One standing requirement that reaches every object type and every caller.
- Deleting a person through the platform stops their runs through the ordinary
  denial path.

**Non-goals**

- Background runs, presence rules, per-run resource/action scope (later changes).
- Suspend and reinstate operations in the platform's own user administration;
  deletion is the only platform operation that ends standing.
- Mirroring identity-provider account status into standing; a disable there ends
  interactive access when the person's token expires.

## Decisions

### D1 — Two principals in the request context

`caller` is the identity authenticated by the bearer, including its client id;
`subject` is the authenticated person or the asserted person built from a grant.
Authorization uses the subject; caller-only policies name the caller. The
service-role predicate is true for a service caller carrying that role and false
for an asserted person. A true caller predicate never substitutes for subject
authorization on a delegated operation. Alternative
rejected: keeping one user object and flagging it — every existing call site would
have to remember the flag.

### D2 — Active-account requirement inside the engine

The engine's public `has_permission`, `has_permissions` and `lookup_resources`
become template methods: for a person subject they add `organization#active` to
the same batch request and return allowed only if both hold; a list lookup checks
standing first. Missing or unavailable standing raises a distinct bounded denial,
which list, batch and filtering helpers preserve through the receiver's response
(403 for a refusal, 503 when standing cannot be consulted) and MCP error mapping
to terminal `authority_lost`. Ordinary lack of an
object permission can still return false or an empty authorized-resource set.
Standing denial cannot be swallowed as an empty result, tool text or a generic
server error. Checks that cannot establish standing never return allowed.
Subclasses implement the raw operations only, so no engine and no caller can skip
the gate. Alternatives: a schema-side gate (misses direct tag grants and public
reads unless every tag gains an organization edge with a backfill); a hybrid (two
places to keep consistent).

`StandingAuthorizationError` extends the existing authorization error with a
bounded denial that receivers preserve. Standing enforcement follows delegation, off for
migration. Standing is checked at the store's higher consistency, so a suspension
written before a decision is observed by it.

Enabled receivers require a compatible selected model and the shared
`organization#standing_ready` marker. The control plane writes the marker at every
start, after the model validates and the default standing entry is written, so its
presence shows that the default entry exists; without that entry every person would
be refused. The marker is an organization-to-itself relation in the authorization
store; it provides startup evidence without a receiver calling the control plane.
An old pinned model, missing marker, unavailable store or noop authorization engine
cannot pass readiness, and a receiver refusing to start reports that account
standing is not ready. Ordinary authorization still checks current `active` on
every decision; the startup marker never substitutes for that check.

### D3 — Standing is a platform-owned block list

The model defines, on `organization`:

```
define suspended: [user]
define active: [user:*] but not suspended
define standing_ready: [organization]
```

The platform is the only source of standing. One default standing entry,
`user:*` `active` on the platform organization, puts every person in good
standing; a direct `suspended` tuple takes one person out of it. Service
identities evaluated as a person subject, such as knowledge-base pod accounts, are
covered by the default entry like any person; their access still depends on their
own relations. No identity-provider listing, account status or administration
right is read to decide or change standing, so standing initialisation needs no
identity administration.

Writers. With delegation enabled, the control plane's startup validates the
model, writes the default standing entry and then the ready marker, reads the
marker back and refuses to start if any step fails. It does this on every start,
before its other startup reconciliations; the writes are idempotent. With
delegation disabled it writes none of them. Person deletion writes the
suspension. No other code path writes or deletes `active`, `suspended` or
`standing_ready` on the platform organization: the generic relation add and delete
operations refuse them, and removing all relations of a person never removes a
`suspended` tuple. A locally valid JWT proves neither current account status nor
permission to change standing, so neither authenticated requests, personal-space
self-heal nor grants write these relations.

Identity-provider account changes do not reach standing. Disabling or deleting an
account there ends interactive access when the person's current token expires; the
person's delegated runs, background tasks and schedules keep their authorization
until the person is deleted through the platform.

Alternative rejected: an allow-list of per-person `active` tuples copied from the
identity provider's enabled accounts by a periodic sweep. It makes standing depend
on identity administration and on a listing that can fail or be partial, leaves a
cadence-long window after every disable, and needs its own health signal and a
second lock ordered against deletion.

### D4 — Deletion suspends before the account is deleted

The delete route keeps its permission check and root-administrator protection.
It then resolves the identity-provider administration client before changing
anything; when identity administration is not available it fails with service
unavailable and nothing is changed. Under the run lifecycle lock, in one SQL
session, it writes the suspension when the engine enforces standing, removes the
person's other relations when relationship authorization is enabled (the
suspension survives), and purges admission records, background task rows and
schedules. Only after that transaction commits does it delete the
identity-provider account. A missing account there is reported as not found after
the cleanup; any other failure propagates with the person already suspended, and a
retry repeats the idempotent cleanup and completes the account deletion. An id
that names no person, the wildcard `*` or a userset containing `#`, is refused as
not found before any change.

The relation cleanup of a person reads only the tuples naming that person: one
targeted read per object type whose model accepts a person directly, plus `group`,
which older stores may still hold, with the reads run together and the standing
tuples on the organization skipped. Its cost grows with that person and not with
the store. The engine refuses the wildcard `*`, a userset id and an empty id
before any read, because none of them names one person.

While the control plane's delegation is off, deletion writes no suspension and
standing is not enforced; the deleted person has no identity-provider account left
and their relations, records, tasks and schedules are gone.

A suspension applies from the person's next authorization decision. Work already
authorized is not interrupted; a delegated run ends with `authority_lost` at its
next receiver call and cancels its children. Late run-end reports follow the
foundation's deleted-record 404 behavior and cannot recreate a purged admission
record; the runtime still ends locally. Receivers never call the control plane or
the identity provider to resolve standing, and fail closed when their standing
check itself is unavailable.

New run, background task, schedule and occurrence admissions explicitly check
standing even when team access resolves through a personal-team shortcut. The
fresh check and persistence share the account-deletion lifecycle critical section;
an earlier check outside it cannot authorize a later write after purge. Terminal
reporting handles a purge between lookup and write as the same deleted-record 404.

Delegation uses trusted client/subject pairs and current person permissions. The
foundation's retained own-credential runtime guards still apply; this step does
not provide complete user/agent parity.

### D5 — The evaluation worker is an allow-listed caller

The worker sends the grant parameters naming the campaign creator with its own
workload token; receivers and the runtime trust its exact client/service-account
subject pair. The runtime accepts the parameters at admission as it would at any
receiver, writes the run record from them with `mode = background`, registers it
using the runtime's own workload token under the foundation's lifecycle-report
contract, and makes its own
downstream calls for that person. No person token or session is needed. Admission
records retain the worker; the registry and downstream request context retain the
runtime as their authenticated caller. Logs exclude all identifiers under the
foundation policy. A
reported origin is never substituted for a bearer-authenticated identity.
The campaign record, written when the creator
was present, is the authorization the worker acts on. Alternative rejected: a
caller-only policy for evaluation (one role-based path left, no attribution).

### D6 — Whitelist applies to the subject

The local whitelist accepts explicit `uid:<subject>` entries alongside existing
email entries. Authenticated people may match their UID or email; asserted people
may match only their UID. An email-only list cannot admit an asserted person until
its UID entry is provisioned. This configuration migration belongs to final
deployment integration and requires no per-call identity-provider or control-plane
lookup.

Where a deployment enables the whitelist access control, an asserted person is
checked against it exactly as an authenticated one.

## Risks / Trade-offs

- [A person disabled in the identity provider keeps their delegated and scheduled
  runs] → by design standing follows the platform only; interactive access ends
  at token expiry, and an administrator deletes the person through the platform
  to stop their runs from the next authorization decision.
- [The default standing entry is missing from the store] → every person would be
  refused; the control plane rewrites it on every start before the ready marker,
  receivers refuse to start without the marker, and the generic relation API
  cannot delete it.
- [Identity-provider deletion fails after the suspension] → the person is already
  refused; the delete reports the failure and a retry completes it.
- [A suspension cannot be lifted through the platform] → deletion is final in this
  change; an account that reappears under a deleted person's identifier stays
  refused until a reinstate operation exists.
- [A person deleted while the control plane's delegation is off has no suspension
  when delegation is later enabled] → they have no identity-provider account,
  relations, admission records, tasks or schedules left, so no path acts for them.
- [Evaluation breaks if the worker's change lags] → shortcuts are removed behind
  the same flag; the flag stays off where evaluations run until the worker sends
  the grant parameters.
- [Engine refactor touches every backend] → template methods keep the public
  signatures; the noop engine follows the same shape.

## Migration Plan

1. Add `organization#suspended` and the derived `organization#active` to the
   canonical model beside `standing_ready`, and regenerate its JSON; publish the
   model before tuple writes or checks use the new relations.
2. Update every reader and writer to that model, including explicit model-ID pins,
   while the gate is still off. Activate the control plane first: its startup
   validates the model and writes the default standing entry and the ready marker.
   Activate the remaining receivers afterwards; each refuses to start on an
   incompatible model or a missing marker, so a partially migrated deployment
   cannot pass the rollout gate.
3. With the gate on at the control plane, prove that deleting a person through
   the platform suspends them before their identity-provider account is deleted,
   that the suspension survives relation cleanup and an old-token request, and
   that it ends a delegated run at its next call.
4. Activate the principal pair, standing enforcement, whitelist checks and shortcut
   removal together in isolated verification. Enable only where the evaluation
   worker sends grants, after
   checking the foundation's rollout prerequisites. Its interfaces precede this
   change; its shared-environment rollout is verified together with this gate.
   Verify migration with a pinned
   old model as well as a clean deployment. Rollback disables the new gate/flag
   before reverting readers; the additive model and tuples may remain, and a
   retained suspension has no effect while the gate is off.
5. Verify standing, authorization, migration and identifier-free delegation logs
   with synthetic test data before shared enablement.

## Open Questions

- How a suspended person is reinstated, and whether the platform needs a suspend
  operation separate from deletion; both are outside this change.
