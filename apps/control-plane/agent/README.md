# Embedded Rust agent

`fred-rust-agent` executes admitted model calls inside the Control Plane workload.
The host owns authentication, consent, instance/space authorization and the common
`model_catalog::instance::decide` decision. The library owns local provisioning
checks, Rig invocation, bounded execution and Fred event production. No separate
listener, deployment, Ralph configuration, tools or memory is introduced.

## Managed execution

`POST {base_url}/agents/execute/stream` accepts an `agent_instance_id`, nonblank
`input` (at most 65,536 bytes), optional `session_id`, and `runtime_context` containing
`space_id`, optional `model_choice: {source_id, upstream_model_id}` and `reasoning`.
The authenticated host resolves current identity and instance authority in process.
It checks the instance's runtime/template, then passes the private admitted decision
to the library. Ralph is an instantiable, fixed template with no capabilities or
tuning fields. Organization enablement and space permissions use the existing
catalog and instance routes. Preparation routes SSE to the Control Plane's own
configured HTTP mount, without an external runtime source entry. The existing
chat's `steering_turn_id` and `language` are accepted as inert metadata; they do
not enable steering or change the inference prompt.

This first chat increment has no memory: every message is an independent model
call. Preparation returns null synchronous-execution and history URLs, and false
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
The 120-second turn deadline starts at local admission. There are no tools or
unbounded agent loops; calls within a turn retain the same credential and decision.

The Fred SSE sequence is `status`, one `assistant_delta` with the completed provider
text, then `final`. This currently buffers one completion; it is not token streaming
from the upstream provider. The provider's finish reason is retained in Fred's
normalized vocabulary. A failed/timed-out completion emits terminal
`execution_error`, with a fixed public message and no provider body or credential.
Dropping the stream cancels the in-flight future; no detached producer remains.
No call can run after the turn closes. Attribution and revisions are logged through
the host's tracing context; the host's existing logger strips dependency payloads.

## Direct demonstration

The existing direct request `{"agent_id":"fred.github.ralph","input":"Bonjour"}`
still replies `Hello world!` without any LLM or managed-instance authority. It cannot
use inference provisioning. Default empty/null unsupported execution options remain
accepted; nondefault capabilities, HITL and history options return 422.

## Targeted verification

`cargo test -p fred-rust-agent --lib` exercises the real Rig HTTP adapter against a
loopback provider: destination, model, options, fictitious credential, repeated
calls, missing/mismatched provisioning, errors, deadlines and stream cancellation.
Control Plane's `agent_instances::model_catalog` integration tests additionally
cover HTTP instance/session creation, preparation under a custom router mount,
the browser execution envelope, delegated admission, browser projection,
source removal and revocation against disposable PostgreSQL. No real provider or
k3d validation is implied. Workspace Cargo.lock and the existing Docker build own
the library dependency.
