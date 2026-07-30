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
let updateTokenImpl: () => Promise<boolean>;

vi.mock("keycloak-js", () => ({
  default: class MockKeycloak {
    token = "initial-token";
    onTokenExpired: (() => void) | null = null;
    updateToken() {
      return updateTokenImpl();
    }
  },
}));

describe("ensureFreshToken", () => {
  beforeEach(() => {
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
    updateTokenImpl = () => Promise.resolve(true);
    const { createKeycloakInstance, ensureFreshToken } = await import("./KeycloakService.ts");
    createKeycloakInstance("http://kc/realms/app", "app");

    await expect(ensureFreshToken(30)).resolves.toBe(true);
  });
});
