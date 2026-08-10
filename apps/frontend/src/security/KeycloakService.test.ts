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

// Regression: keycloak-js's updateToken() has no built-in timeout. A dropped
// connection or unresponsive Keycloak used to leave `ensureFreshToken`'s
// promise pending forever — and since it's a shared single-flight promise,
// every other in-flight or future authenticated request in the app awaited
// that same never-settling promise, wedging the whole app after one hung
// refresh. `ensureFreshToken` now races the refresh against a timeout.
let updateTokenImpl: (minValidity: number) => Promise<boolean>;
// Seconds of life the mock token reports. Drives isTokenExpired the way
// keycloak-js does, so a test can model "already fresh enough" vs "needs a
// real refresh" per caller threshold.
let secondsLeft: number;
let updateTokenCalls: number[];
// Models keycloak-js's clearToken() state: after a refresh rejected with
// HTTP 400 the library drops token/tokenParsed/refreshToken itself, and
// isTokenExpired starts THROWING (a bare string) instead of answering.
let sessionCleared: boolean;

vi.mock("keycloak-js", () => ({
  default: class MockKeycloak {
    // keycloak-js leaves this NULL until a token arrives with a local
    // timestamp, and treats that state as "expiry undeterminable".
    timeSkew: number | null = 0;
    onTokenExpired: (() => void) | null = null;
    onAuthLogout: (() => void) | null = null;
    get token() {
      return sessionCleared ? undefined : "initial-token";
    }
    get tokenParsed() {
      if (sessionCleared) return undefined;
      return { exp: Math.floor(Date.now() / 1000) + secondsLeft };
    }
    // Mirrors keycloak.js: exp - now + timeSkew < minValidity — and the
    // undocumented sharp edge: `throw 'Not authenticated'` (a string, not an
    // Error) once the session state is gone (keycloak.mjs:609-610).
    isTokenExpired(minValidity = 0) {
      if (sessionCleared) throw "Not authenticated";
      return secondsLeft < minValidity;
    }
    updateToken(minValidity: number) {
      updateTokenCalls.push(minValidity);
      // keycloak.mjs:636 — `minValidity = minValidity || 5`. Modelling this is
      // the whole point: isTokenExpired does NOT apply the same floor (0 is
      // falsy there), and the mock omitting it is why a real regression on the
      // ensureFreshToken(0) path went undetected.
      const effective = minValidity || 5;
      // keycloak.mjs:639 — `if (minValidity == -1) { refreshToken = true; }`.
      // The library's ONLY force path: refresh regardless of how the token
      // looks. Without modelling it, a test cannot tell a genuinely forced
      // refresh from one that silently short-circuited.
      if (effective === -1) return updateTokenImpl(effective);
      // keycloak.js:1233-1239 — no HTTP at all when the threshold is already
      // met; it resolves `false` ("not refreshed") without contacting Keycloak.
      if (!this.isTokenExpired(effective)) return Promise.resolve(false);
      return updateTokenImpl(effective);
    }
    logout() {
      sessionCleared = true;
      this.onAuthLogout?.();
      return Promise.resolve();
    }
    // Mirrors keycloak.js clearToken(): drop live state, notify onAuthLogout.
    clearToken() {
      sessionCleared = true;
      this.onAuthLogout?.();
    }
  },
}));

describe("ensureFreshToken", () => {
  beforeEach(() => {
    secondsLeft = 0; // default: token needs refreshing at any threshold
    sessionCleared = false;
    updateTokenCalls = [];
    vi.useFakeTimers();
    // Node 18+'s own experimental global `localStorage` shadows happy-dom's,
    // and throws without a --localstorage-file flag — stub it directly.
    vi.stubGlobal("localStorage", { setItem: vi.fn(), getItem: vi.fn(), removeItem: vi.fn() });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("resolves to false instead of hanging forever when the refresh never settles", async () => {
    updateTokenImpl = () => new Promise(() => {}); // never resolves — simulates a hung refresh
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    const resultPromise = ensureFreshToken(30);
    await vi.advanceTimersByTimeAsync(8_000);

    await expect(resultPromise).resolves.toBe(false);
  });

  it("resolves to true once the refresh succeeds, well before the timeout", async () => {
    // A successful refresh must actually extend the token — `ensureFreshToken`
    // now reports whether the resulting lifetime satisfies the caller, not
    // merely that updateToken settled.
    updateTokenImpl = () => {
      secondsLeft = 300;
      return Promise.resolve(true);
    };
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    await expect(ensureFreshToken(30)).resolves.toBe(true);
  });

  it("does not contact Keycloak when the token already has the requested headroom", async () => {
    secondsLeft = 200;
    updateTokenImpl = () => Promise.resolve(true);
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    await expect(ensureFreshToken(120)).resolves.toBe(true);
    expect(updateTokenCalls).toEqual([]);
  });

  it("a stronger caller does not inherit a weaker no-op refresh", async () => {
    // The band that matters: 30 <= remaining < 120. A background
    // ensureFreshToken(30) is a NO-OP (its threshold is already met) yet still
    // settles true. A turn preflight needing 120 s must not conclude "fresh"
    // from it — that silently launches a turn on a ~40 s token, the mid-stream
    // 401 the preflight exists to prevent.
    secondsLeft = 40;
    let release: (v: boolean) => void = () => {};
    updateTokenImpl = () =>
      new Promise<boolean>((r) => {
        release = r;
      });

    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    const weak = ensureFreshToken(30); // no-op: 40 >= 30
    const strong = ensureFreshToken(120); // must issue a REAL refresh

    await expect(weak).resolves.toBe(true);
    expect(updateTokenCalls).toContain(120);

    secondsLeft = 300; // the real refresh returns a full-lifetime token
    release(true);
    await expect(strong).resolves.toBe(true);
  });

  it("coalesces callers that share a threshold into one refresh", async () => {
    let release: (v: boolean) => void = () => {};
    updateTokenImpl = () =>
      new Promise<boolean>((r) => {
        release = r;
      });
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    const a = ensureFreshToken(120);
    const b = ensureFreshToken(120);
    secondsLeft = 300; // the refresh delivers a full-lifetime token
    release(true);

    await expect(Promise.all([a, b])).resolves.toEqual([true, true]);
    expect(updateTokenCalls).toEqual([120]);
  });

  // ── Session cleared by keycloak-js (refresh HTTP 400 → clearToken) ────────
  //
  // These pin the fail-closed contract for a Keycloak-invalidated session:
  // ensureFreshToken keeps its boolean contract (dynamicBaseQuery awaits it
  // with no catch — a rejection would abort requests before their 401→logout
  // recovery), GetTokenSecondsLeft reports the token DEAD rather than
  // unconstrained (the turn preflight treats null as "no floor to enforce"),
  // and the persisted localStorage copy cannot resurrect the ended session.

  it("resolves false — never rejects — once keycloak-js has cleared the session", async () => {
    sessionCleared = true;
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    await expect(ensureFreshToken(30)).resolves.toBe(false);
    // No doomed exchange is attempted: there is no refresh token left to send.
    expect(updateTokenCalls).toEqual([]);
  });

  it("GetTokenSecondsLeft reports 0 — dead, not unconstrained — once the session ENDS", async () => {
    secondsLeft = 200;
    const mod = await import("./KeycloakService.ts");
    const kc = mod.createKeycloakInstance("http://kc/realms/app", "app");

    // The mock floors `exp` to whole seconds, so up to 1 s is shaved off.
    const live = mod.KeyCloakService.GetTokenSecondsLeft();
    expect(live).toBeGreaterThan(198);
    expect(live).toBeLessThanOrEqual(200);

    // The session must end the way keycloak-js ends it — clearToken() firing
    // onAuthLogout — not by merely losing the token: "no token" alone is also
    // the pre-init state, which the next test pins as NOT dead.
    (kc as unknown as { clearToken: () => void }).clearToken();
    expect(mod.KeyCloakService.GetTokenSecondsLeft()).toBe(0);
  });

  it.each([3, 20, 200])("ensureFreshToken(0) forces a real refresh with %ds left", async (left) => {
    // The 401-recovery path in dynamicBaseQuery calls ensureFreshToken(0) to
    // force a refresh before retrying. The token's apparent lifetime is exactly
    // what it must not trust — the 401 already proved the server disagrees
    // (clock skew against admission's leeway=0, an SSO logout elsewhere, realm
    // key rotation). Any headroom short-circuit here replays the same bearer,
    // takes a second 401, and the base query logs the user out. Note 200s: a
    // 5s-floor coercion would still have short-circuited that one.
    secondsLeft = left;
    updateTokenImpl = () => {
      secondsLeft = 300;
      return Promise.resolve(true);
    };
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    await expect(ensureFreshToken(0)).resolves.toBe(true);
    expect(updateTokenCalls).toEqual([-1]);
  });

  it("resolves false when the refresh cannot deliver the requested headroom", async () => {
    // A realm whose access-token lifespan is below the turn preflight's 120s:
    // updateToken succeeds, but the token it returns is still too short-lived.
    // Reporting true there made the headroom guarantee unkeepable AND skipped
    // the hard floor, which is only consulted when this resolves false.
    secondsLeft = 10;
    updateTokenImpl = () => {
      secondsLeft = 60; // realm lifespan, still < 120
      return Promise.resolve(true);
    };
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    await expect(ensureFreshToken(120)).resolves.toBe(false);
    expect(updateTokenCalls).toEqual([120]);
  });

  it("GetTokenSecondsLeft reports DEAD when keycloak-js cannot determine skew", async () => {
    // timeSkew === null is keycloak-js declaring expiry undeterminable — and
    // its own isTokenExpired answers `true` (expired) in that state. Returning
    // null here read to callers as "no floor to enforce", so the turn preflight
    // sailed past its hard floor on a token the library considers dead. `?? 0`
    // was equally wrong in the other direction (a fast clock became a large
    // negative), so report it dead and let the caller fail closed.
    secondsLeft = 200;
    const mod = await import("./KeycloakService.ts");
    const kc = mod.createKeycloakInstance("http://kc/realms/app", "app");
    (kc as unknown as { timeSkew: number | null }).timeSkew = null;

    expect(mod.KeyCloakService.GetTokenSecondsLeft()).toBe(0);
  });

  it("GetTokenSecondsLeft stays null — unconstrained, not dead — before any session existed", async () => {
    // Bootstrap: the instance exists but init() has not completed, so there is
    // no tokenParsed and no session ever died. Reporting 0 here would
    // hard-refuse turns with "expires in 0s" during app startup.
    sessionCleared = true; // models "no live token yet", with NO clearToken()
    const mod = await import("./KeycloakService.ts");
    mod.createKeycloakInstance("http://kc/realms/app", "app");

    expect(mod.KeyCloakService.GetTokenSecondsLeft()).toBeNull();
  });

  it("drops the persisted token when keycloak-js ends the session, so GetToken cannot resurrect it", async () => {
    const removed: string[] = [];
    vi.stubGlobal("localStorage", {
      setItem: vi.fn(),
      getItem: vi.fn(() => "stale-persisted-token"),
      removeItem: vi.fn((k: string) => removed.push(k)),
    });
    const mod = await import("./KeycloakService.ts");
    const kc = mod.createKeycloakInstance("http://kc/realms/app", "app");

    // Before: live token wins, no removal.
    expect(mod.KeyCloakService.GetToken()).toBe("initial-token");

    // keycloak-js itself ends the session (refresh HTTP 400 → clearToken).
    (kc as unknown as { clearToken: () => void }).clearToken();

    expect(removed).toContain("keycloak_token");
    // The live token is gone AND the persisted copy was removed — an
    // unexpired-but-orphaned bearer must not keep authenticating requests
    // the backend would accept via offline JWT validation.
  });
});

describe("ensureFreshToken — concurrency", () => {
  beforeEach(() => {
    secondsLeft = 0;
    sessionCleared = false;
    updateTokenCalls = [];
    vi.useFakeTimers();
    vi.stubGlobal("localStorage", { setItem: vi.fn(), getItem: vi.fn(), removeItem: vi.fn() });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("a forced caller never piggybacks on an in-flight headroom refresh", async () => {
    // Force was ranked at the 5s floor, which every chain already satisfies, so
    // a post-401 caller silently reused whatever was in flight and never
    // contacted Keycloak — then inherited that chain's verdict and got logged
    // out. Force must do its own work.
    secondsLeft = 10;
    const releases: ((v: boolean) => void)[] = [];
    updateTokenImpl = () =>
      new Promise<boolean>((r) => {
        releases.push(r);
      });
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    const preflight = ensureFreshToken(120); // installs a chain
    const forcedCall = ensureFreshToken(0); // must NOT reuse it

    // The forced caller issued its OWN updateToken with the force sentinel
    // rather than piggy-backing. This asserts two CALLS: keycloak-js coalesces
    // concurrent calls through its module-level refreshQueue, so in production
    // the second may resolve off the first's XHR — what matters is that the
    // force sentinel reached the library at all.
    expect(updateTokenCalls).toEqual([120, -1]);
    secondsLeft = 300;
    releases.forEach((r) => r(true));
    await expect(forcedCall).resolves.toBe(true);
    await expect(preflight).resolves.toBe(true);
  });

  it("a short-lived realm fails the preflight without failing the forced caller", async () => {
    // One chain, two callers with different needs. Baking the headroom verdict
    // into the shared chain made a SUCCESSFUL refresh report failure to the
    // post-401 caller, which then logged the user out mid-session.
    secondsLeft = 10;
    const releases: ((v: boolean) => void)[] = [];
    updateTokenImpl = () =>
      new Promise<boolean>((r) => {
        releases.push(r);
      });
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    // BOTH started before either settles. Awaiting between them would let the
    // first chain's `finally` null `refreshInFlight`, so the second installed a
    // fresh chain and the shared-verdict bug could never appear — which is
    // exactly why the earlier version of this test was vacuous.
    const preflight = ensureFreshToken(120);
    const forcedCall = ensureFreshToken(0);
    secondsLeft = 60; // realm lifespan: satisfies the forced caller, not the 120s one
    releases.forEach((r) => r(true));

    await expect(preflight).resolves.toBe(false); // truthfully short
    await expect(forcedCall).resolves.toBe(true); // the refresh DID work
  });

  it("a refresh settling after logout does not re-persist the bearer", async () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { setItem, getItem: vi.fn(), removeItem: vi.fn() });
    let release: (v: boolean) => void = () => {};
    updateTokenImpl = () =>
      new Promise<boolean>((r) => {
        release = r;
      });
    const mod = await import("./KeycloakService.ts");
    mod.createKeycloakInstance("http://kc/realms/app", "app");

    const inFlight = mod.ensureFreshToken(30);
    mod.KeyCloakService.CallLogout(); // clears the persisted copy, bumps the epoch
    setItem.mockClear();
    secondsLeft = 300;
    release(true);
    await expect(inFlight).resolves.toBe(false);

    expect(setItem).not.toHaveBeenCalledWith("keycloak_token", expect.anything());
  });
});
