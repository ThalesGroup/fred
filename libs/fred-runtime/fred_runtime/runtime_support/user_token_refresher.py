# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Async Keycloak refresh-token exchange for expired user access tokens.

Every 401-recovery path in fred-runtime (Knowledge Flow, MCP, media, workspace)
funnels through here, so this call must never block the event loop: one pod
serves many concurrent SSE turns on a single thread, and a synchronous refresh
stalls unrelated users for the whole round trip. See
`docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` §0.2 invariant #2.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

import httpx
from fred_core.kpi.kpi_writer_structures import Dims, KPIActor

from fred_runtime.runtime_context import get_runtime_context

logger = logging.getLogger(__name__)

REFRESH_TIMEOUT_SECONDS = 10.0

# httpx applies its timeout to each phase INDEPENDENTLY, so a single 10 s value
# would let one exchange run ~40 s end to end. These per-phase budgets sum to
# REFRESH_TIMEOUT_SECONDS, which bounds the common case — but per-phase budgets
# alone are NOT a total bound: a peer that dribbles a byte inside every read
# window resets the read timer forever, so the phase never trips. The hard
# total is therefore enforced separately, inside the exchange task itself.
#
# `pool` is the connection-ACQUISITION wait, not a network phase, so it is set
# to the whole budget rather than a slice of it: a cohort expiry is exactly when
# more than `max_connections` principals refresh at once, and a 1 s acquisition
# cap would shed callers 33+ with a PoolTimeout while the 10 s budget they were
# given went unused. Worse, PoolTimeout subclasses httpx.TimeoutException, so
# the shed callers were logged as "timed out after 10.0s" — naming a budget
# they never actually spent.
_PHASE_TIMEOUT = httpx.Timeout(
    connect=3.0, read=5.0, write=1.0, pool=REFRESH_TIMEOUT_SECONDS
)

# Used when the token response omits `expires_in` (OPTIONAL per RFC 6749 §5.1).
_DEFAULT_EXPIRES_IN_SECONDS = 300

# Ceiling on a claimed lifetime, so a misconfigured IdP or intercepting proxy
# announcing e.g. 1e15 cannot mint an `expires_at_timestamp` decades out.
#
# Defensive only, and deliberately so: NOTHING in the runtime currently gates
# on the value. `adapters.py` writes `runtime_context.access_token_expires_at`
# and no reader exists — `_workspace_access_token` returns any non-empty token
# string without consulting expiry at all. The clamp bounds the field for the
# first consumer that does read it (the AUTH-TX exchange cache is the expected
# one) rather than leaving a value that would be nonsense on arrival.
#
# Clamped, not rejected: a realm legitimately configured with a multi-day token
# keeps working, it is merely re-checked after a day.
_MAX_EXPIRES_IN_SECONDS = 86_400

# Distinguishes an absent `expires_in` (valid — the default applies) from an
# explicit JSON `null` (malformed — `payload.get()` returns None for both).
_MISSING = object()

REFRESH_METRIC = "auth.token_refresh_latency_ms"


@dataclass
class _LoopState:
    """Per-event-loop client and in-flight refresh registry.

    Replica scope (§0.2 invariant #7): **pod-local**, so coalescing holds
    within one pod only — two replicas refreshing one identity still issue two
    Keycloak round trips. Rationale for accepting that:
    RUNTIME-EXECUTION-CONTRACT.md §8.48.
    """

    client: httpx.AsyncClient
    inflight: dict[str, asyncio.Task[dict[str, object]]] = field(default_factory=dict)
    # Set once the client has been closed. The entry deliberately STAYS in
    # `_LOOP_STATE` so a later refresh on the same (still running) loop
    # fails fast instead of silently rebuilding a 32-connection client that
    # nothing will ever close. The closed-loop sweep removes it eventually.
    closed: bool = False


# Keyed per loop, not process-wide: an httpx.AsyncClient's connection pool is
# bound to the loop that created it, so a single global would break as soon as
# a second loop exists (tests, CLI). A pod runs one loop, so this is still one
# client per process in production.
#
# A plain dict with an explicit closed-loop sweep, NOT a WeakKeyDictionary:
# the values reference their key (each asyncio.Task holds its loop, and the
# client's pool is loop-bound), so a weak key is never collectable and every
# entry would live forever while appearing to be self-cleaning. Dead loops are
# swept in `_loop_state()` instead; their clients cannot be `aclose`d anymore
# (the pool died with the loop), so dropping the reference and letting GC
# finalize is all that is left to do.
_LOOP_STATE: dict[asyncio.AbstractEventLoop, _LoopState] = {}


# RFC 6749 §5.2 token-endpoint error codes. Anything outside this set is
# reported as "unrecognized" rather than echoed.
_ALLOWED_OAUTH_ERRORS = frozenset(
    {
        "invalid_request",
        "invalid_client",
        "invalid_grant",
        "unauthorized_client",
        "unsupported_grant_type",
        "invalid_scope",
    }
)


def _safe_error_code(response: httpx.Response | None) -> str:
    """Reduce a Keycloak error body to an allow-listed OAuth code.

    Why it exists:
    - the body is free text this service does not control, and was observed
      carrying a user id and a token-shaped value. It previously reached both
      this module's log AND the RuntimeError message, which Knowledge Flow and
      MCP log again downstream — a textbook OWASP A09 / CWE-532 exposure.
    - the status code plus an allow-listed error code keeps the failure
      diagnosable without echoing anything unbounded.

    How to use it:
    - `code = _safe_error_code(exc.response)`
    """
    if response is None:
        return "unavailable"
    try:
        payload = response.json()
    except ValueError:
        return "unparseable"
    code = payload.get("error") if isinstance(payload, dict) else None
    # isinstance first: an unhashable value (`"error": []`) would make the
    # frozenset membership test itself raise TypeError — from inside the
    # HTTPStatusError handler, bypassing the RuntimeError normalization the
    # callers' 401-recovery paths rely on.
    return (
        code
        if isinstance(code, str) and code in _ALLOWED_OAUTH_ERRORS
        else "unrecognized"
    )


def _coerce_expires_in(value: object) -> int | None:
    """Read `expires_in` without ever letting its value into an exception.

    Why it exists:
    - `int(payload["expires_in"])` puts the rejected value straight into the
      `ValueError` message. On a 2xx response that body is still attacker- or
      misconfiguration-controlled free text, and the resulting exception is
      logged by Knowledge Flow and MCP — the same OWASP A09 / CWE-532 exposure
      `_safe_error_code` closes for the non-2xx path.

    Returns `None` for a present-but-unusable value, which the caller treats as
    a malformed response rather than silently substituting a default: a token
    response that cannot state its own lifetime is not one to trust. Only a
    genuinely ABSENT field gets the default (the `_MISSING` sentinel — RFC 6749
    §5.1 makes the field optional); an explicit JSON `null` arrives here as
    `None` and is malformed, not omitted. Negative lifetimes are likewise
    rejected: no OAuth server issues a token that expired before it was sent.
    """
    if value is _MISSING:
        return _DEFAULT_EXPIRES_IN_SECONDS
    # bool is an int subclass; `expires_in: true` is malformed, not 1 second.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        # json.loads accepts Infinity/NaN, and int() of either raises.
        if not math.isfinite(value) or value < 0:
            return None
        return int(value)
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def _validated_token_payload(response: httpx.Response) -> dict[str, object] | None:
    """Shape-check a 2xx token response, or return `None` if it is malformed.

    Why it exists:
    - a 200 does not guarantee a token. Every field below was previously
      trusted: a non-JSON body, a JSON array, a missing `access_token`, or a
      non-numeric `expires_in` each raised an exception carrying the raw value
      into downstream logs.
    - callers store `access_token` and re-present it; letting a non-string
      through only defers the failure to a less obvious place.
    """
    try:
        raw = response.json()
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    access_token = raw.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return None
    expires_in = _coerce_expires_in(raw.get("expires_in", _MISSING))
    if expires_in is None:
        return None
    bounded = min(expires_in, _MAX_EXPIRES_IN_SECONDS)
    raw_refresh = raw.get("refresh_token")
    # A PROJECTION, not the decoded body. Returning `raw` passed an unbounded,
    # attacker-or-misconfiguration-shaped structure through to every caller —
    # which then had to be deep-copied per coalesced waiter, synchronously on
    # the event loop this module exists to keep free, and could raise
    # RecursionError from `copy.deepcopy` outside the normalization below.
    # These three fields are everything any caller reads.
    payload: dict[str, object] = {
        "access_token": access_token,
        "expires_at_timestamp": time.time() + max(0, bounded - 5),
    }
    if isinstance(raw_refresh, str) and raw_refresh:
        payload["refresh_token"] = raw_refresh
    return payload


class _NoCookieJar(httpx.Cookies):
    """A cookie jar that never stores anything.

    Why it exists:
    - this client is process-wide and carries refreshes for EVERY principal.
      httpx calls `cookies.extract_cookies(response)` on each response, so a
      normal jar would persist whatever Keycloak set for one user and replay it
      on the next user's refresh. The previous throwaway `httpx.post` could not
      do that; a shared client can, so the capability is removed rather than
      cleared after the fact (clearing would race between concurrent principals).
    - the token endpoint is a back-channel call that needs no cookies at all.
    """

    def extract_cookies(self, response: httpx.Response) -> None:
        return None


def _new_async_client(
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Build the refresher's HTTP client.

    Why it exists:
    - a cohort expiry can put many distinct principals into refresh at once
      (coalescing does not help — distinct identities, distinct digests), so
      the pool is bounded explicitly rather than left at httpx's defaults.
    - `transport` is the seam tests use to inject a `MockTransport` *while
      keeping this function's real configuration* — building a bare client in
      the test would validate a different client than production runs (that is
      how the shared cookie jar below went unnoticed).

    The timeout here is httpx's **per-phase** one (connect/read/write/pool each
    get it). `refresh_user_access_token_from_keycloak` enforces the total.
    """
    client = httpx.AsyncClient(
        timeout=_PHASE_TIMEOUT,
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
        transport=transport,
    )
    # Assigned to the private attribute deliberately: httpx's public `cookies`
    # setter does `self._cookies = Cookies(value)`, which re-wraps and discards
    # the no-store subclass. `_cookies` is what `_send_single_request` calls
    # `extract_cookies` on. If httpx ever renames it,
    # `test_shared_client_never_persists_cookies_across_principals` fails —
    # which is the point, since the alternative is silently resuming storage.
    client._cookies = _NoCookieJar()
    # Post-condition, not decoration: the PUBLIC setter re-wraps any value in a
    # plain `Cookies`, and a future `client.cookies = ...` (or an httpx rename
    # of `_cookies`) would silently restore a storing jar on the process-wide
    # client — replaying one principal's Keycloak cookies onto the next
    # principal's refresh, with no error anywhere.
    if not isinstance(client.cookies, _NoCookieJar):  # pragma: no cover - guard
        raise RuntimeError(
            "Refusing to share a token-refresh client that can persist cookies "
            "across principals: the no-store jar was not installed."
        )
    return client


def _loop_state() -> _LoopState:
    """Return (creating on first use) the running loop's refresher state."""
    loop = asyncio.get_running_loop()
    # Sweep entries whose loop has closed (each test's asyncio.run, a CLI
    # invocation) so the registry cannot grow one orphaned client per dead
    # loop. Cheap: the dict holds one entry per live loop, which is 1 in
    # production.
    # `list(...)` snapshots the keys and `pop(..., None)` tolerates a concurrent
    # sweep: `_LOOP_STATE` is a module global with no lock, so two threads each
    # running their own `asyncio.run` can sweep the same dead loop (KeyError) or
    # insert while another iterates ("dictionary changed size during
    # iteration"). Either escapes as a non-RuntimeError the callers'
    # 401-recovery paths do not normalize.
    for stale in [known for known in list(_LOOP_STATE) if known.is_closed()]:
        _LOOP_STATE.pop(stale, None)
    state = _LOOP_STATE.get(loop)
    if state is None:
        state = _LoopState(client=_new_async_client())
        _LOOP_STATE[loop] = state
    elif state.closed:
        # Normalized, because every caller's 401 recovery catches RuntimeError.
        raise RuntimeError("Token refresh failed: refresher is shut down")
    return state


def _identity_digest(keycloak_url: str, client_id: str, refresh_token: str) -> str:
    """Stable coalescing key for one principal's refresh, holding no secret.

    Why it exists:
    - concurrent refreshes must coalesce per identity, but the raw refresh
      token must not become a dictionary key we could later log or dump.
    """
    material = "\x00".join((keycloak_url, client_id, refresh_token))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@contextmanager
def _refresh_timer() -> Iterator[Dims]:
    """Time the refresh through the runtime KPI writer, or degrade to a no-op.

    Why it exists:
    - a caller without an installed runtime context (unit tests) must still be
      able to refresh; a missing metric sink is not a refresh failure.
    - `REFRESH_METRIC` is a dedicated metric name rather than a `phase` dim on
      the shared `app.phase_latency_ms`, because `phase` is deliberately absent
      from `PROMETHEUS_ALLOWED_LABELS` and would be stripped before Grafana.
      `status` is allowed, so name + outcome identify the series without
      spending a new label (OBSERVABILITY-AND-AUDIT.md §3).
    - dims carry only `status`: no token, user, session, or team identity.

    How to use it:
    - `with _refresh_timer() as dims: ...; dims["status"] = "ok"`
    - set the status and leave the block NORMALLY; raising inside it makes
      `KPIWriter._TimerImpl.__exit__` force `status="error"`, discarding the
      value set here.
    """
    try:
        kpi = get_runtime_context().get_kpi_writer()
    except RuntimeError:
        # No runtime context installed (unit test, CLI): metrics are optional.
        yield {}
        return
    with kpi.timer(
        REFRESH_METRIC,
        actor=KPIActor(type="system"),
    ) as dims:
        yield dims


async def _post_token_request(
    client: httpx.AsyncClient, token_url: str, form: dict[str, str]
) -> httpx.Response:
    """The awaitable the total deadline wraps: one POST plus its status check."""
    r = await client.post(token_url, data=form)
    r.raise_for_status()
    return r


async def _exchange_refresh_token(
    client: httpx.AsyncClient,
    keycloak_url: str,
    client_id: str,
    refresh_token: str,
) -> dict[str, object]:
    """Perform one Keycloak refresh round trip and normalize its failures."""
    token_url = f"{keycloak_url.rstrip('/')}/protocol/openid-connect/token"

    form = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }

    started = time.perf_counter()

    # The failure is recorded and re-raised AFTER the timer block: raising
    # through `_TimerImpl.__exit__` would force status="error" and lose the
    # "timeout" outcome (kpi_writer.py — `status = "error" if exc_type else ...`).
    failure_message: str | None = None
    failure_cause: Exception | None = None

    with _refresh_timer() as dims:
        try:
            # The TOTAL deadline lives here, inside the shared task, not at the
            # await site. A per-waiter bound would let a slow-dribble peer time
            # every caller out while the task itself ran on indefinitely,
            # holding its `inflight` slot and its connection — 32 such
            # identities would pin the whole pool with no caller left to notice.
            # Bounding the task instead means every waiter, and the shutdown
            # drain, inherits one deadline that is actually enforced.
            r = await asyncio.wait_for(
                _post_token_request(client, token_url, form),
                timeout=REFRESH_TIMEOUT_SECONDS,
            )
        except httpx.HTTPStatusError as e:
            dims["status"] = "error"
            status = e.response.status_code if e.response is not None else "N/A"
            code = _safe_error_code(e.response)
            logger.error(
                "Keycloak refresh request failed (status=%s, error=%s).",
                status,
                code,
            )
            # Deliberately not the response body: this message propagates into
            # Knowledge Flow / MCP logs and, via tool errors, into chat history.
            failure_message = f"Token refresh failed: {code} (HTTP {status})"
            failure_cause = e
        except (httpx.TimeoutException, asyncio.TimeoutError) as e:
            # httpx.TimeoutException = one phase overran; asyncio.TimeoutError =
            # the total overran without any single phase tripping. Same outcome
            # to the caller, same metric status.
            dims["status"] = "timeout"
            logger.error(
                "Keycloak refresh timed out after %ss.", REFRESH_TIMEOUT_SECONDS
            )
            failure_message = "Token refresh failed: timed out"
            failure_cause = e
        except RuntimeError as e:
            # httpx raises a bare RuntimeError ("Cannot send a request, as the
            # client has been closed") when the pool is torn down under an
            # in-flight exchange — reachable whenever the shutdown drain gives
            # up on its deadline. It matches none of the handlers below, so
            # without this it escapes un-normalized into a caller whose 401
            # recovery only knows how to read our RuntimeError contract.
            #
            # Narrowed on purpose: NotImplementedError (what httpx's base
            # transport raises when one is not wired), httpx.StreamError and
            # RecursionError are ALL RuntimeError subclasses and none is an
            # httpx.HTTPError, so an unconditional clause reported a wiring bug
            # as an orderly shutdown — and did it at WARNING with no type. Only
            # the closed-client case is claimed; everything else is reported as
            # what it is, with the type named.
            dims["status"] = "error"
            if "client has been closed" in str(e):
                logger.warning(
                    "Keycloak refresh aborted: client closed during shutdown."
                )
                failure_message = "Token refresh failed: client closed"
            else:
                logger.error(
                    "Keycloak refresh hit an unexpected runtime error: %s.",
                    type(e).__name__,
                    exc_info=e,
                )
                failure_message = "Token refresh failed: internal error"
            failure_cause = e
        except (httpx.HTTPError, OSError) as e:
            # OSError too: an ssl.SSLError or ConnectionResetError surfacing
            # from below httpx without being wrapped would otherwise escape
            # this chain raw, bypassing the RuntimeError normalization the
            # callers' 401-recovery paths catch — the same shape as the
            # unhashable-`error` TypeError `_safe_error_code` guards against.
            dims["status"] = "error"
            logger.error("Keycloak refresh transport error: %s", type(e).__name__)
            failure_message = "Token refresh failed: transport error"
            failure_cause = e
        else:
            payload = _validated_token_payload(r)
            if payload is None:
                dims["status"] = "error"
                # Status only: the body is what failed validation, so it is
                # exactly the thing that must not be echoed.
                logger.error(
                    "Keycloak refresh returned a malformed token response (HTTP %s).",
                    r.status_code,
                )
                failure_message = "Token refresh failed: malformed token response"
            else:
                dims["status"] = "ok"
                logger.info(
                    "Keycloak user token refresh succeeded in %.0f ms.",
                    (time.perf_counter() - started) * 1000,
                )
                return payload

    raise RuntimeError(failure_message or "Token refresh failed") from failure_cause


async def refresh_user_access_token_from_keycloak(
    keycloak_url: str, client_id: str, refresh_token: str
) -> dict[str, object]:
    """Exchange a refresh token for a fresh access/refresh pair, without blocking.

    Why it exists:
    - expired-token recovery runs inside `async def` request and tool paths; a
      synchronous exchange there stalls every other SSE turn on the pod.
    - Keycloak rotates refresh tokens, so two OVERLAPPING 401s replaying the
      same token would make the second fail `invalid_grant`. Coalescing per
      identity is a correctness fix as much as a latency one — but only for
      calls that overlap in time: a turn whose 401 lands after an earlier
      refresh already completed presents a token Keycloak has consumed and
      still gets `invalid_grant`. Closing that needs a cached result keyed on
      the pre-rotation token, which means holding live credentials in pod
      memory — an AUTH-TX decision (`DELEGATED-DOWNSTREAM-AUTH-RFC.md` Q8), not
      one to make here. It degrades to one failed tool call, not a dead turn.

    How to use it:
    - `payload = await refresh_user_access_token_from_keycloak(url, cid, token)`
    - concurrent callers presenting the same refresh token share one round trip;
      different principals never share a result.

    Example:
        >>> payload = await refresh_user_access_token_from_keycloak(
        ...     "https://kc/realms/app", "app-client", refresh_token
        ... )
        >>> payload["access_token"]
    """
    state = _loop_state()
    digest = _identity_digest(keycloak_url, client_id, refresh_token)

    # There is no `await` between the lookup and the insert, so the event loop
    # cannot interleave another caller here. That is the whole mutual exclusion
    # this registry needs — an asyncio.Lock would add nothing.
    task = state.inflight.get(digest)
    if task is None:
        task = asyncio.create_task(
            _exchange_refresh_token(
                state.client, keycloak_url, client_id, refresh_token
            ),
            name="keycloak-token-refresh",
        )
        state.inflight[digest] = task

        def _release(finished: asyncio.Task[dict[str, object]]) -> None:
            state.inflight.pop(digest, None)
            # Retrieve any exception here so that a sole caller cancelling
            # (client disconnect) before a failing refresh completes does not
            # leave asyncio reporting "Task exception was never retrieved" at
            # teardown. Callers still awaiting get the exception re-raised.
            if not finished.cancelled():
                finished.exception()

        task.add_done_callback(_release)

    # Shielded: one caller being cancelled (client disconnect mid-turn) must not
    # abort the refresh the other coalesced callers are still waiting on.
    #
    # No per-waiter timeout here on purpose. The task already carries the total
    # deadline (`_exchange_refresh_token`), so this await is bounded by
    # construction.
    #
    # A cancelled caller does NOT cancel the exchange, even when it is the only
    # one waiting. Reference-counting waiters so the last one out could cancel
    # was tried and reverted: `_release` clears its own bookkeeping before the
    # waiters resume, so a departing waiter decremented the count of a LATER
    # exchange on the same digest and cancelled a task other live turns were
    # awaiting; and `task.cancel()` leaves the task in `inflight` for a further
    # loop iteration, so the next arrival adopted a doomed task. Both delivered
    # `CancelledError` — a BaseException every caller's `except Exception`
    # 401-recovery handler misses — killing turns instead of degrading them.
    #
    # The cost of NOT cancelling is a rotation nobody consumes: the exchange
    # completes, Keycloak invalidates the presented refresh token, and the
    # replacement is dropped. That is the protocol-inherent lost-rotation race
    # already recorded as open question 8 in
    # `docs/swift/rfc/DELEGATED-DOWNSTREAM-AUTH-RFC.md`, and it degrades to one
    # `invalid_grant` retry — strictly better than cancelling a live turn.
    #
    # Each waiter gets its OWN dict: the task resolves to a single object, and
    # handing the same mutable payload to every coalesced caller would let the
    # first one to mutate it corrupt what the others already read.
    # One dict per waiter. A shallow copy is exact here because
    # `_validated_token_payload` projects the response down to flat scalars —
    # it does not hand back the decoded body.
    return dict(await asyncio.shield(task))


async def aclose_token_refresh_client() -> None:
    """Close the running loop's refresher client.

    Why it exists:
    - shutdown and test teardown need a deterministic way to release the pool
      rather than relying on garbage collection.

    How to use it:
    - `await aclose_token_refresh_client()`
    """
    loop = asyncio.get_running_loop()
    state = _LOOP_STATE.get(loop)
    if state is None:
        return
    # The state stays REGISTERED for the whole drain and is popped only at the
    # end. A refresh arriving mid-drain therefore reuses this client instead of
    # building a second 32-connection one that nothing would ever close — and,
    # because the loop below re-reads `state.inflight` each pass rather than
    # working from a snapshot, that late arrival is drained too. A flag marking
    # "closing" was tried instead and was inert: nothing read it, and the
    # snapshot meant a mid-drain exchange had the transport closed under it,
    # raising `RuntimeError: Cannot send a request, as the client has been
    # closed` past every handler in `_exchange_refresh_token`.
    #
    # Drain before closing: a refresh in flight is shielded, so closing the
    # transport under it turns an orderly shutdown into a spurious auth error
    # for a turn that was still running. Each exchange carries its own total
    # deadline, so this terminates on its own; the deadline here is the
    # belt-and-braces bound against a task wedged before that applies.
    #
    # `asyncio.wait`, not `wait_for(gather(...))`: on timeout `wait_for` cancels
    # the gather, which propagates cancellation into every child task
    # (`return_exceptions=True` only aggregates child *exceptions*, it does not
    # shield them from an outer cancel). Each shielded waiter would then see
    # CancelledError — a BaseException that every caller's `except Exception`
    # 401-recovery handler misses — so a rolling restart killed in-flight turns
    # instead of degrading them. `wait` stops waiting without touching the tasks.
    deadline = time.monotonic() + REFRESH_TIMEOUT_SECONDS
    while True:
        inflight = list(state.inflight.values())
        remaining = deadline - time.monotonic()
        if not inflight:
            break
        if remaining <= 0:
            logger.warning(
                "Shutdown drain gave up after %ss; closing the refresh client "
                "with %d exchange(s) still in flight.",
                REFRESH_TIMEOUT_SECONDS,
                len(inflight),
            )
            break
        await asyncio.wait(inflight, timeout=remaining)

    # Closed BEFORE the entry is dropped. Popping first left one await during
    # which a 401 recovery found no entry, built a second 32-connection client
    # on an already-closing loop, and leaked it — exactly the window the
    # re-reading drain above exists to close. A refresh landing here instead
    # reuses this client and fails with the normalized transport error below.
    await state.client.aclose()
    state.closed = True
