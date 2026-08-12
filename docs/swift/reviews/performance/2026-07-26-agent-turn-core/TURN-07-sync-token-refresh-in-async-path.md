# TURN-07 — expired-token recovery blocks the event loop with synchronous Keycloak HTTP

- **GitHub issue:** [#2125](https://github.com/ThalesGroup/fred/issues/2125)
- **Priority:** P1
- **Verdict:** confirmed — fixed 2026-08-07 (offline; the pod-level
  forced-expiry criterion is still owed — see *Not covered offline* below)
- **Owner:** unassigned

## Production impact

Knowledge Flow and MCP requests are asynchronous, but their 401 recovery calls
a synchronous refresh callback. The shared refresh helper uses top-level
`httpx.post` with a ten-second timeout. While a token refresh is in flight, the
runtime pod's event-loop thread cannot advance unrelated SSE turns, timers, or
tool calls.

The path is exceptional rather than per-turn, but expirations often occur in
cohorts. A refresh wave can therefore create a pod-wide latency cliff.

## Evidence

- `libs/fred-runtime/fred_runtime/runtime_support/user_token_refresher.py:23-52`
  is synchronous and calls `httpx.post(..., timeout=10.0)`.
- `libs/fred-runtime/fred_runtime/common/kf_base_client.py:223-275` is async but
  invokes `_try_refresh_token()` synchronously after a 401.
- `kf_base_client.py:145-178` directly calls the agent/callback refresh method.
- `libs/fred-runtime/fred_runtime/common/mcp_interceptors.py:35-73` is async but
  calls `self._refresh()` synchronously after an expired-token response.
- `libs/fred-runtime/fred_runtime/app/agent_app.py:454-505` and
  `libs/fred-runtime/fred_runtime/integrations/v2_runtime/adapters.py:1393-1442`
  route runtime adapters to the synchronous helper.

## Minimal fix direction

Provide one async token-refresh service backed by a shared async HTTP client,
explicit timeout, and singleflight per refresh-token/session identity. Make
Knowledge Flow, MCP, and media adapters await it. Avoid merely wrapping every
call in an unbounded thread pool.

## Acceptance criteria

- No synchronous network I/O is reachable from an async execution/tool path.
- Concurrent refreshes for one identity coalesce without sharing tokens across
  principals.
- Refresh timeout/failure remains bounded and fail-closed.
- Logs and metrics expose refresh duration/outcome without tokens or user IDs.
- A delayed-Keycloak test proves unrelated SSE streams continue to progress.

## Decision log

- **2026-07-26:** recorded P1 confirmed. A ten-second timeout bounds the remote
  call but does not prevent event-loop blocking.
- **2026-07-27:** tracking issue [#2125](https://github.com/ThalesGroup/fred/issues/2125)
  created, targeting `swift-golive`. Not yet implemented.
- **2026-08-10:** verified against a live stack rebuilt from empty (all volumes
  wiped, platform re-provisioned; readiness GREEN 0 critical / 0 warning). Four
  results worth recording, because each replaces a claim previously argued from
  source with one observed:
  - **Label pinning is real.** Against the *actual* `PrometheusKPIStore` and a
    real registry, a failing sample that writes `error_code` onto
    `agent.tool_latency_ms` produces series carrying only
    `actor_type`/`status`/`tool_name` — the dim is absent. The counter emitted
    in the same run *does* carry it, because its first sample did. This is the
    evidence for §8.51 item 1.
  - **The event loop stays free.** A ticker advanced **172 times** during a live
    Keycloak round trip.
  - **Every legal hook shape resolves** through `resolve_refresh_result`:
    coroutine function, `async __call__`, coroutine-returning lambda, and
    `functools.partial` — the shapes the deleted static guard rejected. A
    synchronous hook degrades loudly and its token is still used.
  - **The wire-time rescue fires**, confirmed by a controlled A/B rather than a
    single observation. With a 31 s realm and 6 s of injected prepare-execution
    latency, the gate saw `left=24` (below the 30 s floor), the token was
    refreshed (`iat` +7 s, `left` 24→31) and the stream went out on the new
    token. The control — same delay, 300 s realm — showed `left=261` and **no
    refresh at all** (`iat` unchanged), ruling out routine background traffic.
    Caveat: keycloak-js refreshes over XHR, so the refresh is inferred from the
    `iat` transition rather than observed as a request.

  Still not covered: **AC5** (pod-level forced expiry across two concurrent SSE
  streams) remains structurally unrunnable, and the shutdown `finally`'s
  *raising-step* branch is unit-test-only — a clean shutdown exercises the path
  but cannot distinguish it from the pre-change sequence.
- **2026-08-10:** final state after the review cycle (§8.51). Two mechanisms
  that repeatedly regressed were replaced rather than patched: the refresh-hook
  contract is now enforced on the awaited *result* (`resolve_refresh_result` —
  no static shape check can classify every legal `Callable[[], Awaitable[str]]`),
  and HITL-prompt staleness is *derived* from the thread's `exchange_id` (no
  counter, no rollback state). Also landed: the closed-client branch pinned
  against httpx's real wording, pod shutdown completing under a per-step
  guarded `finally`, `agent.tool_latency_ms` reduced to `status` (first-sample
  label pinning made richer dims unreachable), and the wire-time token gate
  rescuing once before refusing. AC5 unchanged: still owed to AUTH-TX.
- **2026-08-09:** second external review round. Confirmed and fixed: the
  cleared-session fail-open on the frontend (`isTokenExpired` throws a bare
  string after keycloak-js `clearToken()`; `GetTokenSecondsLeft` reported the
  dead session as unconstrained; `GetToken` resurrected the persisted bearer —
  see §8.50's dated addendum), three malformed-response gaps in the refresher
  (explicit `expires_in: null` conflated with absent, negative lifetimes
  accepted, a non-string `error` value raising `TypeError` past the
  `RuntimeError` normalization), and two doc paragraphs still describing the
  superseded waiter-side timeout. AC5 unchanged: still owed, still
  structurally unreachable.
- **2026-08-07:** implemented. The evidence above listed three surfaces; a
  fourth was found during the fix — the workspace filesystem adapter's
  synchronous `_token()` (`integrations/v2_runtime/adapters.py`) called from
  `async def _download`/`ls`/`delete`/`link_for`. Also corrected: the helper's
  own docstring claimed its callers were sync LangChain callbacks and that
  converting would require propagating async through the media-client chain.
  That was false — `KfMarkdownMediaClient.fetch_media` is `async def` and
  awaits `_request_with_token_refresh`, and no LangChain sync-callback consumer
  of this helper existed. The stale rationale had been protecting the defect.

## Resolution evidence

Resolved 2026-08-07. Contract record:
[`RUNTIME-EXECUTION-CONTRACT.md` §8.48](../../../design/RUNTIME-EXECUTION-CONTRACT.md).

`refresh_user_access_token_from_keycloak` is now `async def`, backed by a
per-event-loop `httpx.AsyncClient` with bounded connection limits, coalescing
concurrent refreshes through a singleflight registry keyed on a SHA-256 digest
of `(realm_url, client_id, refresh_token)`. The in-flight task is
`asyncio.shield`ed so a disconnecting caller cannot abort its peers' refresh.
The synchronous helper was removed outright rather than deprecated, so no sync
network I/O remains reachable from an async path. Timeouts and transport errors
normalize to `RuntimeError`, keeping the path fail-closed.

`REFRESH_TIMEOUT_SECONDS` is enforced **inside the shared exchange task**, not
at the await site. httpx applies its timeout per phase, so the client uses
per-phase budgets that sum to the total — but per-phase budgets are not a
total: a peer dribbling a byte inside every read window resets the read timer
forever and no phase ever trips. A waiter-side bound therefore let every caller
give up on schedule while the exchange ran on indefinitely, holding its
`inflight` slot and a pooled connection with no caller left to observe it;
`max_connections=32` such identities would pin the pool. Wrapping the POST in
the task's own deadline makes the task terminate on its own, so waiters just
`await asyncio.shield(task)` and the shutdown drain inherits the same bound.

The success path is validated rather than trusted: a 2xx must carry a JSON
object with a non-empty string `access_token` and an `expires_in` that is
either absent (optional per RFC 6749 §5.1 — the 300 s default applies) or
numeric. `int(payload["expires_in"])` previously put the rejected value
straight into a `ValueError` that Knowledge Flow and MCP log downstream, which
is the same OWASP A09 / CWE-532 exposure `_safe_error_code` closes on the error
path.

**The singleflight registry is pod-local** (§0.2 invariant #7). `fred-agents`
runs several replicas with no principal-sticky routing, so coalescing holds
within one pod only; two replicas refreshing the same identity still issue two
Keycloak round trips. Accepted rather than escalated to a shared store because
the residual cross-pod rotation race degrades to an ordinary 401 retry.

Within a pod, coalescing also fixes a latent correctness bug: Keycloak rotates
refresh tokens, so two concurrent 401s replaying the same token previously made
the second fail `invalid_grant`.

Against each acceptance criterion:

| Criterion | Evidence |
| --- | --- |
| No sync network I/O reachable from an async path | All four chains await; the sync helper no longer exists. `test_every_401_recovery_hop_is_still_a_coroutine` guards every hop structurally, so re-introducing a sync hop in a *caller* fails the suite |
| Concurrent refreshes coalesce, no cross-principal sharing | `test_concurrent_refreshes_for_one_identity_coalesce` (10 callers → 1 round trip), `test_distinct_principals_never_share_a_token`, `test_same_token_different_client_id_does_not_coalesce`. **Pod-local** — see the replica-scope note above |
| Bounded and fail-closed | `test_timeout_is_bounded_and_fails_closed`, `test_transport_error_fails_closed`, `test_failure_does_not_wedge_the_singleflight_slot`, `test_total_wait_is_bounded_even_if_a_phase_hangs`, and `test_the_exchange_task_itself_is_bounded_not_just_its_waiters` — which asserts the timed-out exchange leaves neither a live task nor a registry entry, and fails against a waiter-side bound |
| Duration/outcome exposed without tokens or user IDs | Emitted as `auth.token_refresh_latency_ms` with `status=ok\|error\|timeout`. `test_emitted_dims_carry_no_secret_or_user_identity` asserts dims ⊆ {`status`, `actor_type`} with `actor_type == "system"` (the writer's own tag, not a user identity); `test_metric_labels_survive_the_prometheus_allow_list` asserts nothing is stripped before Grafana; `test_timeout_emits_timeout_status_not_error` asserts the timeout outcome is distinguishable. Neither an error body nor a malformed 2xx reaches a log sink: `test_error_body_never_reaches_the_log_or_the_exception` and `test_malformed_2xx_body_never_reaches_a_log_sink` (7 body shapes) |
| Delayed-Keycloak test proves unrelated streams progress | `test_refresh_does_not_block_the_event_loop` — a ticker task advances ≥5 times during the refresh window; **0 ticks** against the pre-change implementation, 18 after |

**Not covered offline:** the pod-level forced-expiry scenario from
`WORKING-PROTOCOL.md` §6 (shorten the Keycloak access-token TTL, drive one turn
into a 401, observe unrelated SSE streams). The unit test proves the mechanism —
the event loop stays free — but the end-to-end proof needs a live stack and is
not reachable from `make test`.

## The blocking call is unreachable — but the path is not (found 2026-08-07)

**The Keycloak HTTP call is unreachable, but the guard in front of it is reached
in production and is user-visible.**

`_refresh_runtime_context_access_token` always raises at
`if not refresh_token`, before any HTTP, because `runtime_context.refresh_token`
is always `None`. Two independent causes, in this order:

| Date | Commit | Event |
| --- | --- | --- |
| 2025-10-27 | `a5455f4c` | `GetRefreshToken` introduced — producer alive |
| 2026-02-02 | `b19b76f2` | `ExpiredTokenRetryInterceptor` added |
| **2026-05-21** | **`9680cd5b`** | "remove old legacy code" deletes the WS hook and the last `GetRefreshToken` call sites — **producer dies** |
| 2026-06-28 | `f27fe2f8` (#1862) | F-B nulls body-supplied `refresh_token` — five weeks later |

**F-B sealed an already-dead path; it did not break a working one.**

### What this means for TURN-07 specifically

The pod-wide latency cliff described above **cannot occur today** — execution
never reaches the synchronous `httpx.post`. TURN-07's P1 priority was therefore
overstated *as a latency finding*. The fix is still worth landing: it enforces
§0.2 invariant #2 ahead of any producer being restored, so whoever does that
work does not simultaneously reintroduce a ten-second pod-wide stall.

### The live defect underneath it

Expired-token recovery does not degrade — it fails. Already reported three
times, all closed without a fix, and **no open issue tracks it**:

- [#1948](https://github.com/ThalesGroup/fred/issues/1948) — KEA production, MCP
  401s on expired OIDC token. Closed **not-planned** 2026-08-05.
- [#1951](https://github.com/ThalesGroup/fred/issues/1951) — same on swift.
  Closed as consolidated into #2073.
- [#2073](https://github.com/ThalesGroup/fred/issues/2073) Item 3 — **reproduced
  live** 2026-07-23 ~14:50 (session `5fef7a4a-…`), with this exact guard in the
  stack trace: `RuntimeError: Cannot refresh user access token: refresh_token
  missing from runtime context.` at `adapters.py:1407`. Closed ~4h later with
  "fix not yet implemented".

Exposure window, from the deployment's own config: `accessTokenLifespan` is
**300 s** in the docker and k3d realm templates (`fred-deployment-factory`).
At the time of the incident the frontend refreshed a turn only below **30 s**
remaining, so a turn could begin with as little as 30 seconds of token life;
§8.50 raised that to **120 s** and now refuses to start a turn whose refresh
failed with under 30 s left, so the routine floor is 120 s and the 30 s case
survives only on the degraded path (refresh failed, ≥ 30 s still remaining).

That narrows the window but does not close it: with a 300 s TTL a turn can
still start with 120–300 s and outlive it, and there is **no whole-turn
timeout** — a single `summarize_read` call alone is allowed 300 s. The
fredlab/`gcp-c1` TTL is **unknown**: that chart runs Keycloak with
`args: [start]` and no `--import-realm`, so it inherits a default or a console
edit. No measured turn-duration data with a real LLM and security enabled
exists anywhere in the repo.

### Why it is not fixed here

Restoring delegated refresh is not a matter of re-adding the producer. F-B
neutralizes body-supplied refresh tokens **deliberately** — handing a pod a
user's long-lived refresh token is a security decision, not a bug fix. The
plausible alternatives (RFC 8693 token exchange, which needs a *valid* subject
token and so does not apply to an expired one; or having the pod call Knowledge
Flow under its own M2M identity with the user's claims for authorization) are
architecture changes. Per `CLAUDE.md` that requires an RFC and developer
sign-off, so this change does not attempt it.

What *is* fixed here is the blast radius and the entry window, via the two
no-RFC mitigations
([`RUNTIME-EXECUTION-CONTRACT.md`](../../../design/RUNTIME-EXECUTION-CONTRACT.md)
§8.49 and §8.50): `search_documents_using_vectorization` no longer kills the
turn on a downstream failure, and the chat send path preflights 120 s of token
headroom and refuses to start a turn whose refresh failed over a nearly-dead
token, instead of silently launching it.

The root-cause design — token exchange at admission, replacing the forwarded
user bearer with a pod-derived, audience-scoped, longer-lived credential — is
written up in
[`DELEGATED-DOWNSTREAM-AUTH-RFC.md`](../../../rfc/DELEGATED-DOWNSTREAM-AUTH-RFC.md),
with the deployment preconditions verified (Keycloak 26.3, confidential
`agentic` M2M client, soft-vs-c3 audience validation) and the open questions
listed. Not implemented; awaiting its own issue.
