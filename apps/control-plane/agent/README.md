# Embedded Rust agent

`fred-rust-agent` executes admitted model calls inside the Control Plane workload.
The host owns authentication, consent, instance/space authorization and the common
`model_catalog::instance::decide` decision. The library owns local provisioning
checks, Rig invocation, bounded execution and Fred event production. Document
search is fixed in the runtime, without instance tuning or capability registration.

## Managed execution

`POST {base_url}/agents/execute/stream` accepts an `agent_instance_id`, nonblank
`input` (at most 65,536 bytes), required `session_id`, and `runtime_context` containing
`space_id`, optional `model_choice: {source_id, upstream_model_id}` and `reasoning`.
The authenticated host resolves current identity and instance authority in process.
It checks the instance's runtime/template, then passes the private admitted decision
to the library. Ralph is an instantiable, fixed template with no capabilities or
tuning fields. Organization enablement and space permissions use the existing
catalog and instance routes. Preparation routes SSE to the Control Plane's own
configured HTTP mount, without an external runtime source entry. The existing
chat's `steering_turn_id` and `language` are accepted as inert metadata; they do
not enable steering or change the inference prompt.

Ralph has no memory: every message is an independent turn. Preparation returns
null synchronous-execution and history URLs, and false
HITL/UI-parts support. The existing chat displays a notice and keeps only this
visit's live messages; leaving/reloading does not restore them. Session metadata
still uses the common ownership and instance-association checks. The browser
input limit is 16,384 Unicode scalars, fitting the 65,536-byte runtime ceiling.

The library checks `platform.inference_credentials` against the admitted source,
source revision, destination and credential binding before reading the named local
environment variable. See the parent README for the common contract and coordinated
rotation. An absent or mismatched binding returns 503 before opening the event
stream; forbidden/unknown selections return 409 with the shared decision error.
No failure substitutes another model, source, account or credential.

The pinned `rig-core = 0.42.0` uses its OpenAI Chat Completions adapter, with an
explicit API key, base URL and shared reqwest pool (redirects disabled; 5-second
connect and 60-second HTTP timeouts). Its request builder consumes the admitted
model, temperature, token ceiling, top-p and reasoning. Official versioned API:
[completion request builder](https://docs.rs/rig-core/0.42.0/rig_core/completion/request/struct.CompletionRequestBuilder.html).
The 120-second turn deadline starts at local admission and covers model and search
calls. The answer makes at most two model calls and one document search, retaining the
same model credential, offer and options throughout.

The Fred answer SSE sequence is `status`, one `assistant_delta` with the completed
provider text, then `final`. A successful title may add `session_title` before
`final`. This buffers the final answer; it is not token streaming
from the upstream provider. The provider's finish reason is retained in Fred's
normalized vocabulary. A failed/timed-out completion emits terminal
`execution_error`, with a fixed public message and no provider body or credential.
Dropping the stream cancels the in-flight future; no detached producer remains.
No call can run after the turn closes. Attribution and revisions are logged through
the host's tracing context; the host's existing logger strips dependency payloads.

## Fixed document search

Set `platform.knowledge_flow_url` to KF's trusted base URL, for example
`http://localhost:8111/knowledge-flow/v2`, to expose `search_documents(query)` to
the model. An absent URL keeps text-only execution. The selected model must
support OpenAI-compatible tool calls; no model substitution is performed.

The host reuses `security.m2m` and its cached, renewable Keycloak service token.
The Control Plane workload must have KF's accepted delegation audience and caller
role (normally `fred-delegation` and `delegation_caller`). The URL must contain no
credentials, query or fragment. Redirects are disabled. Configuring a URL without
M2M provisioning returns 503 before inference. Live role provisioning is an
operator prerequisite, not something this library creates or verifies at startup.

The first model response either answers directly or requests one search. The
host calls KF's existing `POST /documents/search` using the admitted person,
instance and space, with a server-generated run ID. The document-context header
selects the authorized corpus of that space and its ancestors; attachments remain
excluded. The model can supply only a nonblank query of at most 2,048 characters.
KF remains responsible for access, publication and lifecycle checks.

Search uses the default KF policy, `top_k=5`, no reranking or retry, and a 30-second
timeout including service-token acquisition. The wire response is capped at
512 KiB, and the model receives at most five excerpts of 4,000 characters, with
document IDs, available page numbers and titles limited to 256 characters. Dataset pointers are
excluded because they are not documentary evidence. Empty results are valid;
transport, authorization and invalid-response failures end the turn explicitly.

The second model call receives the correlated tool result and cannot request
another search. The prompt treats excerpts as untrusted data and asks for textual
title/page references. There is no new source panel or tool event in the browser.
Only in-turn messages are retained, until the stream completes or is dropped.

## Consumption

Ralph participates in the `model_usage` journal for managed execution. A missing
`session_id` returns 422 before inference. The library accumulates input, output
and cache token counts from decoded model responses, including responses without
displayable text. Missing counters default to zero. It reports the aggregate once
on completion, error or stream drop, if any model response was decoded. A failed
search or second model call therefore preserves consumption of the first call.
The host uses the admitted offer, fresh report/exchange UUIDs and server time;
the shared HTTP-report transaction derives person, space and instance from the
session. Token counts never enter browser events, and the agent crate has no DB
access. A turn with no decoded model response produces no report. These counters
cover Ralph's model calls, not KF's embedding workload.

The host starts one write attempt before yielding the response, with a two-second
timeout. This accounting task survives browser disconnection; inference remains
cancellable. A failed write is logged without content or secrets and does not
change the reply. This is best effort: there is no retry, outbox or recovery after
a process crash. The shared transaction preserves atomicity and report idempotency.

## Managed title attempt

Control Plane may reserve one optional title admission for a new session. The host
owns the title future alongside the answer stream, using this crate's existing
`InferenceTurn` transport, credential checks and inference spans. It is an extra
call, with independent bounded options and an organization-selected offer, or the
answer's admitted offer when no dedicated choice exists. No database or model
policy is introduced in the agent crate.

The title request reads at most 600 characters, targets 3–8 words and cleans plain
text to 80 characters. Generation times out after 10 seconds. The host waits at
most 2 seconds before yielding the final event; dropping the stream drops unfinished
title work. Title errors never fail the answer. Decoded title usage goes through
the existing usage callback as a separate report for its actual offer, even when
the text is invalid; it is not included a second time in the answer aggregate.

The host conditionally persists the result with its admitted attempt and provenance
before emitting `session_title`. Manual renames and deletion win at the database
boundary. See the [owner contract](../README.md#automatic-conversation-titles).

## Direct demonstration

The existing direct request `{"agent_id":"fred.github.ralph","input":"Bonjour"}`
still replies `Hello world!` without any LLM or managed-instance authority. It cannot
use inference provisioning, call KF or produce consumption reports. Default empty/null
unsupported execution options remain accepted; nondefault capabilities, HITL and
history options return 422.

## Targeted verification

`cargo test -p fred-rust-agent --lib` exercises the real Rig HTTP adapter against a
loopback provider: destination, model, options, fictitious credential, repeated
calls, missing/mismatched provisioning, errors, deadlines, stream cancellation
usage before the response event, tool-call correlation, single-search bounds,
partial failures and cancellation between model calls.
Control Plane's `agent_instances::model_catalog` integration tests additionally
cover HTTP instance/session creation, preparation under a custom router mount,
the browser execution envelope, delegated admission, browser projection,
source removal, revocation and consumption provenance, including browser
disconnection, against disposable PostgreSQL. A loopback KF fixture checks the
delegated identity, document scope, excerpt limits, empty results and errors. No real provider or k3d validation
is implied. Workspace Cargo.lock and the existing Docker build own the library
dependency.
