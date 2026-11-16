# Fred benchmark client: Swift and Weaver on one engine

One Go executable supports Weaver managed SSE, Swift managed/direct SSE and the
historical Swift WebSocket commands. `-target=swift` remains the default.
Weaver is the lot 2 adaptation of the lot 1 engine, not a second load scheduler.
Unknown targets and unsupported Weaver combinations fail before network access.

An opt-in conversation scenario adds private factory credentials, per-identity
token renewal, concurrency steps and deterministic context/history verification.
The client does not provision Keycloak accounts, start the mock or deploy anything.
The examples below describe available commands; they are not recorded load runs.
Validation uses local `httptest` servers and doubles only.

## Offline interactive HTML report

After each campaign, generate one standalone HTML file from the existing results:

```bash
cd developer_tools/benchmarks
make report DIR=/path/to/results
# Equivalent; Go 1.24.0 must already be installed/cached for offline use:
GOTOOLCHAIN=go1.24.0 GOPROXY=off go run . report -input /path/to/results
# Keep an earlier report and choose another output:
make report DIR=/path/to/results OUTPUT=/path/to/results/report-2.html
```

Open `report.html` directly in a browser. No server, CDN, library, fetch or network
resource is required; JavaScript must be enabled. `make report` defaults to the
Go 1.24.0 toolchain while respecting an explicit `GOTOOLCHAIN` override. It does
not change the existing build/run targets. The `report` subcommand dispatches
before benchmark flags, credentials or runtime initialization, and never starts
load or contacts Fred. Toolchain/dependencies must be installed beforehand;
set `GOPROXY=off` to forbid dependency downloads during the command.

The input is a flat directory of canonical conversation scenario JSONL files:
first record `kind=run`, `schema_version=fred.bench.scenario.v1`, followed by
`fred.bench.scenario.turn.v1` turns and optional step/final records. Each campaign
must appear once. Several targets, runs and concurrency levels may share the
directory. Identity preparation JSONL is recognized by its record kinds and
terminal `fred.bench.preparation.v1` schema and ignored, regardless of filename.
Other JSONL formats, mixed campaigns, duplicate turns and unsupported legacy
formats fail explicitly. JSON, receipts, API captures and private configuration
files are not read. A malformed scenario line preserves the preceding observations
and marks the report incomplete; a missing final summary never becomes successful.
An inconsistent summary is marked incomplete; observed history records establish
history counts. Input files are never changed. The output must be a new `.html`
file, created with mode `0600`; existing files and links are never overwritten.
Remove a generated report deliberately or choose another `-output` to regenerate.

The French interface compares runs, filters concurrency and first/following turns,
shows median/P95/max with sample counts, and paginates the turn/error table.
Execution latencies start at execution; total latencies also include Weaver's
per-turn preparation, which Swift does not perform. Only successful turns with
observed timestamps contribute to latency statistics. N=0 means **not measured**,
never zero latency. Duration and history cover whole selected levels, even when
filtering first/following turns; run status and authentication cover the whole run.
Per-turn charts show medians across clients; per-concurrency charts show medians
across the selected turns. Graphs display at most 2,000 points and 16 legend items,
with an explicit notice; summaries and the 50-row paginated table retain all data.

Bounds are 128 MiB of JSONL, 2 MiB per record, 64 runs and 100,000 turns. This covers
campaigns such as 500 conversations with 10 turns without unbounded DOM growth.
Profiles and identity modes that differ produce a comparability warning; an
interrupted run's profile is unknown because the current header does not record it.
Deployed versions, machines and model configuration are not inferred from the
checkout. Only canonical campaign IDs (32 hexadecimal characters), bounded error
categories, enums, counts and timings enter the report. Identities, conversation
IDs, prompts, arbitrary error strings and unknown fields are omitted. JSON is
escaped through `html/template` in JavaScript context. No conversation link is
invented from pseudonymous identifiers. This report describes client observations,
not production capacity or server admission time.

## Reproduce the local setup from Git

The deployment and setup entry point is the factory's
[benchmark guide](https://github.com/fred-agent/fred-deployment-factory/blob/weaver/docs/BENCHMARKS.md).
Its opt-in `BENCH=reference` profile configures the mock and both Fred lines from
versioned values. Follow its normal bootstrap, identity preparation and
`k3d-bench-prepare` commands before running this client. Operator inputs and generated
password files remain private; no private Helm overlay or manual SQL is required.

Build Weaver's images from a revision containing the current Python SDK contract:
`RuntimeModels` accepts the resolver's `default` and `reasoning_default_on` fields.
The normal `fred-agents` image build includes `libs/fred-sdk`, so the API and worker
use the same correction without a separate image patch. For an existing organization,
the factory uses [the operator source assignment](../../apps/control-plane/README.md#assign-a-source-after-initialization)
before its normal model-policy API calls. Initialization receipts and existing
organization defaults are preserved. A successful setup is not a benchmark run;
start load only with the explicitly selected scenario parameters below.

## Conversation scenario with factory identities

Run from `developer_tools/benchmarks`. Prepare the identities, shared team/space,
agent and mock configuration outside the load window. The selected instance must
use the separately configured mock OpenAI profile `reference` or `streaming`;
`-mock-profile` selects the expected response oracle, not the server configuration.
The marker/ACK contract is maintained in the mock checkout's README under
"Opt-in deterministic chat benchmarks". No real-model performance is measured by
this scenario. Its control flow uses public APIs and has no dependency on Fred's
database, queues, locks or a particular future Redis implementation.

The factory produces a private JSON file (mode `0600`, or stricter):

```json
{"schema_version":1,"issuer":"http://localhost:8080/realms/app","client_id":"fred-bench-local","client_secret":"REDACTED","users":[{"label":"user-0001","username":"bench-example-0001","password":"REDACTED"}]}
```

`-credential-file` is the only credential input for this scenario. Never pass
passwords/client secrets on the command line. The client accepts only regular
private files up to 4 MiB. The issuer must use HTTP(S), one `/realms/<name>` path,
and a local test host: `localhost`, `*.localhost`, loopback IPv4/IPv6, `keycloak`
or `app-keycloak`. Arrange name resolution to the intended test Keycloak first.
Userinfo, query, fragment, escapes and redirects are rejected. Login uses the
issuer's `/protocol/openid-connect/token` direct grant endpoint; no Keycloak
configuration is modified. The dedicated test client must allow this grant.

All required users log in before any load, with `-auth-concurrency=8` by default
(maximum 64). Insufficient accounts, duplicate subjects or a failed login stop
before execution. Tokens remain in memory; refresh has an expiration margin,
one cancellable gate per identity, and atomic refresh-token rotation. Shared
conversations use the same gate. Failed refresh stops that identity; an agent
POST returning 401 is never replayed. JWT `sub` is decoded solely for attribution
and Swift's `runtime_context.user_id`; this is not JWT validation or authority.

Before load, a read-only preflight checks current terms and performs one
Control Plane preparation per identity for access, model/routing and binding.
The same team/space and instance configuration applies to the whole run.
Weaver still prepares every measured turn. Swift prepares only during preflight,
outside turn timing. Each Swift conversation also registers its locally generated
session ID, selected instance and title in Control Plane before its first turn,
using the same identity as execution. Registration is included in load elapsed,
not turn or execution latency. A failed registration stops that conversation
without execution or POST retry; only HTTP 201 establishes ownership. Its CP origin is derived from `-url`; both targets use
`-control-plane-path=/control-plane/v1` unless explicitly changed. No rights,
team membership, invitations or terms acceptance are created by a scenario run.
Errors use fixed categories such as `terms_acceptance_required`, `http_403`,
`preflight_route_or_team_mismatch` or `auth_http_401`, never server response text.

For disposable accounts whose usernames start with `bench-`, a separate command
checks terms or explicitly accepts the current version. It requires the public
Control Plane origin even for Swift. No agent, session or load request is made:

```bash
mkdir -p results
# Set CREDS, TARGET and ORIGIN to the chosen local test installation first.
GOTOOLCHAIN=go1.24.0 go run . \
  -prepare-only -target="$TARGET" \
  -fred-origin="$ORIGIN" -control-plane-path=/control-plane/v1 \
  -credential-file="$CREDS" -accept-test-terms=current \
  -raw-report=results/identity-preparation.jsonl
```

Omit `-accept-test-terms=current` for a read-only check. Each invocation requires
a new report path. Already accepted or disabled terms cause no POST. Weaver
sends the observed version; Swift's API accepts the current version without a
version precondition, so a reread detects changes but cannot promise atomic
version acceptance during a deployment. `accepted_unverified` records a POST
that succeeded but whose follow-up verification failed. Stop deployment changes
during preparation; inspect partial results before retrying. The client never
creates accounts or calls a grants API. Swift's existing first-acceptance handler
also joins configured default teams; explicit terms acceptance therefore retains
that normal backend side effect. The preparation stops at its first failed identity.

Start with an explicitly authorized one-conversation run, then reuse the same
explicit concurrency steps and mock profile on each independently running target:

```bash
# Weaver; all quoted variables are operator-supplied, never written to reports.
GOTOOLCHAIN=go1.24.0 go run . \
  -scenario=conversation -target=weaver -protocol=sse \
  -credential-file="$CREDS" -fred-origin="$WEAVER_ORIGIN" \
  -space-id="$SPACE_ID" -agent-instance-id="$WEAVER_INSTANCE_ID" \
  -concurrency-steps=1 -identity-mode=per-conversation \
  -requests-per-client=10 -mock-profile=reference -timeout=30s \
  -raw-report=results/weaver-scenario.jsonl \
  -json-report=results/weaver-scenario-summary.json

# Swift; SWIFT_STREAM_URL includes the actual public /agents/execute/stream path.
GOTOOLCHAIN=go1.24.0 go run . \
  -scenario=conversation -target=swift -protocol=sse \
  -credential-file="$CREDS" -url="$SWIFT_STREAM_URL" \
  -sse-team-id="$TEAM_ID" -agent-instance-id="$SWIFT_INSTANCE_ID" \
  -concurrency-steps=1 -identity-mode=per-conversation \
  -requests-per-client=10 -mock-profile=reference -timeout=30s \
  -raw-report=results/swift-scenario.jsonl \
  -json-report=results/swift-scenario-summary.json
```

`-concurrency-steps=1,10,50` explicitly selects sequential levels; there is no
automatic escalation, duration mode or ramp. Each level uses the common `runLoad`
engine and fresh conversations. Each conversation performs ten sequential turns
by default, with no intentional pause. `per-conversation` assigns one distinct
authenticated user to each conversation at a level; `shared` is the one-user,
N-conversation reference. Users are reused across levels, conversations are not.
Bounds are 32 levels, 10,000 clients per level and 100 turns per conversation.
Do not use legacy `-clients`, `-requests`, `-ramp-duration`, `-session` or identity
overrides here. Bootstrap, WebSocket, query tokens and TLS bypass are unsupported.

Every turn adds a fresh `MOCK_BENCH_V1` user marker. The bounded oracle checks
the ACK's exact current marker and complete ordered list of earlier user markers,
detecting missing, duplicate or foreign context. For `streaming`, it also checks
all 99 numbered continuation lines; SDK fragments can be split or combined, so
their observed count is recorded rather than equated to the mock's nominal 100.
The final answer and streamed text must agree when both exist. The ACK proves
which marked user history reached the model, not reasoning or unmarked content.

After every load window joins all clients, the client reads owned conversation
history and verifies ordered user markers, assistant final ACKs, session IDs,
exchange pairing and ranks. Weaver resolves `SessionDetails.messages_url`;
Swift uses its existing runtime `/agents/sessions/<id>/messages` endpoint.
Unsupported history is recorded as `unsupported`, never `verified`. Read/shape
or consistency failures are separate from performance errors. There is no
per-turn history GET in this scenario. Only afterwards are created sessions
cleaned up by default; `-delete-session=false` retains them. Weaver validates
deletion acceptance without polling a purge. Swift deletes its owned Control
Plane row through the team session API, which governs runtime erasure and any
configured deletion window; HTTP 204 acknowledges deletion, not physical purge
completion. It never directly deletes runtime history. A created row is cleaned
up even if registration validation or execution subsequently fails; collisions
are never reused or deleted. Retained Swift sessions have the metadata needed
for the UI sidebar. Cleanup is bounded independently of canceled load, and
failures remain visible. No pre-existing session can be supplied.

### Scenario reports

Scenario raw output is required, created exclusively with mode `0600`, written
progressively and synced after each record. Parent directories must already
exist. Existing raw or summary files are refused. Records have kinds `run`,
`auth`, `onboarding`, `preflight`, `turn`, `history`, `step` and `summary`.
The run/summary schema is `fred.bench.scenario.v1`; each turn uses
`fred.bench.scenario.turn.v1`. Legacy exports below keep their existing versions.
Graceful cancellation drains attempted turns, writes their results and closes
the report; already synced rows survive later failure. A failed writer cancels
the load and exits nonzero. Sync can exert client backpressure and is part of
the actual measured client behavior, not server execution time.

Each attempted turn records its level, concurrency, first/following status,
campaign-scoped pseudonyms for identity and conversation, outcome, performance
outcome and integrity outcome. No credentials, usernames, JWT subjects, marker
payloads, prompts, answer text, endpoint URLs or backend session IDs are exported.
The same conversation pseudonym joins turn and post-history records. Auth login
and refresh have their own timed records and aggregate statistics. Turn start
includes refresh waiting; optional `auth` describes a refresh actually performed
by that turn, not a fabricated refresh for every waiter. Preparation, execution
request start, first actual text, final and clean EOF remain distinct timestamps.
Logical text-fragment count and maximum useful silence (initial wait, inter-text
gap and EOF tail) are client observations, never tokenizer or token metrics.
Text retained for verification is limited to 128 KiB; JSON history to 4 MiB.

Per-level summaries distinguish planned, attempted, not started, successful and
failed turns. A failed conversation stops; others continue. Performance errors,
ACK integrity errors, post-history errors/unsupported status and cleanup errors
are separate counts. p50/p95/max and sample counts are given separately for
first and following successful turns: preparation, execution-to-text/final/EOF,
total-to-final/EOF and silence. Percentiles use nearest rank; a zero sample count
means unmeasured, not zero latency. Failed or invalid-ACK turns are excluded;
post-history failure preserves the separately recorded turn measurements.
Load elapsed includes session opening and export backpressure, and excludes
initial login/preflight, post-history and cleanup. Total per-turn latency includes
refresh and Weaver preparation; execution latency begins after preparation.
Compare like phases: Swift has no per-turn preparation samples. An incomplete
run, missing history verification or cleanup failure cannot report `OK`, and no
successful observed turn means `FAILED`. No throughput/capacity claim is made.

## Weaver managed SSE

Requires a user JWT already obtained outside this tool, read access to the space,
a usable managed instance and model, and accepted platform terms where required.
The public Fred origin must serve both Control Plane and the runtime under their
approved paths. The JWT is sent only as a bearer header; there is no fake-token
fallback, refresh, account creation, or per-client identity provisioning.

Usage example, **not an executed campaign** (replace the placeholders only for a
separately authorized run):

```bash
AGENTIC_TOKEN="$TOKEN" GOTOOLCHAIN=go1.24.0 make run ARGS='\
  -target=weaver -protocol=sse \
  -fred-origin=https://fred.example.invalid \
  -control-plane-path=/control-plane/v1 \
  -space-id=<SPACE_UUID> -agent-instance-id=<INSTANCE_UUID> \
  -clients=1 -requests-per-client=2 -ramp-duration=0s \
  -message="Réponds simplement : test réussi" -timeout=30s \
  -delete-session=false \
  -json-report=results/weaver-summary.json \
  -raw-report=results/weaver-turns.jsonl'
```

`-fred-origin` is an HTTP(S) origin without a path, userinfo, query or fragment.
`-control-plane-path` defaults to `/control-plane/v1`. Space/instance identifiers
must be UUIDs. Every client registers a fresh UUID conversation after reading
`configuration_revision` from the public GET agent-instance endpoint. Registration
sends `session_id`, `agent_instance_id`, `agent_configuration_revision` and title.
The returned binding must match; a configuration change is a failure, not an
implicit retry against a different revision. A creation response must be `201`;
`200` cannot silently reuse another conversation.

Each turn POSTs `prepare-execution?session_id=...`. The client checks revision,
space, instance, SSE support, `model_error`, inference selection and the announced
execution path before sending a request. Preparation is informative, **not runtime
admission**. Execution sends `agent_instance_id`, `input`, `session_id` and only
`runtime_context.space_id`; user identity comes from the JWT. Routing follows
`runtimeExecutionUrl.ts`: a canonical origin-relative path with a nonempty mount
ending in `/agents/execute/stream`, no absolute URL, query, fragment, escaping,
duplicate slash or dot segment. All HTTP redirects are refused, even same-origin.
The common SDK event decoder and SSE transport require final **and** normal EOF.

After a successful stream, GET SessionDetails resolves `messages_url`, then GET
that same-origin canonical `/agents/sessions/<session_id>/messages` route reads
the JSON array before the next turn. Only the row count is retained. This is the
minimal history hookup: no content export, pagination, retry/polling or full
history consistency check under load. The runtime contract commits history
before EOF; this legacy count-only read does not verify complete user/assistant
turns. The opt-in scenario above performs that check after load. No durable
history route, invalid JSON or a
failed history read fails this benchmark turn and stops the conversation, with
execution observations preserved separately. JSON responses are bounded to 4 MiB.

Conversations are cleaned up by default (`-delete-session=true`) **after** all
reads and turns, or after an error, with an independent `-timeout` budget per
conversation. Only conversations whose creation returned `201` are eligible.
`-delete-session=false` retains them for inspection in Fred (default title:
`Benchmark`). `-session=<UUID>` reuses an operator conversation with **one client
only**, verifies its binding and never deletes or re-registers it. A lost create
response can leave a conversation retained because ownership was not confirmed;
there is no speculative retry or deletion. Cleanup validates the deletion receipt:
queued/running means accepted, completed means completed, blocked/retrying or an
invalid/failed response counts as a cleanup error. No purge completion is polled.
Errors print a count, return exit status 1, set aggregate `cleanup_errors` and
make an otherwise OK summary DEGRADED; successful turn measurements stay intact.

Weaver supports only persistent managed SSE (`-requests-per-client>0`). It refuses
WebSocket/total-request modes and explicitly supplied Swift-only flags, including
`-url`, `-agent`, agent bootstrap, `-sse-user-id`, `-sse-team-id`, `-session-url`,
`-prepare-sessions`, `-prepare-concurrency`, query/empty auth, TLS bypass,
WebSocket read/debug options and legacy document/search context selections.
Even explicitly passing a default/false value for these options is rejected.
No HITL resume, model choice, attachments or full UI workflow is implemented.
Concurrent clients share the supplied JWT; they are not distinct users.

## Swift managed SSE

From `developer_tools/benchmarks`, with an externally supplied user JWT:

```bash
AGENTIC_TOKEN="$TOKEN" GOTOOLCHAIN=go1.24.0 make run ARGS='\
  -target=swift -protocol=sse \
  -url=http://127.0.0.1:8000/fred/agents/v2/agents/execute/stream \
  -agent-instance-id=<AGENT_INSTANCE_UUID> \
  -sse-team-id=<TEAM_ID> \
  -message="Réponds simplement : test réussi" \
  -clients=1 -requests-per-client=1 -ramp-duration=0s \
  -timeout=30s \
  -json-report=results/summary.json \
  -raw-report=results/turns.jsonl'
```

This historical Swift benchmark does **not** call UI prepare-execution or read
history. It is not equivalent to the full UI journey; raw records explicitly
state `preparation_mode: "not_performed"`.

Managed mode sends `agent_instance_id` and `runtime_context.team_id`, never
`agent_id`. `-agent` is ignored in this mode. Historical direct SSE instead uses
`-agent=<template-id>` without `-agent-instance-id`. `-sse-user-id` still defaults
to `bench`; it is a runtime-context hint, **not a distinct authenticated user**.

With `-requests-per-client>0`, each client owns a stable session and performs
sequential turns without an intentional pause. `-create-session=true` (default)
generates the SSE session ID locally; Swift SSE has no benchmark HTTP session
create/delete call. `-session=<id>` explicitly reuses the supplied session across
clients; this legacy option does not provide conversation isolation. For one
conversation per client, omit it and keep `-create-session=true`.

`-clients=N -requests-per-client=10 -ramp-duration=0s` expresses N concurrent
conversations of ten turns under the **same token**. It is a foundation for the
reference workload, not the full scenario of N different users in one team.
No capacity at 500 clients, or any other level, has been measured in this lot.

SSE success requires a complete `final` event **and clean HTTP body EOF**.
`execution_error`, the legacy bare `error`, and `execution_interrupted` fail the
turn. `node_error` is a nonterminal warning. Malformed events, missing final,
incomplete data frames, broken HTTP bodies, non-2xx responses, timeout and
cancellation cannot succeed. The reader continues after final (and terminal
errors) to observe EOF; timeout bounds that drain. The first terminal/protocol
error is retained if later reading also fails. Redirects are rejected.

## Preserved WebSocket usage

```bash
AGENTIC_TOKEN="$TOKEN" GOTOOLCHAIN=go1.24.0 make run ARGS='\
  -url=ws://localhost:8000/agentic/v1/chatbot/query/ws \
  -agent-uuid=<EXISTING_AGENT_UUID> \
  -clients=1 -requests-per-client=2 -ramp-duration=0s \
  -create-session=true -prepare-sessions=true -delete-session=true \
  -read-limit-bytes=8388608'
```

`-protocol=ws` remains the default. A persistent client reuses one connection
and session. HTTP session preparation/cleanup and agent bootstrap flags remain:

- `-agent=<id>` selects a configured agent. `-agent-uuid` takes precedence and
  bypasses agent creation.
- `-ensure-v2-definition-ref=v2.react.basic` or
  `-ensure-v2-profile-id=rag_expert`, with `-ensure-agent-name`, creates a temporary
  agent; `-delete-created-agent=true` removes it afterwards.
- `-document-library-ids=a,b`, `-document-uids=a,b`, `-search-policy=hybrid`,
  `-search-rag-scope=corpus_only` and optional `-include-session-scope` /
  `-include-corpus-scope` retain their runtime-context mapping.
- `-session-url`, `-agent-create-url`, `-prepare-concurrency`, `-insecure` and
  `-read-limit-bytes` retain their transport/lifecycle uses.
- `-requests-per-client=0 -requests=K` retains total-request scheduling: K
  independent exchanges across up to `-clients` workers. WebSocket opens a
  connection/session per exchange; SSE retains its historical lack of an implicit
  stable session in this mode. The ramp applies only to persistent-client mode.

All Swift modes use `AGENTIC_TOKEN`, overridden by explicit `-token`. Query-token
compatibility (`-token-in-query` or a token already in the URL) remains. The
historical `fake-token` fallback for auth-disabled local development is retained;
it does not authenticate against a secured runtime. Defaults remain 150 clients,
10 turns per client, a 10-second ramp and a 90-second timeout. Set small explicit
values for a separately authorized smoke run.

A failed turn stops that persistent conversation; other clients continue.
SIGINT/SIGTERM cancels active requests, session preparation and ramp waits.
Preparation stops scheduling new creates; known created sessions are cleaned up
with an independent, shared `-timeout` budget when deletion is enabled. Unstarted turns are not
fabricated. WebSocket `final` ends an exchange on the reusable connection; there
is no per-turn stream-close measurement for WebSocket. `-debug-events` now emits
WebSocket receipt notifications only, never response payloads.

## Reports and raw format

Neither report is written unless its flag is supplied. `results/` is Git-ignored.
`-json-report=<path>` retains the existing `v1` aggregate schema: planned request
count, observed successes/errors, elapsed time, throughput and latency percentiles
in integer milliseconds. Its `target` field still means the endpoint URL, with
credentials, query and fragment removed. Its latency is still **start to final**,
not start to EOF. WebSocket total-request latency includes session creation and
dial; Swift persistent mode excludes setup, while Weaver includes its per-turn
preparation. Elapsed campaign time includes
preparation/cleanup, but excludes report writing. Failed turns are excluded from
latency statistics. The stricter SSE completion check can reduce successes, and
waiting for EOF can reduce throughput compared with the former final-only reader.
An interrupted run with unsent turns is no longer reported `OK`.

`-raw-report=<new-path>` writes UTF-8 JSON Lines, one object per attempted turn,
including failures. The file is created with mode `0600`; an existing path is
refused, never overwritten. Before truncating an existing summary, the writer
compares its file identity with the raw destination and refuses collisions,
including symbolic-link and hard-link aliases. Write failures return a nonzero exit status. Records
are collected in memory and exported after the run/cleanup, including graceful
cancellation; a killed process has no guaranteed raw export. Order across clients
is completion order; within a client/conversation it is turn order.

Swift records keep schema `fred.bench.turn.v1`:

| Field | Meaning |
| --- | --- |
| `schema_version` | Exactly `fred.bench.turn.v1`; incompatible changes need a new version. |
| `target`, `protocol` | Actual adaptation (`swift` or `weaver`), and `sse` or `ws`; no endpoint URL. |
| `preparation_mode` | Additive field: `not_performed` for historical Swift, `per_turn` for Weaver. This describes the path, not a successful preparation. |
| `campaign_id` | Automatically generated ID shared by this run's records. |
| `client_id` | One-based logical worker number, not an authenticated user ID. |
| `conversation_id` | Campaign-scoped SHA-256 pseudonym of the session ID; generated local identity if no session exists. No backend ID is exported. |
| `turn` | One-based attempt number within that client's conversation. |
| `started_at` | Client-side execution start in RFC3339Nano, not a server admission/execution timestamp. Includes opening/setup in total-request mode. |
| `first_text_at` | First nonempty assistant text observed: Swift `assistant_delta.delta` or `final.content`; WebSocket `stream.content` or `final.content`. |
| `final_at` | First complete final event received, even if a later failure makes the turn unsuccessful. |
| `stream_closed_at` | Clean SSE HTTP-body EOF observed, even if final is missing. Absent on forced close, transport error or WebSocket. |
| `outcome` | `success`, `error`, `timeout` or `canceled`. |
| `error` | Fixed category on failure; omitted on success. |

Optional timestamps are **omitted**, never zero-filled. Technical status, tool,
reasoning, title and warning events are not first text. A final carrying the
first answer text can set `first_text_at` and `final_at` to the same instant.
Subtract timestamps to obtain first-text, final and EOF latencies; all are client
observations, not server instrumentation. A setup failure records one failed
attempt with no invented text/final/EOF observation.

Error categories are `http_status`, `execution_error`, `execution_interrupted`,
`invalid_event`, `incomplete_stream`, `event_too_large`, `transport_error`,
`timeout` and `canceled`. No arbitrary server error messages, prompts, response
text, headers, tokens or backend conversation IDs enter the raw format. Summary
error samples also use these safe categories. No per-user authentication or
cross-campaign identity correlation is claimed.

### Weaver timing and raw v2

Weaver records use `fred.bench.turn.v2`: `started_at` is the **turn attempt start**,
before preparation, not an execution/admission timestamp. Opening (instance GET,
registration or operator-session GET) is outside successful per-turn latency. An
opening failure produces one failed attempt with its setup start and no fabricated
preparation/execution observations. Unstarted later turns are never exported.

| Weaver observation | Meaning |
| --- | --- |
| `preparation.started_at`, `.finished_at`, optional `.error` | Per-turn preparation request plus client validation, including rejected preparation. |
| `execution_started_at` | Client starts the SSE request after validated preparation; absent if none was sent. Not proof of server admission. |
| `first_text_at`, `final_at`, `stream_closed_at` | Same event/EOF semantics as Swift; all absent on preparation refusal. |
| `history.started_at`, `.finished_at`, optional `.error` | Session metadata and messages reads after successful stream completion. |
| `history_messages` | Number of rows returned, only after successful history reading; not a count of validated turns. |

Subtract preparation timestamps for preparation latency; subtract
`execution_started_at` from text/final/EOF for execution-request observations.
The Weaver summary latency remains start-to-final, including preparation but
excluding history and cleanup. Success requires final, EOF and the history read;
history failure retains the observed execution timestamps but excludes that turn
from successful latency statistics. Campaign elapsed/throughput includes setup,
history and cleanup. Swift latency semantics are unchanged: comparing the two
summaries does not compare equivalent UI paths. Neither format measures admission.
The aggregate schema remains `v1`, with optional Weaver `space_id` and
`cleanup_errors`; its `target` remains a sanitized URL (Fred origin for Weaver).

Weaver adds bounded error categories `http_<status>` for Control Plane/history
requests, `invalid_binding`, `invalid_session`, `session_not_created`,
`unsupported_transport`, `model_unavailable`, `invalid_execution_url`,
`history_unavailable`, `invalid_response` and `invalid_history`. Execution keeps
the shared SSE categories (`http_status`, etc.). No upstream error text is exported.

## Code boundary and local validation

- `main.go`: existing CLI flags, target validation and run/report wiring.
- `engine.go`: one load engine, concurrency, sequential turns, cancellation,
  common observations and isolated collection. It consumes `Open(ctx, client)`
  and a conversation exposing `Execute(ctx)`, `ID()` and `Close()`.
- `swift.go`: Swift sessions and request construction; `ws_bench.go` retains
  Swift WebSocket wire and HTTP lifecycle helpers.
- `weaver.go`: public contracts, per-conversation lifecycle, per-turn preparation,
  execution and minimal history reads; no scheduling loop.
- `sse_bench.go`: reusable HTTP/SSE framing and completion handling, plus the
  shared SDK runtime event decoder used by Swift and Weaver.
- `reports.go`: aggregate compatibility and explicit raw export.
- `report_html.go`, `report.html.tmpl`: offline scenario projection and self-contained interactive report.
- `auth.go`: private factory input, bounded login and per-identity refresh.
- `scenario.go`, `scenario_reports.go`: opt-in levels using the common engine,
  post-window checks, progressive private records and phase summaries.
- `oracle.go`: bounded marker/ACK and persisted-history verification.
- `prepare.go`, `onboarding.go`: explicit preparation command and read-only
  preflight through the existing Control Plane terms/access APIs.

Checks (Go 1.22.2 is installed on the development machine; use the toolchain
override without changing `go.mod`):

```bash
GOTOOLCHAIN=go1.24.0 go test -race ./...
GOTOOLCHAIN=go1.24.0 go vet ./...
git diff --check
```

Local validation runs the commands above (including the existing Swift
Swift regressions), gofmt on changed Go files and `git diff --check`. Tests use
`httptest` and doubles only: opening and two turns, distinct client conversations,
request payload/order, revision/placement errors, 401/403/409, model availability,
URL/redirect refusal, preparation/stream cancellation and timeout, final then EOF,
truncation/terminal errors, history reads, retention/cleanup receipts, CLI wiring,
raw Weaver success/failure privacy and explicit Swift absence of preparation.
Scenario fixtures also cover initial multi-identity login, local issuer policy,
singleflight rotating refresh and sticky failures, both targets with shared or
distinct users, context corruption, history consistency, one failing conversation
without POST replay, 100 logical mock fragments, raw durability during graceful
cancellation, exclusive outputs and real CLI wiring. Terms tests cover explicit
acceptance, disabled/already accepted versions, version changes, safe failures,
synthetic-only preparation and its lack of load requests. All services are
isolated `httptest` doubles, not the running Keycloak, mock or Fred installation.
No real Fred endpoint, k3d, deployment, load campaign or performance comparison
was exercised. Backend/frontend contracts were read, not modified.
