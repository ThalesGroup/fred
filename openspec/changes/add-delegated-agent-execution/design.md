## Context

See [proposal.md](proposal.md) for the objective and the capability specifications for the behavior contract. The runtime authenticates the incoming caller, establishes the person represented by a run and supplies credentials through shared service clients. ReAct and DeepAgent execution use the same credential boundary.

The workload credential is renewable through the identity provider. A run's local record establishes its person and root agent. Receiver authorization applies current permissions and account standing independently of the lifetime of the person's login token.

## Goals / Non-Goals

**Goals**

- Keep the person's credential at admission and supply renewable workload credentials at every delegated call.
- Keep caller authentication, asserted-person authorization and ordinary service identity policies distinct.
- Make attended execution and its descendants stop when response handling ends.
- Preserve shared task, worker, service identity and authentication behavior outside delegated execution.
- Make failures observable without exposing credentials, grant values or identity-bearing error details.

**Boundaries**

- Execution lifecycle and typed-stop guarantees cover ReAct and DeepAgent. Graph agents may need separate work for cancellation, stop propagation and diagnostics.
- A grant is a trusted workload's assertion; it is not an independently signed proof of consent.
- The runtime maintains only local, response-owned admission state. Managed binding resolution is read-only; direct admission has no control-plane dependency.
- The response owns attended execution. Human input resumes application state through a freshly admitted request.
- Delegation adds no wall-clock, child-count, admitted-run-count or live-record-age limit. Existing per-call timeouts and engine step limits remain applicable.
- Deployment provisioning, transport controls, rotation drills and integration verification are explicit deployment responsibilities.

## Decisions

### 1. Caller trust and grant transport

`act_for_people` controls outbound delegation and `accept_delegated_calls` controls receiver interpretation. Both default off. Configuration provides the delegation audience, caller role and claim path, recognized login clients and optional service-account-only validation. The runtime requires user authentication to act for people and requires outbound delegation when it accepts asserted people.

Receivers validate the bearer before interpreting a grant: signature, permitted algorithm, trusted issuer/key source, validity, access-token purpose and intended audience. Delegation additionally requires the configured caller role and excludes tokens issued to login clients. `azp`, with `client_id` as fallback, identifies the verified caller but does not itself establish delegation trust.

The grant contains `person`, `run` and `agent`. It occupies fields of a JSON object body or query parameters for other requests. Grant fields from different transports are not combined. Tool mounts accept the grant only from the outer endpoint, outside tool arguments.

A complete grant from a caller without the delegation role receives 403 when delegated calls are accepted. Query inspection applies to every caller; body inspection for this refusal applies to service identities outside tool mounts. Without a verified grant, the bearer retains its ordinary caller identity and no person is asserted. The caller role remains recognizable when both switches are off.

### 2. Local admission and credential providers

`RunRecordStore` holds the admitted person, run, root agent and relevant execution context. Only admission establishes those values. The runtime checks current standing and direct-target team permission or the managed target's standing-gated team-agent permission. Managed requests require a non-blank team identifier. Managed binding resolution uses one read-only request carrying the workload bearer and record-derived grant.

`DelegatedCredentialProvider` supplies both the authorization header and grant parameters. Knowledge, document, workspace, team-wiki, binding and tool clients ask it immediately before a request. Subagents derive a provider with their own agent identity and the same run. A missing or terminal record prevents credential acquisition. Liveness must still hold after any awaited token acquisition.

`M2MTokenProvider` caches one service-account token per provider in runtime-process memory. Callers reuse it while more than 30 seconds remain. Renewal uses client credentials and one shared in-flight task. The shared HTTP authentication adapter refreshes after the first 401 and retries the same request once. Concurrent and delayed 401 responses for the same cache generation share the replacement. A first 403 or a retry returning 401/403 is terminal. Transport failures preserve their exception class with bounded text so existing polling callers can retry. After a failed acquisition, the next caller may retry immediately.

An ordinary service identity without the caller role runs on its own bearer, with no delegated record. Its provider remains separate from the delegated workload provider.

With `act_for_people` off, `PersonCredentialProvider` reads the person's live bearer at call time and sends no grant. Parent and child calls observe token updates through the same getter.

### 3. Response ownership and stop propagation

The native streaming route and OpenAI-compatible streaming route use `_RunStreamingResponse`, whose `finally` invokes the finisher even when response sending raises or is cancelled. The finisher marks the record terminal, explicitly closes the stream and discards the record in `finally`. Iterator owners and the run scope also participate in cleanup; repeated cleanup must be idempotent.

The required lifecycle covers normal completion, human pause, detected disconnect, request cancellation and response-start/body-send failures. Before asynchronous teardown, the run must become unable to acquire credentials. The execution producer, child agents and descendants must be cancelled and their completion awaited; every owned iterator must close. Asynchronous teardown must remain effective under cancellation, and the admission record must be absent when response handling completes.

The run scope registers spawned agents. ReAct and DeepAgent propagate typed stops; a stopped child ends its parent and cancels siblings. The root reports one typed terminal event, while external cancellation emits no synthetic completion. Capability wrappers preserve these errors instead of presenting them as tool text.

The frontend owns one request per turn, aborts it on unmount or intentional interruption, and reports an unexpected drop once. Server cleanup begins on detected disconnection; sleep or abrupt network loss has no instantaneous-detection guarantee. Already authorized remote operations are not undone by local cleanup.

Credential acquisition rechecks the record and captured run scope after token acquisition. Owner execution marks authority terminal before asynchronous teardown. Iterator closure, descendant joins and runtime disposal complete under cancellation protection. Focused executable acceptance remains in [tasks.md](tasks.md).

### 4. Tool authentication and application integration

For a run using delegated credentials, authenticated tool servers must use `delegated` mode on a supported HTTP transport. Calls carry a current workload bearer and an endpoint grant. `no_token` servers remain unauthenticated. A grant-bearing connection is scoped to one run. Connection, listing and invocation use the shared HTTP authentication adapter. A first 403, a 401/403 after the single authentication retry, or a structured standing-unavailable refusal produces `authority_lost`; unsupported authentication produces `delegation_unavailable`.

Ordinary service identities retain their own bearer and send no grant, including to catalog entries declared `delegated`. Their behavior depends on the credential provider of that execution, not merely on the process-wide delegation switch.

The shared first-party configuration builder assembles the hardened profile, reader authorization, user/workload issuer configuration and one structured delegation block. Required credential configuration is checked during startup. A shared declaration helper exposes grant fields in receiver contracts.

The tool-mount bridge verifies the outer bearer and endpoint grant, carries the verified grant in request-scoped context, strips model-controlled grant fields and inserts only the verified values into the inner route request. It clears context on exit, including failure and cancellation. The bridge hides grant fields from tool schemas and keeps concurrent calls isolated. Optional tool-server integration is available through the package's dedicated extra and exports.

Inner-route authority refusals retain a bounded structured cause in the tool result, including when the outer HTTP response succeeds. The delegated client recognizes that cause before ordinary tool-error conversion. Error text is never used to classify authority; unrelated service failures retain ordinary error handling.

### 5. Service identities and own-credential endpoints

Service-role shortcuts apply only to `is_service_agent(user) and not holds_caller_role(user)`. This applies to team, tag, tabular, ingestion, synchronized-folder, managed execution, per-tool authorization and model-override policies. An asserted person has no bearer roles. Caller-role holders use ordinary endpoint authorization for own-identity operations; under outgoing delegation, agent execution requires a person.

Caller-only operations retain explicit workload and ownership checks, including a knowledge-base instance's run configuration and library publication. These operations do not infer authority from a grant.

#### Own-credential endpoints

| Purpose | Endpoint families |
| --- | --- |
| Conversation history | Session listing, message history and session deletion |
| Checkpoints | Checkpoint listing, reading and deletion |
| Runtime diagnostics | Turn KPIs and audit events |
| Capability configuration | Configuration validation and chat controls |
| OpenAI-compatible execution | `/v1/chat/completions` |

These runtime operations require the directly authenticated identity and reject an asserted person. Authenticated-person compatibility execution can still admit a local delegated run. Native execution, evaluation and streaming also accept a trusted caller's grant where receiver delegation is enabled.

### 6. Account standing and deletion

The authorization model defines organization standing as `active: [user:*] but not suspended`, plus a `standing_ready` marker. Control-plane startup validates the selected model, writes default standing and the marker, and verifies readiness before serving. Receivers enforcing standing validate their model and marker; a non-enforcing engine is incompatible with either delegation switch being enabled.

The authorization engine checks standing for person subjects alongside permissions at higher consistency; list lookups check standing before listing. Typed standing failures propagate through batch/filtering helpers. Generic relation mutation and cleanup cannot change lifecycle-owned standing tuples.

A receiver's structured standing-unavailable refusal uses HTTP 503 and `X-Fred-Denial-Cause: standing_unavailable`. Delegated REST and tool clients preserve that cause and raise `authority_lost`, stopping the run and its descendants. Local per-tool permission and standing refusals use the same typed stop during delegated execution. Generic service-unavailable errors retain ordinary error handling.

Platform deletion preserves permission checks and protected-account rules, rejects wildcard/userset identifiers, and resolves identity administration before mutation. When standing is enforced, it writes suspension before deleting the identity-provider account. Other relations remain. A failed identity deletion leaves the suspension effective; a retry is safe. With standing disabled, deletion writes no suspension.

Suspension applies at the next authorization decision. Existing authorized remote work can finish. Identity-provider account changes do not independently change platform standing. Whitelists evaluate the asserted subject by its immutable subject entry; authenticated people can also match email entries.

### 7. Diagnostics and operational compatibility

The shared handler returns 403 for ordinary permission and decided standing refusals, and 503 for a standing decision marked unavailable. Runtime admission and control-plane handlers preserve this classification. The `X-Fred-Denial-Cause` header distinguishes `permission_refused`, `standing_refused` and `standing_unavailable`. The handler logs bounded cause, decision availability, subject type, action and resource type. Grant acceptance/refusal and standing refusal produce bounded audit events. Ordinary permission denials are not reported as standing audit events.

Execution diagnostics emit a platform-owned sentence and an independent random support reference. Corresponding logs contain bounded exception types and code locations, without exception messages, request data, variable values or source-line text. Request and delegation logs exclude grants, credentials, secret names and identity-bearing details before parsing or authentication, including requests with grants in JSON bodies.

A process-local optional observer exposes initial token acquisition, renewal, latency, caller wait, cache events and delegation decisions with bounded labels. Observer failure does not break authentication. Frontend token-refresh diagnostics contain outcome and duration only.

The control-plane worker command selects its worker configuration. The knowledge backend validates its required authentication secret during startup. Shared task persistence, cancellation, event replay and scheduler behavior retain their established contracts. The control-plane scheduler's connection log excludes host and namespace identifiers.

Local run targets load an overlay only when named explicitly. The overlay can enable delegation directions only for a trusted issuer and audience, preserving all other configuration. The local setup helper supports inspection, writing and reset without editing tracked configuration.

## Risks / Trade-offs

- Trusted workload credentials permit assertions for people; current person permissions and standing remain the authorization boundary. The grant is not independently signed or sender-bound.
- A service identity can retain broad service-role access. Correct caller-role provisioning and explicit endpoint policies are required.
- Provider renewal permits a long attended run to continue while its response stays open. Response ownership and descendant cancellation are required independently of token expiry.
- Connection-loss detection depends on the server and transport. Cancellation cannot reverse an already authorized remote side effect.
- Per-run authenticated tool connections isolate grants and incur connection/listing overhead.
- The workload secret is captured at provider construction; rotation requires restarting participating processes with the updated secret.
- Focused and end-to-end acceptance verification remain open in [tasks.md](tasks.md); source inspection is not evidence that executable checks passed.

## Migration Plan

1. Require database schema and task records compatible with the shipped migrations and task model, preserving unrelated business data. Confirm scheduled workloads match deployed workers.
2. Publish and select the standing-capable authorization model for all readers and writers, including pinned models.
3. Provision trusted workload clients, caller roles and audiences separately from login clients and ordinary service identities. Protect transport, secret storage and external ingress.
4. Start the control plane with standing enforcement before the participating receivers and agent runtimes. Enable receiving delegation wherever an enabled runtime calls on behalf of people.
5. Run the deployment acceptance matrix and secret-rotation drill. Rotation uses the identity provider's overlap period and a controlled workload restart.

Both delegation switches can be disabled together. The authorization model and existing business data remain valid; caller-role holders still receive no service-role shortcuts.
