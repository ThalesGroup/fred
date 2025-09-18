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

// single-flight so concurrent calls don’t trigger multiple refreshes
let refreshInFlight: Promise<boolean> | null = null;

// ---------- Insecure-mode dev token support ----------
// Fred rationale: even when security is off, the frontend + backend contracts
// still expect an Authorization: Bearer <token>. We mint a local, JWT-shaped
// token with "admin" roles so the UI flows (headers, auth guards, role checks)
// behave exactly like production — just without real verification.
const DEV_TOKEN_STORAGE_KEY = "dev_admin_token";

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
    name: "Administrator",
    preferred_username: "admin",
    given_name: "Admin",
    family_name: "User",
    email: "admin@mail.com",
    sub: "admin", // stable ID used by UI and logs in dev
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
  let tok = localStorage.getItem(DEV_TOKEN_STORAGE_KEY);
  if (tok) return tok;
  tok = buildDevAdminToken();
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
      localStorage.removeItem("keycloak_token");
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
    localStorage.removeItem("keycloak_token");
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

  // If a refresh is already running, await it
  if (refreshInFlight) return refreshInFlight;

  // Use KC.updateToken (it refreshes only if needed)
  refreshInFlight = keycloakInstance
    .updateToken(minValidity)
    .then((refreshed) => {
      if (refreshed) {
        localStorage.setItem("keycloak_token", keycloakInstance!.token || "");
      }
      return true;
    })
    .catch((err) => {
      console.warn("[Keycloak] token refresh failed:", err);
      return false;
    })
    .finally(() => {
      refreshInFlight = null;
    });

  return refreshInFlight;
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
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return "admin";
  return (keycloakInstance.tokenParsed as any).preferred_username || null;
};

const GetUserFullName = (): string | null => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return "Administrator";
  return (keycloakInstance.tokenParsed as any).name || null;
};

const GetUserMail = (): string | null => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return "admin@mail.com";
  return (keycloakInstance.tokenParsed as any).email || null;
};

const GetUserId = (): string | null => {
  if (!isSecurityEnabled || !keycloakInstance?.tokenParsed) return "admin";
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
  return keycloakInstance?.token || localStorage.getItem("keycloak_token");
};

const GetTokenParsed = (): any => {
  if (!isSecurityEnabled) {
    const tok = GetToken();                // returns our dev token in insecure mode
    return parseJwtPayload(tok);           // <- decode and return payload JSON
  }
  return keycloakInstance?.tokenParsed ?? null;
};


export const KeyCloakService = {
  CallLogin: Login,
  CallLogout: Logout,
  GetUserName,
  GetUserId,
  GetUserFullName,
  GetUserMail,
  GetToken,
  GetRealmRoles,
  GetUserRoles,
  GetTokenParsed,
  ensureFreshToken,
};
