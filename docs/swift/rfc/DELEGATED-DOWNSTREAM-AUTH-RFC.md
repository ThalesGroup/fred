# RFC AUTH-TX — Delegated downstream auth: token exchange at admission

**Status:** Draft (awaiting developer confirmation; issue to be opened) — 2026-08-07
**Author:** Adrian Giurca / Claude
**ID:** AUTH-TX
**Area:** `fred-runtime` (`agent_app.py` admission, `runtime_support/`), `fred-core` (`security/oidc.py` — read-only dependency), `fred-deployment-factory` (Keycloak realm templates, gcp-c1 provisioning) — **multi-repo**
**Related:**
- `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §8.48 (async singleflight refresh — the prerequisite this RFC builds on), §8.49 (tool-failure degradation), §8.50 (frontend turn-start token preflight), §0.2 invariants #2/#3/#8
- `docs/swift/reviews/performance/2026-07-26-agent-turn-core/TURN-07-sync-token-refresh-in-async-path.md` — incident evidence and commit archaeology
- Incidents: [#1948](https://github.com/ThalesGroup/fred/issues/1948) (KEA prod, closed not-planned), [#1951](https://github.com/ThalesGroup/fred/issues/1951), [#2073](https://github.com/ThalesGroup/fred/issues/2073) Item 3 (reproduced live 2026-07-23) — all closed without a fix; no open issue tracks the defect
- Issue #2125 (TURN-07) — made the refresh path async/coalesced/bounded; explicitly did **not** restore delegated refresh (this RFC is that follow-up)

**Contract impact:** touches `_authorize_and_resolve` (frozen surface behind `agent_app.py`) → dated §8 entry required. New config block on `AgentPodConfig.security.user`. Realm-template changes in the deployment factory. No new wire event kind; no SDK surface change.

---

## 1. Problem

A runtime pod receives the user's Keycloak access token as the `Authorization`
bearer at turn admission and **reuses that same bearer for every downstream
Knowledge Flow / MCP / media / workspace call for the whole turn**
(`agent_app.py` F-B comment: "the pod uses the header bearer for downstream
calls"). The pod has no way to renew it mid-turn:

- `runtime_context.refresh_token` is always `None`. The frontend producer was
  deleted 2026-05-21 (`9680cd5b`), and `_authorize_and_resolve` (control F-B,
  `f27fe2f8`, #1862) nulls any body-supplied value — deliberately, five weeks
  after the producer was already gone.
- `_refresh_runtime_context_access_token` therefore raises at its
  `if not refresh_token` guard before any HTTP. Expired-token recovery fails
  outright instead of degrading.

Exposure window: `accessTokenLifespan` is **300 s** in the docker/k3d realm
templates; the frontend refreshes only below a threshold at turn start
(**120 s** since #2125's §8.50 hardening; 30 s before it), and there is **no
whole-turn timeout** — one `summarize_read` call alone is allowed 300 s. A turn
can therefore outlive its bearer. Reproduced live (#2073 Item 3, session
`5fef7a4a-…`, 2026-07-23): repeated 401s over ~40 s, surfaced to the user.

#2125 bounded the blast radius (async refresh machinery; the most-used RAG tool
now degrades instead of killing the turn). The root cause — *the pod holds one
fixed-lifetime credential for an unbounded-duration turn* — is untouched, and
is what this RFC addresses.

## 2. Proposed solution

**OAuth 2.0 Token Exchange (RFC 8693; Keycloak ≥ 26.2 "standard token
exchange") at admission.** The reframe that makes this compatible with F-B:
F-B forbids *trusting caller-supplied* credentials; it does not forbid the pod
*deriving its own*. The pod already stamps `access_token` from the validated
header — server-derived. This RFC extends that same move.

At `_authorize_and_resolve`, where the user token is provably valid
(`verify_exp`, `leeway=0`):

1. The pod exchanges the header bearer through its **existing confidential M2M
   client** — `security.m2m.client_id: "agentic"` in every shipped config, so
   no new secret plumbing — for an access token that still carries the user's
   `sub` and whose `aud` **satisfies what the downstream service actually
   validates**. Note this is `app`, not `knowledge-flow`: KF checks its
   configured *user* client_id (§5), so the exchanged token must keep `app` in
   `aud` (adding a second audience is fine; replacing it is not). Q6 in §6
   settles whether to keep `app` or additionally introduce a dedicated
   downstream audience with a matching `security.user.client_id` change on KF.
2. That exchanged token is stamped into `runtime_context.access_token` (and
   `access_token_expires_at`). `refresh_token` stays `None`.
3. The `agentic` client gets a **longer client-level access-token lifespan**
   (proposed: 1800 s), so a turn's downstream credential comfortably outlives
   any realistic turn without touching the realm-wide user TTL. **No mid-turn
   refresh is needed at all** — this deletes the problem rather than treating
   it.

Mechanics (all shapes proven by #2125's shipped machinery):

- **Async, bounded, singleflighted** exchange service in `runtime_support/`,
  mirroring `user_token_refresher.py`: per-event-loop shared client, explicit
  total budget via `asyncio.wait_for`, coalescing keyed on a SHA-256 digest of
  the subject token (never the raw token as a key), dedicated
  `auth.token_exchange_latency_ms` KPI with `status=ok|error|timeout` (the
  `phase`-dim pitfall and the raise-outside-the-timer pattern from §8.48 apply
  verbatim).
- **Cache** exchanged tokens per subject-token digest, TTL =
  `min(exchanged_exp, subject_exp)` minus a floor (don't serve a cached token
  with < 60 s left; re-exchange). Pod-local; documented as such (§0.2
  invariant #7). Repeat turns within a browser token's life cost zero extra
  round trips; a cache miss costs one Keycloak RTT pre-LLM (budgeted, KPI'd).
- **Fail-closed** (§0.2 invariant #8): when `token_exchange.enabled`, an
  exchange failure fails admission with a clear 503 — no silent fallback to
  forwarding the raw bearer, because silent fallback makes a misconfigured
  deployment look healthy while silently losing the property it was configured
  for.
- **Disabled by default** (`security.user.token_exchange.enabled: false`), so
  the fred half and the factory half can land in either order and the feature
  turns on only when an operator opts in — per the multi-repo circularity rule.

## 3. Why the user's session security *improves*

- The user's SSO refresh token never leaves the browser (unchanged).
- Knowledge Flow keeps authorizing **the user's own subject** — the
  impersonation surface of pure M2M is avoided; defense in depth preserved.
- The longer lifespan attaches to the exchanged client token, not to the
  realm-wide user TTL, so ordinary browser sessions are unaffected.
- Audience narrowing is a **goal, not a given**: it only materialises if Q6
  resolves toward a dedicated downstream audience. If the exchanged token must
  keep `aud: app` for KF to accept it (§5), the pod's credential is no
  narrower than today's — the win is then confined to lifetime control.

**Costs this buys, which must not be waved away:**

- **Revocation lag.** A logout or admin session revocation invalidates the
  browser's session, but an already-exchanged token stays valid until its own
  `exp`. Raising the lifespan to 1800 s raises the post-revocation window to
  the same figure — strictly worse than today's 300 s. Anything relying on
  prompt revocation (offboarding, credential compromise) needs either a short
  exchanged lifespan, a revocation check, or explicit acceptance of the window.
  **This is the main security trade of the proposal.**
- **A longer-lived token is a more valuable theft target**, and it sits in pod
  memory for its whole life.
- **The exchange cache is pod-local state holding live credentials** keyed by a
  digest of the subject token. It must never be keyed by anything a caller
  controls, must be bounded, and must not outlive the subject token — see the
  cache rules in §2.
- **Keycloak becomes a hard pre-LLM dependency of every cold turn.** With
  fail-closed behaviour a Keycloak outage takes chat down rather than degrading
  it; that is the correct trade for an auth control, but it is a new
  availability coupling and belongs in the runbook.

## 4. Alternatives considered (and rejected)

| Alternative | Why rejected |
| --- | --- |
| Re-add the browser refresh-token producer (what `9680cd5b` deleted) | Confused deputy: hands the pod the user's long-lived, PKCE-bound SSO refresh token; it lands in pod memory and risks checkpoints/logs. F-B exists precisely to forbid this. |
| Pod calls KF under pure M2M identity, asserting the user in a claim/header | KF must then *trust the pod's assertion* — a compromised pod can impersonate any user. Surrenders a defense layer for no gain over exchange. |
| Mid-stream token re-supply from the browser | SSE is one-way; needs a side channel plus replica affinity to reach the pod holding the turn. Over-engineered; still leaves the pod holding user tokens. |
| Raise the realm `accessTokenLifespan` | Global blast radius (every client, every consumer); capped anyway by `FRED_JWT_MAX_LIFETIME_SECONDS = 3600`, enforced as 401. Treats the symptom. |
| Keep refresh, wire a new producer | Even fixed, refresh replays the *user's* credential; exchange derives a narrower one. Strictly worse posture for equal effort. |

## 5. Preconditions verified against the actual deployment

Checked in `fred` and `fred-deployment-factory` on 2026-08-07:

| Fact | Status |
| --- | --- |
| Keycloak version 26.3.0 everywhere (docker, k3d, gcp-c1) | ✅ verified — standard token exchange is GA in ≥ 26.2 |
| `agentic` is confidential (`publicClient=false`, `serviceAccountsEnabled=true`, secret present) | ✅ verified in realm template |
| Pod already holds `agentic` credentials (`security.m2m`) | ✅ verified in `configuration.yaml` / `configuration_prod.yaml` |
| `fred_core` audience validation | ✅ verified: **soft by default** (a mismatch is only logged, at `logger.debug`, `oidc.py:357`), **strict under c3** (`aud` must include the validating service's configured **user** `client_id`, `oidc.py:383-384`) |
| Which audience KF actually requires | ⚠️ **`app`, not `knowledge-flow`** — KF's `security.user.client_id` is `"app"` (`configuration_prod.yaml:241`; factory `userClientId: app`). `knowledge-flow` is KF's **m2m** identity and is *not* what user-token validation checks. See §6 Q6 — this constrains the exchange target |
| `app` client audience mappers | ❌ **absent** — the realm template has no audience mapper on `app` (only a role mapper). Standard token exchange requires the requester client (`agentic`) in the subject token's `aud` → an audience protocol mapper on `app` must be added |
| `agentic` exchange enablement | ❌ absent — needs the standard-token-exchange capability enabled on the client, plus the client-level access-token lifespan |
| fredlab/gcp-c1 realm | ⚠️ imports **no realm** (`args: [start]`, no `--import-realm`); provisioning is kcadm in the provision job → the two client changes must be added there as kcadm steps, and current fredlab TTL is unknown |

## 6. Open questions (to resolve before implementation)

1. **Exact Keycloak 26.3 knob names** — the client capability toggle
   ("Standard token exchange") and client-level lifespan attribute names must
   be confirmed against the 26.3 admin REST schema before the realm templates
   are edited; the factory has no CI to catch a misspelled attribute (it would
   be silently ignored and the exchange would 400 at runtime).
2. **External (non-Knowledge-Flow) MCP servers** — an audience-restricted
   token may be rejected by third-party MCP servers that today accept the raw
   user bearer. All realm-listed MCP servers are KF routes
   (`/knowledge-flow/v1/mcp-*`), but agent configs can add external ones.
   Options: exchange per-audience on demand, or keep the original bearer for
   non-KF MCP only. Decide at implementation; default-off makes this safe to
   defer.
3. **Strict-audience (c3) user tokens today** — under c3, KF requires
   `aud ⊇ app` (its configured *user* `client_id`, per the §5 audit — **not**
   `knowledge-flow`, which is KF's m2m identity and is not what user-token
   validation checks). The realm template puts no audience mapper on `app` at
   all, so a c3-strict KF would reject today's user tokens outright; either c3
   is not active in template-provisioned environments or fredlab's realm was
   hand-configured. Verify against fredlab before assuming. Q6 settles which
   audience the *exchanged* token carries; this question is only about what
   already works today.
4. **Exchanged-token lifespan value** — 1800 s proposed; confirm against
   realistic P95 turn duration (no measured value with a real LLM and security
   enabled exists in the repo; measure via `fred-performance-campaign-runner`
   or Grafana before freezing the number).
5. **Whether a whole-turn wall-clock budget should land with this** — today a
   turn is unbounded; an explicit turn budget would make "lifespan > turn" a
   guarantee instead of a likelihood. Possibly its own issue.
6. **Which audience the exchanged token should carry (blocking).** KF validates
   its configured *user* client_id, which is `app` (§5) — so either the
   exchanged token keeps `app` in `aud` (simplest; no audience narrowing, the
   §3 benefit is lifetime only), or a dedicated downstream audience is
   introduced *and* KF's `security.user.client_id` moves to it in lockstep
   across every deployment surface (narrower, but a breaking multi-repo
   coordination with a rollback story). Settle this before any code: it decides
   whether §3's narrowing claim survives at all.
7. **Exchanged-token revocation window** — pick a lifespan that bounds the
   post-logout validity gap in §3 to something the security owner accepts, or
   add an explicit revocation check. The 1800 s figure in §2 is a placeholder
   pending that decision, not a recommendation.
8. **Refresh-token rotation is not transactional, and this RFC makes that
   matter.** Keycloak invalidates the presented refresh token when it issues
   the replacement, so any exchange that times out or loses its response can
   leave the rotation applied server-side while the pod holds only the now-dead
   original. §8.48 no longer *adds* to this race — the total deadline moved
   inside the exchange task, so there is no longer a shielded refresh whose
   late payload gets discarded — but the underlying lost-response window is
   inherent to the protocol and cannot be closed client-side. Today it is
   unreachable (no refresh token ever reaches the refresher), which is why
   nothing handles it. If this RFC restores a pod-held refresh credential, a
   single unlucky timeout would strand that identity until its credential is
   re-derived — so the implementation must either tolerate re-deriving on
   `invalid_grant` or avoid holding a rotating credential at all (a token
   exchange per turn, which §3 already prefers). Flagged here so it is not
   rediscovered in production.

## 7. Impact

- `fred`: exchange service + admission wiring + config block
  (`security.user.token_exchange`, default off) + tests (MockTransport:
  success / cache-hit / singleflight / fail-closed / timeout / no secret in
  logs or dims); dated §8 entry; `ENV_VARIABLES.md` unchanged (reuses m2m
  credentials).
- `fred-deployment-factory`: audience mapper on `app`, exchange enablement +
  lifespan on `agentic` (docker + k3d templates); kcadm equivalents in the
  gcp-c1 provision job; configmap block for environments that enable it.
  Factory has no CI — the cross-repo contract review (R6) is the only gate.
- Frontend: none (the §8.50 preflight remains as defense in depth).
- Rollout: land fred half disabled-by-default first or factory half first —
  either order is safe by construction.

## 8. Out of scope

- The `ToolObservabilityMiddleware` `"outcome": "succeeded"` mislabel on
  failed-but-caught MCP tool calls (#2073, adjacent to #2011) — separate
  mechanical fix, no RFC needed.
- The two drifted copies of "refresh and store the token"
  (`agent_app.py` vs `adapters.py`) — become dead code if this RFC lands;
  delete then.
- Session-idle/SSO timeouts, offline tokens, Temporal-side auth.
