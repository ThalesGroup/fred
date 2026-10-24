// @vitest-environment jsdom

import { beforeEach, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({
  dispatch: vi.fn(),
  responses: [] as Array<Record<string, unknown>>,
  writes: [] as Array<Record<string, unknown>>,
}));

vi.mock("../common/store", () => ({ store: { dispatch: mock.dispatch } }));
vi.mock("../slices/controlPlane/controlPlaneOpenApi", () => ({
  controlPlaneApi: {
    endpoints: {
      getMyPreferencesControlPlaneV1UsersMePreferencesGet: { initiate: () => ({ operation: "get" }) },
      patchMyPreferencesControlPlaneV1UsersMePreferencesPatch: {
        initiate: (argument: { patchUserPreferences: Record<string, unknown> }) => ({
          operation: "patch",
          body: argument.patchUserPreferences,
        }),
      },
    },
  },
}));

import { initializeUserPreferences, readLegacyPreferences, saveUserPreference } from "./userPreferences";

beforeEach(() => {
  localStorage.clear();
  mock.responses = [];
  mock.writes = [];
  mock.dispatch.mockReset();
  mock.dispatch.mockImplementation((action: { operation: string; body?: Record<string, unknown> }) => {
    if (action.operation === "get") return { unwrap: async () => mock.responses.shift(), unsubscribe: vi.fn() };
    mock.writes.push(action.body ?? {});
    return { unwrap: async () => ({ initialized: true, ...action.body }), reset: vi.fn() };
  });
});

it("imports valid legacy choices once without importing pane widths", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", JSON.stringify("acme"));
  localStorage.setItem("localHook:ApplicationContextProvider.themeMode", JSON.stringify("dark"));
  localStorage.setItem("localHook:team-wiki:rail:width", JSON.stringify(450));
  localStorage.setItem("localHook:inline-drawer:capability-side-panel:width", JSON.stringify(180));
  localStorage.setItem("localHook:import-panel:width", JSON.stringify(-2));
  localStorage.setItem("fred.teamSortMode", "alpha");
  localStorage.setItem("i18nextLng", "fr");
  expect(readLegacyPreferences()).toMatchObject({
    ui_theme_id: "acme",
    theme_mode: "dark",
    language: "fr",
    team_sort_mode: "alpha",
  });
  expect(readLegacyPreferences()).not.toHaveProperty("pane_widths");
  mock.responses.push({ initialized: false });
  await initializeUserPreferences("alice");
  expect(mock.writes).toHaveLength(1);
  expect(mock.writes[0]).toMatchObject({ ui_theme_id: "acme", team_sort_mode: "alpha" });
  expect(localStorage.getItem("fred.usersPreferences.legacyImported")).toBe("1");
});

it("does not import a language synthesized by the detector on a clean browser", () => {
  expect(readLegacyPreferences().language).toBeUndefined();
});

it("uses each account's server record instead of the previous account's browser keys", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", JSON.stringify("cloud"));
  mock.responses.push({ initialized: true, ui_theme_id: "cobalt", theme_mode: "dark" });
  await initializeUserPreferences("alice");
  expect(JSON.parse(localStorage.getItem("localHook:ApplicationContextProvider.uiTheme")!)).toBe("cobalt");
  mock.responses.push({ initialized: true, ui_theme_id: "pebble", theme_mode: "light" });
  await initializeUserPreferences("bob");
  expect(JSON.parse(localStorage.getItem("localHook:ApplicationContextProvider.uiTheme")!)).toBe("pebble");
  expect(mock.writes).toHaveLength(0);
});

it("restores all display choices after browser storage is cleared", async () => {
  mock.responses.push({
    initialized: true,
    ui_theme_id: "cobalt",
    theme_mode: "dark",
    language: "fr",
    sidebar_collapsed: true,
    team_sort_mode: "alpha",
    agent_sort: "updated_at:desc",
    trace_expanded: false,
  });
  await initializeUserPreferences("alice");
  expect(localStorage.getItem("localHook:ApplicationContextProvider.uiTheme")).toBe('"cobalt"');
  expect(localStorage.getItem("localHook:ApplicationContextProvider.isSidebarCollapsed")).toBe("true");
  expect(localStorage.getItem("fred.teamSortMode")).toBe("alpha");
  expect(localStorage.getItem("fred.agentSort")).toBe("updated_at:desc");
  expect(localStorage.getItem("localHook:chatTraceExpanded")).toBe("false");
  expect(localStorage.getItem("localHook:import-panel:width")).toBeNull();
  expect(mock.writes).toHaveLength(0);
});

it("leaves a pane width in localStorage when server preferences hydrate", async () => {
  localStorage.setItem("localHook:import-panel:width", "540");
  mock.responses.push({ initialized: true, ui_theme_id: "cobalt" });
  await initializeUserPreferences("alice");
  expect(localStorage.getItem("localHook:import-panel:width")).toBe("540");
  expect(mock.writes).toHaveLength(0);
});

it("keeps legacy data eligible for import when the first server write fails", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", '"cloud"');
  mock.responses.push({ initialized: false });
  mock.dispatch.mockImplementationOnce(() => ({ unwrap: async () => ({ initialized: false }), unsubscribe: vi.fn() }));
  mock.dispatch.mockImplementationOnce(() => ({
    unwrap: async () => {
      throw new Error("offline");
    },
    reset: vi.fn(),
  }));
  await initializeUserPreferences("alice");
  expect(localStorage.getItem("fred.usersPreferences.legacyImported")).toBeNull();
  expect(JSON.parse(localStorage.getItem("fred.usersPreferences.pendingLegacy:alice")!)).toMatchObject({
    ui_theme_id: "cloud",
  });
  expect(localStorage.getItem("localHook:ApplicationContextProvider.uiTheme")).toBe("null");
});

it("preserves legacy data for a later import when the initial server read fails", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", '"cloud"');
  mock.dispatch.mockImplementationOnce(() => ({
    unwrap: async () => {
      throw new Error("offline");
    },
    unsubscribe: vi.fn(),
  }));
  await initializeUserPreferences("alice");
  expect(JSON.parse(localStorage.getItem("fred.usersPreferences.pendingLegacy:alice")!)).toMatchObject({
    ui_theme_id: "cloud",
  });
  expect(localStorage.getItem("localHook:ApplicationContextProvider.uiTheme")).toBe("null");
  expect(localStorage.getItem("fred.usersPreferences.legacyImported")).toBeNull();
  mock.responses.push({ initialized: false });
  await initializeUserPreferences("alice");
  expect(mock.writes).toEqual([{ ui_theme_id: "cloud" }]);
  expect(localStorage.getItem("fred.usersPreferences.pendingLegacy:alice")).toBeNull();
});

it("does not let another account consume a pending legacy import", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", '"cloud"');
  mock.dispatch.mockImplementationOnce(() => ({
    unwrap: async () => {
      throw new Error("offline");
    },
    unsubscribe: vi.fn(),
  }));
  await initializeUserPreferences("alice");
  mock.responses.push({ initialized: false });
  await initializeUserPreferences("bob");
  expect(mock.writes).toHaveLength(0);
  expect(localStorage.getItem("fred.usersPreferences.legacyImportOwner")).toBe("alice");
  mock.responses.push({ initialized: false });
  await initializeUserPreferences("alice");
  expect(mock.writes).toEqual([{ ui_theme_id: "cloud" }]);
});

it("sends rapid updates in user action order", async () => {
  mock.responses.push({ initialized: true });
  await initializeUserPreferences("alice");
  let finishFirst!: (value: unknown) => void;
  mock.dispatch.mockImplementation((action: { operation: string; body?: Record<string, unknown> }) => {
    if (action.operation !== "patch") throw new Error("unexpected request");
    mock.writes.push(action.body ?? {});
    return {
      unwrap: () =>
        mock.writes.length === 1
          ? new Promise((resolve) => {
              finishFirst = resolve;
            })
          : Promise.resolve({ initialized: true, ...action.body }),
      reset: vi.fn(),
    };
  });
  const first = saveUserPreference({ theme_mode: "dark" });
  const second = saveUserPreference({ theme_mode: "light" });
  await Promise.resolve();
  expect(mock.writes).toHaveLength(1);
  finishFirst({ initialized: true, theme_mode: "dark" });
  await Promise.all([first, second]);
  expect(mock.writes).toEqual([{ theme_mode: "dark" }, { theme_mode: "light" }]);
});
