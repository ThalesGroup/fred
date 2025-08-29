// security/KeyCloakService.ts
// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import Keycloak, { KeycloakInstance } from "keycloak-js";

let keycloakInstance: KeycloakInstance | null = null;
let isSecurityEnabled = false;

// single-flight so concurrent calls don’t trigger multiple refreshes
let refreshInFlight: Promise<boolean> | null = null;

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
 */
const Login = (onAuthenticatedCallback: Function) => {
  if (!isSecurityEnabled) {
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
  if (!isSecurityEnabled || !keycloakInstance) return;
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

const GetToken = (): string | null => {
  if (!isSecurityEnabled) return null;
  return keycloakInstance?.token || localStorage.getItem("keycloak_token");
};

const GetTokenParsed = (): any => {
  if (!isSecurityEnabled) return null;
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
