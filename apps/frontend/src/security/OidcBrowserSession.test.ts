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

import { ErrorResponse, User } from "oidc-client-ts";
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

function newSession(): OidcBrowserSession {
  const session = new OidcBrowserSession("https://identity.example", "ui", undefined, window.location.origin + "/");
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

describe("OIDC sign-in redirect keeps the requested page", () => {
  it("sends the current path, query and hash as url_state", async () => {
    window.history.replaceState({}, "", "/help?topic=agents#tools");
    const session = newSession();
    const redirect = vi.spyOn(session.manager, "signinRedirect").mockResolvedValue();

    await session.login(vi.fn());
    expect(redirect).toHaveBeenCalledWith({ url_state: "/help?topic=agents#tools" });
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
