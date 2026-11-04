# Embedded Rust agent

`fred-rust-agent` executes admitted model calls inside the Control Plane workload.
The host owns authentication, consent, instance/space authorization and the common
`model_catalog::instance::decide` decision. The library owns local provisioning
checks, the turn deadline, usage reports and Fred event production; `rig-agent` owns
the model calls, the tool loop and the history. Document search is fixed in the
runtime, without instance tuning or capability registration.

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

Ralph uses Rig's conversation memory across successful turns. The Control Plane
supplies its PostgreSQL store and the authorized session ID as Rig's log name;
this library has no database access. Rig loads the log before inference and appends
the completed turn before Fred emits `final`. Preparation exposes the shared
`GET {base_url}/agents/sessions/{session_id}/messages` contract, so the existing
chat restores questions, answers, tool traces and sources after reloading. Unknown,
foreign and withdrawn sessions receive the same 404. Synchronous execution and
HITL/UI-parts remain unsupported. Session metadata retains the common ownership
and instance-association checks. The browser input limit is 16,384 Unicode scalars,
fitting the 65,536-byte runtime ceiling.

The library checks `platform.inference_credentials` against the admitted source,
source revision, destination and credential binding before reading the named local
environment variable. See the [Control Plane README](../../apps/control-plane/README.md) for the common contract and coordinated
rotation. An absent or mismatched binding returns 503 before opening the event
stream; forbidden/unknown selections return 409 with the shared decision error.
No failure substitutes another model, source, account or credential.

The pinned Rig 0.46 crates run one `rig-agent` agent per turn, over its Chat
Completions wire with an explicit API key and base URL, and a shared reqwest pool
(redirects disabled; 5-second connect and 60-second read timeouts). A destination
on `api.mistral.ai` uses Rig's Mistral dialect, which sends no `stream_options`.
The agent consumes the admitted model, temperature, token ceiling, top-p and
reasoning through Rig's typed options; an option the wire cannot honour fails the
request instead of being dropped. The 120-second turn deadline starts at local
admission and covers model and search calls. The answer makes at most two model
calls and one document search, retaining the same model credential, offer and
options throughout.

The Fred answer SSE starts with `status`, followed by reasoning, document-search
and `assistant_delta` events as the provider streams them, then `final` with the
complete answer. Native reasoning uses the shared `thought_start`, `thought_delta`
and `thought_end` events with `source: model_native`. Only displayable provider
text is forwarded, never signatures, encrypted or redacted payloads. An answer
without provider reasoning produces no reasoning block. Text a model writes before
its search appears live; the chat clears it at the tool row, and `final` holds only
the last reply.
A successful title may add `session_title` before `final`; the host sequences
the combined stream monotonically. The provider's finish reason is retained in Fred's
normalized vocabulary. A failed/timed-out completion or a provider stream cut before
its end emits terminal `execution_error`, with a fixed public message and no provider
body or credential; deltas already sent stay, and no `final` follows.
The stream is pulled by its consumer, so a slow browser slows the provider read.
Dropping it cancels the in-flight run; no detached producer remains.
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
512 KiB. Empty results are valid. A transport, authorization or invalid-response
failure, like invalid arguments, closes the tool row with `is_error` and a fixed
message; the model then answers, as it does after a Python tool's failure.

The `search` module owns this contract; the host's `kf_search` only transports the hits. It
produces what the Python `search_documents` capability produces, so the shared chat
renders both alike without a Rust-specific path:

- the tool content, read by the model and the trace, is `{query, hits}`: at most
  five excerpts of 4,000 characters, with titles limited to 256 characters and only
  document ID, file name, page, section and score besides;
- `final.sources` carries the whole hits the chat cites as source cards, except
  those scoring below half of the call's best score;
- dataset pointers reach neither, because they are not documentary evidence and
  Ralph has no tabular tool to pivot to.

`libs/fred-sdk/tests/fixtures/embedded_search_turn.json` binds the Rust events, the
Python event contract and the chat's source and trace views.

The second model call receives the correlated tool result under a `none` tool
choice. A model that calls again ends the turn with `execution_error`: Rig's turn
budget refuses a third call, and the search itself runs at most once. The prompt
treats excerpts as untrusted data and asks for textual title/page references. The
shared chat receives `tool_call` before search starts and a correlated `tool_result`
with elapsed time and an error flag. An expired turn closes that tool row before the
terminal `execution_error`.
Each successful run saves its user question, model replies and tool results together.
A failed or cancelled run saves none of its new messages.

## Consumption

Ralph participates in the `model_usage` journal for managed execution. A missing
`session_id` returns 422 before inference. The library accumulates input, output
and cache token counts from each model response Rig completes, including responses
without displayable text. Missing counters default to zero. It reports the aggregate
once on completion, error or stream drop, if any model response completed. A failed
second model call therefore preserves consumption of the first call. A provider
reports usage when its reply ends, so a reply cut or abandoned mid-stream is not
counted; nor is a reply Rig fails on a refused tool call.
The host uses the admitted offer, fresh report/exchange UUIDs and server time;
the shared HTTP-report transaction derives person, space and instance from the
session. Token counts never enter browser events, and the agent crate has no DB
access. A turn with no completed model response produces no report. These counters
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

The title agent has no conversation memory and cannot write the answer log.
The title request reads at most 600 characters, targets 3–8 words and cleans plain
text to 80 characters. Generation times out after 10 seconds. The host waits at
most 2 seconds before yielding the final event; dropping the stream drops unfinished
title work. Title errors never fail the answer. Decoded title usage goes through
the existing usage callback as a separate report for its actual offer, even when
the text is invalid; it is not included a second time in the answer aggregate.

The host conditionally persists the result with its admitted attempt and provenance
before emitting `session_title`. Manual renames and deletion win at the database
boundary. See the [owner contract](../../apps/control-plane/README.md#automatic-conversation-titles).

## Deliberately limited

Rig is pinned to 0.46 and evolving quickly. Ralph uses its memory and concurrency
contracts directly; it does not implement a second history engine.

- The whole log is read each turn, and PostgreSQL rewrites the `bytea` value on
  every append. There is no history window or compaction: a sufficiently long
  conversation exceeds the provider's context limit and fails the turn.
- An interrupted or failed turn saves nothing. Closing the browser during the
  answer loses that question and its partial reply on reload.
- Concurrent runs from two tabs may both consume model tokens. Rig's optimistic
  append accepts the first save; the other run ends with a fixed public history
  error after its model call, without overwriting the saved conversation.
- A failed save can follow already streamed answer text. There is no `final`, and
  the reply is absent after reload. The consumed tokens are still reported.
- Reloaded sources come from the bounded tool result: excerpts are truncated and
  operational fields are absent. Citation filtering uses the saved hits, so its
  threshold can differ from live filtering when a higher-scoring dataset pointer
  was excluded from the tool result. Reasoning, token badges and model metadata
  are deliberately not reconstructed.
- The `rig-session` format belongs to a pre-1.0 library. A Rig upgrade may reject
  an older conversation as unreadable; the reader then fails without rewriting it.
- The store supports conversation logs only, with no images or auxiliary files.

Conversation removal and retention belong to the Control Plane lifecycle, not to
Rig. Removing access hides history immediately; physical deletion follows the
retention receipt and attachment cleanup. The stored log follows the session row's
foreign-key cascade only at physical deletion. `model_usage` is independent and
survives. Python history cleanup is also coordinated by the Control Plane, through
the runtime's own purge routes; the Control Plane never accesses Python's schema.

## Direct demonstration

The existing direct request `{"agent_id":"fred.github.ralph","input":"Bonjour"}`
still replies `Hello world!` without any LLM or managed-instance authority. It cannot
use inference provisioning, call KF or produce consumption reports. Default empty/null
unsupported execution options remain accepted; nondefault capabilities, HITL and
history options return 422.

## Targeted verification

`cargo test -p fred-rust-agent --lib` exercises the real Rig agent and HTTP adapter
against a loopback SSE provider: destination, model, options, fictitious credential,
missing/mismatched provisioning, errors, deadlines, a delta delivered before the
provider finishes, a stream cut before its end, mid-reply cancellation, usage before
the last event, tool-call correlation, single-search bounds, partial failures and
cancellation between model calls.
The same fixtures cover native reasoning, opaque-data exclusion, event ordering,
terminal errors, and cancellation or deadline expiry between trace deliveries.
Memory tests cover second-turn replay and renewed search, cancellation without a
save, persistence before `final`, fixed save errors and the shared history fixture.
Control Plane's `agent_instances::model_catalog` integration tests additionally
cover HTTP instance/session creation, preparation under a custom router mount,
the browser execution envelope, delegated admission, browser projection,
source removal, revocation and consumption provenance, including browser
disconnection, against disposable PostgreSQL. A loopback KF fixture checks the
delegated identity, document scope, excerpt limits, empty results and errors. No real provider or k3d validation
is implied. Workspace Cargo.lock and the existing Docker build own the library
dependency.
