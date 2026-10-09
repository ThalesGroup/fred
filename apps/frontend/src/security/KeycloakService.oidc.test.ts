// @vitest-environment happy-dom
// Copyright Thales 2026
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

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import uidVector from "../../../../validation/fixtures/oidc_uid_vector.json";
import { v5 } from "uuid";
import { ErrorResponse } from "oidc-client-ts";

const state = vi.hoisted(() => ({
  settings: null as Record<string, unknown> | null,
  user: null as any,
  signinRedirect: vi.fn(async () => {}),
  signinRedirectCallback: vi.fn(async () => null as any),
  signinSilent: vi.fn(async () => null as any),
  signoutRedirect: vi.fn(async () => {}),
  signoutRedirectCallback: vi.fn(async () => {}),
  removeUser: vi.fn(async () => {}),
}));

vi.mock("oidc-client-ts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("oidc-client-ts")>()),
  UserManager: class {
    events = { addAccessTokenExpiring: vi.fn(), addUserLoaded: vi.fn(), addUserUnloaded: vi.fn() };
    constructor(settings: Record<string, unknown>) {
      state.settings = settings;
    }
    getUser = async () => state.user;
    storeUser = async (user: unknown) => {
      state.user = user;
    };
    signinRedirect = state.signinRedirect;
    signinRedirectCallback = state.signinRedirectCallback;
    signinSilent = state.signinSilent;
    signoutRedirect = state.signoutRedirect;
    signoutRedirectCallback = state.signoutRedirectCallback;
    removeUser = state.removeUser;
  },
}));

function token(claims: Record<string, unknown>): string {
  return `header.${btoa(JSON.stringify(claims)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_")}.signature`;
}

function user(claims: Record<string, unknown>, seconds = 300) {
  return {
    access_token: token({ exp: Math.floor(Date.now() / 1000) + seconds, ...claims }),
    refresh_token: "refresh",
    expires_in: seconds,
    expired: false,
  };
}

const genericOptions = {
  provider: "oidc" as const,
  scope: "api://fred-api/access_as_user",
  uid_claim: "oid",
  roles_claim: ["roles"],
};

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  state.settings = null;
  state.user = null;
  window.history.replaceState({}, "", "/");
  vi.stubGlobal("localStorage", { setItem: vi.fn(), getItem: vi.fn(), removeItem: vi.fn() });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

it("keeps legacy Keycloak configuration usable without an offline-access grant", async () => {
  const { createKeycloakInstance } = await import("./KeycloakService");
  createKeycloakInstance("https://identity.example/realms/app", "app");
  expect(state.settings).toMatchObject({ scope: "openid profile", disablePKCE: false });
});

describe.each(["keycloak", "oidc"] as const)("%s browser authentication", (provider) => {
  const options = { ...genericOptions, provider };
  it("constructs a PKCE OIDC client with the API scope and no Keycloak realm parser", async () => {
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant/v2.0/", "ui", options);
    expect(state.settings).toMatchObject({
      authority: "https://identity.example/tenant/v2.0",
      client_id: "ui",
      response_type: "code",
      disablePKCE: false,
      scope:
        provider === "keycloak"
          ? "openid profile api://fred-api/access_as_user"
          : "openid profile offline_access api://fred-api/access_as_user",
    });
    if (provider === "oidc") expect(KeyCloakService.GetKeycloakRealmConfig()).toBeNull();
  });

  it("uses the API access token and configured identity/roles after a login callback", async () => {
    const claims = { oid: "91e9b9d4-3ee3-4f8a-af93-33c9c7bf52a0", roles: ["admin"], preferred_username: "alice" };
    const callbackUser = user(claims);
    state.signinRedirectCallback.mockResolvedValue(callbackUser);
    window.history.replaceState({}, "", "/?code=dummy&state=dummy");
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant/v2.0", "ui", options);
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    expect(KeyCloakService.GetToken()).toBe(callbackUser.access_token);
    expect(KeyCloakService.GetUserId()).toBe(claims.oid);
    expect(KeyCloakService.GetUserRoles()).toEqual(["admin"]);
    expect(KeyCloakService.GetUserName()).toBe("alice");
    expect(window.location.search).toBe("");
  });

  it("derives the same UUIDv5 as the Python validator for a non-UUID subject", async () => {
    state.user = user({ sub: uidVector.value, roles: ["reader"] });
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance(uidVector.issuer + "/", "ui", { provider, roles_claim: ["roles"] });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    expect(KeyCloakService.GetUserId()).toBe(provider === "oidc" ? uidVector.expected_uuid : uidVector.value);
    expect(KeyCloakService.GetUserRoles()).toEqual(["reader"]);
  });

  it("keeps a UUID string accepted by Python without deriving a new id", async () => {
    const uid = "91E9B9D43EE34F8AAF9333C9C7BF52A0";
    state.user = user({ sub: uid });
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    expect(KeyCloakService.GetUserId()).toBe(uid);
  });

  it("restores a valid session after reload without redirecting", async () => {
    const restored = user({ sub: "person", roles: ["viewer"] });
    state.user = restored;
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider, roles_claim: ["roles"] });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    expect(state.signinRedirect).not.toHaveBeenCalled();
    expect(KeyCloakService.GetToken()).toBe(restored.access_token);
  });

  it("redirects to the provider when no valid session exists", async () => {
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(state.signinRedirect).toHaveBeenCalledOnce());
    expect(authenticated).not.toHaveBeenCalled();
  });

  it("renews a short-lived API token without changing the user id", async () => {
    const original = user({ sub: "person", roles: ["reader"] }, 5);
    const renewed = user({ sub: "person", roles: ["reader"] }, 300);
    state.user = original;
    state.signinSilent.mockResolvedValue(renewed);
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    await expect(KeyCloakService.ensureFreshToken(30)).resolves.toBe(true);
    expect(state.signinSilent).toHaveBeenCalledOnce();
    expect(KeyCloakService.GetToken()).toBe(renewed.access_token);
    expect(KeyCloakService.GetUserId()).toBe(
      provider === "oidc" ? v5("https://identity.example/tenant#person", v5.URL) : "person",
    );
  });

  it("reads a nested roles claim from the access token", async () => {
    state.user = user({ sub: "person", access: { roles: ["admin"] } });
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", {
      provider,
      roles_claim: ["access", "roles"],
    });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    expect(KeyCloakService.GetUserRoles()).toEqual(["admin"]);
  });

  it("processes the provider logout callback before attempting a new sign-in", async () => {
    window.history.replaceState({}, "", "/?state=logout-state");
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider });
    KeyCloakService.CallLogin(vi.fn());
    await vi.waitFor(() => expect(state.signinRedirect).toHaveBeenCalledOnce());
    expect(state.signoutRedirectCallback).toHaveBeenCalledOnce();
    expect(window.location.search).toBe("");
  });

  it("reports a transient silent renewal failure without replacing the bearer", async () => {
    const original = user({ sub: "person" }, 5);
    state.user = original;
    state.signinSilent.mockRejectedValue(new Error("provider unavailable"));
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    await expect(KeyCloakService.ensureFreshToken(30)).resolves.toBe(false);
    expect(KeyCloakService.GetToken()).toBe(original.access_token);
  });

  it.each([
    "invalid_grant",
    "login_required",
    "interaction_required",
    "consent_required",
    "account_selection_required",
  ])("clears facade credentials after a definitive %s renewal refusal", async (error) => {
    state.user = user({ sub: "person", roles: ["reader"] }, 5);
    state.signinSilent.mockRejectedValue(new ErrorResponse({ error }));
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", options);
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());

    await expect(KeyCloakService.ensureFreshToken(30)).resolves.toBe(false);
    expect(KeyCloakService.GetToken()).toBeNull();
    expect(KeyCloakService.GetRefreshToken()).toBeNull();
    expect(KeyCloakService.GetUserRoles()).toEqual([]);
    expect(state.removeUser).toHaveBeenCalledOnce();
    expect(state.signoutRedirect).not.toHaveBeenCalled();
  });

  it("refreshes the access token and never republishes a late refresh after logout", async () => {
    state.user = user({ sub: "person" }, 5);
    let settleRefresh!: (value: any) => void;
    state.signinSilent.mockImplementation(
      () =>
        new Promise((resolve) => {
          settleRefresh = resolve;
        }),
    );
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    const refreshing = KeyCloakService.ensureFreshToken(30);
    await vi.waitFor(() => expect(state.signinSilent).toHaveBeenCalledOnce());
    KeyCloakService.CallLogout();
    settleRefresh(user({ sub: "person" }, 300));
    await expect(refreshing).resolves.toBe(false);
    expect(KeyCloakService.GetToken()).toBeNull();
    expect(state.signoutRedirect).toHaveBeenCalledOnce();
  });

  it("preserves Keycloak realm configuration and default claims", async () => {
    state.user = user({ sub: "91e9b9d4-3ee3-4f8a-af93-33c9c7bf52a0", resource_access: { app: { roles: ["reader"] } } });
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("http://localhost:8080/realms/app", "app");
    KeyCloakService.CallLogin(vi.fn());
    await vi.waitFor(() => expect(KeyCloakService.GetToken()).not.toBeNull());
    expect(KeyCloakService.GetKeycloakRealmConfig()).toEqual({
      url: "http://localhost:8080/",
      realm: "app",
      clientId: "app",
    });
    expect(KeyCloakService.GetUserRoles()).toEqual(["reader"]);
  });

  it("bounds a hung refresh and never publishes its late response", async () => {
    state.user = user({ sub: "person" }, 5);
    let settle!: (value: any) => void;
    state.signinSilent.mockImplementation(
      () =>
        new Promise((resolve) => {
          settle = resolve;
        }),
    );
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    vi.useFakeTimers();
    const refresh = KeyCloakService.ensureFreshToken(30);
    await vi.advanceTimersByTimeAsync(8001);
    await expect(refresh).resolves.toBe(false);
    const oldToken = KeyCloakService.GetToken();
    settle(user({ sub: "other" }, 300));
    await vi.advanceTimersByTimeAsync(0);
    expect(KeyCloakService.GetToken()).toBe(oldToken);
    vi.useRealTimers();
  });

  it("coalesces renewal while checking each caller's required headroom", async () => {
    state.user = user({ sub: "person" }, 5);
    let settle!: (value: any) => void;
    state.signinSilent.mockImplementation(
      () =>
        new Promise((resolve) => {
          settle = resolve;
        }),
    );
    const { createKeycloakInstance, KeyCloakService } = await import("./KeycloakService");
    createKeycloakInstance("https://identity.example/tenant", "ui", { provider });
    const authenticated = vi.fn();
    KeyCloakService.CallLogin(authenticated);
    await vi.waitFor(() => expect(authenticated).toHaveBeenCalledOnce());
    const strict = KeyCloakService.ensureFreshToken(120);
    const ordinary = KeyCloakService.ensureFreshToken(30);
    const forced = KeyCloakService.ensureFreshToken(0);
    settle(user({ sub: "person" }, 60));
    await expect(strict).resolves.toBe(false);
    await expect(ordinary).resolves.toBe(true);
    await expect(forced).resolves.toBe(true);
    expect(state.signinSilent).toHaveBeenCalledOnce();
  });
});
