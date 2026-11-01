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
