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
import type {
  MarketplaceSettings,
  TeamMarketplaceSettings,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  settings: undefined as MarketplaceSettings | undefined,
  setDefault: vi.fn(),
  setTeam: vi.fn(),
  previewDefault: vi.fn(),
  previewTeam: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMarketplaceSettingsQuery: () => ({ data: h.settings, isLoading: false, isError: false }),
  useSetMarketplaceDefaultMutation: () => [h.setDefault, { isLoading: false }],
  useSetTeamMarketplaceSettingsMutation: () => [h.setTeam, { isLoading: false }],
  useLazyMarketplaceDefaultImpactQuery: () => [h.previewDefault],
  useLazyTeamMarketplaceSettingsImpactQuery: () => [h.previewTeam],
}));

import MarketplacesPage from "./MarketplacesPage";

const resolved = (value: unknown = {}) => ({ unwrap: () => Promise.resolve(value) });

function team(
  over: Partial<TeamMarketplaceSettings> & Pick<TeamMarketplaceSettings, "team_id">,
): TeamMarketplaceSettings {
  return {
    team_name: over.team_id.toUpperCase(),
    agents_publishing_enabled_override: null,
    agents_publish_quota_override: null,
    agents_publishing_enabled: true,
    agents_publish_quota: 5,
    published_count: 0,
    ...over,
  };
}

let container: HTMLDivElement;
let root: Root;

async function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(<MarketplacesPage />);
  });
}

async function click(el: Element | null | undefined) {
  if (!el) throw new Error("element not found");
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

function buttonsIn(scope: ParentNode, label: string): HTMLButtonElement[] {
  return Array.from(scope.querySelectorAll("button")).filter((b) => b.textContent === label);
}

function row(teamId: string): HTMLElement {
  const cell = Array.from(container.querySelectorAll("div")).find((d) => d.textContent === teamId.toUpperCase());
  const found = cell?.closest('[class*="datatable-row"]');
  if (!found) throw new Error(`row ${teamId} not found`);
  return found as HTMLElement;
}

function defaultRow(): HTMLElement {
  const found = container.querySelector('[class*="defaultRow"]');
  if (!found) throw new Error("default row not found");
  return found as HTMLElement;
}

function quotaInput(teamId: string): HTMLInputElement {
  return row(teamId).querySelector("input") as HTMLInputElement;
}

async function typeAndBlur(input: HTMLInputElement, value: string) {
  const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => {
    setValue.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => {
    input.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  });
}

beforeEach(() => {
  h.settings = {
    default: { agents_publishing_enabled: true, agents_publish_quota: 5 },
    teams: [
      team({ team_id: "alpha", published_count: 2 }),
      team({ team_id: "beta", agents_publish_quota_override: 3, agents_publish_quota: 3 }),
      team({ team_id: "gamma", published_count: 4 }),
    ],
  };
  h.setDefault.mockReturnValue(resolved());
  h.setTeam.mockReturnValue(resolved());
  h.previewDefault.mockReturnValue(resolved({ removed_published_agents: 3 }));
  h.previewTeam.mockReturnValue(resolved({ removed_published_agents: 2 }));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
  vi.clearAllMocks();
});

describe("MarketplacesPage", () => {
  it("shows the publication row, every team and its published count", async () => {
    await render();

    expect(defaultRow().textContent).toContain("rework.admin.marketplaces.defaultTitle");
    expect(defaultRow().textContent).toContain("rework.admin.marketplaces.defaultHint");
    expect(container.textContent).toContain("ALPHA");
    expect(row("gamma").textContent).toContain("4");
  });

  it("confirms with the removed agents count before turning a team's switch off, then saves the override", async () => {
    await render();

    await click(buttonsIn(row("alpha"), "rework.admin.marketplaces.choice.disabled")[0]);

    expect(h.previewTeam).toHaveBeenCalledWith({ teamId: "alpha", agentsPublishingEnabled: false });
    expect(h.setTeam).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('rework.admin.marketplaces.offConfirm.agents {"count":2}');

    await click(buttonsIn(document.body, "rework.admin.marketplaces.offConfirm.confirm")[0]);

    expect(h.setTeam).toHaveBeenCalledWith({
      teamId: "alpha",
      setTeamMarketplaceSettingsRequest: { agents_publishing_enabled: false, agents_publish_quota: null },
    });
  });

  it("applies a switch-off directly when it removes no agent", async () => {
    h.previewTeam.mockReturnValue(resolved({ removed_published_agents: 0 }));
    h.previewDefault.mockReturnValue(resolved({ removed_published_agents: 0 }));
    await render();

    await click(buttonsIn(row("alpha"), "rework.admin.marketplaces.choice.disabled")[0]);
    await click(buttonsIn(defaultRow(), "rework.admin.marketplaces.defaultChoice.disabled")[0]);

    expect(buttonsIn(document.body, "rework.admin.marketplaces.offConfirm.confirm")).toHaveLength(0);
    expect(h.setTeam).toHaveBeenCalledWith({
      teamId: "alpha",
      setTeamMarketplaceSettingsRequest: { agents_publishing_enabled: false, agents_publish_quota: null },
    });
    expect(h.setDefault).toHaveBeenCalledWith({
      setAgentsMarketplaceDefaultRequest: { agents_publishing_enabled: false, agents_publish_quota: 5 },
    });
  });

  it("still asks before a switch-off when its impact cannot be previewed", async () => {
    h.previewTeam.mockReturnValue({ unwrap: () => Promise.reject(new Error("boom")) });
    await render();

    await click(buttonsIn(row("alpha"), "rework.admin.marketplaces.choice.disabled")[0]);

    expect(h.setTeam).not.toHaveBeenCalled();
    await click(buttonsIn(document.body, "rework.admin.marketplaces.offConfirm.confirm")[0]);
    expect(h.setTeam).toHaveBeenCalledTimes(1);
  });

  it("saves a switch-on without confirmation", async () => {
    h.settings!.default.agents_publishing_enabled = false;
    h.settings!.teams[0] = team({ team_id: "alpha", agents_publishing_enabled: false });
    await render();

    await click(buttonsIn(row("alpha"), "rework.admin.marketplaces.choice.enabled")[0]);

    expect(h.previewTeam).not.toHaveBeenCalled();
    expect(h.setTeam).toHaveBeenCalledWith({
      teamId: "alpha",
      setTeamMarketplaceSettingsRequest: { agents_publishing_enabled: true, agents_publish_quota: null },
    });
  });

  it("previews a back-to-Default that turns a team off without sending a null switch", async () => {
    h.settings!.default.agents_publishing_enabled = false;
    h.settings!.teams[0] = team({ team_id: "alpha", agents_publishing_enabled_override: true });
    await render();

    await click(buttonsIn(row("alpha"), "rework.admin.marketplaces.choice.default")[0]);

    expect(h.previewTeam).toHaveBeenCalledWith({ teamId: "alpha", agentsPublishingEnabled: undefined });
  });

  it("colours the selected Enabled item success and Disabled error, Default keeps the group colour", async () => {
    h.settings!.teams[1] = team({ team_id: "beta", agents_publishing_enabled_override: true });
    h.settings!.teams[2] = team({ team_id: "gamma", agents_publishing_enabled_override: false });
    await render();

    const selected = (scope: ParentNode) => scope.querySelector('[role="radio"][aria-checked="true"]') as HTMLElement;
    expect(selected(defaultRow()).textContent).toBe("rework.admin.marketplaces.defaultChoice.enabled");
    expect(selected(defaultRow()).dataset.selectedColor).toBe("success");
    expect(buttonsIn(defaultRow(), "rework.admin.marketplaces.defaultChoice.disabled")[0].dataset.selectedColor).toBe(
      "error",
    );
    expect(selected(row("alpha")).hasAttribute("data-selected-color")).toBe(false);
    expect(selected(row("beta")).dataset.selectedColor).toBe("success");
    expect(selected(row("gamma")).dataset.selectedColor).toBe("error");
  });

  it("confirms turning the default switch off with the summed counts", async () => {
    await render();

    await click(buttonsIn(defaultRow(), "rework.admin.marketplaces.defaultChoice.disabled")[0]);

    expect(h.previewDefault).toHaveBeenCalledWith({ agentsPublishingEnabled: false });
    expect(document.body.textContent).toContain('rework.admin.marketplaces.offConfirm.agents {"count":3}');
    await click(buttonsIn(document.body, "rework.admin.marketplaces.offConfirm.cancel")[0]);
    expect(h.setDefault).not.toHaveBeenCalled();
  });

  it("shows Default as text for a following team, an editable quota for a customized one", async () => {
    await render();
    expect(row("alpha").querySelector('[class*="quotaDefault"]')?.textContent).toBe(
      "rework.admin.marketplaces.choice.default",
    );
    expect(quotaInput("alpha")).toBeNull();
    expect(row("beta").querySelector('[class*="quotaDefault"]')).toBeNull();
    expect(quotaInput("beta").disabled).toBe(false);
    expect(quotaInput("beta").value).toBe("3");
  });

  it("customizes a following team's quota only once a value is entered", async () => {
    await render();

    await click(row("alpha").querySelector('[aria-label^="rework.admin.marketplaces.customizeQuotaAria"]'));
    expect(row("alpha").querySelector('[class*="quotaDefault"]')).toBeNull();
    expect(quotaInput("alpha").disabled).toBe(false);
    expect(quotaInput("alpha").value).toBe("5");
    expect(h.setTeam).not.toHaveBeenCalled();

    await typeAndBlur(quotaInput("alpha"), "7");
    expect(h.setTeam).toHaveBeenCalledWith({
      teamId: "alpha",
      setTeamMarketplaceSettingsRequest: { agents_publishing_enabled: null, agents_publish_quota: 7 },
    });
  });

  it("cancels an unsaved customization without saving anything", async () => {
    await render();

    await click(row("alpha").querySelector('[aria-label^="rework.admin.marketplaces.customizeQuotaAria"]'));
    await click(row("alpha").querySelector('[aria-label^="rework.admin.marketplaces.resetQuotaAria"]'));

    expect(quotaInput("alpha")).toBeNull();
    expect(row("alpha").querySelector('[class*="quotaDefault"]')).not.toBeNull();
    expect(h.setTeam).not.toHaveBeenCalled();
  });

  it("puts an overridden quota back to Default with a null override", async () => {
    await render();

    await click(row("beta").querySelector('[aria-label^="rework.admin.marketplaces.resetQuotaAria"]'));

    expect(h.setTeam).toHaveBeenCalledWith({
      teamId: "beta",
      setTeamMarketplaceSettingsRequest: { agents_publishing_enabled: null, agents_publish_quota: null },
    });
    expect(row("alpha").querySelector('[aria-label^="rework.admin.marketplaces.resetQuotaAria"]')).toBeNull();
  });

  it("saves Enter then blur once, and lets the same value retry after a failure", async () => {
    h.setTeam.mockReturnValue({ unwrap: () => Promise.reject(new Error("boom")) });
    await render();
    const input = quotaInput("beta");
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    await act(async () => {
      setValue.call(input, "8");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      input.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    expect(h.setTeam).toHaveBeenCalledOnce();

    await act(async () => {
      input.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    expect(h.setTeam).toHaveBeenCalledTimes(2);
  });

  it("refuses an empty or zero quota instead of saving it", async () => {
    await render();

    for (const value of ["", "0"]) {
      await typeAndBlur(quotaInput("beta"), value);
      expect(row("beta").textContent).toContain("rework.admin.marketplaces.quotaInvalid");
    }
    expect(h.setTeam).not.toHaveBeenCalled();
  });
});
