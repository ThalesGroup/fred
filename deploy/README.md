# Deployment Configuration

This directory contains Docker Compose files and Helm Charts for deployment of **Fred** elements.

## Security profiles & classification tiers

Fred deployments target a classification level (e.g. **C1** baseline, **C2**, **C3**
hardened). The single chart knob that drives the hardened posture is
`...security.profile`, exposed in `charts/fred/values.yaml` on the workloads that act
as request authorities.

| `security.profile` | Meaning |
| ------------------ | ------- |
| _unset_ (default)  | Baseline (C1/C2). Auth and ReBAC follow the individual `user` / `m2m` / `rebac` toggles; dev conveniences (mock-admin, soft JWT) remain possible. |
| `c3`               | Hardened, **fail-closed at startup**. Forces strict JWT issuer/audience validation, forbids no-security / mock-admin, and requires OpenFGA ReBAC enabled. The pod **refuses to boot** if `user`, `m2m`, or `rebac` is not enabled. The control-plane issues **no** signed execution grant — each agentic pod authorizes every request itself (Keycloak JWT + pod-side OpenFGA). |

**Where it is enforced today.** `profile: c3` is honored by the services that call
`apply_security_profile` at startup:

- **control-plane-backend** — ✅ enforced
- **fred-agents** (and any `fred-runtime` agentic pod via `create_agent_app`) — ✅ enforced
- **knowledge-flow-backend** — ✅ enforced
- **\*-worker** (temporal workers) — n/a; they serve no authenticated request surface

> The broader, cross-environment deployment strategy (a full C1/C2/C3 configuration
> matrix, NetworkPolicies, per-pod Keycloak audiences) is being consolidated under a
> dedicated OPS RFC. This section documents only the chart knob available today.

## Root bootstrap secret contract (AUTHZ-07)

`charts/fred` is a portable Apps-layer chart: it knows nothing about GCP, GKE, AKS,
ArgoCD, Flux, Vault, SOPS, or External Secrets. The one thing it does know is that
`control-plane-backend` — and only that pod — needs a single environment variable to
validate `POST /control-plane/v1/bootstrap/platform-admin` (the RFC Part 8 §40-42 root
bootstrap endpoint, closes the very first `platform_admin` grant on a fresh install):

```yaml
applications:
  control-plane-backend:
    configuration:
      app:
        bootstrap_token_env_var: FRED_BOOTSTRAP_TOKEN   # already the chart default
    extraEnvVars:
      - name: FRED_BOOTSTRAP_TOKEN
        valueFrom:
          secretKeyRef:
            name: <an existing Secret owned by the instance's Foundation layer>
            key: <bootstrap token key>
            optional: false
```

The chart never creates that Secret, never carries a literal value in a tracked file,
and never mounts `bootstrap_token_file` (local-dev only, not rendered here) inside
Kubernetes. Every instance overlay — the GKE/ArgoCD reference in
`fred-deployment-factory`, and any future platform (AKS/Flux, etc.) — supplies only the
`extraEnvVars` reference above, pointed at a Secret it already owns.

**If the overlay omits `extraEnvVars`** (the chart's own default), no
`FRED_BOOTSTRAP_TOKEN` variable is injected at all: the backend's own fail-closed logic
(`control_plane_backend/bootstrap/service.py::_read_configured_token`) makes the root
bootstrap endpoint explicitly unavailable rather than silently open. **If the overlay
configures a reference to a Secret/key that does not exist**, `optional: false` makes
Kubernetes itself refuse to start the pod — fail-closed at the platform level, not only
the application level. Both failure modes are intentional; neither is a bug to work
around with a fallback.

**Contract for a future AKS/Flux instance (out of scope here, tracked separately as
`INST-1` in `fred-deployment-factory`).** A new platform overlay reuses this exact same
chart contract unchanged and supplies, per instance:

- the target namespace;
- a pre-existing Kubernetes Secret (created by that platform's own secrets pipeline —
  Vault, External Secrets, sealed-secrets, whatever the target classification requires;
  this chart does not prescribe which) carrying the bootstrap token under a chosen key;
- that Secret's name and key, wired through `extraEnvVars`/`secretKeyRef` exactly as
  above — no forked template, no second chart;
- the instance's own Fred chart values (image tags, Foundation endpoint hostnames,
  ingress, etc.), independent of this contract;
- the Foundation endpoints the Apps layer expects to already exist (Postgres, OpenSearch,
  Keycloak, OpenFGA, Temporal — see `fred-deployment-factory`'s RFC-0001 §2-3 for the
  Foundation/Apps boundary those names must satisfy);
- the same fresh-install sequence as every other instance: empty Foundation → user
  self-registers in Keycloak → authenticated root bootstrap (this contract) → declarative
  platform import (`PLATFORM-IMPORT-RFC.md` §10) — never a Swift-to-Swift upgrade path;
- a recommendation (not enforced by Fred) to rotate or remove the Secret's bootstrap key
  once root bootstrap has completed, mirroring `KC_BOOTSTRAP_ADMIN_*`'s own operational
  hygiene note.

No Fred identity, team, or role ever belongs in that overlay's chart values — every
identity and role is either the self-promoted root bootstrap admin or a name in a
declarative import bundle, never a deployment-config literal.

## Contact

For any security or deployment-related concerns, please reach out via the [Fred GitHub repository](https://github.com/ThalesGroup/fred).
