# RFC — ExecutionGrant security hardening (C3 readiness)

**Status:** Confirmed (decisions D1–D3 resolved 2026-06-26) — implementing Phases 0–4
**Author:** Dimitri Tombroff
**Date:** 2026-06-26
**Task ID:** `RUNTIME-07`
**Area:** `fred-sdk`, `fred-runtime`, `control-plane-backend`, `fred-core`
**Touches:** `RUNTIME-EXECUTION-CONTRACT.md` (§2.2 `ExecutionGrant`, §2.4 grant validation, §8 changelog), `CONTROL-PLANE-PRODUCT-CONTRACT.md` (prepare-execution), `ARCHITECTURAL-SECURITY-REPORT.md`

---

## 1. Problem

The managed chat path lets the browser talk to a runtime pod directly over HTTPS SSE,
authorized by an `ExecutionGrant` the control-plane issues at `prepare-execution`. The
design intent (per `ARCHITECTURAL-SECURITY-REPORT.md`) was a capability/"valet-key"
pattern equivalent to the signed download URLs in `download_token.py`, with the explicit
claim that it "could be made as secure."

A line-by-line audit (2026-06-26) shows the pattern is **not yet realized**, and that
authorization at execution time does not hold up for a multi-team, C3-classified
deployment. Seven findings, severity-ranked:

| # | Finding | Evidence |
|---|---------|----------|
| **F1** | **The grant is unsigned ⇒ forgeable.** Validation is structural only; any authenticated client can fabricate a valid-looking grant in the POST body. | `libs/fred-sdk/fred_sdk/contracts/execution.py:267-325` (`validate_for_execution`), docstring lines 280-283 |
| **F2** | **The runtime never re-checks the user's team authorization.** `_resolve_agent_instance` forwards the **user** token to `GET /agent-instances/{id}/runtime`, which gates on `require_admin` (global admin), **not** team ReBAC, and resolves via `store.get` with **no team filter**. Too strict for normal users, too loose for tenant isolation. | `libs/fred-runtime/fred_runtime/app/agent_app.py:1019-1041`; `apps/control-plane-backend/.../product/api.py:639-665`; `.../product/service.py:1658` (`store.get`) vs `:1568` (`store.get_for_team`); `libs/fred-core/fred_core/security/authorization.py:70-73` |
| **F3** | **`audience` is declared but never enforced.** Contract promises the runtime can reject grants for a different target; `validate_for_execution` takes no `expected_audience` and never checks it → cross-runtime replay / confused deputy. | `execution.py:213-214` (promise) vs `:267-325` (no check) |
| **F4** | **`team_id` in the grant is never validated** and never compared to the resolved instance's `owner_team_id`. | `execution.py:595-598` (`validate_execution_grant` passes neither) |
| **F5** | **JWT issuer/audience validation is soft by default.** `FRED_STRICT_ISSUER` / `FRED_STRICT_AUDIENCE` default `False`; `jwt.decode(..., verify_aud=False)`; mismatches only log. | `libs/fred-core/fred_core/security/oidc.py:43-44, 288-305, 328-331` |
| **F6** | **Fail-open defaults.** No-security mode injects a mock `admin` user; the download signing key has a hardcoded dev fallback that only warns when unset. | `oidc.py:441-443`; `download_token.py:44-50` |
| **F7** | **No replay resistance or durable audit.** No `jti`/nonce, no one-time `resume`, no binding of grant to the bearer token; audit events live in an in-memory ring buffer lost on pod restart. | `execution.py:204-258` (no `jti`); `agent_app.py:137-154` (ring buffer) |

**Net effect:** per-user, per-tenant authorization is enforced **only at grant issuance**
(`prepare_execution`, which correctly runs OpenFGA `CAN_READ` team ReBAC and a team-scoped
`store.get_for_team`). At execution time the runtime relies on (a) a forgeable grant,
(b) a self-satisfiable `grant.user_id == token.uid` correlation, and (c) a mis-scoped
`require_admin` resolution callback. The security of the whole feature therefore reduces
to the Keycloak bearer token alone — which F5/F6 also weaken by default.

**Live-deployment caveat to verify:** if interactive Prism/C3 users hold the global
`admin` role, F1+F2 are an *active* cross-tenant execution path (forge a grant → run any
team's agent), not merely a latent gap. If they do **not**, the managed path is instead
**broken** for normal users (403 at resolution) and only works because the runtime test
mocks the control-plane response (`libs/fred-runtime/tests/test_agent_app.py:437-517`).
Either way the current resolution design is wrong.

## 2. Threat model

Trust boundaries, after this RFC:

- **Browser (untrusted):** may forge any request body, replay captured tokens within TTL,
  and is exposed to XSS / malicious extensions. Holds a valid Keycloak token for *its own*
  user only.
- **Runtime pod (semi-trusted, internet-facing via ingress):** must **verify**, must never
  be able to **mint** a capability it could then present elsewhere.
- **Control-plane (trusted policy authority):** sole issuer of grants; sole holder of the
  signing private key.

Attacks in scope: grant forgery (F1), cross-tenant access via forged/mis-scoped grant
(F2/F4), cross-runtime replay (F3), token/grant replay within TTL (F7), downgrade via weak
JWT validation (F5), fail-open via dev defaults (F6), signing-key compromise on a runtime
pod (drives the asymmetric choice in §4).

Out of scope: TLS termination, ingress DoS, agent-prompt-injection (separate track),
at-rest encryption of derived stores (governance track, noted in §9).

## 3. Design principles

1. **The signed grant is the capability.** Realize the download-URL pattern properly:
   make the grant unforgeable, then the runtime can trust its scope fields.
2. **Defense in depth — verify, don't only trust.** Even with a signed grant, the runtime
   re-checks the requesting user's team authorization, so a single key compromise is not a
   total tenant-isolation break.
3. **Runtimes verify, never mint.** Favor asymmetric signing so an internet-facing pod
   cannot forge grants for other tenants.
4. **Fail closed in classified profiles.** A C3 config profile refuses to start without
   the required keys/secrets and forbids no-security / mock-admin modes.
5. **Every change is independently testable and revertible**, gated behind a flag during
   rollout (enforce-after-observe).

## 4. Design

### 4.1 Signed grant (F1) — **asymmetric, via a shared keyless-signer library (D1 resolved)**

Control-plane signs the grant; runtimes verify with the matching **public** key. The public
key is never secret and never exchanged out-of-band — the runtime fetches it from a JWKS URL
over the in-cluster network, exactly as it already fetches Keycloak's public keys
(`PyJWKClient` in `libs/fred-core/fred_core/security/oidc.py:163`). No external provider, no
CA, no key exchange. Canonical-JSON payload over the existing grant fields plus new `jti`
and `key_id`; detached signature carried alongside the grant.

**New shared capability — one minimal library, used by both sides.** Signing/verification
lands in a new module beside `oidc.py` so it reuses the existing JWKS client + cache, and so
the platform ends with **one** signer rather than per-app copies:

```
libs/fred-core/fred_core/security/keyless_signer.py   (~80–120 LOC)
  GrantSigner (Protocol)        sign(payload: bytes) -> (signature, key_id)
    ├─ IamSignBlobSigner        # GCP keyless — PRIMARY (see below)
    └─ LocalKeypairSigner       # Ed25519/RS256 from a K8s Secret — on-prem fallback
  GrantVerifier                 # PyJWKClient over the signer's JWKS; reuses oidc.py infra
```

- `fred-sdk` (`contracts/execution.py`): add `key_id`, `jti`, `signature` to the envelope
  (optional until enforcement flips) + a pure `canonical_payload()` serializer. Validation
  orchestration calls into the fred-core `GrantVerifier`.
- `control-plane`: sign at `prepare_execution` via the configured `GrantSigner`.
- `runtime`: verify in `validate_execution_grant` via `GrantVerifier`, behind
  `FRED_GRANT_SIGNATURE_ENFORCE` (`observe` → log-only, `enforce` → 403).

**Primary signer — `IamSignBlobSigner` (GCP keyless), reusing the approved FILES-06 pattern.**
The control-plane asks **GCP IAM to sign** under Workload Identity — the private key never
exists in our hands or in a Secret. This is the same trust + ops pattern already shipped and
RSSI-approved for GCS V4 signed URLs (`FILES-06`, `GcsContentStore.get_presigned_url_internal`
in `apps/knowledge-flow-backend/.../gcs_content_store.py:354`), and reuses the same
`signing_service_account_email` config + fail-fast startup validation
(`common/structures.py:183`, `application_context.py:560`). **Important nuance:** FILES-06
signs only *GCS URLs* (via `google-cloud-storage`'s `generate_signed_url`); signing an
arbitrary grant payload uses a **different GCP API** — `google-cloud-iam-credentials`
`IAMCredentialsClient.sign_blob(name=…serviceAccounts/{sa}, payload=…)`. Verification is
likewise keyless: the runtime fetches that service account's Google-published JWKS
(`https://www.googleapis.com/service_accounts/v1/jwk/{sa_email}`) and Google rotates the keys.
So: **keyless on both ends, nothing to distribute, nothing to rotate by hand.**

**Risk (must measure): one `sign_blob` API round-trip per signature.** A grant is minted per
chat turn (5-min TTL), so `IamSignBlobSigner` adds one IAM call per turn — latency + IAM
quota. Mitigation/fallback: `LocalKeypairSigner` signs **in-process** (no API call, no quota)
from an Ed25519/RS256 key in a K8s Secret, behind the **same `GrantSigner` interface** — a
drop-in swap with no contract change. Plan: ship `IamSignBlobSigner` first, measure per-turn
latency under load; flip to `LocalKeypairSigner` only if the hop is material.

**Convergence:** once `keyless_signer.py` exists, the FILES-06 GCS URL signing can later be
refactored onto the same `IamSignBlobSigner` ADC/token bootstrap, removing the duplicate
credential plumbing in `gcs_content_store.py` (follow-up, not blocking).

**Rejected alternative — shared HMAC-SHA256** (as in `download_token.py`): one symmetric
secret on control-plane *and every runtime*, so a compromised internet-facing runtime pod
could **mint** grants for any team (violates principle 3). Rejected as default per D1;
retained here only as documentation of the trade-off.

### 4.2 Runtime authorization fix (F2, F4)

Replace the misuse of the admin operator endpoint with correct, team-scoped, per-user
authorization:

1. Introduce an **M2M-authenticated** internal resolution endpoint (or extend the existing
   one) that takes the **requesting user** + `agent_instance_id`, runs the **same team
   ReBAC** as `prepare_execution` (`CAN_READ` on `owner_team_id`), and resolves via
   `store.get_for_team`. The runtime authenticates to it with its own M2M token; the user
   identity travels as data, not as the caller's admin role. This removes both the
   `require_admin` over-restriction and the unscoped `store.get` under-restriction.
2. In `validate_execution_grant`, pass `expected_team_id` and, after resolution, assert
   `grant.team_id == resolved.owner_team_id`. Reject on mismatch.

This keeps authorization correct **even if** signing (4.1) is delayed, and provides the
defense-in-depth layer once it lands.

### 4.3 Audience binding (F3)

`validate_for_execution` gains `expected_audience`; the runtime passes its own configured
ingress prefix (the value control-plane already mints into `audience`). Reject grants whose
audience does not match this runtime. Also corrects the false claim in
`BACKLOG.md §3c.2.1` that audience is already checked.

### 4.4 JWT strictness + fail-closed C3 profile (F5, F6)

- A `security.profile: c3` setting (or env) that forces `FRED_STRICT_ISSUER=true`,
  `FRED_STRICT_AUDIENCE=true`, `verify_aud=true`, forbids no-security mode and mock-admin,
  and refuses startup if any required signing key / secret is absent (fail closed). Default
  (non-C3) behavior is unchanged for dev ergonomics.

### 4.5 Replay resistance + durable audit (F7)

- `jti` in the signed grant; one-time-use enforcement for `action="resume"` (seen-jti set,
  short-lived, per-session). Optional `cnf`-style binding of the grant to a hash of the
  bearer token so a stolen `(token, grant)` pair cannot be replayed independently.
- Export audit events to a durable sink (align with governance T1: Keycloak/Temporal
  audit), not only the in-memory ring buffer.

## 5. Phased rollout (each phase = one reviewable, testable, revertible commit)

Ordered for safety: tighten cheap structural checks first, add signing behind an observe
flag, fix authorization, then harden defaults. The system stays green at every step.

- **Phase 0 — Baseline & exploitability.** Confirm interactive-user role assignment in the
  target deployment (settles F2 severity). Add **characterization tests** that exercise the
  *real* control-plane resolution (un-mock it) and prove today's behavior: forged-grant
  acceptance, cross-team attempt, audience mismatch. These tests flip from "documents the
  hole" to "proves the fix" across later phases.
- **Phase 1 — Audience + team binding (F3, F4).** Additive structural tightening; no key
  infra. Runtime enforces `expected_audience` and `grant.team_id == owner_team_id`. Correct
  the BACKLOG audience claim. *Lowest risk, immediate value.*
- **Phase 2 — Runtime authorization fix (F2).** M2M internal resolution endpoint with
  per-user team ReBAC + `store.get_for_team`; retire the `require_admin` callback misuse.
  *Closes the active/broken cross-tenant path independent of signing.*
- **Phase 3 — Signed grant (F1), observe→enforce.** 3a `fred-core/security/keyless_signer.py`
  (`GrantSigner`/`GrantVerifier`) + sdk envelope fields (`key_id`, `jti`, `signature`);
  3b control-plane signs at issuance via `IamSignBlobSigner`; 3c runtime verifies in `observe`
  mode (log-only) against the signing SA's Google JWKS; 3d flip to `enforce`. *The capability
  becomes unforgeable.* If GCP `sign_blob` per-turn latency proves material, swap to
  `LocalKeypairSigner` behind the same interface — no contract change.
- **Phase 4 — JWT strictness + fail-closed C3 profile (F5, F6).** Small, config-level.
- **Phase 5 — Replay resistance + durable audit (F7).** Largest; **deferred follow-up** per
  D3 (not in this iteration).

**Weekend target (D3 resolved):** Phases **0–4**. Phase 5 is a tracked follow-up.

## 6. Contract impact

- `RUNTIME-EXECUTION-CONTRACT.md`: amend §2.2 (`ExecutionGrant` gains `key_id`, `jti`,
  `signature`), §2.4 (validation now covers signature, audience, team), and add a dated
  §8 entry per phase. The grant remains non-secret and topology-free (unchanged invariant).
- `CONTROL-PLANE-PRODUCT-CONTRACT.md`: document grant signing at issuance + the verification
  key source (Google SA JWKS for `IamSignBlobSigner`; control-plane-served JWKS for
  `LocalKeypairSigner`) + the M2M internal resolution endpoint.
- `ARCHITECTURAL-SECURITY-REPORT.md`: update the "valet key" section to reflect signed
  capability + defense-in-depth re-check.

## 7. Test plan

- Unit (`fred-sdk`): sign/verify round-trip; tampered payload rejected; expired/`nbf`;
  wrong `key_id`; audience mismatch; team mismatch; `jti` reuse rejected for `resume`.
- Integration (`fred-runtime`): un-mocked resolution; forged grant rejected under `enforce`;
  observe-mode logs but allows; cross-team forbidden; cross-runtime audience replay rejected.
- Control-plane: JWKS endpoint; signed-grant issuance; M2M resolution runs user ReBAC and
  team-scopes; non-member denied; admin no longer bypasses team scope.
- Negative/fail-closed: C3 profile refuses startup without keys; mock-admin disabled.

## 8. Alternatives considered

- **Shared HMAC instead of asymmetric** — simpler, rejected as default (§4.1, D1).
- **Control-plane proxies the SSE stream** (no direct browser→runtime) — removes the grant
  problem entirely but reintroduces the latency/coupling the architecture deliberately
  avoided; rejected.
- **Trust the signed grant only, drop the runtime ReBAC re-check** — simpler, but a single
  key compromise becomes total tenant-isolation loss; rejected in favor of defense in depth
  (§4.2, D2).

## 9. Out of scope / linked tracks

At-rest encryption of derived stores (OpenSearch/Postgres/Parquet) and automated C3
mis-classification detection are governance-track items (see `ignored/prism-governance-docs`)
and are not addressed here, but are part of overall C3 posture.

## 10. Decisions (resolved 2026-06-26)

- **D1 — Signing scheme:** ✅ **Asymmetric (Ed25519/RS256) + JWKS.** Runtimes verify only;
  they cannot mint grants. Shared HMAC rejected for the internet-facing runtime threat.
- **D2 — Runtime authz model:** ✅ **Signed grant + live ReBAC re-check** (defense in depth).
  A signing-key compromise alone does not break tenant isolation.
- **D3 — Scope:** ✅ **Phases 0–4** this iteration. Phase 5 (replay resistance + durable
  audit, F7) is a tracked follow-up.

## 11. Implementation footprint (difficulty & reuse map)

Difficulty: **medium**, and concentrated in design nuance, not code volume. The platform
already provides the three primitives this work composes — JWKS verification, M2M outbound,
and team ReBAC — so this *extends* shared modules rather than inventing subsystems.

| Phase | New prod code | Lands in / reuses |
|---|---|---|
| 0 | ~0 (tests) | characterization tests against un-mocked CP resolution |
| 1 | ~40–60 LOC | `execution.py` (params already on contract) + `agent_app.py` checks |
| 2 | ~150–250 LOC | **reuses** `outbound.py:ClientCredentialsProvider` (M2M) + existing team ReBAC `teams/service.py:get_team_by_id` / `store.get_for_team`; new thin CP endpoint |
| 3 | ~300–450 LOC | **new** `fred-core/security/keyless_signer.py`; **reuses** `oidc.py` `PyJWKClient`+cache and the FILES-06 Workload-Identity/`signing_service_account_email` pattern |
| 4 | ~80–150 LOC | `oidc.py` strict flags (already defined) + a `security.profile` in shared config models |

Net: ~600–1000 LOC production + comparable tests; ~3 existing shared files extended and
**one** new small shared module (`keyless_signer.py`). No new subsystem. The only genuinely
new shared capability is the keyless signer, deliberately placed in `fred-core/security` so
it is reusable platform-wide (and so FILES-06 can later converge onto it).

**Primary unknown:** Phase 3 GCP `sign_blob` per-turn latency/quota. De-risked by the
`observe→enforce` flag (ship observe over the weekend, flip enforce after key ops + latency
are validated) and by the `LocalKeypairSigner` drop-in fallback.
