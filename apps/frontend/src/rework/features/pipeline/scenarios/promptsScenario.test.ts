// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CreatePromptRequest,
  MySpace,
  Prompt,
  PromptCategory,
  UpdatePromptRequest,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { promptFixture, promptSummaryFixture } from "../../../components/pages/PromptsPage/weaverPromptFixtures";
import { SPACES } from "../../../components/pages/TeamAgentsPage/weaverAgentFixtures";
import { usePromptsDeps } from "../deps/prompts";
import { collect } from "./fakePlatform";
import { promptsScenario, type PromptsDeps } from "./promptsScenario";

// Keep the actual page, family wiring, runner and prompt HTTP client. Other families
// are outside this test: their dependencies must not require legacy services.
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../components/pages/admin/SelfTestPage/AuthorizationExtras", () => ({
  AuthorizationExtras: () => null,
}));
vi.mock("../usePipelineRun", () => ({ usePipelineDeps: () => ({ teamId: "personal-reader" }) }));
vi.mock("../useAuthzProbeRun", () => ({
  useAuthzProbeRun: () => ({ steps: [], isRunning: false, runIdentity: async () => {} }),
}));
vi.mock("../deps/platform", () => ({ usePlatformDeps: () => ({}) }));
vi.mock("../deps/authorization", () => ({ useAuthorizationDeps: () => ({}) }));
vi.mock("../deps/knowledge", () => ({ useKnowledgeDeps: () => ({}) }));
vi.mock("../deps/agents", () => ({ useAgentsDeps: () => ({}) }));
vi.mock("../deps/conversations", () => ({ useConversationsDeps: () => ({}) }));
vi.mock("../deps/teams", () => ({ useTeamsDeps: () => ({}) }));
vi.mock("../deps/security", () => ({ useSecurityDeps: () => ({}) }));
vi.mock("../deps/observability", () => ({ useObservabilityDeps: () => ({}) }));
vi.mock("./platformScenario", () => ({ platformScenario: async () => {} }));
vi.mock("./authorizationScenario", () => ({ authorizationScenario: async () => {} }));
vi.mock("./knowledgeScenario", () => ({ knowledgeScenario: async () => {} }));
vi.mock("./agentsScenario", () => ({ agentsScenario: async () => {} }));
vi.mock("./conversationsScenario", () => ({ conversationsScenario: async () => {} }));
vi.mock("./teamsScenario", () => ({ teamsScenario: async () => {} }));
vi.mock("./securityScenario", () => ({ securityScenario: async () => {} }));
vi.mock("./observabilityScenario", () => ({ observabilityScenario: async () => {} }));
vi.mock("./webResearchScenario", () => ({ webResearchScenario: async () => {} }));

vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "fixture",
    GetUserId: () => "reader",
    GetSessionIdentity: () => "fixture/reader",
    ensureFreshToken: async () => true,
  },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
import SelfTestPage, { PromptsSelfTestPage } from "../../../components/pages/admin/SelfTestPage/SelfTestPage";
import { useSelfTestFamilies } from "../families";
import { enhancedControlPlaneApi as api } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const NativeRequest = globalThis.Request;
const SPACE_ID = SPACES[0].id;
const OTHER_PROMPT = "10000000-0000-0000-0000-000000000001";
const CREATED_PROMPT = "10000000-0000-0000-0000-000000000002";
const OTHER_CATEGORY = "20000000-0000-0000-0000-000000000001";
const CREATED_CATEGORY = "20000000-0000-0000-0000-000000000002";
const basePath = `/control-plane/v1/spaces/${SPACE_ID}`;
const json = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const page = (items: unknown[], url: URL) =>
  json({
    items: url.searchParams.has("after") ? items.slice(1) : items.slice(0, 1),
    next_cursor: !url.searchParams.has("after") && items.length > 1 ? OTHER_PROMPT : null,
  });
let root: Root;
let container: HTMLDivElement;
let store: ReturnType<typeof makeStore>;
let spaces: MySpace[];
let prompts: Map<string, Prompt>;
let categories: Map<string, PromptCategory>;
let calls: Array<{ method: string; path: string; body: unknown }>;
let intercept: (request: Request) => Promise<Response | undefined>;
const makeStore = (onRefusal?: () => void) =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (defaults) =>
      defaults().concat(api.middleware, () => (next) => (action) => {
        const result = next(action);
        if (api.endpoints.getPrompt.matchRejected(action) && !action.meta.condition) onRefusal?.();
        return result;
      }),
  });

// HTTP boundary only is simulated: the scenario, hook, generated builders,
// RTK middleware and catalog traversal all execute their real implementations.
async function serve(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  if (path === "/control-plane/v1/me/spaces") return json(spaces);
  if (path === `/control-plane/v1/spaces/${spaces.find((s) => s.id === SPACE_ID)?.organization_id}/marketplace/entries`)
    return page([], url);
  if (path === `${basePath}/prompt-categories`) {
    if (request.method === "GET") return page([...categories.values()], url);
    if (request.method === "POST") {
      const { name } = await request.json();
      const category = { id: CREATED_CATEGORY, space_id: SPACE_ID, name };
      categories.set(category.id, category);
      return json(category, 201);
    }
  }
  if (path.startsWith(`${basePath}/prompt-categories/`)) {
    const id = path.split("/").pop()!;
    if (request.method === "PATCH") {
      const category = { ...categories.get(id)!, ...(await request.json()) };
      categories.set(id, category);
      return json(category);
    }
    if (request.method === "DELETE") {
      if ([...prompts.values()].some((p) => p.category_id === id))
        return json({ code: "prompt_category_conflict" }, 409);
      categories.delete(id);
      return json(null, 204);
    }
  }
  if (path === `${basePath}/prompts`) {
    if (request.method === "GET")
      return page(
        [...prompts.values()].map((p) => promptSummaryFixture(p)),
        url,
      );
    if (request.method === "POST") {
      const body: CreatePromptRequest = await request.json();
      const prompt = promptFixture({ ...body, prompt_id: CREATED_PROMPT, space_id: SPACE_ID });
      prompts.set(prompt.prompt_id, prompt);
      return json(prompt, 201);
    }
  }
  if (path.startsWith(`${basePath}/prompts/`)) {
    const id = path.split("/")[6];
    const prompt = prompts.get(id);
    if (!prompt) return json({ detail: "not found" }, 404);
    if (path.endsWith("/favorite")) {
      prompt.is_favorite = request.method === "PUT";
      return json(null, 204);
    }
    if (request.method === "GET") return json(prompt);
    if (request.method === "PATCH") {
      const body: UpdatePromptRequest = await request.json();
      Object.assign(prompt, body);
      return json(prompt);
    }
    if (request.method === "DELETE") {
      prompts.delete(id);
      return json(null, 204);
    }
  }
  throw new Error(`Unexpected request: ${request.method} ${path}`);
}

beforeEach(() => {
  spaces = [{ ...SPACES[0], kind: "personal", personal_owner: "reader" }];
  prompts = new Map([
    [
      OTHER_PROMPT,
      promptFixture({ prompt_id: OTHER_PROMPT, display_name: "Existing prompt", category_id: OTHER_CATEGORY }),
    ],
  ]);
  categories = new Map([[OTHER_CATEGORY, { id: OTHER_CATEGORY, space_id: SPACE_ID, name: "Existing category" }]]);
  calls = [];
  intercept = async () => undefined;
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      calls.push({
        method: request.method,
        path: new URL(request.url).pathname + new URL(request.url).search,
        body: request.body ? await request.clone().json() : null,
      });
      return (await intercept(request.clone())) ?? serve(request);
    }),
  );
  store = makeStore();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  store.dispatch(api.util.resetApiState());
  vi.unstubAllGlobals();
});

async function run(spaceId: string | undefined = SPACE_ID, signal = new AbortController().signal) {
  let deps!: PromptsDeps;
  function Probe() {
    deps = usePromptsDeps(spaceId);
    return null;
  }
  await act(async () => root.render(createElement(Provider, { store, children: createElement(Probe) })));
  const reports = collect();
  await act(async () => promptsScenario(deps, reports.report, signal));
  return reports;
}
function expectOnlyExistingData() {
  expect([...prompts.keys()]).toEqual([OTHER_PROMPT]);
  expect([...categories.keys()]).toEqual([OTHER_CATEGORY]);
  expect(
    calls
      .filter((call) => call.method === "DELETE")
      .every((call) => call.path.includes(CREATED_PROMPT) || call.path.includes(CREATED_CATEGORY)),
  ).toBe(true);
}

describe("promptsScenario through Weaver requests", () => {
  it("preserves a refusal when concurrent invalidation starts another read before unwrap settles", async () => {
    let refreshed = false;
    store = makeStore(() => {
      if (!refreshed) {
        refreshed = true;
        store.dispatch(api.util.invalidateTags([{ type: "Prompts", id: `${SPACE_ID}:${CREATED_PROMPT}` }]));
      }
    });
    const reports = await run();
    expect(refreshed).toBe(true);
    expect(reports.steps.filter((step) => step.status !== "passed")).toEqual([]);
    expectOnlyExistingData();
  });

  it("keeps delayed catalog reads and the post-delete refusal valid across cache eviction", async () => {
    intercept = async (request) => {
      if (request.method === "GET") await new Promise((resolve) => setTimeout(resolve, 15));
      return undefined;
    };
    const reports = await run();
    expect(reports.steps.filter((step) => step.status !== "passed")).toEqual([]);
    expectOnlyExistingData();
  });

  it.each(["organization", "team", "project", "personal"] as const)(
    "uses the canonical %s space and cleans only its own UUIDs",
    async (kind) => {
      spaces[0].kind = kind;
      const reports = await run();
      expect(reports.steps.filter((s) => s.status !== "passed")).toEqual([]);
      expectOnlyExistingData();
      expect(calls.every((call) => !call.path.includes("/teams/") && !call.path.includes("/prompt-commands"))).toBe(
        true,
      );
      expect(
        calls
          .filter((call) => call.path.includes("/spaces/") && !call.path.includes("/marketplace/entries"))
          .every((call) => call.path.startsWith(`${basePath}/`)),
      ).toBe(true);
      const created = calls.find((call) => call.method === "POST" && call.path.endsWith("/prompts"))!
        .body as CreatePromptRequest;
      expect(created).toMatchObject({
        logical_name: expect.stringMatching(/^selftest-[a-z0-9]+$/),
        display_name: expect.stringContaining("Self-test prompt"),
        category_id: CREATED_CATEGORY,
      });
      expect(created).not.toHaveProperty("name");
      expect(created).not.toHaveProperty("command");
      const patch = calls.find((call) => call.method === "PATCH" && call.path.includes("/prompts/"))!;
      expect(patch.path).toBe(`${basePath}/prompts/${CREATED_PROMPT}`);
      expect(Object.keys(patch.body as object).sort()).toEqual(["display_name", "text"]);
      expect(calls).toContainEqual({
        method: "PUT",
        path: `${basePath}/prompts/${CREATED_PROMPT}/favorite`,
        body: null,
      });
      expect(calls).toContainEqual({
        method: "DELETE",
        path: `${basePath}/prompts/${CREATED_PROMPT}/favorite`,
        body: null,
      });
      expect(calls.some((call) => call.path.includes("/prompts?after="))).toBe(true);
      expect(calls.some((call) => call.path.includes("/prompt-categories?after="))).toBe(true);
      expect(calls.some((call) => call.path === "/control-plane/v1/spaces/org/marketplace/entries?kind=prompt")).toBe(
        true,
      );
      expect(reports.steps.find((step) => step.id === "prompt-command")?.detail).toBe(`/${created.logical_name}`);
    },
  );

  it.each(["", "personal", "personal-reader", "missing"])(
    "refuses an absent or noncanonical selection (%s) before any write",
    async (selection) => {
      expect((await run(selection)).status("prompt-space")).toBe("failed");
      expect(calls.every((call) => call.method === "GET")).toBe(true);
      expectOnlyExistingData();
    },
  );

  it("cleans both creations after the post-create read fails", async () => {
    let first = true;
    intercept = async (request) => {
      if (first && request.method === "GET" && request.url.endsWith(`/prompts/${CREATED_PROMPT}`)) {
        first = false;
        return json({}, 503);
      }
    };
    const reports = await run();
    expect(reports.status("create-prompt")).toBe("failed");
    expect(reports.status("delete-prompt")).toBe("passed");
    expect(reports.status("delete-category")).toBe("passed");
    expectOnlyExistingData();
  });

  it("does not reconcile or delete an existing prompt after a create conflict", async () => {
    intercept = async (request) =>
      request.method === "POST" && request.url.endsWith("/prompts") ? json({}, 409) : undefined;
    const reports = await run();
    expect(reports.status("create-prompt")).toBe("failed");
    expect(reports.status("delete-prompt")).toBe("skipped");
    expectOnlyExistingData();
  });

  it("reports failed cleanup without deleting unrelated data or hiding the assigned category conflict", async () => {
    intercept = async (request) =>
      request.method === "DELETE" && request.url.endsWith(`/prompts/${CREATED_PROMPT}`) ? json({}, 503) : undefined;
    const reports = await run();
    expect(reports.status("delete-prompt")).toBe("failed");
    expect(reports.status("delete-category")).toBe("failed");
    expect([...prompts.keys()]).toEqual([OTHER_PROMPT, CREATED_PROMPT]);
    expect([...categories.keys()]).toEqual([OTHER_CATEGORY, CREATED_CATEGORY]);
  });

  it("retains created ids for cleanup when cancellation arrives with the create response", async () => {
    const controller = new AbortController();
    intercept = async (request) => {
      if (request.method === "POST" && request.url.endsWith("/prompts")) {
        const result = await serve(request);
        controller.abort();
        return result;
      }
    };
    const reports = await run(SPACE_ID, controller.signal);
    expect(reports.status("prompt-update")).toBe("failed");
    expect(reports.status("delete-prompt")).toBe("passed");
    expectOnlyExistingData();
  });

  it.each(["ignored", "lost-category", "changed-command"])("detects an incorrect partial update: %s", async (mode) => {
    intercept = async (request) => {
      if (request.method === "PATCH" && request.url.includes("/prompts/")) {
        if (mode === "ignored") return json(prompts.get(CREATED_PROMPT));
        await serve(request);
        const prompt = prompts.get(CREATED_PROMPT)!;
        if (mode === "lost-category") prompt.category_id = null;
        else prompt.logical_name = "changed";
        return json(prompt);
      }
    };
    expect((await run()).status("prompt-update")).toBe("failed");
    expectOnlyExistingData();
  });

  it("detects a favorite that cannot be removed", async () => {
    intercept = async (request) =>
      request.method === "DELETE" && request.url.endsWith("/favorite") ? json(null, 204) : undefined;
    expect((await run()).status("favorite")).toBe("failed");
    expectOnlyExistingData();
  });

  it("does not accept a partial prompt catalog when its second page is denied", async () => {
    intercept = async (request) =>
      new URL(request.url).pathname.endsWith("/prompts") && new URL(request.url).searchParams.has("after")
        ? json({}, 403)
        : undefined;
    expect((await run()).status("prompt-command")).toBe("failed");
    expectOnlyExistingData();
  });

  it("respects a space write refusal without falling back to legacy or author rights", async () => {
    intercept = async (request) => (request.method === "POST" ? json({}, 403) : undefined);
    const reports = await run();
    expect(reports.status("create-category")).toBe("failed");
    expect(reports.status("create-prompt")).toBe("skipped");
    expectOnlyExistingData();
  });
});

const ORG_A = "30000000-0000-0000-0000-000000000001";
const ORG_B = "30000000-0000-0000-0000-000000000002";
function multipleOrganizations(kind: MySpace["kind"] = "personal") {
  const organizationId = kind === "organization" ? SPACE_ID : ORG_B;
  const target = { ...spaces[0], name: "Library", organization_id: organizationId, kind };
  spaces = [
    { ...target, id: ORG_A, kind: "organization", name: "Organization A", organization_id: ORG_A },
    { ...target, id: SPACES[1].id, kind: "personal", organization_id: ORG_A },
    ...(["organization", "team", "project", "personal"] as const).map((spaceKind, index) => {
      const id =
        spaceKind === kind
          ? SPACE_ID
          : spaceKind === "organization"
            ? ORG_B
            : `40000000-0000-0000-0000-00000000000${index}`;
      return {
        ...target,
        id,
        kind: spaceKind,
        name: spaceKind === "organization" ? "Organization B" : "Library",
        parent_id: spaceKind === "organization" ? null : organizationId,
        path: spaceKind === "organization" ? [id] : [organizationId, id],
        personal_owner: spaceKind === "personal" ? "reader" : null,
      };
    }),
  ];
}

async function mountLauncher() {
  await act(async () => root.render(createElement(Provider, { store, children: createElement(SelfTestPage) })));
  await act(async () => {
    await vi.waitFor(() => expect(api.endpoints.mySpaces.select()(store.getState()).status).toBe("fulfilled"));
  });
}
function spaceSelect() {
  return container.querySelector<HTMLButtonElement>('[data-family="prompts"] [aria-haspopup="listbox"]')!;
}
async function selectSpace(id: string) {
  await act(async () => spaceSelect().click());
  const option = Array.from(document.querySelectorAll<HTMLElement>('[role="option"]')).find((item) =>
    item.textContent?.includes(id),
  );
  expect(option, `space option ${id}`).toBeDefined();
  await act(async () => option!.click());
}
async function launch(all = false) {
  const button = all
    ? Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((item) =>
        item.textContent?.includes("rework.selftest.page.runAll"),
      )!
    : container.querySelector<HTMLButtonElement>('[data-family="prompts"] button')!;
  await act(async () => button.click());
}
async function waitForPromptEnd() {
  await vi.waitFor(async () => {
    await act(async () => {});
    expect(
      container.querySelector('[data-family="prompts"] [aria-label="rework.selftest.report.expand"]'),
    ).not.toBeNull();
    expect(spaceSelect().disabled).toBe(false);
  });
  await act(async () =>
    container
      .querySelector<HTMLButtonElement>('[data-family="prompts"] [aria-label="rework.selftest.report.expand"]')!
      .click(),
  );
}

describe("prompt selection from the real self-test launcher", () => {
  it.each([true, false])("guards the Weaver launcher with Control Plane authority (admin: %s)", async (admin) => {
    intercept = async (request) =>
      request.url.endsWith("/control-plane/v1/me")
        ? json({ platform_roles: admin ? ["platform_admin"] : [] })
        : undefined;
    await act(async () =>
      root.render(
        createElement(Provider, {
          store,
          children: createElement(MemoryRouter, { children: createElement(PromptsSelfTestPage) }),
        }),
      ),
    );
    await act(async () => {
      await vi.waitFor(() => expect(api.endpoints.me.select()(store.getState()).status).toBe("fulfilled"));
    });
    if (!admin) {
      expect(container.querySelectorAll("[data-family]")).toHaveLength(0);
      expect(calls.every((call) => call.method === "GET")).toBe(true);
      return;
    }
    await act(async () => {
      await vi.waitFor(() => expect(api.endpoints.mySpaces.select()(store.getState()).status).toBe("fulfilled"));
    });
    expect(container.querySelectorAll("[data-family]")).toHaveLength(1);
    await selectSpace(SPACE_ID);
    await launch(true);
    await waitForPromptEnd();
    expect(container.querySelector('[data-family="prompts"]')?.textContent).toContain(
      "rework.selftest.report.verified",
    );
    expectOnlyExistingData();
  });

  it.each(["organization", "team", "project", "personal"] as const)(
    "selects a %s UUID explicitly among multiple organizations",
    async (kind) => {
      multipleOrganizations(kind);
      await mountLauncher();
      expect(spaceSelect().textContent).toContain("spacePlaceholder");
      await selectSpace(SPACE_ID);
      expect(spaceSelect().textContent).toContain(
        kind === "organization" ? "Organization B / Organization B" : "Organization B / Library",
      );
      await launch();
      await waitForPromptEnd();
      expect(container.querySelector('[data-family="prompts"]')?.textContent).toContain(
        "rework.selftest.report.verified",
      );
      expect(calls.some((call) => call.method === "POST" && call.path === `${basePath}/prompts`)).toBe(true);
      expect(
        calls
          .filter((call) => call.path.includes("/spaces/"))
          .every(
            (call) =>
              call.path.startsWith(`${basePath}/`) ||
              call.path ===
                `/control-plane/v1/spaces/${spaces.find((space) => space.id === SPACE_ID)!.organization_id}/marketplace/entries?kind=prompt`,
          ),
      ).toBe(true);
      expectOnlyExistingData();
    },
  );

  it.each([false, true])("does not infer a space without selection (Run all: %s)", async (all) => {
    multipleOrganizations();
    await mountLauncher();
    await launch(all);
    await waitForPromptEnd();
    expect(container.textContent).toContain("Select a Weaver space in the Prompts section");
    expect(calls.every((call) => call.method === "GET")).toBe(true);
    expectOnlyExistingData();
  });

  it("passes the explicit selection through Run all and locks the picker until cleanup ends", async () => {
    multipleOrganizations();
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    intercept = async (request) => {
      if (request.method === "DELETE" && request.url.endsWith(`/prompts/${CREATED_PROMPT}`)) await held;
      return undefined;
    };
    await mountLauncher();
    await selectSpace(SPACE_ID);
    await launch(true);
    await act(async () => {
      await vi.waitFor(() =>
        expect(calls.some((call) => call.method === "DELETE" && call.path.endsWith(CREATED_PROMPT))).toBe(true),
      );
    });
    expect(spaceSelect().disabled).toBe(true);
    await act(async () => spaceSelect().click());
    expect(document.querySelector('[role="option"]')).toBeNull();
    expect(spaceSelect().textContent).toContain("Organization B / Library");
    await act(async () => release());
    await waitForPromptEnd();
    expectOnlyExistingData();
  });

  it("keeps the admitted UUID for operations and cleanup even if the family selection changes", async () => {
    multipleOrganizations();
    let selected = SPACE_ID;
    let family!: ReturnType<typeof useSelfTestFamilies>[number];
    function LauncherProbe() {
      family = useSelfTestFamilies(selected).find((item) => item.id === "prompts")!;
      return null;
    }
    const render = () => root.render(createElement(Provider, { store, children: createElement(LauncherProbe) }));
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    intercept = async (request) => {
      if (request.method === "POST" && request.url.endsWith("/prompt-categories")) await held;
      return undefined;
    };
    await act(async () => render());
    let running!: Promise<void>;
    await act(async () => {
      running = family.run.start();
    });
    await act(async () => {
      await vi.waitFor(() => expect(calls.some((call) => call.method === "POST")).toBe(true));
    });
    selected = SPACES[1].id;
    await act(async () => render());
    await act(async () => {
      release();
      await running;
    });
    expect(family.run.steps.filter((step) => step.status !== "passed")).toEqual([]);
    expect(calls.filter((call) => call.method !== "GET").every((call) => call.path.startsWith(`${basePath}/`))).toBe(
      true,
    );
    expectOnlyExistingData();
  });

  it("rechecks the selected membership and never substitutes another space", async () => {
    multipleOrganizations();
    await mountLauncher();
    await selectSpace(SPACE_ID);
    spaces = spaces.filter((space) => space.id !== SPACE_ID);
    await launch();
    await waitForPromptEnd();
    expect(container.textContent).toContain("no longer available");
    expect(calls.every((call) => call.method === "GET")).toBe(true);
    expectOnlyExistingData();
  });

  it("reports the server's write refusal for an explicitly selected space", async () => {
    multipleOrganizations();
    await mountLauncher();
    await selectSpace(SPACE_ID);
    intercept = async (request) => (request.method === "POST" ? json({}, 403) : undefined);
    await launch();
    await waitForPromptEnd();
    expect(container.querySelector('[data-family="prompts"]')?.textContent).toContain("HTTP 403");
    expect(calls.filter((call) => call.method === "POST").map((call) => call.path)).toEqual([
      `${basePath}/prompt-categories`,
    ]);
    expect(calls.some((call) => call.method === "DELETE")).toBe(false);
    expectOnlyExistingData();
  });
});
