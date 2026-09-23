## Why

The delegated execution grant lets a run act for a person, but several places in
the platform still let any caller holding the service role read teams, tags,
tables or knowledge bases, or run agents, without a person and without a
membership check, and nothing stops a deleted person's runs once their
credential is no longer involved. Both must be closed before delegated calls
become the main road: with the grant, standing is the only thing that ends the
runs of a person removed from the platform.

## What Changes

- Every request carries two principals: the caller (the workload behind the
  bearer) and the subject (the person, authenticated or asserted). The service-role
  predicate evaluates the caller only; an asserted person never satisfies it.
- Standing becomes a required fact: the shared authorization engine requires the
  person's `organization#active` relation on every check, batch check and list
  lookup with a person as subject. Missing or unavailable standing produces a
  typed denial, including through list/filter paths, rather than empty success.
- Standing is a block list owned by the platform: every authenticated person is
  in good standing unless the platform has suspended them. The model derives
  `active` from one default standing entry covering every person, minus the
  persons holding `organization#suspended`. Service identities checked as people
  are in good standing under the same rule.
- With delegation enabled, the control plane's startup validates the model and
  writes the default standing entry and the `standing_ready` marker on every
  start, failing closed. Deleting a person through the platform is the only
  operation that ends standing: it suspends the person before their
  identity-provider account is deleted, and the suspension survives the removal
  of their other relations. Only this lifecycle path writes or deletes the
  standing relations; a user JWT, a grant or the generic relation API never does.
- Identity-provider account changes do not change standing. Disabling or deleting
  an account there ends interactive access when the person's token expires; it
  does not stop their delegated or scheduled runs. Deleting the person through
  the platform does, from their next authorization decision.
- Publish the authorization model containing `active`, `suspended` and
  `standing_ready`, update pinned model IDs across readers and writers, and start
  the control plane before enabling the gate on receivers.
- Every service-role shortcut that grants access without a person is removed:
  runtime admission; the control plane's team-permission validator and its
  product and knowledge-base services; Knowledge Flow's ingestion, tabular,
  library-sync and tag services. The evaluation worker acts for the campaign
  creator as an allow-listed caller sending the grant parameters with its own
  workload token.
- The runtime accepts a grant as admission input: a run started by an
  allow-listed caller for a person writes its run record from the parameters,
  registers it under the foundation's workload-report contract, and makes its own
  downstream calls for that person. Admission records retain the worker; receiver
  context identifies the runtime whose bearer was verified. Logs exclude identifiers.
- The whitelist access control applies to asserted persons as to authenticated
  ones.

## Capabilities

### New Capabilities

- `delegation-subject-and-standing`: caller/subject separation, the standing
  requirement on every authorization decision, its lifecycle, and the removal of
  role-based access without a person.

### Modified Capabilities

None. Builds on `delegated-execution-grant`.

## Impact

- Shared security library: principal pair in the request context; engine gate on
  check, batch check and list lookup; typed standing denial; standing lifecycle
  writes (default entry, suspension, ready marker) and the generic relation API's
  refusal of them; whitelist on asserted persons; authorization model and its
  generated JSON.
- Control plane: startup standing initialisation; person deletion that suspends
  before deleting the identity-provider account; team-permission, product and
  knowledge-base services without the shortcut; runtime-binding endpoint trusting
  the evaluation worker's exact client/service-account subject pair.
- Knowledge Flow: ingestion, tabular, library-sync and tag services without the
  shortcut.
- Runtime: grant-as-input admission; shortcut removed; the evaluation worker's
  exact client/service-account subject pair trusted.
- Evaluation worker (separate repository): sends the grant parameters for the
  campaign creator with its own workload token — a prerequisite for enabling
  delegation where evaluations run.
- Sequencing: after the shared/receiver interfaces in `add-delegated-execution-grant`,
  not after its shared-deployment rollout; both rollout gates are verified together.
  The flag may be enabled in
  shared environments only once the new model is selected, the control plane has
  written the default standing entry and the ready marker, this change
  is verified and the worker's change has landed wherever evaluations run.
