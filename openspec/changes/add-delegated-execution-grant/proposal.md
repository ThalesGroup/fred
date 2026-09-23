## Why

An agent run calls Knowledge Flow and the control plane with the person's own
access token. That token lives 300 seconds and the runtime cannot renew it, so
any run longer than that is refused part-way; the refusal reaches the model as
plain text, and no run has a wall-clock ceiling. The runtime must be able to act
for a person without holding a credential that expires, and without the platform
signing or verifying anything of its own.

## What Changes

- One credential provider in the shared runtime supplies outbound credentials at
  call time for every route — the tool-protocol wrapper and the native HTTP
  clients — and for every child agent. No copied credential string.
- Losing authority downstream is a typed, terminal outcome: the run and its
  children are cancelled, the reason is machine-readable on the existing terminal
  error event, upstream detail never reaches the transcript, and the call is never
  retried under the platform's own identity.
- Every run has a wall-clock ceiling and a bound on concurrent children, separate
  from per-call timeouts, with deployment defaults and an agent-level override.
- Failed workload-token refreshes enter a shared, bounded cooldown so concurrent
  runs do not each queue another request to an unavailable identity provider.
- Behind a per-deployment flag (default off): the agent backend verifies the person's
  token locally at admission, then calls receivers with its own workload token plus
  a plain delegation grant — the person, the run and the agent — sent as request
  parameters. A receiver accepts the grant as the caller's statement only when
  the verified workload identity is trusted for that receiver. It builds an
  asserted principal that never carries a service role and applies the person's
  permissions. Explicit own-credential guards remain on the runtime surfaces
  listed in the design; full
  user/agent parity is outside this step. Fred adds no grant signing or keys.
- A supported stream reconnect authenticates the owner with their current token
  locally; it never stores that token or supplies it to the running execution.
- The control plane records every run from an authenticated workload report and
  records its end. It verifies the reporting workload's token and authorizes its
  own API for the asserted person. The person's token stays at runtime admission;
  the report also supports the trusted-workload admission introduced by the next
  change. The record serves listing, cancellation and audit and is never
  consulted by receivers on a call.
- MCP servers gain a `delegated` client auth mode: workload token plus the grant,
  carried outside tool arguments. Under the flag a `user_token` server is refused
  at activation; the person's token is never forwarded.
- The ingress rejects external requests that carry grant parameters, and every
  receiver ignores the parameters unless the caller is allow-listed.
- Deployment acceptance covers token validation, service-account binding,
  user authorization, retained own-credential restrictions, transport protection
  and delegation regression tests.

## Capabilities

### New Capabilities

- `delegated-execution-grant`: how a run identifies the person it acts for after
  admission, how receiving services accept the workload's statement, and how
  authority loss and the run ceiling are enforced.

### Modified Capabilities

None.

## Impact

- Shared security library: grant model as request parameters, parsing in the
  shared user dependency, asserted principal and receiver-owned workload identity
  bindings; the new MCP client auth mode value.
- Shared runtime: credential provider, run record, run registration, typed outcome
  and cancellation, run ceiling, MCP activation rule.
- Receivers: Knowledge Flow (REST and the MCP mount share the parser hook) and the
  control plane; every endpoint a run can call declares the grant parameters and
  the generated clients are regenerated. The control plane's runtime-binding
  endpoint also records the run; a run-end endpoint records how it ended. Protected
  product records and request context retain both identities; logs exclude them.
- SDK contract: additive `reason` field on the terminal error event; dated entry in
  the runtime execution contract; regenerated runtime client.
- Deployment tooling (separate repository): allow-list values per receiver, the
  ingress rule, flag wiring. The workload client and its secret already exist.
  Either half lands first safely because the flag is off by default.
- Deferred to later changes: removal of the service-role shortcuts and the standing
  relation; the background and scheduled lane; per-run resource/action scope; a pod-bound
  workload credential in place of the bearer.
