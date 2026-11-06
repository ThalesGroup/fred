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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CredentialExpiryInput } from "../../../../features/pipeline/scenarios/credentialExpiryScenario";
import { MAX_HOLD_MINUTES, type Scenario } from "../../../../features/pipeline/types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  signedIn: "signed-in-admin",
  otherAccount: "other-account",
  realmConfig: { url: "https://auth.example/", realm: "test-realm", clientId: "web-app" } as {
    url: string;
    realm: string;
    clientId: string;
  } | null,
  provider: "keycloak" as "keycloak" | "oidc" | null,
  pastedTokens: [] as string[],
  teamsError: false,
  campaignRunning: false,
  recoveryNeeded: false,
  campaignCalls: [] as Array<{ username?: string; password?: string; token?: string; recovery?: boolean }>,
  expiryScenario: async () => {},
  steps: {
    expiry: [{ id: "expiry-turn", title: "EXPIRY_STEP", status: "passed" as const }],
    authz: [{ id: "bootstrap-flags", title: "AUTHZ_STEP", status: "passed" as const }],
  },
  familyRunning: false,
  started: [] as string[],
  // Families resolve in order; "knowledge" fails, which must not stop the next.
  families: ["identity", "knowledge", "agents", "authorization"],
  factoryCalls: [] as (CredentialExpiryInput | undefined)[],
  expiryStarted: 0,
  expiryRunning: false,
  tokenSecondsLeft: 285 as number | null,
}));

// `t` echoes its key, plus the interpolated wait where one is passed — that
// figure is what the notice has to quote for the session in hand.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { minutes?: number; maxMinutes?: number }) => {
      const value = opts?.minutes ?? opts?.maxMinutes;
      return value ? `${key}:${value}` : key;
    },
    i18n: { language: "en" },
  }),
}));

// Only the scenario factory is stubbed: the wait rule stays real, so the notice
// is asserted against the very figure the run would size its hold from.
vi.mock("../../../../features/pipeline/scenarios/credentialExpiryScenario", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../../features/pipeline/scenarios/credentialExpiryScenario")>()),
  credentialExpiryScenario: (input?: CredentialExpiryInput) => {
    h.factoryCalls.push(input);
    return h.expiryScenario;
  },
}));

vi.mock("../../../../features/pipeline/usePipelineRun", () => ({
  usePipelineRun: (scenario: Scenario) => ({
    steps: h.steps.expiry,
    isRunning: h.expiryRunning,
    start: async () => {
      h.expiryStarted += 1;
      await scenario({} as never, () => {}, new AbortController().signal);
    },
  }),
}));

vi.mock("../../../../features/pipeline/families", () => ({
  useSelfTestFamilies: () =>
    h.families.map((id) => ({
      id,
      icon: "check_circle",
      run: {
        steps: [
          { id: `${id}-step`, title: `${id.toUpperCase()}_STEP`, status: id === "knowledge" ? "failed" : "passed" },
        ],
        isRunning: h.familyRunning,
        start: async () => {
          h.started.push(id);
          if (id === "knowledge") throw new Error("knowledge family crashed");
        },
      },
    })),
}));

vi.mock("../../../../features/pipeline/useRoleCampaignRun", () => ({
  useRoleCampaignRun: () => ({
    steps: [],
    isRunning: h.campaignRunning,
    hasRecovery: h.recoveryNeeded,
    runForProfile: async (username: string, password: string) => {
      h.campaignCalls.push({ username, password });
    },
    runForToken: async (token: string) => {
      h.campaignCalls.push({ token });
    },
    recover: async () => {
      h.campaignCalls.push({ recovery: true });
    },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useListUsersQuery: () => ({ data: [{ id: "u-2", username: h.otherAccount }] }),
  useListAllTeamsQuery: () => ({
    data: [
      { id: "team-a", name: "Team A" },
      { id: "team-b", name: "Team B" },
      { id: "personal-a", name: "Personal A" },
    ],
    isError: h.teamsError,
  }),
}));

vi.mock("../../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetUserName: () => h.signedIn,
    GetToken: () => "session-token",
    GetKeycloakRealmConfig: () => h.realmConfig,
    GetIdentityProvider: () => h.provider,
    GetTokenSecondsLeft: () => h.tokenSecondsLeft,
  },
}));

import SelfTestPage from "./SelfTestPage";
import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.factoryCalls.length = 0;
  h.expiryStarted = 0;
  h.expiryRunning = false;
  h.familyRunning = false;
  h.started.length = 0;
  h.tokenSecondsLeft = 285;
  h.realmConfig = { url: "https://auth.example/", realm: "test-realm", clientId: "web-app" };
  h.provider = "keycloak";
  h.teamsError = false;
  h.campaignRunning = false;
  h.recoveryNeeded = false;
  h.campaignCalls.length = 0;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<SelfTestPage />);
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function buttonLabelled(key: string): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes(key));
  if (!button) throw new Error(`no button for ${key}`);
  return button;
}

function buttonsLabelled(key: string): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll("button")).filter((b) => b.textContent?.includes(key));
}

function passwordInput(): HTMLInputElement {
  return container.querySelector('input[type="password"]') as HTMLInputElement;
}

function typePassword(value: string): void {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
  act(() => {
    setter.call(passwordInput(), value);
    passwordInput().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

/** The notice is portaled out of the page's own container. */
function dialogButtonLabelled(key: string): HTMLButtonElement {
  const portal = document.querySelector('[data-portal-container="true"]');
  const button = Array.from(portal?.querySelectorAll("button") ?? []).find((b) => b.textContent?.includes(key));
  if (!button) throw new Error(`no dialog button for ${key}`);
  return button;
}

function dialogText(): string {
  return document.querySelector('[data-portal-container="true"]')?.textContent ?? "";
}

function openExpiryWarning(): void {
  act(() => {
    buttonLabelled("rework.selftest.authz.expiry.run").dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true }),
    );
  });
}

function clickDialog(key: string): void {
  act(() => {
    dialogButtonLabelled(key).dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function startExpiryRun(): void {
  openExpiryWarning();
  clickDialog("rework.selftest.authz.expiry.warning.confirm");
}

/** Pick the only listed account in the probe's selector, by keyboard. */
function selectAnotherAccount(): void {
  const trigger = container.querySelector('button[aria-haspopup="listbox"]') as HTMLButtonElement;
  for (const key of ["ArrowDown", "Enter"]) {
    act(() => {
      trigger.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
    });
  }
  expect(trigger.textContent).toContain(h.otherAccount);
}

describe("SelfTestPage credential-expiry check", () => {
  it("starts from SSO without requesting a password", () => {
    expect(passwordInput().value).toBe("");
    expect(buttonLabelled("rework.selftest.authz.expiry.run").disabled).toBe(false);
    startExpiryRun();
    expect(h.expiryStarted).toBe(1);
    expect(h.factoryCalls).toEqual([undefined]);
  });

  it("starts nothing until the wait is accepted, and quotes it from the session in hand", () => {
    openExpiryWarning();

    expect(h.expiryStarted).toBe(0);
    expect(dialogText()).toContain("rework.selftest.authz.expiry.warning.title");
    // 285 s left plus the run's own margin, as minutes.
    expect(dialogText()).toContain("rework.selftest.authz.expiry.warning.message:5");

    clickDialog("rework.selftest.authz.expiry.warning.confirm");
    expect(h.expiryStarted).toBe(1);
    expect(dialogText()).toBe("");
  });

  it("quotes the skip limit from the bound the run enforces", () => {
    expect(container.textContent).toContain(`rework.selftest.authz.expiry.caption:${MAX_HOLD_MINUTES}`);
  });

  it("starts nothing when the notice is dismissed", () => {
    openExpiryWarning();
    clickDialog("common.cancel");

    expect(h.expiryStarted).toBe(0);
    expect(dialogText()).toBe("");
  });

  it("still warns when the session's remaining life is unknown", () => {
    h.tokenSecondsLeft = null;

    openExpiryWarning();

    expect(dialogText()).toContain("rework.selftest.authz.expiry.warning.messageUnknownWait");
    expect(h.expiryStarted).toBe(0);
  });

  it("never passes another profile's credentials into the expiry test", () => {
    selectAnotherAccount();
    typePassword("synthetic password");
    startExpiryRun();
    expect(h.expiryStarted).toBe(1);
    expect(h.factoryCalls).toEqual([undefined]);
    expect(container.textContent).toContain("rework.selftest.authz.expiry.caption");
    expect(container.textContent).not.toContain("-selftest");
  });

  it("locks every other run on the page while it is in flight", () => {
    h.expiryRunning = true;
    act(() => {
      root.render(<SelfTestPage />);
    });

    for (const button of buttonsLabelled("rework.selftest.family.run")) expect(button.disabled).toBe(true);
    expect(buttonLabelled("rework.selftest.page.runAll").disabled).toBe(true);
    expect(buttonLabelled("rework.selftest.page.copyAll").disabled).toBe(true);
    expect(buttonLabelled("rework.selftest.authz.expiry.run").disabled).toBe(true);
  });

  it("reports into its own panel, beside the authorization probe's", () => {
    expect(container.textContent).not.toContain("EXPIRY_STEP");
    act(() => {
      for (const button of container.querySelectorAll<HTMLButtonElement>('[aria-expanded="false"]')) button.click();
    });
    expect(container.textContent).toContain("EXPIRY_STEP");
    expect(container.textContent).toContain("rework.selftest.authz.expiry.title");
  });

  it("is titled by what it proves, in English and French", () => {
    expect(en.rework.selftest.authz.expiry.title).toBe("Agent access after your session expires");
    expect(fr.rework.selftest.authz.expiry.title).toBe("Accès de l'agent après l'expiration de votre session");
  });

  it("offers a token instead of an account/password for OIDC", () => {
    h.provider = "oidc";
    h.realmConfig = null;
    act(() => root.unmount());
    root = createRoot(container);
    act(() => {
      root.render(<SelfTestPage />);
    });

    expect(container.textContent).toContain("rework.selftest.authz.expiry.title");
    expect(container.textContent).toContain("rework.selftest.authz.testProfile.tokenLabel");
    expect(container.textContent).not.toContain("rework.selftest.authz.testProfile.passwordLabel");
    expect(container.textContent).not.toContain("rework.selftest.authz.testProfile.usernameLabel");
    expect(en.rework.selftest.authz.testProfile.tokenCaption).toContain("API access token");
    expect(fr.rework.selftest.authz.testProfile.tokenCaption).toContain("jeton d'accès API");
  });

  it("keeps the account and password form for Keycloak", () => {
    expect(container.textContent).toContain("rework.selftest.authz.testProfile.usernameLabel");
    expect(container.textContent).toContain("rework.selftest.authz.testProfile.passwordLabel");
    expect(container.textContent).not.toContain("rework.selftest.authz.testProfile.tokenLabel");
  });

  it("hides both credential forms when authentication is disabled", () => {
    h.provider = null;
    h.realmConfig = null;
    act(() => root.unmount());
    root = createRoot(container);
    act(() => root.render(<SelfTestPage />));
    expect(container.textContent).not.toContain("rework.selftest.authz.testProfile.title");
  });
});

describe("SelfTestPage families", () => {
  it("renders one section per family, in registry order", () => {
    const order = Array.from(container.querySelectorAll("[data-family]")).map((s) => s.getAttribute("data-family"));
    expect(order).toEqual(h.families);
    expect(order[order.length - 1]).toBe("authorization");
    expect(container.textContent).toContain("rework.selftest.families.knowledge.title");
  });

  it("explains the authorization checks and the separate two-account and expiry runs", () => {
    const authorization = container.querySelector('[data-family="authorization"]');
    expect(authorization?.textContent).toContain("rework.selftest.authz.notice.title");
    expect(authorization?.textContent).toContain("rework.selftest.authz.notice.description");
    expect(container.querySelector('[data-family="agents"]')?.textContent).not.toContain(
      "rework.selftest.authz.notice.title",
    );
    expect(en.rework.selftest.authz.notice.description).toContain("second account");
    expect(en.rework.selftest.authz.notice.description).toContain("Run all");
    expect(fr.rework.selftest.authz.notice.description).toContain("second compte");
    expect(fr.rework.selftest.authz.notice.description).toContain("Tout lancer");
  });

  it("announces how long a full run takes, in English and French", () => {
    expect(container.textContent).toContain("rework.selftest.page.durationTitle");
    expect(en.rework.selftest.page.durationTitle).toBe("A full run takes 5 to 10 minutes");
    expect(fr.rework.selftest.page.durationTitle).toBe("Un run complet prend 5 à 10 minutes");
  });

  it("runs every family in order and keeps going after one fails", async () => {
    await act(async () => {
      buttonLabelled("rework.selftest.page.runAll").dispatchEvent(
        new MouseEvent("click", { bubbles: true, cancelable: true }),
      );
    });
    expect(h.started).toEqual(h.families);
    // The long session-expiry check is never part of Run all.
    expect(h.expiryStarted).toBe(0);
  });

  it("keeps the authorization extras inside the authorization family", () => {
    const authorization = container.querySelector('[data-family="authorization"]');
    expect(authorization?.textContent).toContain("rework.selftest.authz.expiry.title");
    expect(container.querySelector('[data-family="knowledge"]')?.textContent).not.toContain(
      "rework.selftest.authz.expiry.title",
    );
  });

  it("names every family in English and French", () => {
    for (const id of h.families) {
      const key = id as keyof typeof en.rework.selftest.families;
      expect(en.rework.selftest.families[key].title).toBeTruthy();
      expect(fr.rework.selftest.families[key].title).toBeTruthy();
    }
  });
});

describe("automatic role campaign controls", () => {
  it("offers only the automatic second-account campaign, with no expected-role or team selection", () => {
    expect(container.textContent).not.toContain("rework.selftest.authz.roles.comparePlatform");
    expect(container.textContent).not.toContain("rework.selftest.authz.roles.addTeam");
    expect(container.textContent).not.toContain("rework.selftest.authz.testProfile.run");
    expect(container.querySelectorAll('button[aria-haspopup="listbox"]')).toHaveLength(1);
  });

  const runKey = "rework.selftest.authz.campaign.run";
  it("requires credentials and confirmation before changing roles", () => {
    expect(buttonLabelled(runKey).disabled).toBe(true);
    selectAnotherAccount();
    typePassword("dedicated-password");
    act(() => buttonLabelled(runKey).click());
    expect(h.campaignCalls).toEqual([]);
    expect(dialogText()).toContain("rework.selftest.authz.campaign.confirmation");
    clickDialog("rework.selftest.authz.campaign.confirm");
    expect(h.campaignCalls).toEqual([{ username: h.otherAccount, password: "dedicated-password" }]);
    expect(passwordInput().value).toBe("");
  });
  it("does not launch when confirmation is dismissed", () => {
    selectAnotherAccount();
    typePassword("dedicated-password");
    act(() => buttonLabelled(runKey).click());
    clickDialog("common.cancel");
    expect(h.campaignCalls).toEqual([]);
  });
  it("uses the separate Entra token and clears the input on confirmation", () => {
    h.provider = "oidc";
    h.realmConfig = null;
    act(() => root.unmount());
    root = createRoot(container);
    act(() => root.render(<SelfTestPage />));
    typePassword("second-access-token");
    act(() => buttonLabelled(runKey).click());
    clickDialog("rework.selftest.authz.campaign.confirm");
    expect(h.campaignCalls).toEqual([{ token: "second-access-token" }]);
    expect(passwordInput().value).toBe("");
  });
  it("excludes the campaign from Run all", async () => {
    await act(async () => buttonLabelled("rework.selftest.page.runAll").click());
    expect(h.campaignCalls).toEqual([]);
  });
  it("offers recovery and blocks another campaign", () => {
    h.recoveryNeeded = true;
    act(() => root.render(<SelfTestPage />));
    selectAnotherAccount();
    typePassword("dedicated-password");
    expect(buttonLabelled(runKey).disabled).toBe(true);
    expect(container.textContent).toContain("rework.selftest.authz.campaign.recoveryNotice");
    act(() => buttonLabelled("rework.selftest.authz.campaign.recover").click());
    expect(h.campaignCalls).toEqual([{ recovery: true }]);
  });
  it("locks other runs during campaign and recovery", () => {
    h.campaignRunning = true;
    act(() => root.render(<SelfTestPage />));
    expect(buttonLabelled("rework.selftest.page.runAll").disabled).toBe(true);
    expect(buttonLabelled("rework.selftest.authz.expiry.run").disabled).toBe(true);
  });
});
