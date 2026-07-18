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
import type { CapabilityEnablementItem, Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  list: { data: undefined, isLoading: false, isError: false } as {
    data?: { items?: CapabilityEnablementItem[] };
    isLoading: boolean;
    isError: boolean;
  },
  allTeams: { data: [] as Team[], isLoading: false, isError: false },
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
  useListAllTeamsQuery: () => h.allTeams,
  useSetCapabilityDefaultOnMutation: () => [vi.fn(), { isLoading: false }],
  useLazyCapabilityRevokeImpactQuery: () => [vi.fn(), { data: undefined, isFetching: false }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

// Isolate the page from the drawer's own internals (TuningFieldRenderer, tri-state
// mutations, search) — but still render the props CapabilitiesPage passes it, so a
// regression that stops forwarding the global team registry is caught here too.
const drawerProps = vi.hoisted(() => ({ current: undefined as unknown }));
vi.mock("./CapabilityTeamMatrixDrawer", () => ({
  CapabilityTeamMatrixDrawer: (props: unknown) => {
    drawerProps.current = props;
    return null;
  },
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

describe("CapabilitiesPage team registry wiring", () => {
  // Regression coverage for the bug where the "Manage teams" drawer used
  // `useListTeamsQuery` (caller-scoped: only teams the admin belongs to)
  // instead of `useListAllTeamsQuery` (the full registry, `can_list_all_teams`).
  // An admin managing a capability must see every collaborative team, not just
  // their own — `fredlab` is the concrete team named in the original bug report.
  beforeEach(() => {
    h.list = { data: { items: [cap({ id: "web_search" })] }, isLoading: false, isError: false };
    h.allTeams = { data: [], isLoading: false, isError: false };
    drawerProps.current = undefined;
  });

  it("passes the useListAllTeamsQuery result to the drawer, unfiltered", () => {
    // `fredlab` stands in for a team the current admin is not a member of —
    // the global registry hook must still surface it, and the page must not
    // apply any additional client-side membership filter before forwarding it.
    const registryTeams: Team[] = [
      { id: "nightly", name: "Nightly Build" },
      { id: "fredlab", name: "fredlab" },
    ];
    h.allTeams = { data: registryTeams, isLoading: false, isError: false };
    render();
    expect(drawerProps.current).toMatchObject({ teams: registryTeams });
  });

  it("forwards the registry's loading and error flags to the drawer", () => {
    h.allTeams = { data: [], isLoading: true, isError: false };
    render();
    expect(drawerProps.current).toMatchObject({ teamsLoading: true, teamsError: false });

    h.allTeams = { data: [], isLoading: false, isError: true };
    render();
    expect(drawerProps.current).toMatchObject({ teamsLoading: false, teamsError: true });
  });
});

describe("CapabilitiesPage catalog rows", () => {
  it("renders each capability with enabled-team count and a healthy resting state", () => {
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

    // Resting health with no suspended/unknown instances reads as healthy (#1975).
    expect(html).toContain("rework.admin.capabilities.health.healthy");
    expect(html).not.toContain("rework.admin.capabilities.health.suspended");
    expect(html).not.toContain("rework.admin.capabilities.health.unknown");

    // Manage-teams action is offered per row.
    expect(html).toContain("rework.admin.capabilities.manageTeams");
  });

  it("shows the resting suspended count from the row when the capability breaks agents", () => {
    h.list = {
      data: { items: [cap({ id: "web_search", enabled_team_ids: ["nb"], suspended_instances: 3 })] },
      isLoading: false,
      isError: false,
    };
    const html = render();

    // The count comes from the row (`suspended_instances`), not session state.
    expect(html).toContain("rework.admin.capabilities.health.suspended:3");
    expect(html).not.toContain("rework.admin.capabilities.health.healthy");
  });

  it("shows a neutral unknown indicator when a pod was unreachable but nothing is broken", () => {
    h.list = {
      data: {
        items: [
          cap({ id: "web_search", enabled_team_ids: ["nb"], suspended_instances: 0, health_unknown_instances: 2 }),
        ],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();

    // Unknown (unreachable pod) is distinct from suspended (broken).
    expect(html).toContain("rework.admin.capabilities.health.unknown:2");
    expect(html).not.toContain("rework.admin.capabilities.health.suspended");
    expect(html).not.toContain("rework.admin.capabilities.health.healthy");
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

    // 12 teams on the platform, 1 opted out → 11 can use it. The two explicit
    // grants are irrelevant: everyone already inherits access. Personal spaces
    // inherit default-on too, but their roster is unknown here (no user
    // directory), so the unnumbered variant follows on its own line.
    expect(html).toContain("rework.admin.capabilities.enabledTeams.teams:11");
    expect(html).toContain("rework.admin.capabilities.enabledTeams.personalUnknown");
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

describe("CapabilitiesPage kind filter (CAPAB-01, RFC §8.6)", () => {
  it("shows only tool-kind capabilities by default, hiding agent-kind rows", () => {
    h.list = {
      data: {
        items: [cap({ id: "web_search", kind: "tool" }), cap({ id: "sentinel", kind: "agent" })],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();
    expect(html).toContain("cap.web_search");
    expect(html).not.toContain("cap.sentinel");
  });

  it("treats a capability with no kind as a tool (backward-compatible default)", () => {
    h.list = { data: { items: [cap({ id: "legacy_cap" })] }, isLoading: false, isError: false };
    expect(render()).toContain("cap.legacy_cap");
  });

  it("renders the Tools/Agents filter toggle", () => {
    h.list = { data: { items: [] }, isLoading: false, isError: false };
    const html = render();
    expect(html).toContain("rework.admin.capabilities.kindFilter.tool");
    expect(html).toContain("rework.admin.capabilities.kindFilter.agent");
  });
});
