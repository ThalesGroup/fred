# RFC — Config-Driven Frontend Routing For Discovered Runtimes

- **Status:** Draft — awaiting review before implementation
- **Author:** Simon
- **Backlog:** `docs/swift/backlog/BACKLOG.md §3d.12`
- **Related:** `docs/swift/rfc/AGENTIC-POD-RFC.md`, `docs/swift/platform/PLATFORM_RUNTIME_MAP.md`, `docs/swift/backlog/FRONTEND-BACKLOG.md`

---

## 1. What is the need for such an RFC ?

The current architecture already lets `control-plane-backend` discover external
runtimes from `platform.runtime_catalog_sources` and expose their templates to
the frontend.

Example observed on 2026-05-29:

- runtime id: `dt-agents`
- `base_url: http://127.0.0.1:8020/dt/agents/v1`
- `ingress_prefix: /dt/agents/v1`

With that configuration in place, the frontend could list the runtime's agents
through control-plane discovery. But managed execution still failed in local
frontend development until `apps/frontend/vite.config.ts` was edited manually
to add a new proxy prefix for `/dt`.

This is the architectural gap:

- runtime discovery is configuration-driven
- runtime execution from the browser is still partly code-driven

That mismatch violates the Phase 3 configuration minimality rule: adding one
runtime source should require a config change, not a frontend source change.

## 2. Problem Statement

Today the platform has three correct pieces and one missing piece.

### 2.1 What already works

1. `control-plane-backend` discovers templates from
   `platform.runtime_catalog_sources`
2. `prepare-execution` resolves `agent_instance_id` to a configured runtime
3. `prepare-execution` returns ingress-safe relative runtime URLs built from
   `ingress_prefix`

### 2.2 What still drifts

Local frontend reverse proxies are handwritten:

- `apps/frontend/vite.config.ts` hardcodes known prefixes such as `/fred` and
  `/samples`
- `apps/frontend/dockerfiles/docker-entrypoint.sh` hardcodes a fixed set of
  backend locations

As a result, a runtime may be:

- visible in template discovery
- enrollable as a managed instance
- non-executable from the local frontend because its browser prefix has no
  matching proxy rule

## 3. Goals

- Keep `platform.runtime_catalog_sources` as the only product-side routing
  source of truth
- Remove the need to patch frontend source code when a new runtime source is
  added
- Preserve the current direct browser-to-runtime execution model
- Keep cluster-internal URLs out of browser-visible product payloads
- Keep frontend bootstrap free of runtime-routing responsibilities

## 4. Non-Goals

- No control-plane SSE proxy
- No change to the managed execution identity model (`agent_instance_id`,
  `ExecutionGrant`)
- No attempt here to implement Kubernetes auto-discovery; that remains the
  subject of `AGENTIC-POD-RFC.md`
- No expansion of `/config.json` or frontend bootstrap into a routing catalog

## 5. Proposal

### 5.1 Keep the public execution contract unchanged

This RFC does **not** change:

- `runtime_catalog_sources.runtime_id`
- `runtime_catalog_sources.base_url`
- `runtime_catalog_sources.ingress_prefix`
- `ExecutionPreparation.execute_url`
- `ExecutionPreparation.execute_stream_url`
- `ExecutionPreparation.messages_url_template`

The browser should keep receiving ingress-relative URLs and should keep calling
the runtime directly.

### 5.2 Generate frontend-local proxy routing from configured runtime sources

The missing dynamic piece is local/frontend reverse-proxy generation.

Rule:

- for every enabled `runtime_catalog_sources[*]` entry
- the frontend startup toolchain must materialize one proxy rule
- keyed by the exact `ingress_prefix`
- targeting the origin of `base_url`

Example:

```yaml
- runtime_id: dt-agents
  base_url: http://127.0.0.1:8020/dt/agents/v1
  ingress_prefix: /dt/agents/v1
```

becomes the local routing rule:

```text
/dt/agents/v1  ->  http://127.0.0.1:8020
```

The request path stays unchanged after the proxy boundary, so the runtime still
receives `/dt/agents/v1/...`.

### 5.3 Exact-prefix matching, not handwritten shorthand

The generated routing key must be the exact `ingress_prefix`, not a manually
chosen top-level alias such as `/dt`.

Why:

- it keeps the proxy map identical to the runtime contract returned by
  `prepare-execution`
- it avoids prefix guessing rules in frontend tooling
- it reduces accidental collisions between unrelated runtimes

### 5.4 Validation at startup

Generated routing must fail fast when configuration is ambiguous.

At minimum:

- duplicate `ingress_prefix` values are invalid
- overlapping prefixes that shadow each other are invalid
- empty or non-absolute `ingress_prefix` values are invalid

This should be surfaced as a startup/configuration error, not a runtime chat
failure discovered later by a user.

### 5.5 Initial implementation scope

The first required slice is host-based local frontend development with Vite.

That means:

- `vite.config.ts` must stop hardcoding the runtime prefix list
- it must build its runtime proxy entries from the configured runtime sources

Containerized frontend entrypoint parity (`docker-entrypoint.sh`) is desirable,
but it can ship in the same slice or as an explicit follow-up if the team wants
to keep the first implementation smaller.

## 6. Contract Impact

### 6.1 Control-plane product contract

No browser-facing product DTO change is required for this RFC.

The product contract remains:

- control-plane resolves runtime binding
- control-plane returns ingress-safe relative URLs
- browser executes directly against those URLs

### 6.2 Platform runtime map

`PLATFORM_RUNTIME_MAP.md` must be clarified later so the local-development
checklist states that frontend proxy rules are derived from
`runtime_catalog_sources`, not copied manually into `vite.config.ts`.

### 6.3 Frontend bootstrap invariants

This RFC stays aligned with `FRONTEND-BACKLOG.md`:

- runtime routing must not be loaded from bootstrap
- the shell must not require a runtime pod just to boot

The dynamic routing lives in the frontend startup toolchain, not in the browser
application bootstrap payload.

## 7. Alternatives Considered

### 7.1 Keep manual edits in `vite.config.ts`

Rejected.

This is the current failure mode. It makes external runtime onboarding fragile
and breaks the "config only" expectation already documented for
`runtime_catalog_sources`.

### 7.2 Proxy runtime execution through control-plane

Rejected.

This violates the direct SSE architecture and reintroduces exactly the proxy
hot path the runtime/control-plane split was designed to avoid.

### 7.3 Put runtime routing into frontend bootstrap

Rejected.

`FRONTEND-BACKLOG.md` explicitly forbids turning bootstrap into a runtime
routing registry. Bootstrapping the shell and exposing runtime execution paths
must stay separate concerns.

### 7.4 Add a fourth product config field just for frontend proxy targets

Rejected for now.

Phase 3 freezes `runtime_catalog_sources` as a three-field surface:

- `runtime_id`
- `base_url`
- `ingress_prefix`

We should first solve the drift by deriving local proxy rules from those fields.
If containerized frontend deployment later proves that `base_url` origin is
insufficient for reverse-proxy generation, that can be a follow-up RFC
amendment with a concrete use case.

## 8. Implementation Checklist

- Load enabled runtime sources once at frontend startup
- Derive one exact-prefix proxy rule per `ingress_prefix`
- Preserve the request path after the proxy boundary
- Fail fast on duplicate or overlapping prefixes
- Keep `/agentic`, `/knowledge-flow`, and `/control-plane` handling untouched
- Update platform docs so onboarding a new runtime no longer mentions manual
  edits to `vite.config.ts`

## 9. Done Criteria

- A newly added runtime source becomes executable from local frontend dev
  without editing frontend source code
- First-party runtime routes continue to work
- No control-plane execution proxy is introduced
- The documented source of truth remains `platform.runtime_catalog_sources`
