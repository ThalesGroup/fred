# Embedded Rust agent

`fred-rust-agent` is a library linked into the control-plane binary. It validates
one direct-template request and produces Fred runtime events. The host owns the
Axum handler, authentication, consent checks, error envelope, CORS and logs.
There is no separate listener, certificate, process, configuration or deployment.
The library has no dependency on control-plane internals or SQL; SQLx and rig-core
will be introduced only when persistence and model execution are implemented.

## Call the hello-world route

Start the control-plane normally from `apps/control-plane` with `make run`.
Its existing database and identity dependencies still apply. With the default
local address and base URL:

```sh
curl --fail-with-body --no-buffer \
  --header @/absolute/path/to/bearer-header.txt \
  --header 'Content-Type: application/json' \
  --header 'Accept: text/event-stream' \
  --data '{"agent_id":"fred.github.ralph","input":"Bonjour"}' \
  http://localhost:8222/control-plane/v1/agents/execute/stream
```

The private header file contains `Authorization: Bearer <your token>`; keep it
outside the repository. The caller must satisfy the control-plane's existing
admission policy (authentication and CGU when enabled). In an explicitly configured
no-auth development environment, omit the bearer header. Caller-supplied
`runtime_context` never establishes identity or permission.

Use the deployment's HTTPS origin instead of the local HTTP URL when going
through its TLS proxy. The handler disables proxy buffering via
`X-Accel-Buffering: no`; proxy-specific buffering and stream timeouts still need
verification in that deployment. The frontend is not wired to this endpoint.

## Wire contract and limits

`POST {control-plane base_url}/agents/execute/stream` accepts the direct-template
subset of `libs/fred-sdk/fred_sdk/contracts/execution.py::RuntimeExecuteRequest`.
`agent_id` must be `fred.github.ralph`, and `input` must be nonblank. The answer is fixed.
The handler in `../src/embedded_agent.rs` uses the control-plane's `ApiJson` and
`AdmittedUser` extractors; routes and OpenAPI share the same registration.

The library emits the following `RuntimeEvent` subset from
`libs/fred-sdk/fred_sdk/contracts/runtime.py`. As in
`libs/fred-runtime/fred_runtime/app/agent_app.py::_sse`, each JSON object is framed
as `data: <JSON>` followed by a blank line, with `text/event-stream` content type:

```text
data: {"kind":"status","sequence":1,"status":"running"}

data: {"kind":"assistant_delta","sequence":2,"delta":"Hello "}

data: {"kind":"assistant_delta","sequence":3,"delta":"world!"}

data: {"kind":"final","sequence":4,"content":"Hello world!","finish_reason":"stop"}

```

Sequence numbers restart for each request. The stream ends after `final`, without
`[DONE]` or `turn_persisted`. Missing optional event fields retain Fred's defaults.
Each delta follows a 150 ms async delay to make streaming visible. Disconnecting
drops the producer; no detached task or database connection belongs to the stream.

Session/context metadata is accepted without history, retrieval or other effects
and discarded before streaming. Default empty/null execution options are accepted;
nondefault options (HITL, tuning, history seeding, capabilities) return 422.
Managed execution returns 501, unknown agents 404, ambiguous/missing targets or
blank input 422. All errors use the host's JSON `detail`/`code` envelope before
streaming. No business resources are accessed and no team permission is inferred.

The control-plane Cargo.lock resolves this path dependency and its Dockerfile
copies the library sources. No agent-specific build command is needed. The former
standalone HTTPS server and certificate commands have been removed.
