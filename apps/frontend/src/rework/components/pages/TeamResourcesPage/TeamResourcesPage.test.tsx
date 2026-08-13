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

// Coverage for FRONT-09.G: the tab switcher replaces the always-expanded root
// tree — only the active tab's browser renders, "Espace partagé" is hidden
// for a personal team, and the team storage quota shows in the header.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  isPersonalTeam: false,
  team: { id: "team-1", max_resources_storage_size: 5_368_709_120, current_resources_storage_size: 4_509_715_660 } as
    | Record<string, unknown>
    | undefined,
  corpusStatsUninitialized: false,
  corpusStatsRefetch: () => {},
  teamUninitialized: false,
  teamRefetch: () => {},
  onDocumentsChanged: undefined as (() => void) | undefined,
  // Existing "tab switcher" coverage below exercises the 4-tab (flag-on)
  // behavior — defaults true so it keeps passing unmodified. The dedicated
  // "resource spaces feature flag" describe block below overrides this to
  // cover the off (shipped default) case.
  enableAllResourceSpaces: true,
  // True while useGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery
  // hasn't resolved yet — bootstrap is undefined during that window.
  bootstrapPending: false,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));
vi.mock("react-router-dom", () => ({ useParams: () => ({ teamId: "team-1" }) }));
vi.mock("../../../../hooks/useFrontendBootstrap.ts", () => ({
  useFrontendBootstrap: () => ({
    activeTeam: probe.isPersonalTeam ? { id: "team-1" } : { id: "other-team" },
    bootstrap: probe.bootstrapPending
      ? undefined
      : { feature_flags: { enableAllResourceSpaces: probe.enableAllResourceSpaces } },
  }),
}));
vi.mock("../../../../security/KeycloakService.ts", () => ({ KeyCloakService: { GetUserId: () => "u-1" } }));
vi.mock("@shared/utils/teamId.ts", () => ({
  isPersonalTeamId: () => probe.isPersonalTeam,
  personalTeamId: (uid: string) => `personal-${uid}`,
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({
    data: probe.team,
    isUninitialized: probe.teamUninitialized,
    refetch: probe.teamRefetch,
  }),
}));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({ useTeamCapabilities: () => ({ canUpdateResources: true }) }));
vi.mock("../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => ({
    isLoading: false,
    isFetching: false,
    isUninitialized: false,
    isError: false,
  }),
  useGetCorpusTypeStatsKnowledgeFlowV1TagsStatsGetQuery: () => ({
    data: { entries: [] },
    isLoading: false,
    isError: false,
    isUninitialized: probe.corpusStatsUninitialized,
    refetch: probe.corpusStatsRefetch,
  }),
  useTypeStatsKnowledgeFlowV1FsStatsPathGetQuery: () => ({ data: { entries: [] }, isLoading: false, isError: false }),
}));
vi.mock("./DocumentWorkspace/DocumentWorkspace.tsx", () => ({
  default: (props: { onDocumentsChanged?: () => void }) => {
    probe.onDocumentsChanged = props.onDocumentsChanged;
    return <div data-testid="panel-resources" />;
  },
}));
vi.mock("./FilesystemWorkspace/FilesystemWorkspace.tsx", () => ({
  default: (props: { root: string }) => <div data-testid="panel-fs">{props.root}</div>,
}));
vi.mock("./AgentsWorkspace/AgentsWorkspace.tsx", () => ({
  default: () => <div data-testid="panel-agents" />,
}));
vi.mock("./ResourceStatsCards/ResourceStatsCards.tsx", () => ({ default: () => <div data-testid="stats-cards" /> }));

import TeamResourcesPage from "./TeamResourcesPage.tsx";

let container: HTMLDivElement;
let root: Root;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<TeamResourcesPage />);
  });
}

beforeEach(() => {
  probe.isPersonalTeam = false;
  probe.team = {
    id: "team-1",
    max_resources_storage_size: 5_368_709_120,
    current_resources_storage_size: 4_509_715_660,
  };
  probe.corpusStatsUninitialized = false;
  probe.corpusStatsRefetch = vi.fn();
  probe.teamUninitialized = false;
  probe.teamRefetch = vi.fn();
  probe.onDocumentsChanged = undefined;
  probe.enableAllResourceSpaces = true;
  probe.bootstrapPending = false;
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function tabButtons(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll('[role="tab"]'));
}

function click(el: Element | null) {
  act(() => {
    el?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
}

describe("TeamResourcesPage tab switcher", () => {
  it("shows only the Corpus panel by default", () => {
    render();
    expect(container.querySelector('[data-testid="panel-resources"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="panel-fs"]')).toBeNull();
    expect(container.querySelector('[data-testid="panel-agents"]')).toBeNull();
  });

  it("switches panels when a tab is clicked, never rendering two at once", () => {
    render();
    expect(tabButtons()).toHaveLength(4); // resources, mine, team, agents

    click(tabButtons()[3]); // agents
    expect(container.querySelector('[data-testid="panel-agents"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="panel-resources"]')).toBeNull();

    click(tabButtons()[1]); // mine
    expect(container.querySelector('[data-testid="panel-fs"]')?.textContent).toBe("teams/team-1/users/u-1");
    expect(container.querySelector('[data-testid="panel-agents"]')).toBeNull();
  });

  it("hides the Espace partagé tab for a personal team", () => {
    probe.isPersonalTeam = true;
    render();
    expect(tabButtons()).toHaveLength(3); // no "team" tab
  });

  it("shows the team storage quota when the team carries a quota", () => {
    render();
    expect(container.textContent).toContain("rework.resources.storageQuota");
  });

  it("omits the quota block when the team has no quota data", () => {
    probe.team = { id: "team-1" };
    render();
    expect(container.textContent).not.toContain("rework.resources.storageQuota");
  });
});

// The team isn't yet confident Mon espace/Espace d'équipe/Agents pull their
// weight — shipped default is Corpus d'équipe only, with the other three
// gated behind the platform-wide enableAllResourceSpaces flag
// (configuration.yaml, off by default) so they can be turned back on later
// without a code change.
describe("TeamResourcesPage resource spaces feature flag", () => {
  it("shows only Corpus d'équipe, no tab switcher at all, when the flag is off", () => {
    probe.enableAllResourceSpaces = false;
    render();

    expect(tabButtons()).toHaveLength(0);
    expect(container.querySelector('[data-testid="panel-resources"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="panel-fs"]')).toBeNull();
    expect(container.querySelector('[data-testid="panel-agents"]')).toBeNull();
  });

  it("shows the full 4-tab switcher when the flag is on", () => {
    probe.enableAllResourceSpaces = true;
    render();

    expect(tabButtons()).toHaveLength(4);
  });

  it("treats a not-yet-loaded bootstrap as off (safe default), not a crash", () => {
    probe.bootstrapPending = true;
    render();

    expect(tabButtons()).toHaveLength(0);
    expect(container.querySelector('[data-testid="panel-resources"]')).not.toBeNull();
  });
});

// Regression: DocumentWorkspace's useNotifyOnNewTaskTarget does a catch-up
// fire on mount for any task target already in the store. In the same
// commit where activeTab just switched to "resources", DocumentWorkspace
// (child) mounts and can run that effect before corpusStats' own
// subscribing effect (parent) has dispatched its first fetch — React
// flushes child effects before parent effects. Calling RTK Query's
// `.refetch()` on a query that was never started throws ("Cannot refetch a
// query that has not been started yet") and previously took down the whole
// app. onDocumentsChanged must no-op instead of calling refetch() while
// corpusStats is still uninitialized.
describe("TeamResourcesPage onDocumentsChanged — refetch guard", () => {
  it("does not call refetch while corpusStats has not started yet", () => {
    probe.corpusStatsUninitialized = true;
    render();

    expect(() => probe.onDocumentsChanged?.()).not.toThrow();
    expect(probe.corpusStatsRefetch).not.toHaveBeenCalled();
  });

  it("calls refetch once corpusStats has started", () => {
    probe.corpusStatsUninitialized = false;
    render();

    probe.onDocumentsChanged?.();
    expect(probe.corpusStatsRefetch).toHaveBeenCalledOnce();
  });

  it("does not call the team refetch while the team query has not started yet", () => {
    probe.teamUninitialized = true;
    render();

    expect(() => probe.onDocumentsChanged?.()).not.toThrow();
    expect(probe.teamRefetch).not.toHaveBeenCalled();
  });
});

// The storage meter reads the control-plane team row, but every write to its
// `current_resources_storage_size` comes from the knowledge-flow API — a
// separate RTK Query instance whose tag invalidations cannot reach this cache
// entry. Deleting a document or a library therefore left the meter frozen on
// its mount-time figure until a manual page reload.
describe("TeamResourcesPage storage meter freshness", () => {
  it("refetches the team so the quota meter follows corpus add/delete", () => {
    render();

    probe.onDocumentsChanged?.();
    expect(probe.teamRefetch).toHaveBeenCalledOnce();
  });
});

describe("TeamResourcesPage stats toggle", () => {
  function statsToggle(): HTMLButtonElement {
    const button = Array.from(container.querySelectorAll("button")).find((b) => b.hasAttribute("aria-expanded"));
    if (!button) throw new Error("stats toggle chip not rendered");
    return button;
  }

  it("hides the stats cards by default", () => {
    render();
    expect(container.querySelector('[data-testid="stats-cards"]')).toBeNull();
    expect(statsToggle().getAttribute("aria-expanded")).toBe("false");
  });

  it("shows the stats cards when the header chip is toggled on, and back off when clicked again", () => {
    render();

    click(statsToggle());
    expect(container.querySelector('[data-testid="stats-cards"]')).not.toBeNull();
    expect(statsToggle().getAttribute("aria-expanded")).toBe("true");

    click(statsToggle());
    expect(container.querySelector('[data-testid="stats-cards"]')).toBeNull();
  });
});
