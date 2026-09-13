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
//
// Plus the level above the folders: Corpus d'équipe opens on the team's
// knowledge bases, and the document workspace mounts one level in.

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
  // Last `skip` each stats query was rendered with — the stats endpoints are
  // whole-corpus scans, so whether they run at all is the behaviour worth
  // pinning, and it is invisible in the DOM.
  corpusStatsSkip: true,
  fsStatsSkip: {} as Record<string, boolean>,
  // Lifecycle flags of the KF health probe that gates the whole page.
  kfProbe: { isLoading: false, isFetching: false, isUninitialized: false, isError: false },
  // The knowledge bases a contributor fills for this team, as
  // GET /knowledge-bases/instances returns them.
  knowledgeBases: [] as Record<string, unknown>[],
  knowledgeBasesUninitialized: false,
  knowledgeBasesRefetch: () => {},
  // Last `knowledgeBase` scope the document workspace was mounted with.
  workspaceScope: undefined as Record<string, unknown> | undefined,
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
// The team's knowledge bases are read here and handed down — the workspace
// below speaks to Knowledge Flow only.
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useListKnowledgeBaseInstancesControlPlaneV1KnowledgeBasesInstancesGetQuery: () => ({
    data: probe.knowledgeBases,
    isUninitialized: probe.knowledgeBasesUninitialized,
    refetch: probe.knowledgeBasesRefetch,
  }),
}));
vi.mock("../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  // The rollup reads the team's terminal ingestion history (#2384); no
  // history in these fixtures, so it falls back to the live task feed.
  useListTasksKnowledgeFlowV1TasksGetQuery: () => ({ data: undefined }),
  useListAllTagsKnowledgeFlowV1TagsGetQuery: () => probe.kfProbe,
  useGetCorpusTypeStatsKnowledgeFlowV1TagsStatsGetQuery: (_arg: unknown, options?: { skip?: boolean }) => {
    probe.corpusStatsSkip = options?.skip ?? false;
    return {
      data: { entries: [] },
      isLoading: false,
      isError: false,
      isUninitialized: probe.corpusStatsUninitialized,
      refetch: probe.corpusStatsRefetch,
    };
  },
  useTypeStatsKnowledgeFlowV1FsStatsPathGetQuery: (arg: { path: string }, options?: { skip?: boolean }) => {
    probe.fsStatsSkip[arg.path] = options?.skip ?? false;
    return { data: { entries: [] }, isLoading: false, isError: false };
  },
}));
vi.mock("./DocumentWorkspace/DocumentWorkspace.tsx", () => ({
  default: (props: { onDocumentsChanged?: () => void; knowledgeBase?: Record<string, unknown> }) => {
    probe.onDocumentsChanged = props.onDocumentsChanged;
    probe.workspaceScope = props.knowledgeBase;
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

/** Corpus d'équipe now opens on the list of knowledge bases. Every assertion
 *  below about the document workspace is about the level under one of them, so
 *  `render` walks into Fred's unless told to stay on the list. */
function render({ enter = true }: { enter?: boolean } = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<TeamResourcesPage />);
  });
  if (enter) openKnowledgeBase("rework.resources.knowledgeBases.nativeName");
}

/** Clicks the row for the knowledge base whose name cell reads `name`. A
 *  no-op when the list isn't showing (a blocked page, a non-corpus tab). */
function openKnowledgeBase(name: string) {
  const row = Array.from(container.querySelectorAll("button")).find((button) => button.textContent?.includes(name));
  if (row) click(row);
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
  probe.corpusStatsSkip = true;
  probe.fsStatsSkip = {};
  probe.kfProbe = { isLoading: false, isFetching: false, isUninitialized: false, isError: false };
  probe.knowledgeBases = [];
  probe.knowledgeBasesUninitialized = false;
  probe.knowledgeBasesRefetch = vi.fn();
  probe.workspaceScope = undefined;
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

  // The folder-creation form creates a knowledge base instance through the
  // control plane, but the only change signal that comes back out of the
  // workspace is a Knowledge Flow tag refetch — which cannot invalidate this
  // page's control-plane cache entry. Without this the just-connected base is
  // missing from the list, and its library shows inside Fred's own base as an
  // ordinary folder with every action offered over it, until a page reload.
  it("refetches the knowledge bases so a just-connected one is not left out of the list", () => {
    render();

    probe.onDocumentsChanged?.();
    expect(probe.knowledgeBasesRefetch).toHaveBeenCalledOnce();
  });

  it("does not call the knowledge-bases refetch while that query has not started yet", () => {
    // Skipped entirely in a personal space, where it never starts.
    probe.knowledgeBasesUninitialized = true;
    render();

    expect(() => probe.onDocumentsChanged?.()).not.toThrow();
    expect(probe.knowledgeBasesRefetch).not.toHaveBeenCalled();
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

  it("does not query the corpus stats until the cards are opened", () => {
    // The endpoint walks every library the user can read and every document in
    // each of them; running it on mount scanned the whole corpus for a panel
    // nobody had opened.
    render();
    expect(probe.corpusStatsSkip).toBe(true);

    click(statsToggle());
    expect(probe.corpusStatsSkip).toBe(false);

    click(statsToggle());
    expect(probe.corpusStatsSkip).toBe(true);
  });

  it("queries only the open tab's stats source", () => {
    render();
    click(statsToggle());

    // "Mon espace" and "Espace partagé" both read /fs stats, on different roots.
    expect(probe.corpusStatsSkip).toBe(false);
    expect(Object.values(probe.fsStatsSkip).every((skipped) => skipped)).toBe(true);

    click(tabButtons()[1]);
    expect(probe.corpusStatsSkip).toBe(true);
    expect(probe.fsStatsSkip["teams/team-1/users/u-1"]).toBe(false);
    expect(probe.fsStatsSkip["teams/team-1/shared"]).toBe(true);
  });
});

// The first level of Corpus d'équipe is the team's knowledge bases, not its
// folders: Fred's own next to every library a contributor fills. The folder
// view is unchanged — it simply mounts one level in, scoped to the base that
// was opened.
describe("TeamResourcesPage knowledge bases", () => {
  const localFolder = {
    id: "kb-1",
    library_id: "lib-local",
    library_name: "Local-2",
    definition_name: "GitHub",
    definition_id: "some.contributor.local-folder",
  };

  function rowNames(): string[] {
    return Array.from(container.querySelectorAll("button"))
      .map((button) => button.textContent ?? "")
      .filter((text) => text.includes("knowledgeBases.nativeName") || text.includes("Local-2"));
  }

  it("lists Fred's knowledge base and every contributed one, before any folder", () => {
    probe.knowledgeBases = [localFolder];
    render({ enter: false });

    expect(container.querySelector('[data-testid="panel-resources"]')).toBeNull();
    expect(rowNames()).toHaveLength(2);
    expect(container.textContent).toContain("rework.resources.knowledgeBases.nativeName");
    expect(container.textContent).toContain("Local-2");
  });

  it("badges Fred's with a Fred concept and a contributed one with the name it declared", () => {
    probe.knowledgeBases = [localFolder];
    render({ enter: false });

    expect(container.textContent).toContain("rework.resources.knowledgeBases.manualDeposit");
    // Straight from the data — no mapping from "GitHub" to anything this
    // frontend knows, which is what lets the next contributor publish
    // something nobody here has heard of.
    expect(container.textContent).toContain("GitHub");
    expect(container.textContent).toContain("rework.resources.knowledgeBases.readOnly");
  });

  it("hands Fred's own base the contributed libraries so its tree can leave them out", () => {
    probe.knowledgeBases = [localFolder];
    render();

    expect(container.querySelector('[data-testid="panel-resources"]')).not.toBeNull();
    expect(probe.workspaceScope).toMatchObject({ kind: "native" });
    expect([...((probe.workspaceScope?.contributedLibraryIds as Set<string>) ?? [])]).toEqual(["lib-local"]);
  });

  it("roots the same workspace at the library when a contributed base is opened", () => {
    probe.knowledgeBases = [localFolder];
    render({ enter: false });
    openKnowledgeBase("Local-2");

    expect(container.querySelector('[data-testid="panel-resources"]')).not.toBeNull();
    expect(probe.workspaceScope).toMatchObject({ kind: "contributed", libraryId: "lib-local", label: "Local-2" });
  });

  it("returns to the list when the open base is gone from the instance list", () => {
    probe.knowledgeBases = [localFolder];
    render({ enter: false });
    openKnowledgeBase("Local-2");
    expect(container.querySelector('[data-testid="panel-resources"]')).not.toBeNull();

    probe.knowledgeBases = [];
    act(() => {
      root.render(<TeamResourcesPage />);
    });

    expect(container.querySelector('[data-testid="panel-resources"]')).toBeNull();
    expect(container.textContent).toContain("rework.resources.knowledgeBases.nativeName");
  });
});

describe("TeamResourcesPage health gate", () => {
  function rerender() {
    act(() => {
      root.render(<TeamResourcesPage />);
    });
  }

  it("blocks the page until the probe has answered once", () => {
    probe.kfProbe = { isLoading: true, isFetching: true, isUninitialized: false, isError: false };
    render();
    expect(container.querySelector('[data-testid="panel-resources"]')).toBeNull();
  });

  it("keeps the workspace mounted through a background revalidation", () => {
    // The workspace owns the folder you are standing in, its loaded document
    // pages and its resolved folder sizes. Sending the page back to a spinner
    // on a refetch threw all of that away — and, with no subscribers left,
    // dropped its queries' cache entries too, so everything reloaded.
    render();
    const panel = container.querySelector('[data-testid="panel-resources"]');
    expect(panel).not.toBeNull();

    probe.kfProbe = { isLoading: false, isFetching: true, isUninitialized: false, isError: false };
    rerender();

    // Same DOM node, not a fresh one: a remount would have replaced it.
    expect(container.querySelector('[data-testid="panel-resources"]')).toBe(panel);
  });

  it("shows the service notice once a failed probe has settled", () => {
    probe.kfProbe = { isLoading: false, isFetching: false, isUninitialized: false, isError: true };
    render();
    expect(container.querySelector('[data-testid="panel-resources"]')).toBeNull();
  });
});
