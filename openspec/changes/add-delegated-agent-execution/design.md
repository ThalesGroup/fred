## Context

See [proposal.md](proposal.md) for the objective and the capability specifications for the behavior contract. The runtime authenticates the incoming caller, establishes the person represented by a run and supplies credentials through shared service clients. ReAct and DeepAgent execution use the same credential boundary.

The workload credential is renewable through the identity provider. A run's local record establishes its person and root agent. Receiver authorization applies current permissions and account status independently of the lifetime of the person's login token.

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

The grant contains `person`, `run` and `agent`. A value containing `*` or `#` makes the grant malformed, so no grant names the wildcard subject or a userset. A value may contain `:`, as the subject identifier of a user federated without import does. It occupies fields of a JSON object body or query parameters for other requests. Grant fields from different transports are not combined. Tool mounts accept the grant only from the outer endpoint, outside tool arguments.

A complete grant from a caller without the delegation role receives 403 when delegated calls are accepted. Query inspection applies to every caller; body inspection for this refusal applies to service identities outside tool mounts. Without a verified grant, the bearer retains its ordinary caller identity and no person is asserted. The caller role remains recognizable when both switches are off.

### 2. Local admission and credential providers

`RunRecordStore` holds the admitted person, run, root agent and relevant execution context. Only admission establishes those values. The request's account status check (Decision 6) has already run for the person; admission then checks the direct target's team permission, when it names a team, or the managed target's team-agent permission. Managed requests require a non-blank team identifier. Managed binding resolution uses one read-only request carrying the workload bearer and record-derived grant.

`DelegatedCredentialProvider` checks run liveness and supplies the grant parameters; it acquires no token. The shared HTTP authentication adapter is the only source of the workload bearer: it takes a token from the same provider for each request and owns the single 401 renewal, whose retry carries the renewed token. Knowledge, document, workspace, team-wiki, binding and tool clients ask the provider for the grant immediately before a request and send the request through that adapter. Subagents derive a provider with their own agent identity and the same run. A missing or terminal record prevents a token or its renewal from being released, and liveness must still hold after the awaited acquisition. A failed acquisition writes one log line naming only the error type.

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

For a run using delegated credentials, authenticated tool servers must use `delegated` mode on a supported HTTP transport. Calls carry a current workload bearer and an endpoint grant. `no_token` servers remain unauthenticated. A grant-bearing connection is scoped to one run. Connection, listing and invocation use the shared HTTP authentication adapter. A first 403, a 401/403 after the single authentication retry, or a structured `account_status_unavailable` refusal produces `authority_lost`; unsupported authentication produces `delegation_unavailable`.

Ordinary service identities retain their own bearer and send no grant, including to catalog entries declared `delegated`. Their behavior depends on the credential provider of that execution, not merely on the process-wide delegation switch.

The shared first-party configuration builder assembles the hardened profile, reader authorization, user/workload issuer configuration and one structured delegation block. Required credential configuration is checked during startup. A shared declaration helper exposes grant fields in receiver contracts.

The tool-mount bridge verifies the outer bearer and endpoint grant, carries the verified grant in request-scoped context, strips model-controlled grant fields and inserts only the verified values into the inner route request. It clears context on exit, including failure and cancellation. The bridge hides grant fields from tool schemas and keeps concurrent calls isolated. Optional tool-server integration is available through the package's dedicated extra and exports.

Inner-route authority refusals retain a bounded structured cause in the tool result, including when the outer HTTP response succeeds. The delegated client recognizes that cause before ordinary tool-error conversion. Error text is never used to classify authority; unrelated service failures retain ordinary error handling.

The existing SQL diagnostic exception remains available through the bridge: `read_query` HTTP 400 responses preserve only their already-redacted, non-empty string `detail` in the error envelope recognized by the runtime. Other response fields and malformed bodies remain generic failures, with or without delegation.

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
| Agent configuration (control plane) | Agent-instance enrollment and update, with or without asset uploads |
| Conversation deletion (control plane) | Session deletion, bulk session deletion and attachment deletion |
| Synchronized folders (control plane) | Knowledge-base instance creation and deletion |

These operations require the directly authenticated identity and reject an asserted person. The control-plane operations present their caller's bearer to another service, and a service that does not act for people presents no delegated caller's bearer onward; they therefore refuse an asserted person with 403 `requires_own_credential`. Managed execution preparation still accepts an asserted person but makes no call presenting the caller's bearer: it returns no capability composer controls for that person. Authenticated-person compatibility execution can still admit a local delegated run. Native execution, evaluation and streaming also accept a trusted caller's grant where receiver delegation is enabled.

### 6. Account status and deletion

The authorization model defines account status through `suspended: [user]` on the organization: a person has an active account unless suspended, so no entry is stored for anyone else and startup writes nothing. Every service enforcing account status validates that its selected model defines `suspended` before it starts and installs its engine for the request's account status check, and services start in any order. A non-enforcing engine is incompatible with either delegation switch being enabled.

With either delegation switch on, account status is checked once per authenticated request where the request's subject is established, after the bearer and any grant are resolved and before the route runs: one check at higher consistency that the subject — a signed-in person, a person named by a grant or a service identity — does not hold `organization#suspended`. On a tool mount, the route that serves a mounted tool call performs that check; the mount itself only authenticates. Checks, batch checks and list lookups do not repeat that check and keep the consistency their caller asks for. With a switch on and no engine installed for the check, or during an authorization-store outage, every authenticated request is refused with 503 `account_status_unavailable`, without exemptions. For a delegated run, the per-tool recheck checks account status before every tool call in every team, concurrently with the team permission check in a collaborative team; a run without delegated credentials makes no per-tool account status check. Background work admitted by a request before a suspension finishes without an account status check of its own. Generic relation mutation and cleanup cannot change lifecycle-owned suspension tuples.

A receiver's structured `account_status_unavailable` refusal uses HTTP 503 and `X-Fred-Denial-Cause: account_status_unavailable`. Delegated REST and tool clients preserve that cause and raise `authority_lost`, stopping the run and its descendants. Local per-tool permission and account status refusals use the same typed stop during delegated execution. Generic service-unavailable errors retain ordinary error handling.

Platform deletion preserves permission checks and protected-account rules, rejects wildcard/userset identifiers, and resolves identity administration before mutation. When account status is enforced, it writes suspension before deleting the identity-provider account. Other relations remain. A failed identity deletion leaves the suspension effective; a retry is safe. With account status disabled, deletion writes no suspension.

Suspension applies at the person's next request at every receiver and at the next tool call of a delegated run acting for them. A request that has passed its account status check completes, and background work admitted before the suspension finishes. Identity-provider account changes do not independently change platform account status. Whitelists evaluate the asserted subject by its immutable subject entry; authenticated people can also match email entries.

### 7. Diagnostics and operational compatibility

The shared handler returns 403 for ordinary permission and decided account status refusals, and 503 for an account status decision marked unavailable. Runtime admission and control-plane handlers preserve this classification. The `X-Fred-Denial-Cause` header distinguishes `permission_refused`, `account_suspended` and `account_status_unavailable`. The handler logs bounded cause, decision availability, subject type, action and resource type. Grant acceptance/refusal and account status refusal (`authorization.account.refused`, reason `account_suspended` or `account_status_unavailable`) produce bounded audit events. Managed runtime admission records a refused team permission as a `rebac_denied` audit event carrying only outcome `rejected` and reason `permission_refused`, whatever the switches; other services' permission denials stay in the bounded denial log. Ordinary permission denials are not reported as account status audit events.

Execution diagnostics emit a platform-owned sentence and an independent random support reference. Corresponding logs contain bounded exception types and code locations, without exception messages, request data, variable values or source-line text. With either delegation switch on, request and delegation logs exclude grants, credentials, secret names and identity-bearing details before parsing or authentication, including requests with grants in JSON bodies. With either switch on, each request is logged once, by the access log; a backend's own request/response logging middleware writes nothing.

A process-local optional observer exposes initial token acquisition, renewal, latency, caller wait, cache events and delegation decisions with bounded labels. A delegated request makes one acquisition, plus one per 401 renewal; the retry reuses the renewed token. Observer failure does not break authentication.

The control-plane worker command selects its worker configuration. The knowledge backend validates its required authentication secret during startup. Shared task persistence, cancellation, event replay and scheduler behavior retain their established contracts. The control-plane scheduler's connection log excludes host and namespace identifiers.

Local run targets load an overlay only when named explicitly. The overlay can enable delegation directions only for a trusted issuer and audience, preserving all other configuration. The local setup helper supports inspection, writing and reset without editing tracked configuration.

## Risks / Trade-offs

- Trusted workload credentials permit assertions for people; current person permissions and account status remain the authorization boundary. The grant is not independently signed or sender-bound.
- A service identity can retain broad service-role access. Correct caller-role provisioning and explicit endpoint policies are required.
- Provider renewal permits a long attended run to continue while its response stays open. Response ownership and descendant cancellation are required independently of token expiry.
- Connection-loss detection depends on the server and transport. Cancellation cannot reverse an already authorized remote side effect.
- Per-run authenticated tool connections isolate grants and incur connection/listing overhead.
- The workload secret is captured at provider construction; rotation requires restarting participating processes with the updated secret.
- With a delegation switch on, every authenticated request makes one account status check, and an authorization-store outage refuses every authenticated request with 503; a tool mount's initialization and tool listing make none. A collaborative-team tool call makes its account status and permission checks concurrently.
- Background work admitted before a suspension completes for the suspended person.
- With both delegation switches off, runtime audit events other than `rebac_denied` still carry identifiers such as the acting principal and team.
- Focused and end-to-end acceptance verification remain open in [tasks.md](tasks.md); source inspection is not evidence that executable checks passed.

## Migration Plan

1. Require database schema and task records compatible with the shipped migrations and task model, preserving unrelated business data. Confirm scheduled workloads match deployed workers.
2. Publish and select the authorization model carrying `suspended` for all readers and writers, including pinned models.
3. Provision trusted workload clients, caller roles and audiences separately from login clients and ordinary service identities. Protect transport, secret storage and external ingress.
4. Enable receiving delegation wherever an enabled runtime calls on behalf of people. Each service with a switch on then checks account status on every authenticated request, a tool mount's initialization and tool listing excepted, and needs its authorization store reachable to serve.
5. Run the deployment acceptance matrix and secret-rotation drill. Rotation uses the identity provider's overlap period and a controlled workload restart.

Both delegation switches can be disabled together. The authorization model and existing business data remain valid; caller-role holders still receive no service-role shortcuts.
