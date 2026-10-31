// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { useComposerCommands } from "../../rework/components/pages/ManagedChatPage/useComposerCommands";
import { afterEach, describe, expect, it, vi } from "vitest";
import { promptFixture, promptSummaryFixture } from "../../rework/components/pages/PromptsPage/weaverPromptFixtures";
import { configureStore } from "@reduxjs/toolkit";
import type { ImportBlueprintApiResponse, MeApiResponse, MySpacesApiResponse } from "./controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../legacyControlPlane/legacyControlPlaneOpenApi", () => ({
  useGetAgentInstanceSkillsQuery: (_args: unknown, options: { skip: boolean }) => {
    expect(options.skip).toBe(true);
    return { isFetching: false, isError: false };
  },
}));
vi.mock("../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "operator-token",
    GetUserId: vi.fn(() => "operator" as string | null),
    GetSessionIdentity: vi.fn(() => "fixture/operator"),
    ensureFreshToken: vi.fn().mockResolvedValue(true),
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));

import { KeyCloakService } from "../../security/KeycloakService";

import * as managerApi from "./controlPlaneApiEnhancements";
import { enhancedControlPlaneApi as api } from "./controlPlaneApiEnhancements";

const NativeRequest = globalThis.Request;
const report: ImportBlueprintApiResponse = {
  identities_resolved: 15,
  identities_created: 15,
  spaces_reconciled: 4,
  grants_acknowledged: 44,
};

function setup(reply: unknown, status = 200) {
  // Browser Request resolves same-origin paths; Node's implementation needs a base.
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  const fetch = vi.fn(
    async (_request: Request) =>
      new Response(JSON.stringify(reply), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetch);
  const store = configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (defaults) => defaults().concat(api.middleware),
  });
  return { store, fetch };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("generated control-plane client", () => {
  it("sends the binary ZIP as one multipart field with the operator bearer and returns the completed report", async () => {
    const { store, fetch } = setup(report);
    const bytes = new Uint8Array([0x50, 0x4b, 3, 4, 0, 255]);
    const result = await store
      .dispatch(
        api.endpoints.importBlueprint.initiate({
          provisioningUpload: { file: new File([bytes], "demo.zip", { type: "application/zip" }) },
        }),
      )
      .unwrap();
    expect(result).toEqual(report);
    expect(fetch).toHaveBeenCalledTimes(1);
    const request = fetch.mock.calls[0][0];
    expect(request.url).toBe("http://localhost/control-plane/v1/import-export/import");
    expect(request.method).toBe("POST");
    expect(request.headers.get("authorization")).toBe("Bearer operator-token");
    expect(request.headers.get("content-type")).toMatch(/^multipart\/form-data; boundary=/);
    const form = await request.formData();
    expect([...form.keys()]).toEqual(["file"]);
    const file = form.get("file") as File;
    expect(file.name).toBe("demo.zip");
    expect(new Uint8Array(await file.arrayBuffer())).toEqual(bytes);
    store.dispatch(api.util.resetApiState());
  });

  it("preserves a failed import's safe detail without inventing success or retrying", async () => {
    const { store, fetch } = setup({ detail: "not_yet_supported" }, 422);
    const result = await store.dispatch(
      api.endpoints.importBlueprint.initiate({
        provisioningUpload: { file: new File(["legacy"], "old.zip") },
      }),
    );
    expect(result).toEqual({ error: { status: 422, data: { detail: "not_yet_supported" } } });
    expect(fetch).toHaveBeenCalledTimes(1);
    store.dispatch(api.util.resetApiState());
  });

  it("does not refresh and replay an import that expires after partial effects", async () => {
    const detail =
      "provisioning identities failed: invalid or expired operator bearer; identities_created=2; correct the cause and replay";
    const { store, fetch } = setup({ detail }, 401);
    const result = await store.dispatch(
      api.endpoints.importBlueprint.initiate({
        provisioningUpload: { file: new File(["zip"], "demo.zip") },
      }),
    );
    expect(result).toEqual({ error: { status: 401, data: { detail } } });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
    expect(KeyCloakService.CallLogout).not.toHaveBeenCalled();
    store.dispatch(api.util.resetApiState());
  });

  it("does not replay personal-space creation on 401", async () => {
    const { store, fetch } = setup(null);
    fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));
    const result = await store.dispatch(
      api.endpoints.createPersonalSpace.initiate({ createPersonalSpace: { organization_id: "org" } }),
    );
    expect(result).toEqual({ error: { status: 401, data: { detail: "expired" } } });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledExactlyOnceWith(30);
    store.dispatch(api.util.resetApiState());
  });

  it("exposes no document metadata routes or provisional document mutations", () => {
    for (const operation of ["createDocument", "renameDocument", "ingestDocument", "getDocument", "listDocuments"]) {
      expect(api.endpoints).not.toHaveProperty(operation);
    }
    expect(managerApi).not.toHaveProperty("useIngestDocumentMutation");
    expect(api.endpoints).toHaveProperty("entries");
  });

  it("retains the standard token retry for ordinary queries", async () => {
    const { store, fetch } = setup({ user_id: "u", username: "U", platform_roles: [] });
    fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));
    const query = store.dispatch(api.endpoints.me.initiate());
    await query.unwrap();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(KeyCloakService.ensureFreshToken).toHaveBeenCalledWith(0);
    query.unsubscribe();
    store.dispatch(api.util.resetApiState());
  });

  it("reads manager authority and flat nullable spaces through generated query contracts", async () => {
    const me: MeApiResponse = { user_id: "alice", username: "Alice", platform_roles: ["platform_admin"] };
    const { store, fetch } = setup(me);
    const actor = store.dispatch(api.endpoints.me.initiate());
    expect(await actor.unwrap()).toEqual(me);
    expect(fetch.mock.calls[0][0].url).toBe("http://localhost/control-plane/v1/me");
    const spaces: MySpacesApiResponse = [
      {
        id: "org-id",
        kind: "organization",
        organization_id: "org",
        name: "Demo",
        parent_id: null,
        personal_owner: null,
        path: ["org-id"],
        roles: ["owner", "analyst"],
        inherited_roles: [],
      },
    ];
    fetch.mockImplementationOnce(
      async () =>
        new Response(JSON.stringify(spaces), {
          headers: { "Content-Type": "application/json" },
        }),
    );
    const query = store.dispatch(api.endpoints.mySpaces.initiate());
    expect(await query.unwrap()).toEqual(spaces);
    expect(fetch.mock.calls[1][0].url).toBe("http://localhost/control-plane/v1/me/spaces");
    actor.unsubscribe();
    query.unsubscribe();
    store.dispatch(api.util.resetApiState());
  });
});

it("allows same-account token refresh and refuses a late response after account change", async () => {
  const { store, fetch } = setup({ user_id: "operator", username: "Operator", platform_roles: [] });
  vi.mocked(KeyCloakService.GetUserId).mockReturnValueOnce(null);
  const same = store.dispatch(api.endpoints.me.initiate(undefined, { subscribe: false, forceRefetch: true }));
  expect((await same.unwrap()).user_id).toBe("operator");
  expect(fetch).toHaveBeenCalledTimes(1);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  fetch.mockImplementationOnce(async () => {
    await held;
    return new Response(JSON.stringify({ user_id: "operator" }));
  });
  const late = store.dispatch(api.endpoints.me.initiate(undefined, { subscribe: false, forceRefetch: true }));
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  vi.mocked(KeyCloakService.GetSessionIdentity).mockReturnValue("fixture/other");
  release();
  expect((await late).error).toEqual({ status: "CUSTOM_ERROR", error: "Account changed during request" });
  fetch.mockImplementationOnce(async () => new Response(JSON.stringify({ user_id: "other" })));
  const other = await store.dispatch(api.endpoints.me.initiate(undefined, { subscribe: false })).unwrap();
  expect(other.user_id).toBe("other");
  expect(fetch).toHaveBeenCalledTimes(3);
  vi.mocked(KeyCloakService.GetSessionIdentity).mockReturnValue("fixture/operator");
  store.dispatch(api.util.resetApiState());
});

it("deletes a document through the generated route and refreshes directory and storage subscriptions", async () => {
  const { store, fetch } = setup({});
  const directory = store.dispatch(api.endpoints.entries.initiate({ id: "space", parentId: "folder" }));
  const storage = store.dispatch(api.endpoints.summary.initiate({ id: "space" }));
  await Promise.all([directory.unwrap(), storage.unwrap()]);
  fetch.mockClear();
  const receipt: import("./controlPlaneOpenApi").Receipt = {
    id: "receipt",
    actor_subject: "operator",
    organization_id: "org",
    target_id: "doc",
    target_kind: "document",
    status: "queued",
    requested_at: "2026-10-24T10:00:00Z",
    due_at: "2026-10-24T10:00:00Z",
    documents_deleted: 0,
    folders_deleted: 0,
    spaces_deleted: 0,
  };
  fetch.mockImplementationOnce(async () => new Response(JSON.stringify(receipt)));
  expect(await store.dispatch(api.endpoints.deleteDocument.initiate({ id: "doc" })).unwrap()).toEqual(receipt);
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
  expect(fetch.mock.calls.map(([request]) => [request.method, new URL(request.url).pathname])).toEqual(
    expect.arrayContaining([
      ["DELETE", "/control-plane/v1/documents/doc"],
      ["GET", "/control-plane/v1/spaces/space/entries"],
      ["GET", "/control-plane/v1/spaces/space/storage"],
    ]),
  );
  directory.unsubscribe();
  storage.unsubscribe();
  store.dispatch(api.util.resetApiState());
});

it("patches the edited organization into cached registry pages without refetching them", async () => {
  const space = (id: string, name: string) => ({ id, name }) as import("./controlPlaneOpenApi").Space;
  const { store, fetch } = setup({ items: [space("a", "Demo"), space("b", "Other")], next_cursor: null });
  const registry = store.dispatch(api.endpoints.organizationRegistry.initiate({}));
  await registry.unwrap();
  fetch.mockClear();
  const detail = { organization: space("a", "Renamed"), owners: [], admins: [] };
  fetch.mockImplementationOnce(async () => new Response(JSON.stringify(detail)));
  await store
    .dispatch(api.endpoints.updateOrganization.initiate({ id: "a", updateOrganization: { name: "Renamed" } }))
    .unwrap();
  await vi.waitFor(() =>
    expect(
      api.endpoints.organizationRegistry
        .select({})(store.getState())
        .data?.items.map((o) => o.name),
    ).toEqual(["Renamed", "Other"]),
  );
  expect(fetch).toHaveBeenCalledTimes(1);
  registry.unsubscribe();
  store.dispatch(api.util.resetApiState());
});

describe("Weaver prompt catalog", () => {
  const page = (ids: string[], next_cursor: string | null = null) => ({
    items: ids.map((id) => promptSummaryFixture({ prompt_id: id, logical_name: id })),
    next_cursor,
  });
  const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

  it("publishes all pages together, including later prompts, and deduplicates repeated identities", async () => {
    const { store, fetch } = setup(page(["a"], "a"));
    let finish!: (value: Response) => void;
    fetch.mockResolvedValueOnce(response(page(["a"], "a"))).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const query = store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "team" }));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(api.endpoints.listPrompts.select({ spaceId: "team" })(store.getState()).data).toBeUndefined();
    expect(new URL(fetch.mock.calls[1][0].url).searchParams.get("after")).toBe("a");
    finish(response(page(["a", "z"])));
    expect((await query.unwrap()).items.map((p) => p.prompt_id)).toEqual(["a", "z"]);
    store.dispatch(api.util.resetApiState());
  });

  it.each(["http", "same", "backwards", "bound"])(
    "fails explicitly without publishing a partial catalog: %s",
    async (failure) => {
      const { store, fetch } = setup(page(["a"], "b"));
      if (failure === "bound") {
        let n = 0;
        fetch.mockImplementation(async () => response(page([`p${n}`], String(++n).padStart(5, "0"))));
      } else {
        fetch.mockResolvedValueOnce(response(page(["a"], "b")));
        fetch.mockResolvedValueOnce(
          failure === "http"
            ? response({ detail: "unavailable" }, 503)
            : response(page(["c"], failure === "same" ? "b" : "a")),
        );
      }
      const result = await store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "team" }));
      expect(result.data).toBeUndefined();
      expect(result.error).toMatchObject(
        failure === "http" ? { status: 503 } : { status: "CUSTOM_ERROR", error: "prompt_catalog_incomplete" },
      );
      expect(fetch.mock.calls.length).toBeLessThanOrEqual(100);
      store.dispatch(api.util.resetApiState());
    },
  );

  it("shares in-flight work and lets the remaining subscriber finish", async () => {
    const { store, fetch } = setup(page(["a"]));
    let finish!: (value: Response) => void;
    fetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const first = store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "team" }));
    const second = store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "team" }));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    first.unsubscribe();
    expect(fetch.mock.calls[0][0].signal.aborted).toBe(false);
    finish(response(page(["a"], "a")));
    expect((await second.unwrap()).items.map((p) => p.prompt_id)).toEqual(["a"]);
    expect(fetch).toHaveBeenCalledTimes(2);
    second.unsubscribe();
    store.dispatch(api.util.resetApiState());
  });

  it("aborts remaining work when its last subscriber leaves", async () => {
    const { store, fetch } = setup(page([]));
    fetch.mockImplementationOnce(
      (request) =>
        new Promise((_resolve, reject) => {
          request.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), {
            once: true,
          });
        }),
    );
    const query = store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "team" }));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    query.unsubscribe();
    await vi.waitFor(() => expect(fetch.mock.calls[0][0].signal.aborted).toBe(true));
    expect((await query).data).toBeUndefined();
    expect(fetch).toHaveBeenCalledOnce();
    store.dispatch(api.util.resetApiState());
  });

  it.each(["space", "account"])("isolates a late catalog after changing %s", async (change) => {
    const { store, fetch } = setup(page(["new"]));
    let finish!: (value: Response) => void;
    fetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const old = store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "team" }));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    if (change === "account") vi.mocked(KeyCloakService.GetSessionIdentity).mockReturnValue("fixture/new-account");
    const args = { spaceId: change === "space" ? "other-team" : "team" };
    const current = store.dispatch(api.endpoints.listPrompts.initiate(args));
    expect((await current.unwrap()).items.map((p) => p.prompt_id)).toEqual(["new"]);
    finish(response(page(["old"])));
    await old;
    expect(
      api.endpoints.listPrompts
        .select(args)(store.getState())
        .data?.items.map((p) => p.prompt_id),
    ).toEqual(["new"]);
    vi.mocked(KeyCloakService.GetSessionIdentity).mockReturnValue("fixture/operator");
    store.dispatch(api.util.resetApiState());
  });

  it.each(["create", "update", "delete", "failed"])(
    "invalidates only the affected space and prompt after %s",
    async (mutation) => {
      const { store, fetch } = setup(page(["a"]));
      fetch.mockImplementation(async (request) =>
        response(
          new URL(request.url).pathname.endsWith("/prompts")
            ? page(["a"])
            : promptFixture({ prompt_id: request.url.split("/").pop() }),
        ),
      );
      await Promise.all([
        store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "team" })).unwrap(),
        store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "other" })).unwrap(),
        ...["a", "b"].map((promptId) =>
          store.dispatch(api.endpoints.getPrompt.initiate({ spaceId: "team", promptId })).unwrap(),
        ),
      ]);
      fetch.mockClear();
      fetch.mockImplementation(async (request) => {
        if (mutation === "failed" && request.method !== "GET")
          return response({ code: "prompt_name_conflict", detail: "taken" }, 409);
        if (request.method === "DELETE") return new Response(null, { status: 204 });
        return response(
          request.method === "GET" && new URL(request.url).pathname.endsWith("/prompts")
            ? page(["a"])
            : promptFixture(),
        );
      });
      const args = { spaceId: "team", promptId: "a" };
      if (mutation === "create")
        await store.dispatch(
          api.endpoints.createPrompt.initiate({
            spaceId: "team",
            createPromptRequest: { logical_name: "new", display_name: "New", text: "body" },
          }),
        );
      else if (mutation === "delete") await store.dispatch(api.endpoints.deletePrompt.initiate(args));
      else
        await store.dispatch(api.endpoints.updatePrompt.initiate({ ...args, updatePromptRequest: { text: "edited" } }));
      const running = store.dispatch(api.util.getRunningQueriesThunk());
      await Promise.all(running);
      const urls = fetch.mock.calls.filter(([r]) => r.method === "GET").map(([r]) => new URL(r.url).pathname);
      expect(urls.sort()).toEqual(
        mutation === "failed"
          ? []
          : mutation === "create"
            ? ["/control-plane/v1/spaces/team/prompts"]
            : ["/control-plane/v1/spaces/team/prompts", "/control-plane/v1/spaces/team/prompts/a"],
      );
      store.dispatch(api.util.resetApiState());
    },
  );

  it.each(["none", "http", "refresh"])(
    "enforces the total deadline including an unauthorized retry: %s",
    async (retry) => {
      vi.useFakeTimers();
      const { store, fetch } = setup(page([]));
      let finishRefresh: ((value: boolean) => void) | undefined;
      if (retry === "refresh")
        vi.mocked(KeyCloakService.ensureFreshToken).mockImplementation((minValidity) =>
          minValidity === 0
            ? new Promise((resolve) => {
                finishRefresh = resolve;
              })
            : Promise.resolve(true),
        );
      let n = 0;
      fetch.mockImplementation(
        (request) =>
          new Promise((resolve, reject) => {
            const attempt = ++n;
            const timer = setTimeout(
              () =>
                resolve(
                  response(
                    attempt <= 4
                      ? page([`p${attempt}`], String(attempt))
                      : retry !== "none" && attempt === 5
                        ? { detail: "expired" }
                        : page(["last"]),
                    retry !== "none" && attempt === 5 ? 401 : 200,
                  ),
                ),
              attempt <= 4 ? 14_000 : retry !== "none" ? 3_000 : 5_000,
            );
            request.signal.addEventListener(
              "abort",
              () => {
                clearTimeout(timer);
                reject(request.signal.reason);
              },
              { once: true },
            );
          }),
      );
      try {
        const query = store.dispatch(api.endpoints.listPrompts.initiate({ spaceId: "team" }));
        await vi.advanceTimersByTimeAsync(60_001);
        const result = api.endpoints.listPrompts.select({ spaceId: "team" })(store.getState());
        expect(result.status).toBe("rejected");
        expect(result.error).toMatchObject({ status: "TIMEOUT_ERROR" });
        expect(result.data).toBeUndefined();
        await query;
        expect(fetch.mock.calls.slice(-1)[0]?.[0].signal.aborted).toBe(true);
      } finally {
        finishRefresh?.(true);
        vi.mocked(KeyCloakService.ensureFreshToken).mockResolvedValue(true);
        store.dispatch(api.util.resetApiState());
        vi.useRealTimers();
      }
    },
  );
});

it.each([false, true])(
  "resolves a slash beyond page one only from a complete HTTP catalog (page failure: %s)",
  async (failed) => {
    const { store, fetch } = setup(null);
    fetch.mockImplementation(async (request) => {
      const url = new URL(request.url);
      const body = url.pathname.endsWith("/prompts/z")
        ? promptFixture({ prompt_id: "z", logical_name: "z", text: "  Full text beyond page one\n" })
        : {
            items: [
              promptSummaryFixture({
                prompt_id: url.searchParams.has("after") ? "z" : "a",
                logical_name: url.searchParams.has("after") ? "z" : "a",
              }),
            ],
            next_cursor: url.searchParams.has("after") ? null : "a",
          };
      return new Response(JSON.stringify(body), { status: failed && url.searchParams.has("after") ? 503 : 200 });
    });
    const onRunCommand = vi.fn();
    const onSend = vi.fn();
    const onResolveError = vi.fn();
    const setInput = vi.fn();
    let submit!: () => void;
    function Composer() {
      submit = useComposerCommands({
        teamId: "team",
        skillsEnabled: false,
        input: "/z notes",
        setInput,
        onRunCommand,
        onSend,
        onResolveError,
      }).submit;
      return null;
    }
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    try {
      await act(async () => root.render(createElement(Provider, { store, children: createElement(Composer) })));
      await act(async () => {
        await Promise.all(store.dispatch(api.util.getRunningQueriesThunk()));
      });
      await act(async () => submit());
      await act(async () => {
        await Promise.all(store.dispatch(api.util.getRunningQueriesThunk()));
      });
      if (failed) {
        expect(onRunCommand).not.toHaveBeenCalled();
        expect(onResolveError).toHaveBeenCalledExactlyOnceWith("unreadable", "z");
        expect(fetch.mock.calls.some(([request]) => request.url.endsWith("/prompts/z"))).toBe(false);
      } else {
        expect(onRunCommand).toHaveBeenCalledWith(
          expect.objectContaining({
            text: "  Full text beyond page one\n\n\nnotes",
            command: expect.objectContaining({ prompt_id: "z" }),
          }),
        );
        expect(onResolveError).not.toHaveBeenCalled();
      }
      expect(onSend).not.toHaveBeenCalled();
      expect(setInput).not.toHaveBeenCalled();
    } finally {
      act(() => root.unmount());
      container.remove();
      store.dispatch(api.util.resetApiState());
    }
  },
);
