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
      getMyPreferences: { initiate: () => ({ operation: "get" }) },
      patchMyPreferences: {
        initiate: (argument: { patchUserPreferences: Record<string, unknown> }) => ({
          operation: "patch",
          body: argument.patchUserPreferences,
        }),
      },
    },
  },
}));

import {
  getCurrentUserPreferences,
  initializeUserPreferences,
  persistUserPreference,
  saveUserPreference,
  setCurrentUserPreferences,
} from "./userPreferences";

beforeEach(() => {
  localStorage.clear();
  setCurrentUserPreferences({});
  mock.responses = [];
  mock.writes = [];
  mock.dispatch.mockReset();
  mock.dispatch.mockImplementation((action: { operation: string; body?: Record<string, unknown> }) => {
    if (action.operation === "get") return { unwrap: async () => mock.responses.shift(), unsubscribe: vi.fn() };
    mock.writes.push(action.body ?? {});
    return { unwrap: async () => ({ initialized: true, ...action.body }), reset: vi.fn() };
  });
});

it("uses database defaults without importing retained browser choices", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", JSON.stringify("acme"));
  localStorage.setItem("localHook:ApplicationContextProvider.themeMode", JSON.stringify("dark"));
  localStorage.setItem("localHook:team-wiki:rail:width", JSON.stringify(450));
  localStorage.setItem("fred.teamSortMode", "alpha");
  localStorage.setItem("i18nextLng", "fr");
  mock.responses.push({ initialized: false });
  expect(await initializeUserPreferences("alice")).toEqual({ initialized: false });
  expect(mock.writes).toHaveLength(0);
  expect(getCurrentUserPreferences().ui_theme_id).toBeUndefined();
  expect(getCurrentUserPreferences().theme_mode).toBeUndefined();
  expect(getCurrentUserPreferences().team_sort_mode).toBeUndefined();
  expect(localStorage.getItem("localHook:ApplicationContextProvider.uiTheme")).toBe('"acme"');
  expect(localStorage.getItem("fred.teamSortMode")).toBe("alpha");
  expect(localStorage.getItem("localHook:team-wiki:rail:width")).toBe("450");
});

it("uses defaults without a subject instead of retained browser choices", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", '"cloud"');
  expect(await initializeUserPreferences(null)).toEqual({});
  expect(getCurrentUserPreferences().ui_theme_id).toBeUndefined();
  expect(mock.dispatch).not.toHaveBeenCalled();
});

it("uses each account's server record instead of the previous account's browser keys", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", JSON.stringify("cloud"));
  mock.responses.push({ initialized: true, ui_theme_id: "cobalt", theme_mode: "dark" });
  await initializeUserPreferences("alice");
  expect(getCurrentUserPreferences().ui_theme_id).toBe("cobalt");
  mock.responses.push({ initialized: true, ui_theme_id: "pebble", theme_mode: "light" });
  await initializeUserPreferences("bob");
  expect(getCurrentUserPreferences().ui_theme_id).toBe("pebble");
  expect(localStorage.getItem("localHook:ApplicationContextProvider.uiTheme")).toBe('"cloud"');
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
  });
  await initializeUserPreferences("alice");
  expect(getCurrentUserPreferences().ui_theme_id).toBe("cobalt");
  expect(getCurrentUserPreferences().sidebar_collapsed).toBe(true);
  expect(getCurrentUserPreferences().team_sort_mode).toBe("alpha");
  expect(getCurrentUserPreferences().agent_sort).toBe("updated_at:desc");
  expect(localStorage.getItem("localHook:ApplicationContextProvider.uiTheme")).toBeNull();
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

it("uses defaults after a failed read without consulting browser choices or a cached record", async () => {
  localStorage.setItem("localHook:ApplicationContextProvider.uiTheme", '"cloud"');
  localStorage.setItem("fred.usersPreferences:alice", JSON.stringify({ initialized: true, ui_theme_id: "cobalt" }));
  mock.dispatch.mockImplementationOnce(() => ({
    unwrap: async () => {
      throw new Error("offline");
    },
    unsubscribe: vi.fn(),
  }));
  expect(await initializeUserPreferences("alice")).toEqual({});
  expect(getCurrentUserPreferences().ui_theme_id).toBeUndefined();
  expect(mock.writes).toHaveLength(0);
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

it("rolls back an unsaved choice while leaving legacy browser values untouched", async () => {
  mock.responses.push({ initialized: true, sidebar_collapsed: false });
  await initializeUserPreferences("alice");
  localStorage.setItem("localHook:ApplicationContextProvider.isSidebarCollapsed", "true");
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  mock.dispatch.mockImplementationOnce(() => ({ unwrap: async () => Promise.reject({ status: 403 }), reset: vi.fn() }));
  persistUserPreference({ sidebar_collapsed: true });
  expect(getCurrentUserPreferences().sidebar_collapsed).toBe(true);
  await vi.waitFor(() => expect(getCurrentUserPreferences().sidebar_collapsed).toBe(false));
  expect(localStorage.getItem("localHook:ApplicationContextProvider.isSidebarCollapsed")).toBe("true");
  expect(error).toHaveBeenCalledOnce();
  error.mockRestore();
});

it("retries one transient failure before keeping a durable choice", async () => {
  mock.responses.push({ initialized: true, team_sort_mode: "recent" });
  await initializeUserPreferences("alice");
  mock.dispatch.mockImplementationOnce(() => ({ unwrap: async () => Promise.reject({ status: 503 }), reset: vi.fn() }));
  persistUserPreference({ team_sort_mode: "alpha" });
  await vi.waitFor(() => expect(mock.writes).toEqual([{ team_sort_mode: "alpha" }]));
  expect(getCurrentUserPreferences().team_sort_mode).toBe("alpha");
});

it("does not roll back a newer choice when an older save fails", async () => {
  mock.responses.push({ initialized: true, agent_sort: "name" });
  await initializeUserPreferences("alice");
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  let rejectFirst!: (reason: unknown) => void;
  mock.dispatch.mockImplementationOnce(() => ({
    unwrap: () => new Promise((_, reject) => (rejectFirst = reject)),
    reset: vi.fn(),
  }));
  persistUserPreference({ agent_sort: "created_at:desc" });
  await vi.waitFor(() => expect(rejectFirst).toBeDefined());
  persistUserPreference({ agent_sort: "updated_at:desc" });
  rejectFirst({ status: 403 });
  await vi.waitFor(() => expect(mock.writes).toEqual([{ agent_sort: "updated_at:desc" }]));
  expect(getCurrentUserPreferences().agent_sort).toBe("updated_at:desc");
  error.mockRestore();
});

it("returns to the database value when two queued choices both fail", async () => {
  mock.responses.push({ initialized: true, agent_sort: "name" });
  await initializeUserPreferences("alice");
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  mock.dispatch.mockImplementation((action: { body?: Record<string, unknown> }) => {
    mock.writes.push(action.body ?? {});
    return { unwrap: async () => Promise.reject({ status: 403 }), reset: vi.fn() };
  });
  persistUserPreference({ agent_sort: "created_at:desc" });
  persistUserPreference({ agent_sort: "updated_at:desc" });
  await vi.waitFor(() => expect(error).toHaveBeenCalledTimes(2));
  expect(mock.writes).toEqual([{ agent_sort: "created_at:desc" }, { agent_sort: "updated_at:desc" }]);
  expect(getCurrentUserPreferences().agent_sort).toBe("name");
  error.mockRestore();
});

it("retries an older choice before sending a newer choice", async () => {
  mock.responses.push({ initialized: true, agent_sort: "name" });
  await initializeUserPreferences("alice");
  let attempts = 0;
  mock.dispatch.mockImplementation((action: { body?: Record<string, unknown> }) => {
    mock.writes.push(action.body ?? {});
    attempts++;
    return {
      unwrap: async () => {
        if (attempts === 1) throw { status: 503 };
      },
      reset: vi.fn(),
    };
  });
  persistUserPreference({ agent_sort: "created_at:desc" });
  persistUserPreference({ agent_sort: "updated_at:desc" });
  await vi.waitFor(() => expect(mock.writes).toHaveLength(3));
  expect(mock.writes).toEqual([
    { agent_sort: "created_at:desc" },
    { agent_sort: "created_at:desc" },
    { agent_sort: "updated_at:desc" },
  ]);
  expect(getCurrentUserPreferences().agent_sort).toBe("updated_at:desc");
});
