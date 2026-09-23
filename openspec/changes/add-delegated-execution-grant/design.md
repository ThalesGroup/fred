## Context

Admission validates the person's token locally against the identity provider's
published keys and asks the authorization engine whether the person may use the
agent in the team; the pod then reuses that bearer for every downstream call, and
the runtime context never holds a refresh token. One wrapper covers the
tool-protocol route while native clients bypass it, and members of an agent team
share the token. The terminal error event carries only a message. Per-call
timeouts exist; no run ceiling does. The realm issues 300-second access tokens.
Receivers validate tokens locally against the provider's keys, all against the
same shared client id, and check the token's audience only under the hardened
profile. The realm's default scope resolves audiences from client roles, and
the provisioning gives every service account the service role on that shared
client, so a workload token already carries the audience every receiver
expects. The
workload client secret is read once, when the token provider is constructed.
Knowledge Flow mounts its MCP tools behind the same user dependency as its REST
routes. At run
start the runtime calls the control plane's runtime-binding endpoint with the
person's bearer; that endpoint verifies the person and applies team
authorization. The runtime's own workload client exists in the shared library
and in its configuration but is not used on the agent path. Background tasks
already have a durable record with their creator and team; attended runs have
none. Every shipped `user_token` MCP server is a Knowledge Flow route. See
proposal.md — Why.

## Goals / Non-Goals

**Goals**

- The person's credential stays at local admission and owner-reattachment boundaries,
  never in execution state or downstream requests.
- Every delegated call authenticates a workload and identifies an asserted person.
- No grant signing or key custody; reuse the Keycloak verifier and validate claims locally.
- Authority loss is typed and terminal; every run has a ceiling.
- Rollout behind a flag with no silent fallback.

**Non-goals**

- Token exchange or any renewal of the person's credential.
- Removing the service-role shortcuts (next change).
- Background or scheduled runs; per-run resource/action scope.
- A pod-bound workload credential (operations change).
- Third-party MCP servers acting for a person.

## Decisions

### D1 — The person is a statement; trust comes from the caller

The workload token renews from the platform's own secret and names the program.
The person is carried as a plain statement that a receiver accepts only because
the program making it is on the receiver's allow-list of programs that may speak
for people. The statement is not independent proof of user consent or admission.
A compromised trusted workload can assert another person and exercise that
person's permissions on delegation-capable endpoints; caller allowlisting and
registry correlation do not establish the person's consent.
Alternatives rejected: a signed grant (additional signing and key custody);
a random reference resolved at the control plane (a dependency on every
call at every receiver); token exchange (on the pinned provider an exchanged
token is bound to the person's session, cannot carry offline scope and issues no
actor claim, so it neither serves an unattended run nor distinguishes an agent's
call from the person's own).

### D2 — Grant content and transport

Three request parameters: `person` (the subject identifier), `run` (the run
identifier) and `agent` (the agent identifier). They travel as body fields when
the request has a body and as query parameters otherwise, so every receiver
endpoint declares them in its API contract and validates them like any other
field. For tool servers they travel outside tool arguments, in the protocol's
out-of-band request metadata or on the server endpoint. The set is minimal by
design: the team is already part of every team-scoped request, roles are
relations in the authorization graph, and scope and actions arrive with later
changes as further parameters. A header was rejected: outside the contract,
unvalidated, and invisible to the generated clients.

### D3 — Acceptance at the receiver

Bearer first (trusted issuer/key, allowed algorithm, validity, access-token purpose
and intended audience), then the configured workload service-account identity,
the receiver's trusted client/subject binding and the parameters,
then the asserted principal. A bearer whose client is not allow-listed leaves the
parameters ignored, the request without a subject, and the attempt audited. An
allow-listed bearer without parameters is a service caller acting for nobody. The
grant has no lifetime of its own: it is worth exactly what the bearer beside it
is worth, and it is presented on every call, retries included. A receiver never
forwards it.

Bind the verified client to its configured service-account subject; `azp` alone
does not establish a workload identity. Browser/user tokens cannot satisfy that
binding, even with the same client claim or service role. Keycloak clients used
for delegation have only required service-account flows enabled; user-facing
clients and workload clients are distinct.

Each receiver trusts explicit workload client/subject pairs and applies the
asserted person's function, object, field and team permissions. Administrative
actions rely on their normal user authorization unless an explicit own-credential
guard applies.
The control plane authorizes its own APIs locally and is not queried by other
receivers for delegation decisions. Run-end keeps the caller-only reporting
identity and record-ownership checks in D5.

The shared configuration has `caller_policies` entries containing `client_id` and
the service-account `subject`. Caller-policy validation rejects unknown fields.
Existing `allowed_callers` strings alone never authorize a delegated subject.
Enabling delegation requires exact issuer and audience validation using the
receiver's existing token verifier. Access-token purpose comes from
signature-verified claims, never an unverified header.

MCP mount authentication reads the grant only from the outer request query and
never consumes the protocol body. The local MCP adapter removes grant fields from
model-controlled tool arguments and forwards only the validated outer grant into
the inner REST request. Both boundaries verify workload identity and preserve
user authorization.

#### Retained own-credential endpoint restrictions

These runtime endpoints continue to reject an asserted/delegated person when
authentication is enabled. Paths omit the configured deployment base prefix;
the compatibility endpoint is mounted at `/v1`.

| Purpose | Endpoints |
| --- | --- |
| Conversation history | `GET /agents/sessions`; `GET /agents/sessions/{session_id}/messages`; `DELETE /agents/sessions/{session_id}` |
| Checkpoints | `GET /agents/checkpoints`; `GET /agents/checkpoints/{session_id}`; `DELETE /agents/checkpoints/{session_id}` |
| Runtime diagnostics | `GET /agents/kpi-turns`; `GET /agents/audit-events` |
| Capability configuration | `POST /agents/capabilities/{capability_id}/validate-config`; `POST /agents/capabilities/chat-controls` |
| OpenAI-compatible execution | `POST /v1/chat/completions` |
| Foreground reconnect | `POST /agents/execute/stream` with a reconnect request |

An own-credential guard uses the identity authenticated directly by the bearer;
it is not a universal requirement for a human token. Native execute, evaluate
and new stream admissions already support delegated subjects. The reconnect
branch retains its direct-identity, owner and single-attachment checks. No guard
listed above is relaxed in this step, so complete user/agent parity is not claimed.
Caller-only product reporting and publication also retain their existing workload
identity and record/resource ownership authorization.

### D4 — The credential provider reads only the run record

The provider composes the outbound credentials from the record admission wrote:
person, agent and run. After admission, no request argument, tool input or model
output can change them. Every outbound client asks the provider at call time, and children
receive the provider rather than a value; each member of an agent team names its
own agent identifier with the shared run.

### D5 — Every run is registered, off the call path

Interactive admission verifies the person's token at the runtime. The dependent
single-subject change also admits runs from a trusted workload's bearer and
grant. In either case, the runtime-binding call registers the admitted record
using the runtime's own workload bearer and record-derived grant parameters;
the person's credential is never sent to the control plane under delegation.

The control plane verifies the reporting workload's token, requires its client
on the allow-list, and applies its ordinary team permission check to the asserted
person. It records person, team, agent, reporting program, start time and ceiling.
The reporting program comes from the verified bearer, never a claimed client id.
The person remains an assertion by that program, not a person authenticated by
the control plane. Invalid or untrusted bearers and denied subjects cannot write
a record. An admitted run does not start execution if registration fails.

The runtime reports the end with its workload bearer. Run-end is an explicit
caller-only operation: only the recorded reporting client can append an allowed
terminal outcome to its existing run, even after the person's standing is lost.
It cannot change the person or scope or authorize more execution. Runtime
admission retains the incoming caller in the lifecycle record; downstream request
context carries its own authenticated caller. Identifiers remain in product
records and request context, never in log sinks. The registry serves listing and
cancellation; it does not establish per-operation security audit attribution.
No receiver consults it on a call. This
is lifecycle reporting, not certification of a delegation or a credential service.
After an execution stop, this narrow terminal report is the only permitted further
outbound operation for the run; it cannot restart tools or data access. If account
deletion has already purged the record, run-end returns 404 and the runtime treats
it as a deleted record, without recreating it, retrying or changing the local
terminal outcome. Recording an end requires a retained lifecycle record.

The product API adds `POST /agent-runs` for registration and runtime-binding
resolution in one call; the existing binding GET remains read-only. Its body
selects exactly one of `agent_instance_id` and direct `agent_id`, with `team_id`
required for managed execution, admission `started_at`, the deployment default
`run_ceiling_seconds`, `mode`, and optional recorded `origin_caller`. Person,
run and acting agent come only from the authenticated grant; a target mismatch
denies registration. The response contains `run_id`, the effective
`run_ceiling_seconds`, and `binding` for a managed instance. The managed override
comes from stored tuning, never the request. Direct development execution remains
available outside the hardened profile, with standing checked and team permission
checked when scoped; its already-authorized runtime supplies the trusted template
ceiling. Direct execution stays unavailable under the hardened profile.

`POST /agent-runs/{run_id}/end` accepts only a terminal `outcome` and optional
declared stop `reason`. Its explicit caller-only policy requires the same verified
client and service-account subject recorded at registration. It does not resolve
an asserted person or check their current standing. Matching repeat terminal
reports are idempotent; conflicting outcomes return 409. Missing records return
404. Neither registration nor completion retries automatically. Registration is
serialized with account deletion: the fresh standing check and record insertion
share the same cross-replica critical section. Personal-team access does not bypass
standing. Every execution surface, including the OpenAI-compatible route, completes
registration and finalizes the effective ceiling before execution; failed admission
cleans up the local record. A purge between the initial completion lookup and the
terminal write also returns 404. The registry stores lifecycle metadata only.

### D6 — Typed terminal outcome

An optional `reason` enum on the existing terminal error event:
`authority_lost`, `run_ceiling_reached`, `child_limit_reached`, `cancelled`,
`delegation_unavailable`.
The message stays a bounded, platform-owned sentence. A new event kind was
rejected (every consumer must learn it; a resume affordance belongs to the
background lane); message text alone cannot distinguish a lost credential from a
crash.

### D7 — Run ceiling

A wall-clock budget in shared engine code, default 15 minutes for attended runs,
overridable through the agent's settings, plus a bound on concurrent children.
An unset override uses the deployment value; configured limits are positive and
validated before admission. Admission resolves the effective limits once; a
reconnect or child cannot reset the parent's budget. Managed tuning is resolved
through registration; direct execution uses the agent definition's ceiling. The
shared resolver hook remains an optional extension point.
Per-call timeouts are unchanged; they bound one call, never the run.

`AgentTuning.run_ceiling_seconds` is an optional finite positive setting, mirrored
by managed tuning. Admission first fixes the local grant record and start time,
then resolves and registers through its workload provider, and finally fixes the
effective limit on that record and execution target. Elapsed admission time counts
toward the ceiling. Children inherit the open parent scope; per-run state carries
limits without a mutable process-wide map of managed-agent identifiers. Record
expiry uses that run's effective ceiling plus the existing cleanup margin.

The child bound counts children in flight, including ancestors awaiting their
descendants. Ordinary sibling work may queue for capacity. A nested invocation
that cannot acquire capacity immediately ends the run with `child_limit_reached`
before spawning more work, rather than waiting for a permit its ancestor holds.
This outcome is distinct from exhausting the wall-clock budget.

Managed execution requests require `runtime_context.team_id` during SDK request
validation. Direct template requests retain optional team context. The existing
request schema represents those alternatives with `oneOf`, so generated clients
retain conditional requiredness without a new wire envelope.

### D8 — MCP auth modes

`delegated`: workload bearer plus the grant outside tool arguments. `user_token`:
refused at activation when the flag is on, with reason `delegation_unavailable`.
`no_token`: unchanged. Forwarding the person's bearer to non-receivers was
rejected because it would put a standing exception into the no-forwarding rule for a
path nothing uses; a URL-prefix rule was rejected as a heuristic inside an
authorisation decision. `user_token` remains the default for new catalog entries
because it fails closed.

### D9 — Fail closed

With the flag on, a missing allow-list or workload client configuration fails
admission with a clear error. The person's bearer is never forwarded as a
fallback.

### D10 — Replica scope

The working copy of the run record is pod-local: the run executes in the
admitting pod and team members run in-process. The registry holds lifecycle
metadata; the background lane defines the durable task admission payload from
which each execution starts and registers its own lifecycle record.

### D11 — The workload token is accepted by every receiver

Each calling client — the agent backend, every installed application and the
evaluation worker — holds the service role on the shared client, which the
realm's audience resolution turns into the audience every receiver expects;
receivers identify the caller by the token's `azp` claim, which the shared
parser already extracts, plus the configured service-account binding in D3.
Shared deployments require strict issuer and audience validation. The shared
audience's intended receiver set is explicit; it grants no operation permission.
Acceptance is verified against the provisioned realm. Reuse the existing verifier;
required token-purpose and workload-identity checks remain in shared receiver code.

### D12 — Workload secret rotation

The pod captures its client secret at startup, so a rotation is a rolling
restart. The procedure: enable the identity provider's rotated-secret grace so
the previous and the new secret are both valid, change the stored secret, roll
the pods, then let the grace expire. In-flight turns finish on the token they
hold; the token provider re-fetches with the new secret after the restart.
Reading the secret again on a failed fetch is a later refinement.

### D13 — Delegation requires user authentication

The flag is honoured only when user authentication is enabled; with
authentication disabled the runtime refuses to start with the flag on, and
behaves exactly as today with the flag off. Admission must establish an authorized
person, either from that person's token or, in the dependent change, an accepted
statement from a trusted workload.

### D14 — Failed token refresh has a shared cooldown

The shared token provider allows one refresh attempt at a time. A failed attempt
records a monotonic retry deadline using `refresh_failure_cooldown_seconds`
(default 5 seconds, finite and greater than zero, at most 60 seconds) in the
machine-to-machine configuration. All
waiters observe that same failure and fail promptly without another token request
or sleeping through the cooldown. After the deadline, one caller probes again;
success clears the failure state. Each network attempt retains its timeout. The
provider never returns an expired token or the person's credential as fallback;
delegated callers receive the existing bounded terminal failure. Verification
uses concurrent callers and a controlled clock to prove bounded attempts, waiter
completion, recovery and sanitized errors.

## Risks / Trade-offs

- [Stolen workload bearer] → impersonation remains possible for its remaining
  lifetime, subject to user permissions and retained endpoint guards; shared
  audiences enlarge the recipient set.
  A stolen client secret can mint replacements until issuance is stopped.
  Receiver policy, transport and secret controls reduce exposure; registry
  correlation is detection only. Sender binding is absent from this version.
- [A person disabled in the identity provider during a run keeps running] →
  disabling there ends interactive access when the person's token expires, not
  delegated work; in the next change, deleting the person through the platform
  suspends them and ends the run at its next call; until it lands the flag stays
  off in shared environments. The same holds for a person removed from a
  deployment's user whitelist mid-run: the whitelist is checked on the credential
  presented at admission, and a receiver checks only the caller's bearer against it.
- [Service-role shortcuts sit on the main road until the next change] → the flag
  stays off in shared environments until then; the asserted principal never
  carries the service role from day one.
- [Grant parameters appear in access logs] → scrub identifiers from query strings,
  request bodies and exception paths; absence of a secret does not permit logging.
- [A missing role or scope is invisible in a default deployment] → the
  acceptance test runs with the hardened profile on, against the realm the
  deployment tooling provisions.
- [Logs cannot identify individual actors] → retain caller and person in required
  run records and request context; delegation logs contain only bounded events,
  outcomes and reasons.
- [Under the flag the tool-server listing runs once per run] → the grant on the
  tool-server endpoint makes a connection single-use, so a delegated connection
  is never cached and each run pays the per-server listing again; carrying the
  grant in the tool protocol's per-call metadata restores the shared connection
  once the client library exposes it.
- [A failed workload-token refresh queues callers behind one lock] → D14's shared
  cooldown and concurrent-failure test are prerequisites for enabling the flag
  in a shared environment.
- [The ceiling check costs a few microseconds per streamed event] → measured at
  about three microseconds per event under concurrency, below two percent of one
  core at two hundred concurrent streams; arming the timer only near the
  deadline is the fallback if the load gate shows tail latency movement.

## Migration Plan

1. Complete local implementation across the shared libraries, runtime, receivers,
   standing, reconnect and background changes with the flag off. Finish generated
   clients, regression tests and fixes from independent review.
2. Complete deployment tooling and evaluation-worker integration last. Provision
   identities, policies, model selection, transport, ingress, affinity and scheduler
   settings; update the worker to send the creator's grant.
3. Run full end-to-end verification with those integrations present, including
   failed refresh, standing lifecycle, whitelist checks, shortcut removal and
   sessionless campaigns. Fix findings before shared-environment enablement.
4. Enable in one test environment and run the gate suite, then enable per
   deployment. Rollback is the flag: today's behaviour returns with no
   data migration.

### Deployment runbook

Apply the implementation in two separate rollout stages. The first stage installs
the code and database changes with delegation disabled. The later activation stage
provisions workload identities and receiver policy, completes the external gates,
and only then enables delegation.

#### Stage 1 — install the implementation with delegation disabled

1. Inventory the live release before changing it. Capture the Helm values and
   manifest, application ConfigMaps, workload images, replica counts, Services,
   persistent-volume claim UIDs and the intended installed-application catalog.
   The rendered update MUST retain the environment's current application list;
   an application intentionally removed before the rollout MUST NOT be restored.
2. Verify deployment dependencies from inside the cluster, including PostgreSQL,
   OpenSearch, the identity and authorization services, Temporal and every configured
   model endpoint. A host model endpoint MUST use a hostname that resolves from a pod
   after the container runtime restarts. Do not begin migrations while a required
   dependency is unavailable.
3. Back up every database changed by the release. Record table row counts and the
   current Alembic version-table heads so post-upgrade preservation and schema
   advancement can be checked without exposing record identifiers.
4. Build every application image from one immutable source snapshot under one
   unique tag. Label each image with the source revision and snapshot digest. Verify
   that runtime and capability migration trees are present in the runtime image and
   that each backend image imports its application and resolves its Alembic head.
5. Publish the images to the deployment registry, or import them into every node of
   an isolated local cluster. Verify each node has all images and that their source
   digest matches the snapshot. Do not use a mutable shared tag.
6. Render the complete application release against the live values. Keep delegation
   disabled. Compare the render with the live release and
   require all of the following before continuing: no storage object is removed or
   replaced; existing secret contents match without being printed; model, catalog,
   integration and installed-application configuration is preserved; only the
   intended application images and explicit disabled security defaults change.
7. Run the migration-backed Helm upgrade through deployment tooling. The pre-upgrade
   hooks scale down the control-plane and knowledge-flow backends, run their Alembic
   upgrades, and run the runtime command that upgrades both the runtime schema and
   every installed capability schema. Wait for all migration jobs and workload
   rollouts. When the existing release contains server-side ownership drift, resolve
   those field conflicts explicitly; do not force-replace Deployments, storage or
   other live resources, and do not recreate the cluster.
8. Verify the resulting release before accepting it: every migration job succeeded;
   all schema heads equal the heads packaged in the deployed images; protected table
   counts remain consistent with the expected migrations; all intended workloads are
   ready on the unique image tag; image IDs match the imported or published images;
   persistent-volume claim and deployment UIDs are preserved; rendered ConfigMaps
   match the live ConfigMaps; and the intentionally retained installed applications
   remain healthy.
9. Verify the application through an authenticated browser. The Usage page MUST
   return searchable KPI data or its valid empty state, and the Activity page MUST
   return data or its valid empty state. Confirm their backend requests complete
   successfully. Exercise the retained installed application without enabling
   delegation. Keep identifiers, request content and credentials out of verification
   logs and evidence.

If Stage 1 fails, keep delegation disabled. Diagnose the failed hook or workload
against the saved render, image metadata, migration heads and dependency checks.
Do not blindly roll back to an older failed Helm revision or restore a database over
successful additive migrations. Use the database backup only for a reviewed recovery
from a migration that changed data incorrectly.

#### Stage 2 — activate delegation after external integration

1. Provision one confidential workload client and service account for each caller,
   configure the required audiences and service role, deliver each secret only to its
   workload, and verify token claims and receiver-specific client/subject bindings.
2. Configure receiver allow-lists, internal transport, ingress rejection of external
   grant parameters, secret rotation, reconnect affinity and scheduler settings. Add
   the evaluation worker only when its creator-grant propagation is implemented.
3. Run the provisioned-token REST, MCP, registration and terminal-reporting matrix,
   the standing and revocation cases, workload-removal propagation tests, transport
   failure tests and session-expiry end-to-end run. Retain sanitized evidence.
4. Enable delegation in one test environment, repeat the full gate, then enable it
   per deployment. If activation fails, turn the flag off while retaining the Stage 1
   images and additive schema changes.

## Known limitations and implementation gaps

| Limitation or gap | Status |
| --- | --- |
| Bearer replay | A stolen bearer remains usable within its validity and receiver policy; sender binding is outside this version |
| Client-secret compromise | A stolen secret can mint replacement tokens until issuance is stopped; rotation and receiver policy remain required |
| Identity-provider account changes | Disabling or deleting an account in the identity provider ends interactive access at token expiry and does not stop delegated or scheduled runs; deleting the person through the platform suspends them from their next authorization decision |
| Per-run resource/action restriction | Deferred; user permissions, trusted workload identity and retained endpoint guards are the current bounds |
| Log attribution | Identifier-free logs cannot identify individual actors; required run records retain lifecycle attribution |
| Deployment tooling | Unimplemented external gap: client provisioning, receiver policy, transport, ingress, rotation and rollout evidence |
| Evaluation worker | Unimplemented external gap: creator grant propagation and campaign integration; tracked in the single-subject change |

## Deferred

The next stages of this version are their own changes and hold their own
decisions:

- `add-delegation-single-subject` — caller and subject as separate principals;
  standing required inside the shared engine as a platform-owned block list;
  person deletion through the platform suspends the person first;
  the service-role shortcuts removed; the evaluation worker as an allow-listed
  caller.
- `add-delegation-background-lane` — presence rule, background runs as tasks,
  schedules, listing and cancellation.

Not part of this version; candidates for a later one: a scope parameter on the
grant enforced by receivers, read-only agents through an actions parameter, and
acceptance metrics with a reconciliation job and a pod-bound workload
credential.

The per-agent ceiling override of D7 is carried from the agent definition or
managed tuning through admission, registration and finalized run limits; task 1.8
covers admission tests. It is required work in this change, not a deferred capability.
