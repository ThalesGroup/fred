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

// The Capabilities dashboard is data-driven from the aggregated enablement list.
// `t` is mocked to echo its key (plus any interpolated count), so we assert on
// which key each state uses and on the enabled-team count and health it renders.

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  list: { data: undefined, isLoading: false, isError: false } as {
    data?: { items?: CapabilityEnablementItem[] };
    isLoading: boolean;
    isError: boolean;
  },
}));

// `t` echoes its key, but appends an interpolated `count` (or the composed
// `content` of the "All (…)" wrapper) when one is passed — those are the values
// under test for the enabled-teams column, and a bare key echo would hide
// whether the right number ever reached the label.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string; count?: number; content?: string }) => {
      const interpolated = opts?.count ?? opts?.content;
      return opts?.defaultValue ?? (interpolated === undefined ? key : `${key}:${interpolated}`);
    },
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAdminCapabilitiesQuery: () => h.list,
  useListTeamsQuery: () => ({ data: [] }),
  useSetCapabilityDefaultOnMutation: () => [vi.fn(), { isLoading: false }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

// Isolate the page from the drawer (which drags in TuningFieldRenderer + prompt hooks).
vi.mock("./CapabilityTeamMatrixDrawer", () => ({
  CapabilityTeamMatrixDrawer: () => null,
}));

import CapabilitiesPage from "./CapabilitiesPage";

function cap(over: Partial<CapabilityEnablementItem> & Pick<CapabilityEnablementItem, "id">): CapabilityEnablementItem {
  return {
    name: `cap.${over.id}`,
    version: "1.0.0",
    icon: "extension",
    team_scope: "admin_gated",
    default_on: false,
    enabled_team_ids: [],
    team_settings_fields: [],
    ...over,
  };
}

function render(): string {
  return renderToStaticMarkup(<CapabilitiesPage />);
}

describe("CapabilitiesPage states", () => {
  beforeEach(() => {
    h.list = { data: undefined, isLoading: false, isError: false };
  });

  it("shows the loading state while the catalog is fetching", () => {
    h.list = { data: undefined, isLoading: true, isError: false };
    expect(render()).toContain("rework.admin.capabilities.loading");
  });

  it("shows the error state when the catalog fails to load", () => {
    h.list = { data: undefined, isLoading: false, isError: true };
    expect(render()).toContain("rework.admin.capabilities.loadError");
  });

  it("shows the empty state when no capability is advertised", () => {
    h.list = { data: { items: [] }, isLoading: false, isError: false };
    expect(render()).toContain("rework.admin.capabilities.empty");
  });
});

describe("CapabilitiesPage catalog rows", () => {
  it("renders each capability with enabled-team count and neutral health", () => {
    h.list = {
      data: {
        items: [cap({ id: "web_search", team_scope: "admin_gated", default_on: false, enabled_team_ids: ["nb"] })],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();

    // A non-default-on capability counts explicit grants only, labeled as teams.
    expect(html).toContain("rework.admin.capabilities.enabledTeams.teams:1");

    // Health is neutral (no resting per-capability count until the sweep, #1975).
    expect(html).toContain("rework.admin.capabilities.health.pending");
    expect(html).not.toContain("rework.admin.capabilities.health.suspended");

    // Manage-teams action is offered per row.
    expect(html).toContain("rework.admin.capabilities.manageTeams");
  });

  it("counts a default-on capability from the roster minus opt-outs, not its grants", () => {
    h.list = {
      data: {
        items: [
          cap({
            id: "document_access",
            team_scope: "default_on",
            default_on: true,
            enabled_team_ids: ["nb", "ops"],
            disabled_team_ids: ["legal"],
            total_team_count: 12,
          }),
        ],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();

    // 12 teams on the platform, 1 opted out → 11 can use it, wrapped in the
    // "All (…)" label. The two explicit grants are irrelevant: everyone already
    // inherits access. Personal spaces inherit default-on too, but their roster
    // is unknown here (no user directory), so the unlabeled variant follows.
    expect(html).toContain(
      "rework.admin.capabilities.enabledTeams.all:" +
        "rework.admin.capabilities.enabledTeams.teams:11 + rework.admin.capabilities.enabledTeams.personalUnknown",
    );
    expect(html).not.toContain("teams:2");
  });

  it("shows only the personal-space part when no team has access (zero parts are hidden)", () => {
    h.list = {
      data: {
        items: [
          cap({
            id: "personal_only",
            default_on: false,
            enabled_team_ids: [],
            personal_scope: "enabled",
            total_personal_space_count: 8,
          }),
        ],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();

    // "8 personal spaces", not "0 teams + 8 personal spaces".
    expect(html).toContain("rework.admin.capabilities.enabledTeams.personal:8");
    expect(html).not.toContain("rework.admin.capabilities.enabledTeams.teams");
  });

  it("leaves the cell empty when the capability reaches no team and no personal space", () => {
    h.list = {
      data: {
        items: [cap({ id: "reaches_nobody", default_on: false, enabled_team_ids: [], personal_scope: "disabled" })],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();

    expect(html).not.toContain("rework.admin.capabilities.enabledTeams.teams");
    expect(html).not.toContain("rework.admin.capabilities.enabledTeams.personal");
    expect(html).not.toContain(">0<");
  });

  it("shows unknown rather than zero when a default-on cap has no team roster", () => {
    h.list = {
      data: {
        items: [cap({ id: "document_access", team_scope: "default_on", default_on: true, total_team_count: 0 })],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();

    // Rendering 0 here would read as "nobody has this" — the opposite of true.
    expect(html).toContain("rework.admin.capabilities.enabledTeams.unknown");
    expect(html).not.toContain(">0<");
  });

  it("leads with the default-on toggle column, then the capability", () => {
    h.list = {
      data: { items: [cap({ id: "web_search" })] },
      isLoading: false,
      isError: false,
    };
    const html = render();

    expect(html.indexOf("rework.admin.capabilities.col.defaultOn")).toBeLessThan(
      html.indexOf("rework.admin.capabilities.col.capability"),
    );
  });

  it("dims a capability no team can use, and leaves the in-use ones bright", () => {
    h.list = {
      data: {
        items: [
          cap({ id: "unused_cap", default_on: false, enabled_team_ids: [] }),
          cap({ id: "used_cap", default_on: false, enabled_team_ids: ["nb"] }),
        ],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();

    const unusedRow = html.slice(html.indexOf("cap.unused_cap"), html.indexOf("cap.used_cap"));
    const usedRow = html.slice(html.indexOf("cap.used_cap"));
    expect(unusedRow).toContain("dimmed");
    expect(usedRow).not.toContain("dimmed");
  });

  it("reflects the default-on flag on the toggle (checked only for default-on caps)", () => {
    h.list = {
      data: { items: [cap({ id: "only_on", default_on: true })] },
      isLoading: false,
      isError: false,
    };
    expect(render()).toContain("checked");
  });
});
