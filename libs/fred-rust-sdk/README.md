# fred-rust-sdk

Internal Rust library shared by the Control Plane and the monitor. It is a local
Cargo path dependency with `publish = false`; nothing is published to crates.io.

The initial public surface is `security`:

- `authentication`: the existing Fred JWT/OIDC verifier, JWKS cache, identity
  mapping, route-scoped runtime delegation and Axum caller extractor.
- `platform`: typed platform roles and read-only checks of the existing
  `platform_role_grant` table. The caller supplies a PostgreSQL pool or executor.

The library does not start services, open a database pool or run migrations.
Applications own configuration and admission of callers. Control Plane still owns
role mutations, schema migrations, consent and organization/space authorization.
Its existing Rust module paths re-export the shared types to preserve consumers.

The root Cargo workspace contains this library, Control Plane, its existing agent
crate and `apps/monitor`. It shares one root `Cargo.lock` and default `target/`.
Rust packages are built independently; building the monitor does not build the
Control Plane, Temporal or the S3 SDK.

From this directory:

```sh
make code-quality
make test
```

Authentication regressions moved here with the implementation. Changes must
preserve issuer/audience/signature/time validation, identity mapping and the
separate human and delegated-workload admission contracts.

Experimental diagnostic tracing uses the existing logging subscriber. Applications
pass the configured `observability` section to the SDK; Control Plane supports:

```yaml
observability:
  tracer: diagnostic
  diagnostic:
    collector_endpoint: http://collector:4318/v1/traces
```

Without this selection, no exporter or worker is created. The service identity
comes from the application (`control-plane`), and the full endpoint comes from
YAML. The fixed parent-based sampler drops new roots and honors sampled incoming
W3C parents. Bench chooses which turns request traces; ordinary requests without
a sampled parent remain unrecorded. No activation or sampling environment variable
is needed. `logging::init` returns the optional provider, drained by
`telemetry::shutdown` at exit.

The middleware accepts W3C context without changing caller authority or the
separate request/correlation IDs. Unsampled context still propagates to JWKS
HTTP requests; baggage is not forwarded. This is a development diagnostic tool,
not production tracing or an authenticated bench-only channel.
Explicit spans cover HTTP,
runtime binding, JWKS cache lookup, actual JWKS HTTP, and local JWT validation.
Only a Keycloak network fetch has category `keycloak`; cached validation stays
`auth`. The runtime-binding span includes its SQL work, without per-query spans.
The export boundary admits fixed operation names and bounded technical attributes,
and removes events, payloads, SQL text, links and error descriptions. Failed
JWKS fetches, failed lookups and local JWT rejection carry an error status;
a successful stale-key fallback remains a successful lookup even if its nested
fetch failed. This producer-side safeguard is retained because all current Rust
observations are technical; destination-specific filtering also occurs in the
collector before the report file is written. Stdout logs
remain independent, including when the configured log threshold is WARNING.

The export queue holds at most 2048 spans, with batches of 256, a three-second
HTTP timeout and a five-second shutdown wait. A full queue or unavailable
collector may lose telemetry; export failure does not fail a request. These
technical durations are not accounting or benchmark acceptance results.
