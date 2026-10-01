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

import { v5 } from "uuid";
import { OidcBrowserSession } from "./OidcBrowserSession";

let isSecurityEnabled = false;
let oidcSession: OidcBrowserSession | null = null;
let identityProvider: "keycloak" | "oidc" = "keycloak";
let identityIssuer = "";
let identityClientId = "";
let uidClaim = "sub";
let rolesClaim: string[] | null = null;

export interface BrowserAuthOptions {
  provider?: "keycloak" | "oidc";
  scope?: string | null;
  user_directory?: "keycloak" | "local";
  uid_claim?: string;
  roles_claim?: string[] | null;
  redirect_uri?: string;
}

let sessionInvalidated = false;
let authEpoch = 0;
const clearPersistedToken = () => {
  sessionInvalidated = true;
  authEpoch += 1;
  localStorage.removeItem("keycloak_token");
};

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

export function createKeycloakInstance(
  keycloak_url: string,
  keycloak_client_id: string,
  options: BrowserAuthOptions = {},
) {
  if (!oidcSession) {
    isSecurityEnabled = true;
    identityProvider = options.provider ?? "keycloak";
    identityIssuer = keycloak_url.replace(/\/+$/, "");
    identityClientId = keycloak_client_id;
    uidClaim = options.uid_claim ?? "sub";
    rolesClaim = options.roles_claim ?? null;
    localStorage.removeItem("keycloak_token");
    oidcSession = new OidcBrowserSession(
      identityIssuer,
      identityClientId,
      options.scope ?? undefined,
      options.redirect_uri ?? `${window.location.origin}/`,
    );
  }
  return oidcSession.manager;
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

  void oidcSession!
    .login(() => {
      sessionInvalidated = false;
      onAuthenticatedCallback();
    })
    .catch((error) => console.error("[OIDC] login error:", error));
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

  // Preserve oidc-client-ts callback state in sessionStorage.
  clearPersistedToken();
  void oidcSession?.logout().catch((error) => console.error("[OIDC] logout error:", error));
};

/**
 * Ensure token validity (minValidity seconds).
 * Returns true if token is valid or refreshed, false if refresh failed.
 *
 * In insecure mode this is trivially true — the token is local and
 * intentionally long-lived to avoid surprising dev UX during demos.
 */
export async function ensureFreshToken(minValidity = 30): Promise<boolean> {
  if (!isSecurityEnabled) return true;
  if (!oidcSession) return false;
  const epochAtStart = authEpoch;
  const fresh = await oidcSession.ensureFreshToken(minValidity);
  return fresh && epochAtStart === authEpoch && !sessionInvalidated;
}

// ========================= Getters =========================

const claimPath = (payload: Record<string, any>, path: string[]): unknown =>
  path.reduce<unknown>(
    (value, key) => (value && typeof value === "object" ? (value as Record<string, unknown>)[key] : null),
    payload,
  );

const GetRealmRoles = (): string[] => {
  if (!isSecurityEnabled) return ["admin"];
  const value = GetTokenParsed()?.realm_access?.roles;
  return Array.isArray(value) ? value : [];
};

const GetUserRoles = (): string[] => {
  if (!isSecurityEnabled) return ["admin"];
  const payload = GetTokenParsed();
  if (!payload) return [];
  const value = rolesClaim ? claimPath(payload, rolesClaim) : payload.resource_access?.[identityClientId]?.roles;
  return Array.isArray(value) ? [...value] : [];
};

const GetUserName = (): string | null => {
  if (!isSecurityEnabled) return DEV_USERNAME;
  return GetTokenParsed()?.preferred_username || null;
};

const GetUserFullName = (): string | null => {
  if (!isSecurityEnabled) return DEV_USERNAME;
  return GetTokenParsed()?.name || null;
};

const GetUserGivenName = (): string | null => {
  if (!isSecurityEnabled) return DEV_USERNAME;
  return GetTokenParsed()?.given_name || null;
};

const GetUserMail = (): string | null => {
  if (!isSecurityEnabled) return `${DEV_USERNAME}@localhost`;
  return GetTokenParsed()?.email || null;
};

// Match Python uuid.UUID() acceptance, including hyphenless and braced UUIDs.
const isPythonUuid = (value: string): boolean =>
  /^[0-9a-fA-F]{32}$/.test(
    value
      .replace(/^urn:uuid:/i, "")
      .replace(/^\{|\}$/g, "")
      .replace(/-/g, ""),
  );

const GetUserId = (): string | null => {
  if (!isSecurityEnabled) return DEV_USERNAME;
  const value = GetTokenParsed()?.[uidClaim];
  if (typeof value !== "string" || !value) return null;
  return identityProvider === "oidc" && !isPythonUuid(value) ? v5(`${identityIssuer}#${value}`, v5.URL) : value;
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
  if (sessionInvalidated) return null;
  return oidcSession?.token ?? null;
};
const GetRefreshToken = (): string | null => {
  if (!isSecurityEnabled) {
    // In dev mode, there is no real refresh token
    return "dev-refresh-token-dummy";
  }
  if (sessionInvalidated) return null;
  return oidcSession?.refreshToken ?? null;
};
const GetTokenParsed = (): any => {
  if (!isSecurityEnabled) {
    const tok = GetToken(); // returns our dev token in insecure mode
    return parseJwtPayload(tok); // <- decode and return payload JSON
  }
  if (sessionInvalidated) return null;
  return oidcSession?.tokenParsed ?? null;
};

/** Remaining access-token lifetime, or zero after explicit logout. */
const GetTokenSecondsLeft = (): number | null => {
  if (!isSecurityEnabled) return null;
  if (sessionInvalidated) return 0;
  return oidcSession?.tokenSecondsLeft ?? null;
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
  if (!isSecurityEnabled || identityProvider !== "keycloak") return null;
  const { url, realm } = parseKeycloakUrl(identityIssuer);
  return { url, realm, clientId: identityClientId };
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
