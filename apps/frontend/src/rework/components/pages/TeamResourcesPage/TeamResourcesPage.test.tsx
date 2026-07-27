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
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));
vi.mock("react-router-dom", () => ({ useParams: () => ({ teamId: "team-1" }) }));
vi.mock("../../../../hooks/useFrontendBootstrap.ts", () => ({
  useFrontendBootstrap: () => ({ activeTeam: probe.isPersonalTeam ? { id: "team-1" } : { id: "other-team" } }),
}));
vi.mock("../../../../security/KeycloakService.ts", () => ({ KeyCloakService: { GetUserId: () => "u-1" } }));
vi.mock("@shared/utils/teamId.ts", () => ({
  isPersonalTeamId: () => probe.isPersonalTeam,
  personalTeamId: (uid: string) => `personal-${uid}`,
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: probe.team }),
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
  }),
  useTypeStatsKnowledgeFlowV1FsStatsPathGetQuery: () => ({ data: { entries: [] }, isLoading: false, isError: false }),
}));
vi.mock("./DocumentWorkspace/DocumentWorkspace.tsx", () => ({ default: () => <div data-testid="panel-resources" /> }));
vi.mock("./TeamFilesystemBrowser/TeamFilesystemBrowser.tsx", () => ({
  default: (props: { root: string }) => <div data-testid="panel-fs">{props.root}</div>,
}));
vi.mock("./AgentFilesystemBrowser/AgentFilesystemBrowser.tsx", () => ({
  default: () => <div data-testid="panel-agents" />,
}));
vi.mock("./FsRootMeta/FsRootMeta.tsx", () => ({ default: () => null }));
vi.mock("./FsRootAddMenu/FsRootAddMenu.tsx", () => ({ default: () => null }));
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
