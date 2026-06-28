# Architectural Security Report: Managed Agent Execution

**Subject:** Secure Decoupled Control & Data Plane — pod-side authorization
**Status:** ✅ **Current (RUNTIME-07 rev. 2, 2026-06-28 — RFC decision D5).** This is the
authoritative security narrative for managed agent execution. The field-level contracts are
[`RUNTIME-EXECUTION-CONTRACT.md`](./RUNTIME-EXECUTION-CONTRACT.md) (execution surface) and
[`CONTROL-PLANE-PRODUCT-CONTRACT.md`](./CONTROL-PLANE-PRODUCT-CONTRACT.md) (product surface).

> **History.** An earlier revision of this document argued for a control-plane-issued,
> cryptographically **signed Execution Grant** (a "valet key"). That approach was **rejected**
> (RFC §13/D5): it makes the control-plane a proprietary cryptographic root of trust — an
> unnecessary homologation burden for C3. The grant was removed; see
> [`EXECUTION-GRANT-SECURITY-HARDENING-RFC.md`](../rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md)
> and `RUNTIME-EXECUTION-CONTRACT.md` §8.11 for the full record.

---

## 1. Executive Summary

The platform uses a **decoupled architecture**:

- A **Control Plane** manages the catalogue: teams, permissions, agent instances, sessions.
- A **Runtime (Agentic Pod)** performs **execution only** and is the **authorization authority
  for execution**.

The key property: **the control plane issues no capability token.** It tells the browser
*where* an agent runs; it does not hand out a credential the pod must trust. Each agent pod is
a **Keycloak OAuth2 resource server** that authenticates the caller's JWT and authorizes every
request itself with a **pod-side OpenFGA (ReBAC) check**. This is the model already homologated
on `main`'s agentic-backend, re-instantiated per pod.

This separation enables:

- **Strong security (Zero Trust)** — every request proves identity and authorization at the pod
- **High performance** — direct SSE streaming, no proxy bottleneck
- **Homologability (C3)** — no bespoke cryptographic root of trust; only Keycloak + OpenFGA

---

## 2. Key Concepts

| Concept                   | Meaning                                                                  |
| ------------------------- | ------------------------------------------------------------------------ |
| **User**                  | Authenticated via Keycloak (identity = the JWT `sub`)                    |
| **Team**                  | Security boundary; all data & agents are scoped to a team (incl. the personal team `personal-<uid>`) |
| **Control Plane**         | Catalogue + display-filtering + runtime **resolution** (no token issuance) |
| **Runtime (Agentic Pod)** | Resource server; runs agents, streams responses, **authorizes every request** |
| **`runtime_context.team_id`** | The team the caller acts in; the pod authorizes against it via OpenFGA |

---

## 3. The Execution Flow (Step-by-Step)

### Step 1 — Prepare (Control Plane, no token)

The frontend calls `POST /teams/{team_id}/agent-instances/{id}/prepare-execution`. The control
plane validates team membership, resolves which runtime pod serves the instance, resolves the
session's context prompt, and returns an `ExecutionPreparation`: ingress-relative URLs
(`execute_stream_url`, …), `team_id`, `agent_instance_id`, and `context_prompt_text`.
**No grant, no expiry, no capability.**

### Step 2 — Execute (Runtime, direct)

The frontend calls the runtime pod **directly** at `execute_stream_url`, carrying:

- the **user's Keycloak JWT** in the `Authorization: Bearer` header (identity), and
- `runtime_context.team_id` in the body (the team the caller claims to act in).

There is no second credential.

### Step 3 — The pod authorizes (`_authorize_and_resolve` in `agent_app.py`)

Every execute / resume / evaluate request passes the same gate, in order:

1. **🔒 Identity from the token, never the body.** `user_id` is stamped from the validated JWT;
   any body-supplied `access_token` / `refresh_token` is neutralized.
2. **🔒 Session ownership.** An existing `session_id` must belong to the caller — conversations
   are private per owner, which blocks intra-team session hijacking by guessing an id.
3. **🔒 OpenFGA authorization.** The caller must hold `CAN_READ` on `runtime_context.team_id`
   (the canonical id, e.g. `personal-<uid>` for a personal space). Denial **fails closed (403)**.
   A direct `agent_id` is **forbidden under the `c3` profile**.
4. **🔗 Team-scoped resolution + cross-check.** The instance template + tuning is resolved from
   the control plane through a ReBAC-gated, team-scoped callback; the resolved owner team is
   then cross-checked against the caller's claimed team.

The `team_id` is caller-supplied but safe: OpenFGA only authorizes teams the user actually has
a relation to.

---

## 4. The `c3` Security Profile (fail-closed)

Because the pod is the only thing standing between a caller and execution, the authorization
path must never silently degrade. The `security.profile: c3` setting
(`fred_core.security.oidc.apply_security_profile`) enforces this **at startup**:

- forces **strict JWT issuer + audience** validation (`verify_aud=True`);
- **refuses to boot** unless Keycloak user auth, M2M, and OpenFGA ReBAC are all enabled
  (no no-security / mock-admin, no permissive Noop engine).

So *misconfigured = won't start*, never *misconfigured = silently open*. The profile is honored
today by **control-plane-backend, fred-agents, and knowledge-flow-backend**. Workers (temporal)
serve no authenticated request surface and do not apply it. See
[`deploy/README.md`](../../../deploy/README.md) for the chart knob and classification tiers.

### Per-agent audience (anti-confused-deputy)

Each agent pod is its own Keycloak client and validates `aud == its own client_id` (decision
D5c). A token minted for one agent therefore cannot be replayed against another agent's pod.

---

## 5. Why This Design

### ✅ No central bottleneck

The control plane never proxies execution; runtime SSE streams directly to the user. `prepare`
is a one-shot resolution, off the streaming path.

### ✅ Zero Trust, decided at the pod

Every request proves **who** you are (Keycloak JWT) and **what you may do** (OpenFGA on your
team), independently, at the pod. No trust is granted by network location, internal service,
or implicit relationship.

### ✅ Homologable

Authorization uses only Keycloak (a standard OIDC provider) and OpenFGA (the ReBAC engine
already used platform-wide). There is no bespoke signing key, JWKS endpoint, or capability
format to review or rotate — which was the homologation burden the signed-grant approach
introduced.

---

## 6. Infrastructure Security (Defense in Depth)

The pod-side checks sit on top of standard Kubernetes security:

- **Transport** — HTTPS / mTLS via ingress / service mesh.
- **Network isolation** — runtime pods are reached only through controlled ingress; the
  frontend never sees internal service names, pod IPs, or cluster topology.
- **Deferred hardening (not yet in-tree, tracked under RUNTIME-07 / OPS):** NetworkPolicies
  (ingress→pod, pod→OpenFGA, pod→Keycloak, deny inter-agent), per-pod Keycloak audience
  mappers, and per-pod client_id Helm values. These complete the C3 posture at the
  infrastructure layer; the application-layer fail-closed behavior above does not depend on them.

---

## 7. One-Line Summary (for reviewers)

> Every direct runtime call must carry an authenticated Keycloak JWT, and the agent pod
> authorizes it per request with an OpenFGA `CAN_READ` check on the caller's team — the control
> plane issues no token. This eliminates proxy bottlenecks and any bespoke cryptographic root
> of trust while keeping strict, fail-closed, team-scoped access control.
