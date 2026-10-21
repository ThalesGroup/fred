// @vitest-environment happy-dom
// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { useRoleCampaignRun } from "./useRoleCampaignRun";
import { CAMPAIGN_JOURNAL_KEY, type CampaignDeps } from "./scenarios/roleCampaignScenario";
import type { StepReport } from "./types";
const h = vi.hoisted(() => ({
  fresh: true,
  userId: "root-user",
  token: "admin-old",
  available: true,
  scenario: vi.fn(),
  recovery: vi.fn(),
  fetch: vi.fn(),
  login: vi.fn(),
  realm: { url: "https://idp.example/", realm: "test", clientId: "web" } as object | null,
  steps: [] as StepReport[],
}));
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: {
    ensureFreshToken: async () => h.fresh,
    GetUserId: () => h.userId,
    GetToken: () => h.token,
    GetKeycloakRealmConfig: () => h.realm,
  },
}));
vi.mock("./useAuthzProbeRun", () => ({ authedFetch: (...args: unknown[]) => h.fetch(...args), authzProbeDeps: {} }));
vi.mock("./keycloakDirectGrant", () => ({ loginWithPassword: (...args: unknown[]) => h.login(...args) }));
vi.mock("./useScenarioRun", () => ({
  useRunner: () => ({
    steps: h.steps,
    isRunning: false,
    run: async (body: (report: (step: StepReport) => void, signal: AbortSignal) => Promise<void>) =>
      body((step) => h.steps.push(step), new AbortController().signal),
  }),
}));
vi.mock("./scenarios/roleCampaignScenario", async (original) => ({
  ...(await original<typeof import("./scenarios/roleCampaignScenario")>()),
  roleCampaignScenario: (...args: unknown[]) => h.scenario(...args),
  recoverRoleCampaign: (...args: unknown[]) => h.recovery(...args),
}));
let hook: ReturnType<typeof useRoleCampaignRun>, root: Root, container: HTMLDivElement;
function Harness() {
  hook = useRoleCampaignRun();
  return null;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  h.steps.length = 0;
  h.fresh = true;
  h.userId = "root-user";
  h.token = "admin-old";
  h.available = true;
  h.realm = { url: "https://idp.example/", realm: "test", clientId: "web" };
  h.fetch.mockResolvedValue({ status: 200, body: null });
  h.login.mockResolvedValue("target-secret");
  Object.defineProperty(navigator, "locks", {
    configurable: true,
    value: {
      request: async (_name: string, _options: unknown, callback: (lock: unknown) => Promise<void>) =>
        callback(h.available ? {} : null),
    },
  });
  container = document.createElement("div");
  root = createRoot(container);
  act(() => root.render(<Harness />));
});
afterEach(() => {
  act(() => root.unmount());
  vi.unstubAllGlobals();
  localStorage.clear();
});
describe("automatic role campaign transport", () => {
  it("normalizes the pasted token and refreshes only admin requests", async () => {
    h.scenario.mockImplementation(async (_admin: string, _target: string, deps: CampaignDeps) => {
      h.token = "admin-fresh";
      await deps.request("/admin", "admin-old");
      await deps.request("/target", "target-secret");
    });
    await act(async () => hook.runForToken(" Bearer target-secret "));
    expect(h.scenario.mock.calls[0].slice(0, 2)).toEqual(["admin-old", "target-secret"]);
    expect(h.fetch.mock.calls).toEqual([
      ["/admin", "admin-fresh", undefined],
      ["/target", "target-secret", undefined],
    ]);
    expect(localStorage.length).toBe(0);
  });
  it("uses direct login only for the Keycloak path", async () => {
    await act(async () => hook.runForProfile("dedicated-user", "password-secret"));
    expect(h.login).toHaveBeenCalledWith(h.realm, "dedicated-user", "password-secret");
    expect(h.scenario.mock.calls[0][1]).toBe("target-secret");
    expect(localStorage.length).toBe(0);
  });
  it("recovers without the second account credential", async () => {
    localStorage.setItem(CAMPAIGN_JOURNAL_KEY, "{}");
    await act(async () => hook.recover());
    expect(h.recovery).toHaveBeenCalled();
    expect(h.login).not.toHaveBeenCalled();
    expect(h.scenario).not.toHaveBeenCalled();
    expect(hook.hasRecovery).toBe(true);
  });
  it.each(["lock", "session", "browser"])("refuses unavailable %s before scenario writes", async (unavailable) => {
    if (unavailable === "lock") h.available = false;
    if (unavailable === "session") h.fresh = false;
    if (unavailable === "browser") Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
    await act(async () => hook.runForToken("target-secret"));
    expect(h.scenario).not.toHaveBeenCalled();
    expect(h.steps.some((s) => s.status === "failed")).toBe(true);
  });
  it("rejects an admin identity change during the run", async () => {
    h.scenario.mockImplementation(async (_admin: string, _target: string, deps: CampaignDeps) => {
      h.userId = "different-user";
      await deps.request("/admin", "admin-old", { method: "POST" });
    });
    await act(async () => hook.runForToken("target-secret"));
    expect(h.fetch).not.toHaveBeenCalled();
    expect(h.steps.some((s) => s.status === "failed")).toBe(true);
  });
  it("shows persisted recovery and does not discard malformed data", async () => {
    localStorage.setItem(CAMPAIGN_JOURNAL_KEY, "malformed");
    h.scenario.mockImplementation(async (_admin: string, _target: string, deps: CampaignDeps) => deps.readJournal());
    await act(async () => hook.runForToken("target-secret"));
    expect(hook.hasRecovery).toBe(true);
    expect(localStorage.getItem(CAMPAIGN_JOURNAL_KEY)).toBe("malformed");
  });
});
