// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import Keycloak, { KeycloakInstance } from "keycloak-js";

let keycloakInstance: KeycloakInstance | null = null;
let isSecurityEnabled = false;

// keycloak-js's own floor: `updateToken` does `minValidity = minValidity || 5`,
// so 0 does NOT mean "don't check" — it means five seconds. `isTokenExpired`
// disagrees (0 is falsy there and subtracts nothing), so any threshold we test
// must be coerced the same way before the two are compared.
const KEYCLOAK_MIN_VALIDITY_FLOOR_S = 5;
// keycloak-js's sentinel for "refresh regardless of what the token looks like"
// (`if (minValidity == -1) { refreshToken = true; }`). The only force path it
// offers.
const KEYCLOAK_FORCE_REFRESH = -1;
// Work rank for a forced refresh: strictly above any headroom threshold, so a
// forced caller never reuses another chain and every other caller may reuse a
// forced one (it produces a full-lifetime token).
const KEYCLOAK_FORCE_WORK = Number.POSITIVE_INFINITY;

// single-flight so concurrent calls don’t trigger multiple refreshes
let refreshInFlight: Promise<boolean> | null = null;
// True once the session has genuinely ended — either keycloak-js ended it
// itself (clearToken → onAuthLogout, e.g. after a refresh answered HTTP 400)
// or the app deliberately ended it (explicit Logout/CallLogout). Distinguishes
// "session died" from "not logged in yet": keycloak-js sets
// `authenticated = false` in BOTH states, so the fields alone cannot tell them
// apart, and GetTokenSecondsLeft must report the first as dead (0) without
// reporting app bootstrap the same way.
// Reset when a refreshed token is stored; a full login resets it with the page.
let sessionInvalidated = false;

// The ONE owner of "the persisted token dies with the session". Every path
// that ends a session (keycloak-js's own clearToken via onAuthLogout, Logout,
// CallLogout) must go through this — a teardown path that skips it leaves an
// orphaned bearer that GetToken()'s localStorage fallback will re-present and
// the backend will accept via offline JWT validation.
const clearPersistedToken = () => {
  sessionInvalidated = true;
  authEpoch += 1;
  localStorage.removeItem("keycloak_token");
};
// The headroom the in-flight refresh was started with. A caller needing MORE
// headroom cannot reuse a weaker in-flight check: a turn preflight asking for
// 120 s would otherwise inherit an ordinary fetch's 30 s check and be told
// "fresh" with only 30 s of validity.
let refreshInFlightWork = 0;
// Bumped whenever the session is deliberately torn down, so a refresh that
// settles afterwards can tell it has been superseded.
let authEpoch = 0;

// keycloak-js's updateToken() has no built-in timeout — a dropped connection
// or unresponsive Keycloak leaves it pending forever. Since `refreshInFlight`
// is a shared singleton, every other in-flight or future request awaits that
// same never-settling promise, wedging every authenticated call in the app
// (dynamicBaseQuery awaits ensureFreshToken before every fetch). Bound it so
// a hung refresh fails fast instead, falling through to the existing 401 ->
// retry -> logout recovery path in dynamicBaseQuery.tsx.
const TOKEN_REFRESH_TIMEOUT_MS = 8_000;

// ---------- Insecure-mode dev token support ----------
// Fred rationale: even when security is off, the frontend + backend contracts
// still expect an Authorization: Bearer <token>. We mint a local, JWT-shaped
// token with the current user's identity so the UI flows (headers, auth guards,
// role checks) behave exactly like production — just without real verification.
// VITE_DEV_USERNAME is injected at dev-server start time via `make run`
// (VITE_DEV_USERNAME=$(whoami) npm run dev), giving the real Unix username.
const DEV_TOKEN_STORAGE_KEY = "dev_admin_token";
const DEV_USERNAME = import.meta.env.VITE_DEV_USERNAME || "dev";

// Minimal base64url (no padding) to build a JWT-shaped string without crypto.
function b64url(obj: unknown): string {
  const json = typeof obj === "string" ? obj : JSON.stringify(obj);
  // Note: window.btoa expects Latin1; for safety, escape UTF-8 properly:
  const utf8 = unescape(encodeURIComponent(json));
  return btoa(utf8).replace(/=+$/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

/**
 * Build a local, unsigned JWT-shaped token.
 * - Shape matches typical Keycloak claims so downstream code (and dev tools)
 *   can "mouse over" tokenParsed-like content and understand the model.
 * - Signature is a fixed string (not cryptographically valid). That's OK:
 *   in insecure mode the backend shouldn't verify it.
 */
function buildDevAdminToken(): string {
  const now = Math.floor(Date.now() / 1000);
  const oneWeek = 7 * 24 * 60 * 60;

  const header = { alg: "none", typ: "JWT" };

  const payload = {
    exp: now + oneWeek,
    iat: now,
    // Mirror common KC fields so getters remain predictable in dev:
    iss: "http://dev-keycloak/realms/dev",
    typ: "Bearer",
    azp: "app",
    scope: "openid profile email",
    email_verified: true,
    name: DEV_USERNAME,
    preferred_username: DEV_USERNAME,
    given_name: DEV_USERNAME,
    family_name: "",
    email: `${DEV_USERNAME}@localhost`,
    sub: DEV_USERNAME, // stable ID used by UI and logs in dev
    realm_access: { roles: ["admin"] },
    resource_access: {
      app: { roles: ["admin"] },
    },
  };

  // JWT-shape: header.payload.signature — signature is intentionally dummy
  return `${b64url(header)}.${b64url(payload)}.devsig`;
}

function base64UrlToUtf8Json(b64url: string): any {
  // Convert base64url -> base64
  const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((b64url.length + 3) % 4);
  // Decode to UTF-8 string
  const jsonStr = decodeURIComponent(escape(atob(b64)));
  return JSON.parse(jsonStr);
}

function parseJwtPayload(token: string | null | undefined): any | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    return base64UrlToUtf8Json(parts[1]); // payload
  } catch {
    return null;
  }
}

function getOrCreateDevToken(): string {
  const cached = localStorage.getItem(DEV_TOKEN_STORAGE_KEY);
  if (cached) {
    // Invalidate if the Unix username has changed since the token was cached.
    const parsed = parseJwtPayload(cached);
    if (parsed?.preferred_username === DEV_USERNAME) return cached;
    localStorage.removeItem(DEV_TOKEN_STORAGE_KEY);
  }
  const tok = buildDevAdminToken();
  localStorage.setItem(DEV_TOKEN_STORAGE_KEY, tok);
  return tok;
}

// -----------------------------------------------------

/**
 * Parse a full KC realm URL like:
 *   http://kc:8080/realms/myrealm
 * => { url: "http://kc:8080/", realm: "myrealm" }
 */
function parseKeycloakUrl(fullUrl: string): { url: string; realm: string } {
  const match = fullUrl.match(/^(https?:\/\/[^/]+(?:\/[^/]+)*)\/realms\/([^/]+)\/?$/);
  if (!match) throw new Error(`Invalid keycloak_url format: ${fullUrl}`);
  return { url: match[1] + "/", realm: match[2] };
}

export function createKeycloakInstance(keycloak_url: string, keycloak_client_id: string) {
  if (!keycloakInstance) {
    isSecurityEnabled = true;
    const { url, realm } = parseKeycloakUrl(keycloak_url);

    keycloakInstance = new Keycloak({ url, realm, clientId: keycloak_client_id });

    // keycloak-js clears its live token itself when a refresh comes back
    // HTTP 400 (clearToken → onAuthLogout). Drop the persisted copy in the
    // same breath: GetToken() falls back to localStorage, and an
    // unexpired-but-orphaned bearer would otherwise keep authenticating
    // requests (the backend validates JWTs offline) after Keycloak has
    // already ended the session.
    keycloakInstance.onAuthLogout = () => {
      clearPersistedToken();
    };

    // Proactive refresh when KC tells us the token is expired
    keycloakInstance.onTokenExpired = () => {
      // try to refresh quietly; if it fails, KC will push to login on next API call
      ensureFreshToken(30).catch(() => {
        // no-op; the baseQuery will handle 401 -> logout
      });
    };
  }
  return keycloakInstance!;
}

/**
 * Call on app startup (after createKeycloakInstance).
 *
 * Fred architecture note:
 * - In prod, we delegate identity to Keycloak (OIDC, PKCE, refresh).
 * - In dev/insecure mode, we *still* surface a token + roles so the rest
 *   of the app (RTK Query baseQuery, guards, UX) behaves identically.
 */
const Login = (onAuthenticatedCallback: Function) => {
  if (!isSecurityEnabled) {
    // In insecure mode we "log in" by minting a local dev admin token.
    const devToken = getOrCreateDevToken();
    localStorage.setItem("keycloak_token", devToken);
    onAuthenticatedCallback();
    return;
  }

  keycloakInstance!
    .init({
      onLoad: "login-required",
      pkceMethod: "S256",
      checkLoginIframe: false,
    })
    .then((authenticated) => {
      if (authenticated) {
        localStorage.setItem("keycloak_token", keycloakInstance!.token || "");
        onAuthenticatedCallback();
      } else {
        alert("User not authenticated");
      }
    })
    .catch((e) => {
      console.error("[Keycloak] init error:", e);
    });
};

const Logout = () => {
  if (!isSecurityEnabled) {
    // Clear dev token + app state, stay on homepage.
    try {
      sessionStorage.clear();
      clearPersistedToken();
      localStorage.removeItem(DEV_TOKEN_STORAGE_KEY);
    } finally {
      // No KC logout redirect in insecure mode.
      window.location.assign("/");
    }
    return;
  }

  if (!keycloakInstance) return;
  try {
    sessionStorage.clear();
    clearPersistedToken();
  } finally {
    keycloakInstance.logout({ redirectUri: window.location.origin + "/" });
  }
};

/**
 * Ensure token validity (minValidity seconds).
 * Returns true if token is valid or refreshed, false if refresh failed.
 *
 * In insecure mode this is trivially true — the token is local and
 * intentionally long-lived to avoid surprising dev UX during demos.
 */
export async function ensureFreshToken(minValidity = 30): Promise<boolean> {
  if (!isSecurityEnabled || !keycloakInstance) return true;

  // Already enough headroom: keycloak-js would no-op anyway (it only refreshes
  // when isTokenExpired(minValidity)), and settling it here means a caller
  // needing MORE headroom never blocks on a weaker refresh.
  //
  // isTokenExpired THROWS (a bare string, 'Not authenticated') once
  // clearToken() has run — keycloak-js does that itself after a refresh
  // rejected with HTTP 400 ends the session. That state has no live token and
  // no refresh token left to exchange, so it is this function's `false`, not
  // an exception: dynamicBaseQuery awaits us with no catch, and an escaping
  // throw would abort ordinary requests before their 401→logout recovery ran.
  //
  // `minValidity <= 0` means FORCE — the caller has already seen a 401, so the
  // browser's own view of the token is exactly what it must not trust (clock
  // skew against admission's `leeway=0`, an SSO logout elsewhere, realm key
  // rotation). keycloak-js expresses that as `updateToken(-1)`, its only
  // unconditional path; coercing 0 up to the 5 s floor merely moved the hole.
  const forced = minValidity <= 0;
  const effectiveMinValidity = forced ? KEYCLOAK_FORCE_REFRESH : Math.max(minValidity, KEYCLOAK_MIN_VALIDITY_FLOOR_S);

  if (!forced) {
    let hasHeadroom: boolean;
    try {
      hasHeadroom = !keycloakInstance.isTokenExpired(effectiveMinValidity);
    } catch {
      return false;
    }
    if (hasHeadroom) return true;
  }

  // Whether the token we hold NOW satisfies this particular caller. Deliberately
  // evaluated per caller rather than baked into the shared chain: the chain
  // answers only "did a refresh complete", and a caller's headroom is its own
  // business. Folding the two together is what made a SUCCESSFUL refresh report
  // failure to a post-401 caller (because some other caller's 120 s threshold
  // was not met by a 60 s realm) and log the user out mid-session.
  const satisfiedNow = (refreshed: boolean): boolean => {
    if (!refreshed) return false;
    // A forced refresh's contract is "you contacted Keycloak", not a lifetime.
    if (forced) return true;
    try {
      return !keycloakInstance!.isTokenExpired(effectiveMinValidity);
    } catch {
      return false;
    }
  };

  // Reuse an in-flight refresh only when it does at least as much WORK as this
  // caller needs — ranked by work, not by threshold. A forced refresh is the
  // most work there is, so it both reuses nothing and satisfies everyone.
  // Ranking by threshold put force at 5 s, the weakest rung, so a forced caller
  // silently piggy-backed on any chain in flight and never contacted Keycloak
  // at all — the retry then replayed the dying bearer straight into a logout.
  const requiredWork = forced ? KEYCLOAK_FORCE_WORK : effectiveMinValidity;
  if (refreshInFlight && refreshInFlightWork >= requiredWork) {
    return satisfiedNow(await refreshInFlight);
  }

  // Install our own chain, replacing any weaker one (whose waiters keep their
  // promise). keycloak-js coalesces concurrent refreshes through its
  // refreshQueue, so this costs no extra token request, and the
  // ownership-checked finally below stops the older chain clearing this slot.
  // Raced against a timeout so a hung refresh resolves "failed", not forever.
  refreshInFlightWork = requiredWork;
  // The session generation this refresh belongs to. A logout bumps it, so a
  // response arriving after the user signed out cannot re-persist a live bearer
  // over the copy `clearPersistedToken` just removed — the window is real
  // because `logout()` navigates without cancelling in-flight XHRs.
  const epochAtStart = authEpoch;
  // Cleared when the race settles either way. Without this the loser timer
  // still fired, logging "token refresh timed out" 8 s after every SUCCESSFUL
  // refresh — noise in precisely the area (#2125) this work exists to make
  // diagnosable, plus one stray timer retained per refresh for the tab's life.
  let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
  const chain: Promise<boolean> = Promise.race([
    keycloakInstance.updateToken(effectiveMinValidity).then(() => {
      if (authEpoch !== epochAtStart) {
        // Superseded by a logout while this was in flight. Do not resurrect the
        // persisted token and do not clear `sessionInvalidated`.
        return false;
      }
      sessionInvalidated = false;
      localStorage.setItem("keycloak_token", keycloakInstance!.token || "");
      return true;
    }),
    new Promise<boolean>((resolve) => {
      timeoutHandle = setTimeout(() => {
        console.warn("[Keycloak] token refresh timed out after", TOKEN_REFRESH_TIMEOUT_MS, "ms");
        resolve(false);
      }, TOKEN_REFRESH_TIMEOUT_MS);
    }),
  ])
    .catch((err) => {
      console.warn("[Keycloak] token refresh failed:", err);
      return false;
    })
    .finally(() => {
      if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
      // Clear only if this chain still owns the slot, so a settling chain can
      // never null out a newer one installed behind it.
      if (refreshInFlight === chain) {
        refreshInFlight = null;
        refreshInFlightWork = 0;
      }
    });
  refreshInFlight = chain;

  return satisfiedNow(await chain);
}

// ========================= Getters =========================

const GetRealmRoles = (): string[] => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return ["admin"];
  return keycloakInstance.tokenParsed.realm_access?.roles || [];
};

const GetUserRoles = (): string[] => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return ["admin"];
  const clientId = (keycloakInstance as any).clientId as string;
  const clientRoles = keycloakInstance.tokenParsed.resource_access?.[clientId]?.roles || [];
  return [...clientRoles];
};

const GetUserName = (): string | null => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return DEV_USERNAME;
  return (keycloakInstance.tokenParsed as any).preferred_username || null;
};

const GetUserFullName = (): string | null => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return DEV_USERNAME;
  return (keycloakInstance.tokenParsed as any).name || null;
};

const GetUserGivenName = (): string | null => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return DEV_USERNAME;
  return (keycloakInstance.tokenParsed as any).given_name || null;
};

const GetUserMail = (): string | null => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return `${DEV_USERNAME}@localhost`;
  return (keycloakInstance.tokenParsed as any).email || null;
};

const GetUserId = (): string | null => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return DEV_USERNAME;
  return (keycloakInstance.tokenParsed as any).sub || null;
};

/**
 * Always return a Bearer token:
 * - prod: real KC token
 * - dev: local, JWT-shaped dev admin token
 *
 * Why? Because downstream code (RTK Query baseQuery, HTTP middlewares,
 * and sometimes backend logs) assume a token is present. Keeping that
 * invariant reduces branches and keeps the app “prod-shaped” in dev.
 */
const GetToken = (): string | null => {
  if (!isSecurityEnabled) {
    const tok = getOrCreateDevToken();
    // Keep key name consistent so other places only read "keycloak_token".
    localStorage.setItem("keycloak_token", tok);
    return tok;
  }
  // A refresh that settles after the session ended can resurrect
  // keycloakInstance.token in memory (keycloak-js's setToken() runs
  // synchronously, before our epoch check even sees the response) — once the
  // session is invalidated, never hand that back, and never fall through to
  // the localStorage copy either, since clearPersistedToken already removed it.
  if (sessionInvalidated) return null;
  return keycloakInstance?.token || localStorage.getItem("keycloak_token");
};
const GetRefreshToken = (): string | null => {
  if (!isSecurityEnabled) {
    // In dev mode, there is no real refresh token
    return "dev-refresh-token-dummy";
  }
  if (sessionInvalidated) return null;
  // 🔑 Access the refreshToken property on the KeycloakInstance
  return keycloakInstance?.refreshToken || null;
};
const GetTokenParsed = (): any => {
  if (!isSecurityEnabled) {
    const tok = GetToken(); // returns our dev token in insecure mode
    return parseJwtPayload(tok); // <- decode and return payload JSON
  }
  if (sessionInvalidated) return null;
  return keycloakInstance?.tokenParsed ?? null;
};

/**
 * Seconds until the current access token's `exp`, or null when there is no
 * expiry constraint to enforce (security disabled, no token, no exp claim).
 *
 * Why: `ensureFreshToken` resolves false on refresh failure/timeout instead of
 * rejecting, so callers about to start long-running work (an SSE agent turn)
 * need to know whether the token they are left with is nearly dead — starting
 * a turn with seconds of validity fails mid-stream with no recovery path.
 * Applies keycloak-js's `timeSkew` so a drifting client clock does not report
 * a dead token as alive (or vice versa), matching how its own
 * `isTokenExpired` compares. Still intended for floor checks rather than exact
 * scheduling — the skew estimate is refreshed only when a token is received.
 */
const GetTokenSecondsLeft = (): number | null => {
  if (!isSecurityEnabled) return null; // dev token: intentionally long-lived
  // Session ENDED (keycloak-js clearToken(), e.g. after a refresh HTTP 400, or
  // the app itself deliberately logging out via clearPersistedToken): there is
  // no live token to trust. Report it DEAD (0), not unconstrained (null) —
  // callers use null as "no floor to enforce", and the turn preflight would
  // otherwise proceed on a resurrected or stale token.
  // `sessionInvalidated` ALONE — no `!tokenParsed` conjunct — distinguishes
  // "session died" from "not logged in yet" (app bootstrap, reload with
  // check-sso in flight): the flag defaults to false and is never set true
  // until a real session actually ends, so bootstrap never trips it. A
  // `!tokenParsed` conjunct used to sit here to guard that same distinction,
  // but it was never needed for it and instead opened a hole: a refresh that
  // settles after logout resurrects keycloakInstance.tokenParsed in memory
  // (keycloak-js's setToken() runs synchronously before our epoch check even
  // sees the response), which made `!tokenParsed` false and suppressed the
  // dead-session report for an already-invalidated session.
  if (sessionInvalidated) return 0;
  const exp = GetTokenParsed()?.exp;
  if (typeof exp !== "number") return null;
  // `timeSkew` cancels client-clock drift exactly as keycloak-js's own
  // `isTokenExpired` does; without it a client running minutes fast reports a
  // negative remaining life for a token the server still considers valid.
  //
  // A NULL skew is not zero skew — it is keycloak-js declaring the answer
  // undeterminable (it only sets the field once a token arrives with a local
  // timestamp, and its own isTokenExpired bails out in that window). Defaulting
  // to 0 there turned a fast client clock into a large negative and hard-refused
  // every turn with "expires in 0s" for a bearer the server still accepts, so
  // report "no floor to enforce" instead and let the refresh decide.
  // A NULL skew is keycloak-js declaring the answer undeterminable (it sets the
  // field only once a token arrives with a local timestamp). Neither `?? 0` nor
  // `null` is right: the first turns a fast client clock into a large negative,
  // the second reads to callers as "no floor to enforce" — and keycloak-js
  // itself treats this state as EXPIRED (`isTokenExpired` returns true when
  // timeSkew == null). Report it DEAD so the caller's fail-closed floor fires.
  const skew = keycloakInstance?.timeSkew;
  if (typeof skew !== "number") return 0;
  return exp - Date.now() / 1000 + skew;
};

export interface KeycloakRealmConfig {
  url: string;
  realm: string;
  clientId: string;
}

/**
 * The realm/client coordinates `createKeycloakInstance` already resolved,
 * exposed for callers that need to talk to Keycloak directly (outside the
 * normal login/refresh flow) — e.g. the admin self-test's "log in as another
 * account" diagnostic, which needs the token endpoint URL to perform its own
 * short-lived password-grant login.
 *
 * `null` in insecure/dev-token mode: there is no real Keycloak to target.
 */
const GetKeycloakRealmConfig = (): KeycloakRealmConfig | null => {
  if (!isSecurityEnabled || !keycloakInstance) return null;
  const { authServerUrl, realm, clientId } = keycloakInstance as unknown as {
    authServerUrl?: string;
    realm?: string;
    clientId?: string;
  };
  if (!authServerUrl || !realm || !clientId) return null;
  return { url: authServerUrl.endsWith("/") ? authServerUrl : `${authServerUrl}/`, realm, clientId };
};

export const KeyCloakService = {
  CallLogin: Login,
  CallLogout: Logout,
  GetUserName,
  GetUserId,
  GetUserFullName,
  GetUserGivenName,
  GetUserMail,
  GetToken,
  GetRealmRoles,
  GetUserRoles,
  GetTokenParsed,
  GetTokenSecondsLeft,
  ensureFreshToken,
  GetRefreshToken,
  GetKeycloakRealmConfig,
};
