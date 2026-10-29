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

// The Knowledge Bases tab still renders the legacy enablement catalog.
// `t` is mocked to echo its key (plus any interpolated count), so we assert on
// which key each state uses and on the enabled-team count it renders.

import { renderToStaticMarkup } from "react-dom/server";
import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  applicationsEnabled: false,
  list: { data: undefined, isLoading: false, isError: false } as {
    data?: { items?: CapabilityEnablementItem[] };
    isLoading: boolean;
    isError: boolean;
  },
  // Every key `t` was asked for during the last render. Needed for hints that
  // live in a `Tooltip`: its panel is portaled and only mounts once hovered, so
  // the rendered markup never contains the hint text — the key request is the
  // only observable signal that the hint was wired up.
  tKeys: [] as string[],
}));
const translate = vi.hoisted(
  () => (key: string, opts?: { defaultValue?: string; count?: number; content?: string }) => {
    h.tKeys.push(key);
    const interpolated = opts?.count ?? opts?.content;
    return opts?.defaultValue ?? (interpolated === undefined ? key : `${key}:${interpolated}`);
  },
);

// `t` echoes its key, but appends an interpolated `count` (or the composed
// `content` of the "All (…)" wrapper) when one is passed — those are the values
// under test for the enabled-teams column, and a bare key echo would hide
// whether the right number ever reached the label.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: translate,
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationAgentsQuery: () => ({ currentData: undefined, isLoading: false, isError: false }),
  useSetOrganizationAgentDefaultMutation: () => [() => ({ unwrap: async () => ({}) }), { isLoading: false }],
  useSetOrganizationCapabilityDefaultMutation: () => [vi.fn(), { isLoading: false }],
  useOrganizationCapabilitiesQuery: () => ({ data: undefined }),
  useLazyOrganizationCapabilityRevokeImpactQuery: () => [vi.fn(), { data: undefined, isFetching: false }],
}));

vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useAdminCapabilitiesQuery: () => h.list,
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));
vi.mock("@hooks/useFrontendFeatureFlag.ts", () => ({
  useFrontendFeatureFlag: () => ({ enabled: h.applicationsEnabled, isLoading: false }),
}));

// The offers panel has its own suite; a marker is enough to see which panel the page chose.
vi.mock("./OrganizationCapabilities", () => ({ OrganizationCapabilities: () => <p>organization-offers</p> }));

import FeaturesPage from "./FeaturesPage";

function cap(over: Partial<CapabilityEnablementItem> & Pick<CapabilityEnablementItem, "id">): CapabilityEnablementItem {
  return {
    name: `cap.${over.id}`,
    version: "1.0.0",
    icon: "extension",
    kind: "knowledge_base",
    team_scope: "admin_gated",
    default_on: false,
    enabled_team_ids: [],
    team_settings_fields: [],
    ...over,
  };
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.applicationsEnabled = false;
  h.list = { data: undefined, isLoading: false, isError: false };
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

/** Render the organization page and open the Knowledge Bases tab. */
function renderKnowledgeBases(items?: CapabilityEnablementItem[]): string {
  if (items) h.list = { data: { items }, isLoading: false, isError: false };
  h.tKeys = [];
  act(() => root.render(<FeaturesPage organizationId="O1" />));
  const tab = Array.from(container.querySelectorAll<HTMLElement>('[role="radio"]')).find((element) =>
    element.textContent?.endsWith("kindFilter.knowledge_base"),
  );
  if (!tab) throw new Error("no Knowledge Bases tab");
  act(() => tab.click());
  return container.innerHTML;
}

/** The default-on column is the first cell, so its Switch is the first input. */
const defaultOnInput = () =>
  container.querySelector<HTMLInputElement>('input[aria-label="rework.admin.capabilities.col.defaultOn"]');

describe("FeaturesPage states", () => {
  it("shows the loading state while the catalog is fetching", () => {
    h.list = { data: undefined, isLoading: true, isError: false };
    expect(renderKnowledgeBases()).toContain("rework.admin.capabilities.loading");
  });

  it("shows the error state when the catalog fails to load", () => {
    h.list = { data: undefined, isLoading: false, isError: true };
    expect(renderKnowledgeBases()).toContain("rework.admin.capabilities.loadError");
  });

  it("shows the empty state when no Knowledge Base is published", () => {
    expect(renderKnowledgeBases([])).toContain("rework.admin.capabilities.emptyKnowledgeBases");
  });
});

describe("FeaturesPage catalog rows", () => {
  it("renders each Knowledge Base with its enabled-team count and a disabled manage action", () => {
    const html = renderKnowledgeBases([cap({ id: "kb", enabled_team_ids: ["nb"] })]);

    // A non-default-on capability counts explicit grants only, labeled as teams.
    expect(html).toContain("rework.admin.capabilities.enabledTeams.teams:1");
    expect(html).toMatch(/>groups<\/span>1<\/span>/);

    const manageButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("rework.admin.capabilities.manageTeams"),
    );
    expect(manageButton?.hasAttribute("disabled")).toBe(true);
  });

  it("counts a default-on capability from the roster minus opt-outs, not its grants", () => {
    const html = renderKnowledgeBases([
      cap({
        id: "kb",
        team_scope: "default_on",
        default_on: true,
        enabled_team_ids: ["nb", "ops"],
        disabled_team_ids: ["legal"],
        total_team_count: 12,
      }),
    ]);

    // 12 teams on the platform, 1 opted out → 11 can use it. The two explicit
    // grants are irrelevant: everyone already inherits access.
    expect(html).toContain("rework.admin.capabilities.enabledTeams.teams:11");
    expect(html).not.toContain("teams:2");
  });

  it("leaves the cell empty when the capability reaches no team", () => {
    const html = renderKnowledgeBases([cap({ id: "reaches_nobody" })]);

    expect(html).not.toContain("rework.admin.capabilities.enabledTeams.teams");
    expect(html).not.toContain("rework.admin.capabilities.enabledTeams.personal");
    expect(html).not.toContain(">0<");
  });

  it("shows unknown rather than zero when a default-on cap has no team roster", () => {
    const html = renderKnowledgeBases([
      cap({ id: "kb", team_scope: "default_on", default_on: true, total_team_count: 0 }),
    ]);

    // Rendering 0 here would read as "nobody has this" — the opposite of true.
    expect(html).toContain("rework.admin.capabilities.enabledTeams.unknown");
    expect(html).not.toContain(">0<");
  });

  it("leads with the default-on toggle column, then the capability", () => {
    const html = renderKnowledgeBases([cap({ id: "kb" })]);

    expect(html.indexOf("rework.admin.capabilities.col.defaultOn")).toBeLessThan(
      html.indexOf("rework.admin.capabilities.col.capability"),
    );
  });

  it("dims a capability no team can use, and leaves the in-use ones bright", () => {
    const html = renderKnowledgeBases([cap({ id: "unused_cap" }), cap({ id: "used_cap", enabled_team_ids: ["nb"] })]);

    const unusedRow = html.slice(html.indexOf("cap.unused_cap"), html.indexOf("cap.used_cap"));
    const usedRow = html.slice(html.indexOf("cap.used_cap"));
    expect(unusedRow).toContain("dimmed");
    expect(usedRow).not.toContain("dimmed");
  });

  it("reflects the default-on flag on a read-only toggle", () => {
    renderKnowledgeBases([cap({ id: "only_on", default_on: true })]);

    expect(defaultOnInput()?.checked).toBe(true);
    expect(defaultOnInput()?.disabled).toBe(true);
  });
});

// The default-on switch is not offered for a capability with a required team
// setting, which the backend always refuses (`DefaultOnNotAllowed`, HTTP 409)
// — nobody has filled the settings for the teams that would inherit it (RFC §8.2).
describe("FeaturesPage default-on gate for required team settings", () => {
  const REQUIRED_FIELD = { key: "endpoint", type: "url" as const, title: "Endpoint", required: true };

  it("disables the switch and offers the hint when a required setting blocks default-on", () => {
    renderKnowledgeBases([cap({ id: "corp_drive", team_settings_fields: [REQUIRED_FIELD] })]);

    expect(defaultOnInput()?.disabled).toBe(true);
    expect(h.tKeys).toContain("rework.admin.capabilities.defaultOnRequiresSettingsHint");
  });

  it("offers no hint for an already-default-on capability", () => {
    renderKnowledgeBases([cap({ id: "corp_drive", default_on: true, team_settings_fields: [REQUIRED_FIELD] })]);

    expect(h.tKeys).not.toContain("rework.admin.capabilities.defaultOnRequiresSettingsHint");
  });
});

describe("FeaturesPage kind filter", () => {
  it("hides the Apps filter by default", () => {
    const html = renderToStaticMarkup(<FeaturesPage organizationId="O1" />);
    expect(html).not.toContain("rework.admin.capabilities.kindFilter.app");
  });

  it("renders the Apps filter only when the deployment switch is enabled", () => {
    h.applicationsEnabled = true;
    const html = renderToStaticMarkup(<FeaturesPage organizationId="O1" />);
    expect(html).toContain("rework.admin.capabilities.kindFilter.tool");
    expect(html).toContain("rework.admin.capabilities.kindFilter.agent");
    expect(html).toContain("rework.admin.capabilities.kindFilter.model");
    expect(html).toContain("rework.admin.capabilities.kindFilter.knowledge_base");
    expect(html).toContain("rework.admin.capabilities.kindFilter.app");
  });

  it("falls back to the pod offers when the deployment switch goes off on the Apps tab", () => {
    h.applicationsEnabled = true;
    renderKnowledgeBases([cap({ id: "legacy_tool", kind: "tool" })]);
    const appsTab = Array.from(container.querySelectorAll<HTMLElement>('[role="radio"]')).find((element) =>
      element.textContent?.endsWith("kindFilter.app"),
    );
    act(() => appsTab!.click());

    h.applicationsEnabled = false;
    act(() => root.render(<FeaturesPage organizationId="O1" />));

    expect(container.textContent).toContain("organization-offers");
    expect(container.textContent).not.toContain("cap.legacy_tool");
    expect(container.textContent).not.toContain("kindFilter.app");
  });
});
