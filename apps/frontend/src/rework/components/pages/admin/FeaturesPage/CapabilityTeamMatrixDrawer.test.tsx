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

// Regression coverage for the "Manage teams" drawer showing (effectively) nothing
// when the team registry hasn't resolved yet, and for conflating "no team exists"
// with "your search matched nothing" or a fetch error. `t` echoes its key (plus
// any interpolated `team`/`count`), so assertions match on translation keys.
//
// Rendered with `renderToStaticMarkup` (no effects run — same convention as
// FeaturesPage.test.tsx; this repo's test environment has no DOM/jsdom), so
// `orderedTeams` never advances past its initial value (the `teams` prop as
// passed): rows render in input order, which the tri-state tests below rely on.

import { renderToStaticMarkup } from "react-dom/server";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem, Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { CapabilityTeamMatrixDrawer } from "./CapabilityTeamMatrixDrawer";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string; team?: string; count?: number; deps?: string }) => {
      if (opts?.defaultValue !== undefined) return opts.defaultValue;
      // `deps` (the #2408 dependency hints) is echoed like `team`/`count`: the
      // resolved dependency NAMES are what the assertions are about, and a
      // bare key echo would hide whether they ever reached the label.
      const interpolated = opts?.team ?? opts?.deps ?? opts?.count;
      return interpolated === undefined ? key : `${key}:${interpolated}`;
    },
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useEnableTeamCapabilityMutation: () => [vi.fn(), { isLoading: false }],
  useDisableTeamCapabilityMutation: () => [vi.fn(), { isLoading: false }],
  useSetCapabilityPersonalScopeMutation: () => [vi.fn(), { isLoading: false }],
  useLazyAdminTeamCapabilitySettingsQuery: () => [vi.fn(), { isLoading: false }],
  useSetTeamCapabilitySettingsMutation: () => [vi.fn(), { isLoading: false }],
  useCapabilityTeamSettingsMapQuery: () => ({ data: settingsMapData, refetch: vi.fn() }),
}));

// Mutable so a test can say which teams have an option on.
let settingsMapData: { capability_id: string; by_team: Record<string, Record<string, unknown>> } | undefined;

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

function capability(over: Partial<CapabilityEnablementItem> = {}): CapabilityEnablementItem {
  return {
    id: "web_search",
    name: "cap.web_search",
    version: "1.0.0",
    icon: "extension",
    team_scope: "admin_gated",
    default_on: false,
    enabled_team_ids: [],
    team_settings_fields: [],
    ...over,
  };
}

function team(id: string, name: string): Team {
  return { id, name };
}

function render(props: Partial<ComponentProps<typeof CapabilityTeamMatrixDrawer>> = {}): string {
  return renderToStaticMarkup(
    <CapabilityTeamMatrixDrawer
      capability={capability()}
      allCapabilities={[]}
      teams={[]}
      teamsLoading={false}
      teamsError={false}
      open
      onClose={vi.fn()}
      {...props}
    />,
  );
}

describe("CapabilityTeamMatrixDrawer team-registry states", () => {
  it("shows a loading message while the registry is in flight, not an empty state", () => {
    const html = render({ teamsLoading: true, teams: [] });
    expect(html).toContain("rework.admin.capabilities.matrix.teamsLoading");
    expect(html).not.toContain("rework.admin.capabilities.matrix.noTeams");
    expect(html).not.toContain("rework.admin.capabilities.matrix.searchEmpty");
  });

  it("shows an explicit error message when the registry fails to load, not a silent empty list", () => {
    const html = render({ teamsError: true, teams: [] });
    expect(html).toContain("rework.admin.capabilities.matrix.teamsError");
    expect(html).not.toContain("rework.admin.capabilities.matrix.noTeams");
  });

  it("distinguishes an empty registry from a search with no matches", () => {
    const html = render({ teams: [] });
    expect(html).toContain("rework.admin.capabilities.matrix.noTeams");
    expect(html).not.toContain("rework.admin.capabilities.matrix.searchEmpty");
  });

  it("renders every team from the registry, including one the admin doesn't personally belong to", () => {
    // `fredlab` stands in for a team outside the admin's own membership — the
    // original bug (sourcing the drawer from the caller-scoped /teams list)
    // made exactly this class of team invisible here.
    const teams = [team("nightly", "Nightly Build"), team("fredlab", "fredlab")];
    const html = render({ teams });
    expect(html).toContain("fredlab");
    expect(html).toContain("Nightly Build");
    expect(html).not.toContain("rework.admin.capabilities.matrix.noTeams");
  });
});

describe("CapabilityTeamMatrixDrawer tri-state controls", () => {
  const CHOICES = ["disabled", "default", "enabled"];

  /**
   * One HTML chunk per `<li>` team row, in render order (see file-level note on
   * why order == input order here). Excludes the pinned "All personal spaces"
   * row (RFC §8.4) — it is not a team, and these tests assert on per-team rows.
   */
  function rowsInOrder(html: string): string[] {
    return html
      .split("<li ")
      .slice(1)
      .filter((row) => !row.includes("_personalRow_"));
  }

  /** Index of the row's `<button role="radio">` carrying `aria-checked="true"`. */
  function checkedChoiceIndex(rowHtml: string): number {
    const buttons = rowHtml.split("<button").slice(1);
    return buttons.findIndex((b) => b.includes('aria-checked="true"'));
  }

  it("marks the segment matching each team's explicit grant, per team", () => {
    const cap = capability({ enabled_team_ids: ["nb"], disabled_team_ids: ["legal"] });
    const teams = [team("nb", "Nightly Build"), team("legal", "Legal"), team("ops", "Ops")];
    const rows = rowsInOrder(render({ capability: cap, teams }));

    expect(rows[0]).toContain("Nightly Build");
    expect(CHOICES[checkedChoiceIndex(rows[0])]).toBe("enabled");

    expect(rows[1]).toContain("Legal");
    expect(CHOICES[checkedChoiceIndex(rows[1])]).toBe("disabled");

    expect(rows[2]).toContain("Ops");
    expect(CHOICES[checkedChoiceIndex(rows[2])]).toBe("default");
  });

  it("still offers Disable / Default / Enable for every visible team", () => {
    const teams = [team("nb", "Nightly Build")];
    const html = render({ teams });
    expect(html).toContain("rework.admin.capabilities.matrix.disable");
    expect(html).toContain("rework.admin.capabilities.matrix.default");
    expect(html).toContain("rework.admin.capabilities.matrix.enable");
  });

  it("does not offer the personal-space class control for an application", () => {
    const html = render({
      capability: capability({ id: "app__example", kind: "app" }),
      teams: [team("nb", "Nightly Build")],
    });
    expect(html).toContain("Nightly Build");
    expect(html).not.toContain("rework.admin.capabilities.matrix.personal.label");
  });
});

// Regression coverage for #2408: activating an agent whose default tool
// capabilities the target team (or every personal space) cannot use yet was
// offered freely and answered with a bare HTTP 409. The row says which
// dependency is in the way.
//
// #2470 changed the remedy, not the diagnosis: the Enable segment stays
// CLICKABLE so it can open the "Enable all" confirmation, which grants the
// missing dependencies before the template. What keeps a bare grant off the
// wire is `selectChoice`/`submitEnable`, not a disabled attribute — so these
// tests assert the hint, and assert that the segment is reachable.
describe("CapabilityTeamMatrixDrawer agent dependency gate (#2408, RFC §8.6 depends_on)", () => {
  const agent = capability({ id: "sentinel", name: "cap.sentinel", kind: "agent", default_capability_ids: ["dep"] });
  const dep = (over: Partial<CapabilityEnablementItem> = {}) => capability({ id: "dep", name: "Tabular MCP", ...over });
  const nb = [team("nb", "Nightly Build")];

  const rows = (html: string) => html.split("<li ").slice(1);
  const teamRow = (html: string) => rows(html).find((row) => !row.includes("_personalRow_")) ?? "";
  const personalRow = (html: string) => rows(html).find((row) => row.includes("_personalRow_")) ?? "";
  /** The row's three tri-state buttons, in CHOICES (disable/default/enable) order. */
  const enableSegment = (rowHtml: string) => rowHtml.split("<button").slice(1, 4)[2] ?? "";

  it("names the dependency, and keeps Enable clickable so it can offer to grant it", () => {
    const html = render({ capability: agent, allCapabilities: [agent, dep()], teams: nb });
    const row = teamRow(html);
    expect(row).toContain("rework.admin.capabilities.matrix.dependencyHint:Tabular MCP");
    // #2470: reachable on purpose — the click opens the "Enable all" dialog
    // rather than doing nothing. A disabled segment is also keyboard-dead,
    // which is what left the admin with no in-place way forward.
    expect(enableSegment(row)).not.toContain("disabled");
  });

  it("offers Enable normally once the dependency is enabled for that team", () => {
    const html = render({
      capability: agent,
      allCapabilities: [agent, dep({ enabled_team_ids: ["nb"] })],
      teams: nb,
    });
    const row = teamRow(html);
    expect(row).not.toContain("rework.admin.capabilities.matrix.dependencyHint");
    expect(enableSegment(row)).not.toContain("disabled");
  });

  it("fails open when the dependency is not in the catalog list at all", () => {
    // The backend stays the authority; blocking on a row we cannot evaluate
    // would forbid a grant the server may well accept.
    const html = render({ capability: agent, allCapabilities: [agent], teams: nb });
    const row = teamRow(html);
    expect(row).not.toContain("rework.admin.capabilities.matrix.dependencyHint");
    expect(enableSegment(row)).not.toContain("disabled");
  });

  it("leaves an ordinary tool row untouched", () => {
    const tool = capability({ id: "web_search" });
    const html = render({ capability: tool, allCapabilities: [tool, dep()], teams: nb });
    const row = teamRow(html);
    expect(row).not.toContain("rework.admin.capabilities.matrix.dependencyHint");
    expect(enableSegment(row)).not.toContain("disabled");
  });

  it("never disables the segment a team is already on, even with the dependency revoked", () => {
    // A dependency CAN be revoked after the agent was granted. `ButtonGroup`
    // gives only the selected item `tabIndex={0}`, so disabling it would strand
    // the whole row for keyboard users — the admin could not even undo the
    // now-broken grant. The stale "enable X first" hint is dropped with it.
    const html = render({
      capability: capability({ ...agent, enabled_team_ids: ["nb"] }),
      allCapabilities: [agent, dep()],
      teams: nb,
    });
    const row = teamRow(html);
    expect(enableSegment(row)).not.toContain("disabled");
    expect(row).not.toContain("rework.admin.capabilities.matrix.dependencyHint");
  });

  it("never disables the personal segment when the class is already enabled", () => {
    const html = render({
      capability: capability({ ...agent, personal_scope: "enabled" }),
      allCapabilities: [agent, dep()],
      teams: nb,
    });
    const row = personalRow(html);
    expect(enableSegment(row)).not.toContain("disabled");
    expect(row).not.toContain("rework.admin.capabilities.matrix.personal.dependencyHint");
  });

  it("names the dependency on the personal-space class row, Enable still clickable", () => {
    const html = render({ capability: agent, allCapabilities: [agent, dep()], teams: nb });
    const row = personalRow(html);
    expect(row).toContain("rework.admin.capabilities.matrix.personal.dependencyHint:Tabular MCP");
    // #2470, same as the team row: the click opens the "Enable all" dialog.
    expect(enableSegment(row)).not.toContain("disabled");
  });

  it("still hard-blocks the personal class row when the capability needs required team settings", () => {
    // Unchanged by #2470: this synthetic class row has no form to fill the
    // settings in with, so there is nothing "Enable all" could do about it.
    const gated = capability({
      ...agent,
      team_settings_fields: [{ key: "token", type: "string", required: true, title: "Token" }],
    });
    const html = render({ capability: gated, allCapabilities: [gated, dep({ default_on: true })], teams: nb });
    expect(enableSegment(personalRow(html))).toContain("disabled");
  });

  it("offers the personal-space class row once the dependency is on by default", () => {
    const html = render({ capability: agent, allCapabilities: [agent, dep({ default_on: true })], teams: nb });
    const row = personalRow(html);
    expect(row).not.toContain("rework.admin.capabilities.matrix.personal.dependencyHint");
    expect(enableSegment(row)).not.toContain("disabled");
  });
});

describe("CapabilityTeamMatrixDrawer per-team settings affordance", () => {
  const JS_FIELD = {
    key: "allow_javascript",
    type: "boolean" as const,
    title: "cap.html_artifact.teamSettings.allow_javascript.title",
    default: false,
  };

  const OPTIONS_ARIA = "rework.admin.capabilities.matrix.editSettingsAria";

  it("offers the options control for an enabled team when the capability has settings", () => {
    // Without it, changing one setting meant disabling the capability first —
    // which suspends every agent depending on it.
    const html = render({
      capability: capability({ team_settings_fields: [JS_FIELD], enabled_team_ids: ["t1"] }),
      teams: [team("t1", "Alpha")],
    });

    expect(html).toContain(OPTIONS_ARIA);
  });

  it("offers nothing for a capability that declares no settings", () => {
    const html = render({
      capability: capability({ team_settings_fields: [], enabled_team_ids: ["t1"] }),
      teams: [team("t1", "Alpha")],
    });

    expect(html).not.toContain(OPTIONS_ARIA);
  });

  it("offers nothing for a team the capability is not enabled for", () => {
    // There are no settings to edit until the capability is granted.
    const html = render({
      capability: capability({ team_settings_fields: [JS_FIELD], enabled_team_ids: [] }),
      teams: [team("t1", "Alpha")],
    });

    expect(html).not.toContain(OPTIONS_ARIA);
  });
});

describe("CapabilityTeamMatrixDrawer active-option dot", () => {
  const JS_FIELD = {
    key: "allow_javascript",
    type: "boolean" as const,
    title: "cap.html_artifact.teamSettings.allow_javascript.title",
    default: false,
  };

  const ACTIVE_ARIA = "rework.admin.capabilities.matrix.editSettingsActiveAria";
  const PLAIN_ARIA = "rework.admin.capabilities.matrix.editSettingsAria";

  const renderRows = () =>
    render({
      capability: capability({ team_settings_fields: [JS_FIELD], enabled_team_ids: ["t1", "t2"] }),
      teams: [team("t1", "Alpha"), team("t2", "Beta")],
    });

  afterEach(() => {
    settingsMapData = undefined;
  });

  it("marks only the team whose option is on", () => {
    settingsMapData = {
      capability_id: "web_search",
      by_team: { t1: { allow_javascript: true }, t2: { allow_javascript: false } },
    };

    const html = renderRows();

    // The dot is aria-hidden, so the row's meaning has to travel in the label.
    expect(html).toContain(ACTIVE_ARIA);
    expect(html).toContain(PLAIN_ARIA);
  });

  it("marks nothing when no team has the option on", () => {
    settingsMapData = { capability_id: "web_search", by_team: { t1: { allow_javascript: false } } };

    const html = renderRows();

    expect(html).not.toContain(ACTIVE_ARIA);
    expect(html).toContain(PLAIN_ARIA);
  });

  it("marks nothing while the map has not loaded", () => {
    // Fails quiet rather than guessing: a dot that appears then vanishes reads
    // as a state change the admin did not make.
    settingsMapData = undefined;

    const html = renderRows();

    expect(html).not.toContain(ACTIVE_ARIA);
  });
});

describe("CapabilityTeamMatrixDrawer personal-class settings", () => {
  const JS_FIELD = {
    key: "allow_javascript",
    type: "boolean" as const,
    title: "cap.html_artifact.teamSettings.allow_javascript.title",
    default: false,
  };

  const PERSONAL_LABEL = "rework.admin.capabilities.matrix.personal.label";
  const OPTIONS_ARIA = `rework.admin.capabilities.matrix.editSettingsAria:${PERSONAL_LABEL}`;
  const ACTIVE_ARIA = `rework.admin.capabilities.matrix.editSettingsActiveAria:${PERSONAL_LABEL}`;

  const rows = (html: string) => html.split("<li ").slice(1);
  const personalRow = (html: string) => rows(html).find((row) => row.includes("_personalRow_")) ?? "";

  const renderPersonal = (over: Partial<CapabilityEnablementItem> = {}) =>
    render({
      capability: capability({ kind: "agent", team_settings_fields: [JS_FIELD], ...over }),
      teams: [team("t1", "Alpha")],
    });

  afterEach(() => {
    settingsMapData = undefined;
  });

  it("offers one options control for the whole personal class", () => {
    // Personal access is granted as a class, so its options are one decision:
    // there is no per-space row to carry a second one.
    const html = renderPersonal({ personal_scope: "enabled" });

    expect(personalRow(html)).toContain(OPTIONS_ARIA);
  });

  it("offers it when the class merely inherits a default-on capability", () => {
    const html = renderPersonal({ personal_scope: "default", default_on: true });

    expect(personalRow(html)).toContain(OPTIONS_ARIA);
  });

  it("offers nothing while the class does not have the capability", () => {
    const html = renderPersonal({ personal_scope: "default", default_on: false });

    expect(personalRow(html)).not.toContain(OPTIONS_ARIA);
  });

  it("marks the class from the shared record, not from any one space", () => {
    settingsMapData = {
      capability_id: "web_search",
      by_team: { __personal_scope__: { allow_javascript: true } },
    };

    const html = renderPersonal({ personal_scope: "enabled" });

    expect(personalRow(html)).toContain(ACTIVE_ARIA);
  });
});
