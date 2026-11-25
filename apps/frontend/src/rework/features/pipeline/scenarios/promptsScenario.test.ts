// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
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

vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "fixture",
    GetUserId: () => "reader",
    GetSessionIdentity: () => "fixture/reader",
    ensureFreshToken: async () => true,
  },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
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

  it.each(["wrong command", "wrong prompt", "separate matches", "absent"])(
    "requires the command and prompt to match in the same catalog entry: %s",
    async (mode) => {
      intercept = async (request) => {
        const url = new URL(request.url);
        const created = prompts.get(CREATED_PROMPT);
        if (request.method !== "GET" || url.pathname !== `${basePath}/prompts` || !created) return;
        const match = promptSummaryFixture(created);
        const wrongCommand = { ...match, logical_name: "unrelated-command" };
        const wrongPrompt = { ...match, prompt_id: OTHER_PROMPT };
        return page(
          mode === "wrong command"
            ? [wrongCommand]
            : mode === "wrong prompt"
              ? [wrongPrompt]
              : mode === "separate matches"
                ? [wrongCommand, wrongPrompt]
                : [],
          url,
        );
      };
      const reports = await run();
      expect(reports.status("prompt-command")).toBe("failed");
      expect(reports.status("delete-prompt")).toBe("passed");
      expect(reports.status("delete-category")).toBe("passed");
      expectOnlyExistingData();
    },
  );

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
