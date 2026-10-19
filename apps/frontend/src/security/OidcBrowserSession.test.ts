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

import { ErrorResponse, OidcClient, User } from "oidc-client-ts";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApplicationRequest } from "../rework/features/applications/applicationRequest";
import { OidcBrowserSession } from "./OidcBrowserSession";

const sessions: OidcBrowserSession[] = [];

function person(seconds = 300, subject = "person", url_state?: string): User {
  const now = Math.floor(Date.now() / 1000);
  const profile = { iss: "https://identity.example", aud: "ui", sub: subject, iat: now, exp: now + seconds };
  const payload = btoa(JSON.stringify(profile)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return new User({
    access_token: `header.${payload}.signature`,
    refresh_token: "synthetic-refresh",
    token_type: "Bearer",
    expires_at: now + seconds,
    profile,
    url_state,
  });
}

function newSession(provider: "keycloak" | "oidc" = "oidc"): OidcBrowserSession {
  const session = new OidcBrowserSession(
    "https://identity.example",
    "ui",
    undefined,
    window.location.origin + "/",
    provider,
  );
  sessions.push(session);
  return session;
}

async function restoredSession(original = person()): Promise<OidcBrowserSession> {
  const session = newSession();
  await session.manager.storeUser(original);
  const authenticated = vi.fn();
  await session.login(authenticated);
  expect(authenticated).toHaveBeenCalledOnce();
  return session;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  window.sessionStorage.clear();
});

afterEach(async () => {
  vi.restoreAllMocks();
  for (const session of sessions.splice(0)) await session.manager.removeUser();
  vi.useRealTimers();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("OIDC renewal with real user storage", () => {
  it("keeps queue identity through access-token expiry and renewal, then clears it on logout", async () => {
    const session = await restoredSession();
    const identity = session.sessionIdentity("sub");
    expect(identity).toBe(JSON.stringify(["https://identity.example", "person"]));
    vi.spyOn(Date, "now").mockReturnValue(Date.now() + 301_000);
    expect(session.token).toBeNull();
    expect(session.tokenParsed).toBeNull();
    expect(session.sessionIdentity("sub")).toBe(identity);
    vi.spyOn(session.manager, "signinSilent").mockResolvedValue(person());
    expect(await session.ensureFreshToken(0)).toBe(true);
    expect(session.sessionIdentity("sub")).toBe(identity);
    vi.spyOn(session.manager, "signoutRedirect").mockResolvedValue();
    await session.logout();
    expect(session.sessionIdentity("sub")).toBeNull();
  });
  it.each([
    "invalid_grant",
    "login_required",
    "interaction_required",
    "consent_required",
    "account_selection_required",
  ])("removes the live and stored session after %s without provider logout", async (error) => {
    const session = await restoredSession();
    vi.spyOn(session.manager, "signinSilent").mockRejectedValue(new ErrorResponse({ error }));
    const logout = vi.spyOn(session.manager, "signoutRedirect").mockResolvedValue();

    await expect(session.ensureFreshToken(0)).resolves.toBe(false);
    expect(session.token).toBeNull();
    expect(session.refreshToken).toBeNull();
    expect(session.tokenParsed).toBeNull();
    expect(session.tokenSecondsLeft).toBe(0);
    expect(await session.manager.getUser()).toBeNull();
    expect(logout).not.toHaveBeenCalled();

    const reloaded = newSession();
    const redirect = vi.spyOn(reloaded.manager, "signinRedirect").mockResolvedValue();
    const authenticated = vi.fn();
    await reloaded.login(authenticated);
    expect(authenticated).not.toHaveBeenCalled();
    expect(redirect).toHaveBeenCalledOnce();
  });

  it.each([
    new TypeError("Failed to fetch"),
    new ErrorResponse({ error: "server_error" }),
    new ErrorResponse({ error: "temporarily_unavailable" }),
    new Error("invalid_grant in an unstructured diagnostic"),
  ])("keeps the unexpired session and allows retry after %s", async (error) => {
    const original = person();
    const session = await restoredSession(original);
    const renewed = person(600);
    const silent = vi
      .spyOn(session.manager, "signinSilent")
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce(renewed);

    await expect(session.ensureFreshToken(0)).resolves.toBe(false);
    expect(session.token).toBe(original.access_token);
    expect((await session.manager.getUser())?.access_token).toBe(original.access_token);
    await expect(session.ensureFreshToken(0)).resolves.toBe(true);
    expect(session.token).toBe(renewed.access_token);
    expect(silent).toHaveBeenCalledTimes(2);
  });

  it("revokes live tokens immediately and waits for one stored-user cleanup for concurrent callers", async () => {
    const session = await restoredSession();
    vi.spyOn(session.manager, "signinSilent").mockRejectedValue(new ErrorResponse({ error: "invalid_grant" }));
    const cleanup = deferred<void>();
    const removeUser = session.manager.removeUser.bind(session.manager);
    const removal = vi.spyOn(session.manager, "removeUser").mockImplementation(async () => {
      await cleanup.promise;
      await removeUser();
    });
    const first = session.ensureFreshToken(0);
    const second = session.ensureFreshToken(0);
    const settled = vi.fn();
    void first.then(settled);
    void second.then(settled);
    await vi.waitFor(() => expect(removal).toHaveBeenCalledOnce());

    expect(session.token).toBeNull();
    expect(session.refreshToken).toBeNull();
    expect(settled).not.toHaveBeenCalled();
    cleanup.resolve();
    expect(await Promise.all([first, second])).toEqual([false, false]);
    expect(await session.manager.getUser()).toBeNull();
  });

  it("keeps current-session tokens invalidated when stored-user cleanup throws", async () => {
    const session = await restoredSession();
    const silent = vi
      .spyOn(session.manager, "signinSilent")
      .mockRejectedValue(new ErrorResponse({ error: "invalid_grant" }));
    vi.spyOn(session.manager, "removeUser").mockRejectedValue(new Error("storage unavailable"));

    await expect(session.ensureFreshToken(0)).resolves.toBe(false);
    expect(session.token).toBeNull();
    expect(session.refreshToken).toBeNull();
    expect(session.tokenParsed).toBeNull();
    await expect(session.ensureFreshToken(30)).resolves.toBe(false);
    expect(silent).toHaveBeenCalledOnce();
  });

  it("keeps a transiently failed bearer hidden once it expires", async () => {
    vi.useFakeTimers();
    const session = await restoredSession(person());
    vi.spyOn(session.manager, "signinSilent").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(session.ensureFreshToken(0)).resolves.toBe(false);

    await vi.advanceTimersByTimeAsync(301_000);
    expect(session.token).toBeNull();
    expect(session.tokenParsed).toBeNull();
  });

  it("allows retry after timeout and ignores a stale terminal rejection", async () => {
    vi.useFakeTimers();
    const original = person();
    const session = await restoredSession(original);
    const late = deferred<User>();
    const renewed = person(600, "new-generation");
    vi.spyOn(session.manager, "signinSilent").mockReturnValueOnce(late.promise).mockResolvedValueOnce(renewed);
    const first = session.ensureFreshToken(0);
    await vi.advanceTimersByTimeAsync(8_001);
    await expect(first).resolves.toBe(false);
    expect(session.token).toBe(original.access_token);
    await expect(session.ensureFreshToken(0)).resolves.toBe(true);

    late.reject(new ErrorResponse({ error: "invalid_grant" }));
    await vi.advanceTimersByTimeAsync(0);
    expect(session.token).toBe(renewed.access_token);
  });

  it("cannot publish a redirect callback that finishes after a terminal refresh refusal", async () => {
    const session = await restoredSession();
    const callback = deferred<User>();
    vi.spyOn(session.manager, "signinRedirectCallback").mockImplementation(async () => {
      const user = await callback.promise;
      await session.manager.storeUser(user);
      return user;
    });
    window.history.replaceState({}, "", "/?code=synthetic&state=synthetic");
    const authenticated = vi.fn();
    const login = session.login(authenticated);
    vi.spyOn(session.manager, "signinSilent").mockRejectedValue(new ErrorResponse({ error: "invalid_grant" }));
    await expect(session.ensureFreshToken(0)).resolves.toBe(false);

    callback.resolve(person(600));
    await login;
    expect(authenticated).not.toHaveBeenCalled();
    expect(session.token).toBeNull();
    expect(await session.manager.getUser()).toBeNull();
  });

  it("restores the newer live and stored user after an older refresh writes a late result", async () => {
    vi.useFakeTimers();
    const session = await restoredSession();
    const late = deferred<User>();
    const renewed = person(600, "accepted-generation");
    vi.spyOn(session.manager, "signinSilent")
      .mockImplementationOnce(async () => {
        const stale = await late.promise;
        await session.manager.storeUser(stale);
        await session.manager.events.load(stale);
        return stale;
      })
      .mockResolvedValueOnce(renewed);
    const first = session.ensureFreshToken(0);
    await vi.advanceTimersByTimeAsync(8_001);
    await expect(first).resolves.toBe(false);
    await expect(session.ensureFreshToken(0)).resolves.toBe(true);

    late.resolve(person(900, "discarded-generation"));
    await vi.advanceTimersByTimeAsync(0);
    expect(session.token).toBe(renewed.access_token);
    expect((await session.manager.getUser())?.access_token).toBe(renewed.access_token);
  });

  it("removes an older successful renewal that arrives after a newer terminal refusal", async () => {
    vi.useFakeTimers();
    const session = await restoredSession();
    const late = deferred<User>();
    vi.spyOn(session.manager, "signinSilent")
      .mockImplementationOnce(async () => {
        const stale = await late.promise;
        await session.manager.storeUser(stale);
        await session.manager.events.load(stale);
        return stale;
      })
      .mockRejectedValueOnce(new ErrorResponse({ error: "invalid_grant" }));
    const first = session.ensureFreshToken(0);
    await vi.advanceTimersByTimeAsync(8_001);
    await expect(first).resolves.toBe(false);
    await expect(session.ensureFreshToken(0)).resolves.toBe(false);

    late.resolve(person(600));
    await vi.advanceTimersByTimeAsync(0);
    expect(session.token).toBeNull();
    expect(session.refreshToken).toBeNull();
    expect(await session.manager.getUser()).toBeNull();
  });

  it("keeps the accepted user's proactive renewal timer when old and current results arrive together", async () => {
    vi.useFakeTimers();
    const session = await restoredSession();
    const late = deferred<User>();
    const current = deferred<User>();
    const renewed = person(600, "accepted-generation");
    const deliver = async (response: Promise<User>) => {
      const user = await response;
      await session.manager.storeUser(user);
      await session.manager.events.load(user);
      return user;
    };
    const silent = vi
      .spyOn(session.manager, "signinSilent")
      .mockImplementationOnce(() => deliver(late.promise))
      .mockImplementationOnce(() => deliver(current.promise))
      .mockRejectedValue(new TypeError("Failed to fetch"));
    const first = session.ensureFreshToken(0);
    await vi.advanceTimersByTimeAsync(8_001);
    await expect(first).resolves.toBe(false);
    const second = session.ensureFreshToken(0);

    late.resolve(person(900, "discarded-generation"));
    current.resolve(renewed);
    await expect(second).resolves.toBe(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(session.token).toBe(renewed.access_token);
    expect(silent).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(538_000);
    expect(silent).toHaveBeenCalledTimes(3);
    expect(session.token).toBe(renewed.access_token);
  });

  it("does not send the refused bearer through an application request", async () => {
    const session = await restoredSession(person(20));
    vi.spyOn(session.manager, "signinSilent").mockRejectedValue(new ErrorResponse({ error: "invalid_grant" }));
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(null, { status: 401 }));
    const logout = vi.fn();
    const request = createApplicationRequest("sample", "team", {
      fetch,
      ensureFreshToken: (minValidity) => session.ensureFreshToken(minValidity),
      getToken: () => session.token,
      logout,
    });

    await request("resource");
    expect(fetch).toHaveBeenCalledOnce();
    const headers = fetch.mock.calls[0][1]?.headers as Headers;
    expect(headers.has("authorization")).toBe(false);
    expect(logout).toHaveBeenCalledOnce();
  });
});

it("preserves a Free enrollment route through the OIDC round trip", async () => {
  const target = "/fred/join/opaque-link";
  window.history.replaceState({}, "", target);
  const session = newSession();
  const signin = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
  await session.login(vi.fn());
  expect(signin).toHaveBeenCalledWith({ state: target });
  window.history.replaceState({}, "", "/?code=callback&state=opaque-state");
  const signedIn = person();
  Object.defineProperty(signedIn, "state", { value: target });
  vi.spyOn(session.manager, "signinRedirectCallback").mockResolvedValue(signedIn);
  const authenticated = vi.fn();
  await session.login(authenticated);
  expect(window.location.pathname).toBe(target);
  expect(authenticated).toHaveBeenCalledOnce();
});

describe("OIDC sign-in redirect keeps the requested page", () => {
  it("stores the current path, query and hash in local state", async () => {
    window.history.replaceState({}, "", "/help?topic=agents#tools");
    const session = newSession();
    const redirect = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();

    await session.login(vi.fn());
    expect(redirect).toHaveBeenCalledWith({ state: "/help?topic=agents#tools" });
  });

  it("returns to url_state after the callback, or to the root without it", async () => {
    for (const [urlState, expected] of [
      ["/help?topic=agents#tools", "/help?topic=agents#tools"],
      [undefined, "/"],
    ] as const) {
      const session = newSession();
      const user = person(600, "person", urlState);
      vi.spyOn(session.manager, "signinRedirectCallback").mockResolvedValue(user);
      window.history.replaceState({}, "", "/?code=synthetic&state=synthetic");
      const authenticated = vi.fn();

      await session.login(authenticated);
      expect(authenticated).toHaveBeenCalledOnce();
      expect(window.location.pathname + window.location.search + window.location.hash).toBe(expected);
    }
  });
});

it("rejects external callback destinations", async () => {
  for (const destination of ["//example.org/", "https://example.org/"]) {
    const session = newSession();
    vi.spyOn(session.manager, "signinRedirectCallback").mockResolvedValue(person(600, "person", destination));
    window.history.replaceState({}, "", "/?code=synthetic&state=synthetic");
    await session.login(vi.fn());
    expect(window.location.pathname).toBe("/");
  }
});

describe("explicit local Keycloak login", () => {
  it.each(["keycloak", "oidc"] as const)("creates a one-time PKCE request with provider %s", async (provider) => {
    const capability = "synthetic-capability-token".padEnd(43, "x");
    const target = `/fred/join/${capability}?source=invitation#terms`;
    window.history.replaceState({ preserved: true }, "", target.replace("#", "&keycloak-login=true#"));
    const session = newSession(provider);
    const signin = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
    const authenticated = vi.fn();

    await session.login(authenticated);

    expect(authenticated).not.toHaveBeenCalled();
    expect(signin).toHaveBeenCalledExactlyOnceWith({
      state: target,
      prompt: "login",
      extraQueryParams: { kc_idp_hint: "" },
    });
    expect(window.location.pathname + window.location.search + window.location.hash).toBe(target);
    expect(window.history.state).toEqual({ preserved: true });

    const client = new OidcClient({
      ...session.manager.settings,
      metadata: {
        issuer: "https://identity.example",
        authorization_endpoint: "https://identity.example/authorize",
        token_endpoint: "https://identity.example/token",
      },
    });
    const request = await client.createSigninRequest(signin.mock.calls[0][0]);
    const params = new URL(request.url).searchParams;
    expect(params.has("kc_idp_hint")).toBe(true);
    expect(params.get("kc_idp_hint")).toBe("");
    expect(params.get("prompt")).toBe("login");
    expect(params.get("response_type")).toBe("code");
    expect(params.get("code_challenge_method")).toBe("S256");
    expect(params.get("code_challenge")).toBeTruthy();
    expect(params.get("state")).toBe(request.state.id);
    expect(params.get("scope")).toBe(provider === "keycloak" ? "openid profile" : "openid profile offline_access");
    expect(request.state.data).toBe(target);
    expect(decodeURIComponent(request.url)).not.toContain(capability);
    expect(request.url).not.toContain("keycloak-login");
  });

  it.each(["keycloak", "oidc"] as const)(
    "replaces a cached session without provider logout with %s",
    async (provider) => {
      const session = newSession(provider);
      await session.manager.storeUser(person());
      await session.login(vi.fn());
      expect(session.token).not.toBeNull();
      window.history.replaceState({}, "", "/help?keycloak-login=true#tools");
      const signin = vi.spyOn(session.manager, "signinRedirect").mockImplementation(async () => {
        expect(session.token).toBeNull();
        expect(session.refreshToken).toBeNull();
        expect(session.tokenParsed).toBeNull();
        expect(await session.manager.getUser()).toBeNull();
      });
      const silent = vi.spyOn(session.manager, "signinSilent");
      const logout = vi.spyOn(session.manager, "signoutRedirect");
      const authenticated = vi.fn();

      await session.login(authenticated);

      expect(signin).toHaveBeenCalledOnce();
      expect(authenticated).not.toHaveBeenCalled();
      expect(silent).not.toHaveBeenCalled();
      expect(logout).not.toHaveBeenCalled();
    },
  );

  it("returns to the cleaned deep link and restores the new account on reload", async () => {
    window.history.replaceState({}, "", "/help?topic=agents&keycloak-login=true#tools");
    const outgoing = newSession();
    const signin = vi.spyOn(outgoing.manager, "signinRedirect").mockResolvedValue();
    await outgoing.login(vi.fn());
    const target = signin.mock.calls[0][0]?.state;
    const user = person(600, "new-person");
    Object.defineProperty(user, "state", { value: target });

    // A top-level OIDC round trip creates a new browser session instance.
    window.history.replaceState({}, "", "/?code=callback&state=opaque-state");
    const incoming = newSession();
    vi.spyOn(incoming.manager, "signinRedirectCallback").mockImplementation(async () => {
      await incoming.manager.storeUser(user);
      return user;
    });
    const authenticated = vi.fn();
    await incoming.login(authenticated);
    expect(authenticated).toHaveBeenCalledOnce();
    expect(incoming.tokenParsed?.sub).toBe("new-person");
    expect(window.location.pathname + window.location.search + window.location.hash).toBe("/help?topic=agents#tools");

    const reloaded = newSession();
    const redirect = vi.spyOn(reloaded.manager, "signinRedirect").mockResolvedValue();
    await reloaded.login(authenticated);
    expect(redirect).not.toHaveBeenCalled();
    expect(reloaded.tokenParsed?.sub).toBe("new-person");
    expect(authenticated).toHaveBeenCalledTimes(2);
  });

  it.each(["", "?keycloak-login=false", "?keycloak-login=", "?keycloak-login=True"])(
    "preserves ordinary sign-in without exact opt-in: %s",
    async (search) => {
      window.history.replaceState({}, "", `/help${search}#tools`);
      const session = newSession();
      const signin = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
      await session.login(vi.fn());
      expect(signin).toHaveBeenCalledExactlyOnceWith({ state: `/help${search}#tools` });
      await session.manager.storeUser(person());
      const authenticated = vi.fn();
      await session.login(authenticated);
      expect(authenticated).toHaveBeenCalledOnce();
      expect(signin).toHaveBeenCalledOnce();
    },
  );

  it("processes a success callback before the opt-in flag", async () => {
    window.history.replaceState({}, "", "/?code=callback&state=opaque-state&keycloak-login=true");
    const session = newSession();
    const callback = vi
      .spyOn(session.manager, "signinRedirectCallback")
      .mockResolvedValue(person(600, "new-person", "/help"));
    const redirect = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
    const authenticated = vi.fn();
    await session.login(authenticated);
    expect(callback).toHaveBeenCalledOnce();
    expect(redirect).not.toHaveBeenCalled();
    expect(authenticated).toHaveBeenCalledOnce();
    expect(window.location.pathname).toBe("/help");
  });

  it("preserves callback errors instead of starting another explicit login", async () => {
    window.history.replaceState({}, "", "/?error=access_denied&state=opaque-state&keycloak-login=true");
    const session = newSession();
    const error = new ErrorResponse({ error: "access_denied" });
    vi.spyOn(session.manager, "signinRedirectCallback").mockRejectedValue(error);
    const redirect = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
    await expect(session.login(vi.fn())).rejects.toBe(error);
    expect(redirect).not.toHaveBeenCalled();
  });

  it("rejects a late renewal from the previous account", async () => {
    const session = await restoredSession();
    const late = deferred<User>();
    const stale = person(600, "previous-person");
    vi.spyOn(session.manager, "signinSilent").mockImplementation(async () => {
      const user = await late.promise;
      await session.manager.storeUser(user);
      return user;
    });
    const refresh = session.ensureFreshToken(0);
    window.history.replaceState({}, "", "/?keycloak-login=true");
    vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
    await session.login(vi.fn());
    late.resolve(stale);
    await expect(refresh).resolves.toBe(false);
    expect(session.token).toBeNull();
    expect(await session.manager.getUser()).toBeNull();
  });

  it("does not let an older renewal timeout cancel the explicit login", async () => {
    vi.useFakeTimers();
    const session = await restoredSession();
    vi.spyOn(session.manager, "signinSilent").mockReturnValue(new Promise(() => undefined));
    const refresh = session.ensureFreshToken(0);
    const cleanup = deferred<void>();
    const removeUser = session.manager.removeUser.bind(session.manager);
    vi.spyOn(session.manager, "removeUser").mockImplementationOnce(async () => {
      await cleanup.promise;
      await removeUser();
    });
    window.history.replaceState({}, "", "/?keycloak-login=true");
    const redirect = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
    const login = session.login(vi.fn());
    await vi.advanceTimersByTimeAsync(8_000);
    await expect(refresh).resolves.toBe(false);
    cleanup.resolve();
    await login;
    expect(redirect).toHaveBeenCalledOnce();
    expect(session.token).toBeNull();
  });

  it("rejects a callback that started before the explicit request", async () => {
    const session = newSession();
    const late = deferred<User>();
    vi.spyOn(session.manager, "signinRedirectCallback").mockImplementation(async () => {
      const user = await late.promise;
      await session.manager.storeUser(user);
      return user;
    });
    window.history.replaceState({}, "", "/?code=callback&state=opaque-state");
    const authenticated = vi.fn();
    const callback = session.login(authenticated);
    window.history.replaceState({}, "", "/?keycloak-login=true");
    vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
    await session.login(authenticated);
    late.resolve(person(600, "previous-person"));
    await callback;
    expect(authenticated).not.toHaveBeenCalled();
    expect(session.token).toBeNull();
    expect(await session.manager.getUser()).toBeNull();
  });

  it("keeps the previous bearer unavailable if stored-user removal fails", async () => {
    const session = await restoredSession();
    const error = new Error("storage unavailable");
    vi.spyOn(session.manager, "removeUser").mockRejectedValueOnce(error);
    const redirect = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
    window.history.replaceState({}, "", "/?keycloak-login=true");
    await expect(session.login(vi.fn())).rejects.toBe(error);
    expect(session.token).toBeNull();
    expect(session.refreshToken).toBeNull();
    expect(redirect).not.toHaveBeenCalled();
    expect(window.location.search).toBe("");
  });
});

it("keeps invitation capabilities out of the provider authorization state", async () => {
  const capability = "synthetic-capability-token".padEnd(43, "x");
  const target = `/fred/join/${capability}?source=invitation#terms`;
  window.history.replaceState({}, "", target);
  const session = newSession();
  const signin = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();
  await session.login(vi.fn());
  const client = new OidcClient({
    authority: "https://identity.example",
    client_id: "ui",
    redirect_uri: "https://fred.example/",
    response_type: "code",
    scope: "openid",
    metadata: {
      issuer: "https://identity.example",
      authorization_endpoint: "https://identity.example/authorize",
      token_endpoint: "https://identity.example/token",
    },
  });
  const request = await client.createSigninRequest(signin.mock.calls[0][0]);
  const authorizationState = new URL(request.url).searchParams.get("state");
  expect(request.state.data).toBe(target);
  expect(authorizationState).toBe(request.state.id);
  expect(decodeURIComponent(request.url)).not.toContain(capability);
  expect(request.state.url_state).toBeUndefined();
});
