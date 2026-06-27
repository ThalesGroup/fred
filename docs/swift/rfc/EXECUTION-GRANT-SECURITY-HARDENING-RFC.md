# RFC — ExecutionGrant security hardening (C3 readiness)

**Status:** Confirmed — revised 2026-06-27 (self-contained signed grant; old Phase 2 folded in)
**Author:** Dimitri Tombroff
**Date:** 2026-06-26 (rev. 2026-06-27)
**Task ID:** `RUNTIME-07`
**Area:** `fred-sdk`, `fred-runtime`, `control-plane-backend`, `fred-core`
**Touches:** `RUNTIME-EXECUTION-CONTRACT.md` (§2.2 `ExecutionGrant`, §2.4 grant validation, §8 changelog), `CONTROL-PLANE-PRODUCT-CONTRACT.md` (prepare-execution), `ARCHITECTURAL-SECURITY-REPORT.md`

---

## 1. Problem

The managed chat path lets the browser talk to a runtime pod directly over HTTPS SSE,
authorized by an `ExecutionGrant` the control-plane issues at `prepare-execution`. The
design intent (per `ARCHITECTURAL-SECURITY-REPORT.md`) was a capability/"valet-key"
pattern — the control-plane signs a short-lived grant once, and the runtime then verifies
and executes **autonomously**, freeing the control-plane from per-turn load.

A line-by-line audit (2026-06-26) shows the pattern is **not realized**: the grant is not
signed, the runtime does not trust it, and — critically — the runtime makes a **per-turn
callback** to the control-plane to resolve and (mis-)authorize every execution. Findings,
severity-ranked:

| # | Finding | Evidence |
|---|---------|----------|
| **F1** | **The grant is unsigned ⇒ forgeable.** Validation is structural only; any authenticated client can fabricate a valid-looking grant in the POST body. | `libs/fred-sdk/fred_sdk/contracts/execution.py` (`validate_for_execution`) |
| **F2** | **The runtime authorizes execution with the wrong check, via a per-turn callback.** `_resolve_agent_instance` calls `GET /agent-instances/{id}/runtime` (forwarding the user token) which gates on `require_admin` (global admin), not team ReBAC, and resolves via unscoped `store.get`. **Two symptoms:** regular team members are **refused (403)** — managed chat is broken for them; and the two global admins can resolve/execute **any** team's instance. | `agent_app.py:_resolve_agent_instance`; `product/api.py:get_agent_instance_runtime` (`require_admin`); `product/service.py` (`store.get` vs `store.get_for_team`) |
| **F3** | `audience` declared but never enforced → cross-runtime replay. **(FIXED — Phase 1.)** | `execution.py` |
| **F4** | `grant.team_id` never tied to the instance's `owner_team_id`. **(FIXED — Phase 1.)** | `execution.py` |
| **F5** | JWT issuer/audience validation soft by default. | `oidc.py:43-44, 288-305, 328-331` |
| **F6** | Fail-open defaults: no-security mock `admin` user; hardcoded download-key dev fallback. | `oidc.py:441-443`; `download_token.py:44-50` |
| **F7** | No replay resistance or durable audit (no `jti`; in-memory ring buffer). | `execution.py`; `agent_app.py:137-154` |

**Deployment fact (confirmed 2026-06-27):** exactly **two** platform (global `admin`)
accounts exist; **all** interactive users are non-admin team members. Therefore F2 is, in
production: **(a)** a functional outage for normal members (403 at the per-turn callback),
and **(b)** a cross-tenant reach for the two admin accounts. Phase 0 characterization tests
pin both halves.

**Architectural finding (the per-turn callback):** even setting authorization aside, the
runtime calls the control-plane **once per turn** to fetch the instance's template/tuning/
owner-team (`_resolve_agent_instance`, no cache). The SSE *stream* is direct, but the
control-plane is **not** freed from per-turn metadata load. This defeats the original
valet-key intent and is the architectural target of this RFC.

## 2. Threat model

Trust boundaries:

- **Browser (untrusted):** may forge any request body, replay captured tokens within TTL,
  exposed to XSS / extensions. Holds a valid Keycloak token for *its own* user only.
- **Runtime pod (semi-trusted, internet-facing):** must **verify**, must never be able to
  **mint** a capability. Must be able to execute **without** calling the control-plane.
- **Control-plane (trusted policy authority):** sole issuer/signer of grants. Holds (or
  delegates to GCP) the signing private key. Runs ReBAC once, at issuance.

In scope: grant forgery (F1), cross-tenant access (F2/F4), cross-runtime replay (F3),
token/grant replay within TTL (F7), weak JWT validation (F5), fail-open defaults (F6),
signing-key compromise on a runtime pod (drives the asymmetric choice, §4).

Out of scope: TLS termination, ingress DoS, prompt-injection, at-rest encryption of derived
stores (governance track, §9).

## 3. Design principles

1. **The signed grant is the whole capability.** It carries *both* authorization **and**
   resolution data, so the runtime needs **nothing** from the control-plane at execution
   time — it verifies a signature and runs. This is the valet-key pattern, realized.
2. **Sign once, verify autonomously, many times.** The control-plane signs each grant once
   at issuance (after ReBAC). The runtime verifies it locally with the control-plane's
   **public** key — the same asymmetric, no-callback model the platform already uses for
   Keycloak JWTs.
3. **Runtimes verify, never mint.** Asymmetric signing: an internet-facing pod holds only
   the public key and cannot forge grants for any tenant.
4. **Fail closed in classified profiles.** A C3 profile refuses to start without the
   required keys and forbids no-security / mock-admin modes.
5. **Every change is independently testable and revertible**, gated behind an
   `observe → enforce` flag during rollout.

**On defense-in-depth (D2 revised — see §10).** The earlier plan kept a *per-turn* ReBAC
re-check at the runtime. We are **replacing** that with trust in the signed grant plus a
short TTL, because (a) it is the only way to eliminate the per-turn callback and free the
control-plane — the original intent; (b) the keyless asymmetric signer (D1) keeps the
private key in GCP, making key compromise the dominant residual risk rather than grant
forgery; and (c) revocation latency is bounded by the ≤5-minute TTL. Authorization remains
freshly evaluated **at issuance** every turn-start; what we drop is the *redundant* runtime
re-evaluation, not the check itself.

## 4. Design

### 4.1 The self-contained signed grant

The grant becomes a signed token (JWT-shaped) that the control-plane signs at
`prepare-execution`, carrying everything the runtime needs:

```
header:  { alg: "EdDSA"|"RS256", kid: "<key id>" }
payload: {
  # authorization (control-plane ran ReBAC before signing)
  user_id, team_id, agent_instance_id, action,
  audience,                      # the intended runtime (F3, now signed)
  issued_at, expires_at, jti,    # short TTL + replay id
  # resolution (NEW — removes the per-turn callback)
  template_agent_id,             # which registered template to run
  owner_team_id,                 # authoritative owning team (F4, now signed)
  tuning: { ... }                # inline tuning snapshot (D4)
}
signature                        # over header+payload, by the CP private key
```

The runtime: fetch the control-plane public key once (cached), **verify the signature
locally**, check `exp`/`audience`/`jti`, then read `template_agent_id` + `tuning` +
`owner_team_id` **straight from the verified grant** and run. **No control-plane call.**

`tuning` is carried **inline** (D4): the grant is in the request body (not a header), so
size is not a constraint, and inline keeps the runtime fully autonomous (no tuning cache,
no fetch). Within the ≤5-minute TTL the tuning snapshot is authoritative.

### 4.2 How F2 is fixed — by elimination, not surgery

Because the verified grant carries `template_agent_id`, `owner_team_id` and `tuning`, the
runtime **stops calling** `GET /agent-instances/{id}/runtime` for execution entirely. As a
consequence, with **no** change to that endpoint:

- **Member bug gone:** members no longer hit `require_admin` — they run on their grant
  (which `prepare-execution` already issued after a successful team ReBAC check).
- **Admin cross-tenant hole gone:** authorization is baked into the signed grant at
  issuance (team-scoped `store.get_for_team` + `CAN_READ` ReBAC), not the global-admin gate.
- **Per-turn load gone:** the callback disappears.

The existing `require_admin` resolution endpoint remains **as-is**, now used only by
operators/CLI for binding **inspection** — a legitimate admin function, decoupled from
execution authorization. No new M2M endpoint is introduced. *(This supersedes the previous
Phase 2 design, which added an M2M ReBAC resolution endpoint; the self-contained grant makes
it unnecessary.)*

### 4.3 Signing mechanism — asymmetric keyless (D1), shared signer library

Control-plane signs with a **private** key; the runtime verifies with the matching
**public** key fetched from a JWKS URL (in-cluster, the same `PyJWKClient` used for
Keycloak — `oidc.py:163`). No CA, no key exchange; only the public key ever travels.

One new shared module, used by both sides:

```
libs/fred-core/fred_core/security/keyless_signer.py   (~120–180 LOC)
  GrantSigner (Protocol)        sign(payload: bytes) -> (signature, key_id)
    ├─ IamSignBlobSigner        # GCP keyless — PRIMARY
    └─ LocalKeypairSigner       # Ed25519/RS256 from a K8s Secret — on-prem fallback
  GrantVerifier                 # PyJWKClient over the signer's JWKS; reuses oidc.py infra
```

**Primary — `IamSignBlobSigner` (GCP keyless, reuses the RSSI-approved FILES-06 pattern).**
Control-plane asks **GCP IAM to sign** under Workload Identity — the private key never
exists in our hands or a Secret. Signing an arbitrary grant payload uses
`google-cloud-iam-credentials` `IAMCredentialsClient.sign_blob` (a *different* API than the
GCS-URL signing in `gcs_content_store.py:354`, which only signs GCS URLs). The runtime
verifies against that service account's Google-published JWKS
(`https://www.googleapis.com/service_accounts/v1/jwk/{sa_email}`); Google rotates the keys.
Keyless on both ends, nothing to distribute.

**Latency note:** `IamSignBlobSigner` adds one IAM `sign_blob` round-trip per grant minted
(at `prepare-execution`). This is on the issuance path (already a control-plane call), **not**
on the per-turn runtime path (which now has zero calls). `LocalKeypairSigner` signs
in-process behind the same interface if the IAM hop proves material.

**Rejected — shared HMAC:** one secret on every runtime → a compromised pod could **mint**
grants (violates principle 3). Documentation only.

### 4.4 Audience + team binding (F3, F4) — delivered (Phase 1), now signed

Phase 1 already added `expected_audience` enforcement and the `grant.team_id ==
owner_team_id` runtime binding. Once the grant is signed (§4.1), `audience`, `team_id` and
`owner_team_id` are all **inside the signature** — so these checks become tamper-proof, and
the team binding reduces to an internal-consistency check on signed claims.

### 4.5 JWT strictness + fail-closed C3 profile (F5, F6)

A `security.profile: c3` setting forcing `FRED_STRICT_ISSUER=true`,
`FRED_STRICT_AUDIENCE=true`, `verify_aud=true`; forbidding no-security / mock-admin; and
refusing startup when a required signing key / public-key source is absent (fail closed).
Default (non-C3) behavior unchanged for dev ergonomics.

### 4.6 Revocation trade-off (accepted)

With the per-turn callback gone, the runtime cannot learn mid-grant that a user was removed
from a team. A grant stays valid until `exp` (≤5 min). Accepted: bounded by the short TTL.
Optional future hardening (not in scope): a revoked-`jti` denylist the runtime polls
out-of-band (reintroduces a lookup, but not per-turn), and/or shortening the TTL.

### 4.7 Replay resistance + durable audit (F7) — deferred follow-up

`jti` (added by §4.1) enables later one-time-use enforcement for `action="resume"` and
optional bearer-token binding; durable audit export aligns with governance T1. Tracked as a
follow-up phase, not in this iteration.

## 5. Phased rollout (each phase = one reviewable, testable, revertible commit)

- **Phase 0 — Baseline & exploitability.** ✅ Done (2026-06-27). Characterization tests pin
  F1/F3/F4 (fred-sdk) and F2 (control-plane: member 403, non-member admin 200).
- **Phase 1 — Audience + team binding (F3, F4).** ✅ Done (2026-06-27). `expected_audience`
  enforcement + `_validate_grant_team_binding`; opt-in `platform.audience` config.
- **Phase 2 — Self-contained signed grant (F1 + F2 + load).** The centerpiece. Sub-steps:
  - **2a** — `fred-core/security/keyless_signer.py` (`GrantSigner`/`GrantVerifier`); sdk
    envelope gains `key_id`, `jti`, `signature`, and the resolution claims
    `template_agent_id`, `owner_team_id`, `tuning`; `canonical_payload()` serializer.
  - **2b** — control-plane signs at `prepare-execution` via `IamSignBlobSigner` and embeds
    the resolution claims (it already has the instance from `store.get_for_team`).
  - **2c** — runtime **verifies** the signature (`observe` mode: verify *and* still call the
    old callback, log any mismatch — proves equivalence on real traffic, zero risk).
  - **2d** — runtime reads resolution from the verified grant and **drops the callback**
    (`enforce`): member bug + admin hole + per-turn load all resolved together.
  - Flag: `FRED_GRANT_SIGNATURE_ENFORCE` (`observe` → `enforce`).
- **Phase 3 — JWT strictness + fail-closed C3 profile (F5, F6).** Small, config-level.
- **Phase 4 — Replay resistance + durable audit (F7).** Deferred follow-up.

*(This revision folds the former standalone Phase 2 — an M2M ReBAC resolution endpoint —
into Phase 2 as "fix by elimination": the self-contained grant removes the callback rather
than re-authorizing it.)*

## 6. Contract impact

- `RUNTIME-EXECUTION-CONTRACT.md`: §2.2 `ExecutionGrant` gains `key_id`, `jti`, `signature`,
  **and** the resolution claims `template_agent_id`, `owner_team_id`, `tuning`; §2.4 gains
  signature verification and documents that managed execution no longer calls the
  resolution endpoint; dated §8 entry per phase. The grant remains non-secret and
  topology-free (it carries logical ids/tuning, never connection strings — invariant kept).
- `CONTROL-PLANE-PRODUCT-CONTRACT.md`: grant signing + resolution-embedding at
  `prepare-execution`; the public-key (JWKS) source; the `require_admin` resolution endpoint
  documented as operator/CLI-only.
- `ARCHITECTURAL-SECURITY-REPORT.md`: valet-key section updated to the self-contained signed
  grant with no per-turn callback.

## 7. Test plan

- Unit (`fred-sdk` / `fred-core`): sign/verify round-trip; tampered payload rejected;
  expired/`nbf`; wrong `kid`; audience/team mismatch; resolution claims survive round-trip.
- Integration (`fred-runtime`): observe mode logs grant-vs-callback equivalence; enforce
  mode runs purely from the grant with **no** control-plane HTTP call (assert the resolver
  is not invoked); forged/expired grant rejected; member executes successfully; non-member
  (incl. global admin) cannot obtain a valid grant.
- Control-plane: `prepare-execution` signs + embeds resolution; non-member denied at
  issuance; member issued a complete signed grant.
- Negative/fail-closed: C3 profile refuses startup without a key source; mock-admin disabled.

## 8. Alternatives considered

- **Per-turn runtime ReBAC re-check (former D2).** Keeps a control-plane call every turn →
  defeats the offload goal. Replaced by trust-the-signed-grant + short TTL (§3, §10).
- **M2M resolution endpoint (former Phase 2).** Fixes authz but keeps the per-turn callback.
  Superseded by the self-contained grant.
- **Shared HMAC signing.** Lets a compromised runtime mint grants. Rejected (§4.3).
- **Control-plane proxies the SSE stream.** Removes the grant problem but reintroduces the
  latency/coupling the architecture avoids. Rejected.
- **Tuning by hash + runtime cache** (instead of inline). Smaller grants, but reintroduces a
  fetch on cache miss. Rejected for the autonomy goal (D4); revisit only if grant size bites.

## 9. Out of scope / linked tracks

At-rest encryption of derived stores and automated C3 mis-classification detection are
governance-track items (`ignored/prism-governance-docs`); part of overall C3 posture.

## 10. Decisions

- **D1 — Signing scheme (2026-06-26):** ✅ **Asymmetric (Ed25519/RS256) + JWKS, GCP-keyless
  primary.** Runtimes verify only; cannot mint. HMAC rejected.
- **D2 — Runtime authz model (REVISED 2026-06-27):** ✅ **Trust the signed, self-contained
  grant; eliminate the per-turn control-plane callback.** *Supersedes* the earlier
  "signed grant + live ReBAC re-check": that re-check would keep a per-turn call and defeat
  the control-plane offload that is the feature's original intent. Authorization is enforced
  at issuance (ReBAC, every turn-start); revocation latency is bounded by the ≤5-min TTL
  (§4.6). Residual risk concentrates on the signing key, which D1 keeps in GCP.
- **D3 — Scope (2026-06-27):** Phases **0–3** this iteration (0–1 done). Phase 4 (replay +
  durable audit, F7) deferred.
- **D4 — Resolution data in the grant (2026-06-27):** ✅ **Inline `tuning`** (+ ids), for a
  fully autonomous runtime. Hash-and-cache rejected unless grant size becomes a problem.

## 11. Implementation footprint

Difficulty: **medium**, concentrated in the signing/serialization design and the
observe→enforce rollout, not code volume. Reuses JWKS verification (`oidc.py`), the
FILES-06 Workload-Identity pattern, and the existing issuance-time team ReBAC.

| Phase | New prod code | Lands in / reuses |
|---|---|---|
| 0 | ~0 (tests) | ✅ done |
| 1 | ~60 LOC | ✅ done — `execution.py` + `agent_app.py` |
| 2 | ~350–500 LOC | **new** `fred-core/security/keyless_signer.py`; sdk envelope + resolution claims (`execution.py`); control-plane signs + embeds at `prepare_execution`; runtime verify + callback removal (`agent_app.py`); reuses `oidc.py` PyJWKClient + FILES-06 ADC/Workload-Identity |
| 3 | ~80–150 LOC | `oidc.py` strict flags + `security.profile` in shared config |

Net: one new shared module + contract envelope growth. The callback **removal** in Phase 2
is a net *simplification* of the runtime path.

**Primary unknown:** Phase 2 grant size with inline tuning, and GCP `sign_blob` issuance
latency. De-risked by the `observe→enforce` flag and the `LocalKeypairSigner` fallback.
