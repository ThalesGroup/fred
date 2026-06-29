# RFC — Runtime authorization model (C3 readiness): Keycloak resource servers + pod-side OpenFGA

**Status:** Active (rev. 2, 2026-06-27) — supersedes the signed-grant design (now in Appendix A).
**Author:** Dimitri Tombroff
**Date:** 2026-06-26 · reversed 2026-06-27
**Task ID:** `RUNTIME-07`
**Area:** `fred-sdk`, `fred-runtime`, `control-plane-backend`, `fred-core`, `apps/frontend`, `deploy/charts`
**Touches:** `RUNTIME-EXECUTION-CONTRACT.md` (§2.2/§2.4 grant → removed; managed-execution authz), `CONTROL-PLANE-PRODUCT-CONTRACT.md` (prepare-execution), `ARCHITECTURAL-SECURITY-REPORT.md` (valet-key thesis withdrawn)

> **Why this RFC was reversed.** A prior revision (Appendix A) hardened the managed-execution
> path by having the control-plane **mint an RS256-signed `ExecutionGrant`**. That makes the
> control-plane a **proprietary cryptographic root of trust** — an unnecessary C3/ANSSI
> homologation burden (private-key protection, anti-replay, proprietary revocation, RGS
> crypto on our own signature). We withdraw it. The target below is the model already
> homologated on `main`, re-instantiated for the multi-pod topology this track introduced.

---

## 1. Problem and root cause

The track split the agentic monolith into three independently-deployed pods
(`fred-agent`, `dt-agent`, `rags-agent`), one namespace each, and moved the browser→runtime
transport to **HTTPS/SSE**. Both are good and are kept. But the same track also moved the
**authorization decision out of the pod**: on `main` the agent backend calls OpenFGA on
every request (`check_user_team_permission_or_raise`, `chatbot_controller.py`); on this
branch the pod calls OpenFGA **never** (verified — the only `ReBAC/OpenFGA` mentions in
`libs/fred-runtime/.../agent_app.py` are docstrings with no code behind them). The decision
is taken **once** in the control-plane at `prepare-execution` and **sealed into a signed
grant** the pod trusts.

**Root cause:** the signed grant is not an independent design choice — it is the *consequence*
of relocating the OpenFGA decision into the control-plane. The grant exists only to carry
"already authorized" to a pod that can no longer decide for itself. Therefore the fix is to
**restore the OpenFGA decision at the pod**, after which the grant is redundant and is removed.

**Two facts that make this urgent for C3:**
- "Runtime runs on the grant alone, no callback" is true only in `enforce` mode
  (`_should_resolve_from_grant`) — which the **C3 profile forces**. The defect peaks exactly
  in the homologation target.
- The `observe`-mode fallback callback `GET /agent-instances/{id}/runtime` is `require_admin`,
  so non-admin members cannot resolve through it (finding F2). The grant **masked** a broken
  authorization callback instead of fixing it.

## 2. Threat model

- **Browser (untrusted):** holds a valid Keycloak token for *its own* user only; may forge
  any request body and replay captured tokens within their TTL.
- **Runtime pod (semi-trusted, internet-facing):** must **decide authorization itself**
  (Keycloak identity + OpenFGA), must never trust a control-plane assertion or a
  proxy-injected identity header, and must never be able to mint a capability.
- **Control-plane (policy/catalogue authority):** serves the **static catalogue** of the
  three agents and does OpenFGA checks **for display filtering only** — it is *not* the
  execution authority.

In scope: cross-tenant access, cross-runtime replay (confused deputy), weak JWT validation,
fail-open defaults, half-authenticated sessions, proxy header spoofing.
Out of scope: TLS termination details, ingress DoS, prompt injection, at-rest encryption of
derived stores (governance track).

## 3. Target design — classic, standard, defensible

**Principle:** *Keycloak proves identity. OpenFGA decides authorization. We never emit a
signed capability.*

1. **Identity = Keycloak, per pod.** Each pod is an **OAuth2 resource server**. The UI opens
   the chat directly against the right pod over HTTPS/SSE, presenting the **Keycloak JWT** in
   `Authorization: Bearer`. The pod validates the JWT (JWKS signature; strict
   `iss`/`aud`/`exp`/`nbf`; `alg` pinned to `RS256`). The client→agent return channel (POST
   for HITL/resume/interruptions) carries and **re-validates the same JWT**.
2. **Authorization = OpenFGA, pod-side, per request.** Each pod runs an OpenFGA check on
   every execute/stream/resume request using the shared `fred_core.security.rebac` engine —
   the `main` model. The check lives in the **common path** traversed by all three verbs, so
   no half-authenticated session is possible. The decision is **never cached**.
3. **No signed token.** The control-plane emits nothing signed. It serves the static
   catalogue to the UI and may run an OpenFGA check to filter what the UI shows — advisory,
   not authoritative.
4. **Resolution model (D5b — REVISED to "Option Kept", see §11).** Runtimes are declared
   statically (no runtime discovery). **Managed agent instances + per-team tuning are
   retained**: the pod resolves an instance's template+tuning from a team-scoped,
   ReBAC-gated control-plane endpoint (config only, never a capability), and the request
   body carries `agent_instance_id` + `runtime_context.team_id` as **non-authoritative**
   input; the pod's OpenFGA check decides *whether* the caller may run it. *(The earlier D5b
   — drop managed instances for a fully static model — was reversed to avoid deleting a
   shipped feature; the per-turn resolution call is config-only, not the authority.)*
5. **One audience per agent (D5c).** `fred-/dt-/rags-agent` are three distinct Keycloak
   confidential clients; each pod validates `aud == its_own_client_id` in strict mode
   (anti-confused-deputy). Replaces the grant's `audience` claim with Keycloak-native scoping.
6. **Fail closed in C3.** A `security.profile: c3` setting forces strict JWT
   issuer/audience, requires user + m2m auth enabled, forbids no-security / mock-admin, and
   makes the pod-side OpenFGA check fail-closed (no permissive `NoopRebacEngine`). Refuses to
   start otherwise.

**Kept from this branch (good, orthogonal to authz):** multi-pod packaging, HTTPS/SSE
transport, sessionless POST resume, the shared HTTP/SSE client libs, and the unrelated
import/export improvements.

## 4. How the original findings (F1–F7) are addressed by the target

| # | Finding | Resolution in the target |
|---|---------|--------------------------|
| F1 | Grant unsigned ⇒ forgeable | **Grant removed.** No body-carried authorization exists to forge; authz is the pod's OpenFGA check against the verified JWT identity. |
| F2 | Runtime authorizes via wrong check / admin-only callback | **Grant + callback removed.** The pod authorizes every request via OpenFGA on the caller's own team membership — members pass, no admin gate, no cross-tenant reach. |
| F3 | `audience` declared, never enforced ⇒ cross-runtime replay | **Per-agent Keycloak audience**, strict validation per pod (§3.5). |
| F4 | `grant.team_id` not tied to instance owner | N/A — no grant. The pod checks the caller's OpenFGA relation to the requested team directly. |
| F5 | Soft JWT issuer/audience defaults | **Kept** from the branch: C3 profile forces `STRICT_ISSUER`/`STRICT_AUDIENCE` (`oidc.apply_security_profile`). |
| F6 | Fail-open dev defaults (mock-admin, hardcoded keys) | **Kept**: C3 profile forbids no-security/mock-admin and fails closed at startup. |
| F7 | No replay resistance / durable audit | Keycloak token TTL + revocation cover replay; pod logs OpenFGA allow/deny for audit. Durable audit export remains a governance follow-up. |

## 5. Removal inventory (what disappears)

- **fred-sdk:** `contracts/grant_signing.py`; the signing/resolution fields on
  `ExecutionGrant` (`key_id`, `signature`, `jti`, `owner_team_id`, `template_agent_id`,
  `tuning`, `display_name`) and `canonical_payload()`/`is_signed()`. Decide per §6 whether a
  minimal unsigned `ExecutionContext` survives or the type is deleted.
- **fred-core:** `security/keyless_signer.py` (all); `GrantSigningConfig` in
  `security/structure.py`; the grant clauses in `oidc.apply_security_profile` (keep the
  `STRICT_*` + `user/m2m enabled` clauses).
- **control-plane:** `product/grant_signing.py`; `GET /.well-known/grant-jwks`;
  `build_grant_signer`/`sign_grant` calls in `product/service.py`; `execution_grant` from the
  `prepare-execution` response schemas.
- **runtime:** `_verify_grant_signature`, `_load_grant_verifier`, `_should_resolve_from_grant`,
  `_resolve_from_grant`, `_validate_grant_team_binding`, grant-signature wiring in the three
  execute endpoints; `grant_verifier`/`grant_signing_enforcement` from config/context.
- **config/secrets:** `scripts/gen-grant-signing-key.py` + `make gen-grant-key`; the
  `security.grant_signing` blocks in both `configuration_prod.yaml` + JSON schemas +
  `deploy/charts/fred/values.schema.json`; `grant-signing-key.pem`, `grant-jwks.json`, and
  the RS256 private-key K8s Secret + rotation (the headline homologation saving).
- **frontend:** regenerated `runtimeOpenApi.ts`/`controlPlaneOpenApi.ts`; `execution_grant`
  removed from `useChatSse.ts`.

## 6. Restoration / adaptation (mostly already present)

- **Reused as-is (shared fred-core):** Keycloak JWT validation
  (`oidc.decode_jwt`/`get_current_user`) — the pod already uses it; the OpenFGA ReBAC engine
  (`fred_core.security.rebac`, `TeamPermission`, `check_user_team_permission_or_raise`).
- **Adapted (1→3 pods):** wire the OpenFGA check into the pod's common execute/stream/resume
  path; give each pod an OpenFGA client + namespace→OpenFGA reachability; one Keycloak client
  per pod; keep the ingress-relative `execute_stream_url` routing returned by
  `prepare-execution`, minus the grant.
- **`prepare-execution` decision (open, see §9):** keep it as a non-authoritative resolver
  (pod URL + context-prompt + session registration) with the grant stripped, **or** replace
  it with a catalogue endpoint and have the UI call the pod directly.

## 7. Contract impact

- `RUNTIME-EXECUTION-CONTRACT.md`: §2.2 `ExecutionGrant` and §2.4 grant-validation are
  removed; managed execution is documented as JWT-authenticated + pod-side OpenFGA; dated §8
  entry.
- `CONTROL-PLANE-PRODUCT-CONTRACT.md`: `prepare-execution` no longer returns a grant; the
  control-plane is documented as catalogue + display-filtering authority, not issuer.
- `ARCHITECTURAL-SECURITY-REPORT.md`: the valet-key/Execution-Grant thesis is withdrawn and
  replaced by the resource-server + pod-side-OpenFGA model.

## 8. Migration order (validation before removal — non-negotiable)

This is a **candidate-branch rewrite**, not a live prod rollout, so the production-only
`observe→enforce` staging is collapsed; each step is still a green, revertible commit.

1. (this RFC) record the reversal. ✅
2. **C1** — wire the pod-side OpenFGA check into the common execute/stream/resume path,
   fail-closed under C3; pod gets a rebac engine + OpenFGA reachability. *(No grant removed
   yet — authz now exists in two places.)*
3. **C2** — one Keycloak client/audience per agent; pods in strict audience.
4. **C3** — remove the grant layer (§5) once C1/C2 are green. *(The only window without a
   second authz layer; do it only after C1 is proven.)*
5. **C4** — settle `prepare-execution` (§9) + static agent config (D5b).
6. **C5** — adapt the C3 profile (drop `grant_signing`, keep strict + fail-closed OpenFGA);
   rewrite `test_security_profile.py`.
7. **C6** — NetworkPolicies (ingress→pod, pod→OpenFGA, pod→Keycloak, deny inter-agent) +
   end-to-end TLS to the pod (chart); regenerate frontend clients; full `make code-quality`
   + `make test` green across all touched packages.

**Recommendation: gut the grant in this branch, do not restart from `main`.** The branch
already has the multi-pod packaging, HTTPS/SSE, sessionless resume, pod-side Keycloak JWT
validation, and the C3 profile shell. Restarting from `main` would mean re-porting ~292
commits of reorganization and re-importing `main`'s own flaw (WS auth checked once at
connect). What the branch lacks — the pod-side OpenFGA check — lives in a shared fred-core
module already consumed elsewhere.

## 9. Resolved decision — `prepare-execution`

**RESOLVED (2026-06-28): keep `prepare-execution`, grant stripped.** It returns the pod URLs
+ resolved context-prompt + effective chat options (no `execution_grant`, no `expires_at`, no
`grant_refresh_required`); session/context-prompt logic is preserved. The alternative
(remove it for a UI-read catalogue endpoint) was not pursued — it would move the
context-prompt/session resolution to the frontend for no security gain.

## 10. Test plan

- Unit (fred-core/fred-sdk): JWT strict validation (iss/aud/exp/nbf/alg); OpenFGA allow/deny
  mapping; C3 profile fail-closed; no grant symbols remain (import guard).
- Integration (fred-runtime): member with team relation executes; non-member denied 403; the
  same check fires on execute, stream **and** resume (no half-session); OpenFGA unreachable ⇒
  403 under C3; proxy-injected identity header ignored.
- Control-plane: `prepare-execution` returns no grant; catalogue/display filtering reflects
  OpenFGA.
- Negative/fail-closed: C3 refuses startup without strict JWT / user+m2m / fail-closed OpenFGA.

## 11. Decisions

- **D5 — Reverse the signed grant (2026-06-27):** ✅ The control-plane emits no signed
  capability. Pods are Keycloak resource servers; authorization is a pod-side OpenFGA check
  per request. *Supersedes D1 (asymmetric signer), D2 (trust-the-grant), D4 (inline tuning).*
- **D5b — Resolution model (REVISED 2026-06-28, "Option Kept"):** ✅ **Managed agent
  instances + per-team tuning are RETAINED.** *(This supersedes the earlier D5b, which
  proposed dropping managed instances for a fully static `main`-style model — that would have
  deleted a shipped product feature and cascaded into the control-plane product API, the
  frontend agent-management UI, history keyed by `agent_instance_id`, and eval.)* Instead, the
  pod resolves an instance's template+tuning from a **team-scoped, ReBAC-gated control-plane
  endpoint** (`GET /teams/{team_id}/agent-instances/{id}/runtime`, `CAN_READ` +
  `store.get_for_team`) — config only, never a capability. The pod forwards the user's
  Keycloak JWT (the runtime has no M2M outbound today; switching this call to the pod's own
  M2M identity is a trivial future change with identical security, since the pod already
  authorizes the user via OpenFGA). This **fixes F2** (members resolve; no cross-tenant reach)
  and keeps the per-turn resolution call, which is now config-only and not the authority.
- **D5c — Per-agent Keycloak audience (2026-06-27):** ✅ One clientID/`aud` per agent, strict
  audience validation per pod. Code enforces `aud == security.user.client_id` (strict under
  c3); per-agent client values + realm audience mappers are a deployment step.

**Implementation status (2026-06-28):** delivered on branch `1853` — C1 (pod OpenFGA),
team-scoped resolution endpoint, full grant removal across fred-sdk/fred-core/control-plane/
runtime/config/schemas/chart, frontend clients regenerated, C3 profile reworked, lib minor
versions bumped (fred-core 3.4.0, fred-sdk 3.3.0, fred-runtime 3.3.0). All offline suites
green. **Not in this branch (deployment infra):** NetworkPolicies + end-to-end TLS (T5),
Keycloak realm audience mappers, and the per-release pod `client_id` Helm values.

---

## Appendix A — Rejected approach: control-plane-signed `ExecutionGrant` (and why)

Retained as the homologation rationale ("why not a signed grant?"), **not as an
implementation plan. Do not implement anything in this appendix.**

The rejected design had the control-plane sign a short-lived (≤5 min) JWT-shaped
`ExecutionGrant` at `prepare-execution` (RS256, `kid`, `jti`, `aud`, carrying authorization
*and* resolution claims `template_agent_id`/`owner_team_id`/`tuning`), which the runtime
verified locally against the control-plane's JWKS and then executed on **without any
callback** — a "valet-key" capability pattern. Phases 0–3 were delivered on PR #1857
(`fred-core/security/keyless_signer.py`, sdk envelope, control-plane signer + `/.well-known/
grant-jwks`, runtime verifier, `security.profile: c3`).

**Why rejected for a C3 / ANSSI homologation:**
- It makes the control-plane a **proprietary cryptographic root of trust**, moving the entire
  burden of proof onto us: private-key protection (K8s Secret/HSM), key rotation, anti-replay
  (`jti` bookkeeping), **proprietary revocation** (a signed 5-min grant is not revocable), and
  **RGS crypto-conformance on our own signature**.
- On `main` all of that already sat with **Keycloak**, a standard hardened IdP — i.e. we were
  a *consumer* of a recognized authority, never an issuer. The grant regressed that posture.
- It solved a problem we did not have: the legitimate goals (multi-pod packaging, HTTPS/SSE)
  are orthogonal to who issues authorization. The grant added a trust root, attack surface,
  and homologation burden for nothing the project actually needed.
- It also masked, rather than fixed, the broken `require_admin` resolution callback (F2).

The condemned-but-instructive insight kept from this work: authorization must be **freshly
evaluated at execution time** — which the target does correctly by checking OpenFGA at the
pod on every request, instead of trusting a decision frozen into a token at issuance.
