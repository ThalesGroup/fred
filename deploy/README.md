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

## Contact

For any security or deployment-related concerns, please reach out via the [Fred GitHub repository](https://github.com/ThalesGroup/fred).
