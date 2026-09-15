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
  // The functional scenario is mocked to a known identity, so the pipeline-run
  // mock can tell the two runs apart: the page now wraps the expiry one.
  functionalScenario: async () => {},
  expiryScenario: async () => {},
  steps: {
    expiry: [{ id: "expiry-turn", title: "EXPIRY_STEP", status: "passed" as const }],
    functional: [{ id: "create-folder", title: "FUNCTIONAL_STEP", status: "passed" as const }],
    authz: [{ id: "bootstrap-flags", title: "AUTHZ_STEP", status: "passed" as const }],
  },
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

vi.mock("../../../../features/pipeline/scenarios/selfTestScenario", () => ({
  selfTestScenario: h.functionalScenario,
}));

vi.mock("../../../../features/pipeline/usePipelineRun", () => ({
  usePipelineRun: (scenario: Scenario) => {
    const isExpiry = scenario !== h.functionalScenario;
    return {
      steps: isExpiry ? h.steps.expiry : h.steps.functional,
      isRunning: isExpiry && h.expiryRunning,
      start: () => {
        if (!isExpiry) return;
        h.expiryStarted += 1;
        void scenario({} as never, () => {}, new AbortController().signal);
      },
    };
  },
}));

vi.mock("../../../../features/pipeline/useAuthzProbeRun", () => ({
  useAuthzProbeRun: () => ({
    steps: h.steps.authz,
    isRunning: false,
    runForMyself: vi.fn(),
    runForProfile: vi.fn(),
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useListUsersQuery: () => ({ data: [{ id: "u-2", username: h.otherAccount }] }),
}));

vi.mock("../../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetUserName: () => h.signedIn,
    GetKeycloakRealmConfig: () => h.realmConfig,
    GetTokenSecondsLeft: () => h.tokenSecondsLeft,
  },
}));

import SelfTestPage from "./SelfTestPage";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.factoryCalls.length = 0;
  h.expiryStarted = 0;
  h.expiryRunning = false;
  h.tokenSecondsLeft = 285;
  h.realmConfig = { url: "https://auth.example/", realm: "test-realm", clientId: "web-app" };
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

    expect(buttonLabelled("rework.selftest.functional.run").disabled).toBe(true);
    expect(buttonLabelled("rework.selftest.authz.runSelf").disabled).toBe(true);
    expect(buttonLabelled("rework.selftest.authz.expiry.run").disabled).toBe(true);
  });

  it("reports into its own panel, beside the authorization probe's", () => {
    expect(container.textContent).toContain("AUTHZ_STEP");
    expect(container.textContent).toContain("EXPIRY_STEP");
    expect(container.textContent).toContain("rework.selftest.authz.expiry.title");
  });

  it("offers nothing of the check on a deployment with no realm", () => {
    // The realm is read once per mount, so this needs a fresh one.
    h.realmConfig = null;
    act(() => root.unmount());
    root = createRoot(container);
    act(() => {
      root.render(<SelfTestPage />);
    });

    expect(container.textContent).not.toContain("rework.selftest.authz.expiry");
    expect(container.textContent).toContain("rework.selftest.authz.testProfile.disabledInsecure");
  });
});
