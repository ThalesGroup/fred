// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";
import TeamResourcesPage from "./TeamResourcesPage";
import { fredManagerApi as api, type Document, type Folder } from "../../../../slices/fredManager/fredManagerOpenApi";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { page?: number }) => (options?.page ? `${key} ${options.page}` : key),
  }),
}));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "reader", ensureFreshToken: async () => true, CallLogout: vi.fn() },
}));
vi.mock("../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));

const firstSpace = "00000000-0000-4000-8000-000000000001";
const secondSpace = "00000000-0000-4000-8000-000000000002";
const folder: Folder = { id: "folder-a", space_id: firstSpace, parent_id: null, path: "/folder-a/", name: "Library" };
const docs: Document[] = Array.from({ length: 53 }, (_, i) => ({
  id: `doc-${i}`,
  space_id: firstSpace,
  folder_id: folder.id,
  name: `Document ${i}`,
  mime: "text/plain",
  size: 10,
  sha256: "digest",
  created_by: "reader",
}));
const NativeRequest = globalThis.Request;
let root: Root;
let host: HTMLDivElement;
let store: ReturnType<typeof makeStore>;
let requests: URL[];
let reply: (url: URL, request: Request) => Promise<Response>;
let navigate: ReturnType<typeof useNavigate>;
function makeStore() {
  return configureStore({ reducer: { [api.reducerPath]: api.reducer }, middleware: (g) => g().concat(api.middleware) });
}
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}
async function standard(url: URL) {
  if (url.pathname.endsWith("/authorize/space")) return json({ allowed: false });
  if (url.pathname.endsWith("/me/spaces")) return json([]);
  if (url.pathname.includes(secondSpace)) return json([]);
  if (url.pathname.endsWith("/folders")) return json(url.searchParams.has("parent_id") ? [] : [folder]);
  const after = url.searchParams.get("after_id");
  const start = after ? docs.findIndex((d) => d.id === after) + 1 : 0;
  return json(url.searchParams.has("folder_id") ? docs.slice(start, start + 51) : []);
}
function Harness() {
  navigate = useNavigate();
  return (
    <Routes>
      <Route path="team/:teamId/resources" element={<TeamResourcesPage />} />
    </Routes>
  );
}
async function flush() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });
}
async function click(label: string) {
  const button = [...document.querySelectorAll("button")].find(
    (b) => b.getAttribute("aria-label") === label || b.textContent?.endsWith(label),
  );
  expect(button, label).toBeDefined();
  await act(async () => button!.click());
  await flush();
}
beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  requests = [];
  reply = standard;
  vi.stubGlobal("fetch", async (request: Request) => {
    const url = new URL(request.url);
    requests.push(url);
    return reply(url, request);
  });
  store = makeStore();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () =>
    root.render(
      <StrictMode>
        <Provider store={store}>
          <MemoryRouter initialEntries={[`/team/${firstSpace}/resources`]}>
            <Harness />
          </MemoryRouter>
        </Provider>
      </StrictMode>,
    ),
  );
  await flush();
});
afterEach(async () => {
  await act(async () => root.unmount());
  store.dispatch(api.util.resetApiState());
  host.remove();
  vi.unstubAllGlobals();
});

it("uses only manager reads, traverses folders and paired cursor pages, then resets at the root", async () => {
  expect(host.textContent).toContain("Library");
  await click("Library");
  expect(host.querySelectorAll('[class*="datatable-row"]').length).toBe(50);
  expect(host.textContent).not.toContain("Document 50");
  await click("dataTable.pagination.next");
  expect(host.textContent).toContain("Document 52");
  expect(host.querySelectorAll('[class*="datatable-row"]').length).toBe(3);
  const last = [...requests].reverse().find((url) => url.pathname.endsWith("/documents"))!;
  expect(last.searchParams.get("after_id")).toBe("doc-49");
  expect(last.searchParams.get("after_name")).toBe("Document 49");
  expect(last.searchParams.get("limit")).toBe("51");
  await click("dataTable.pagination.prev");
  expect(host.querySelectorAll('[class*="datatable-row"]').length).toBe(50);
  await click("rework.sidebar.team.menu.resources");
  expect(host.textContent).toContain("Library");
  expect(host.textContent).not.toContain("Document 0");
  expect(requests.every((url) => url.pathname.startsWith("/fred-manager/v1/"))).toBe(true);
});

it("hides cached rows on re-entry, distinguishes refusals from errors and emptiness, and retries", async () => {
  await click("Library");
  await click("rework.back");
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  reply = async (url) => {
    if (url.pathname.endsWith("/documents") && url.searchParams.has("folder_id")) {
      await held;
      return json({ detail: "denied" }, 403);
    }
    return standard(url);
  };
  await click("Library");
  expect(host.textContent).toContain("rework.resources.loading");
  expect(host.textContent).not.toContain("Document 0");
  await act(async () => release());
  await flush();
  expect(host.textContent).toContain("rework.resources.managerRead.denied");
  expect(host.textContent).not.toContain("rework.resources.empty.folder");
  reply = async () => json({ detail: "failed" }, 500);
  await click("rework.bootstrap.reload");
  expect(host.textContent).toContain("rework.resources.managerRead.unavailable");
  reply = async () => json([]);
  await click("rework.bootstrap.reload");
  expect(host.textContent).toContain("rework.resources.empty.folder");
});

it("does not let a late prior-space response populate the new space", async () => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  reply = async (url) => {
    if (url.pathname.includes(firstSpace) && url.searchParams.has("folder_id")) await held;
    return standard(url);
  };
  await click("Library");
  await act(async () => navigate(`/team/${secondSpace}/resources`));
  await flush();
  expect(host.textContent).toContain("rework.resources.empty.folder");
  await act(async () => release());
  await flush();
  expect(host.textContent).not.toContain("Document 0");
  expect(host.textContent).not.toContain("Library");
});

it("re-entering an in-flight folder must revalidate instead of accepting the earlier success", async () => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let revoked = false;
  reply = async (url) => {
    if (url.searchParams.has("folder_id") || url.searchParams.has("parent_id")) {
      if (revoked) return json({ detail: "denied" }, 403);
      await held;
      return standard(url);
    }
    return standard(url);
  };
  await click("Library");
  await click("rework.back");
  revoked = true;
  await click("Library");
  await act(async () => release());
  await flush();
  expect(host.textContent).not.toContain("Document 0");
  expect(host.textContent).toContain("rework.resources.managerRead.denied");
});

function typeFolderName(value: string) {
  const input = document.querySelector<HTMLInputElement>('[role="dialog"] input')!;
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  return input;
}

it("creates once through the generated mutation and refreshes the first page of the same folder", async () => {
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const posted: unknown[] = [];
  let created = false;
  reply = async (url, request) => {
    if (url.pathname.endsWith("/authorize/space")) return json({ allowed: true });
    if (request.method === "POST" && url.pathname.endsWith("/folders")) {
      posted.push(await request.json());
      await pending;
      created = true;
      return json({ ...folder, id: "new", name: "Notes", parent_id: folder.id }, 201);
    }
    if (created && url.pathname.endsWith("/folders") && url.searchParams.has("parent_id"))
      return json([{ ...folder, id: "new", name: "Notes", parent_id: folder.id }]);
    return standard(url);
  };
  await click("Library");
  await click("dataTable.pagination.next");
  await click("rework.resources.menu.newFolder");
  const input = typeFolderName("  Notes  ");
  await act(async () => {
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  });
  await flush();
  expect(posted).toEqual([{ space_id: firstSpace, parent_id: folder.id, name: "Notes" }]);
  await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  await act(async () => finish());
  await flush();
  await flush();
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(host.textContent).toContain("Notes");
  expect(host.textContent).toContain("Document 0");
  expect(requests.every((url) => url.pathname.startsWith("/fred-manager/v1/"))).toBe(true);
});

it("fails closed, preserves the name after a conflict, and disables creation after revocation", async () => {
  expect(document.querySelector('[aria-label="rework.resources.menu.newFolder"]')).toBeNull();
  let status = 409,
    posts = 0;
  reply = async (url, request) => {
    if (url.pathname.endsWith("/authorize/space")) return json({ allowed: true });
    if (request.method === "POST" && url.pathname.endsWith("/folders")) {
      posts++;
      return json({ detail: "failure" }, status);
    }
    return standard(url);
  };
  await click("rework.resources.action.refresh");
  await click("rework.resources.menu.newFolder");
  typeFolderName("existing");
  await click("rework.resources.folderModal.create");
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain("rework.resources.managerCreate.conflict");
  expect(document.querySelector<HTMLInputElement>('[role="dialog"] input')?.value).toBe("existing");
  status = 403;
  await click("rework.resources.folderModal.create");
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain("rework.resources.managerCreate.denied");
  expect(posts).toBe(2);
  await click("rework.resources.folderModal.cancel");
  expect(document.querySelector('[aria-label="rework.resources.menu.newFolder"]')).toBeNull();
});

it("does not replay a 401 write or change a different space after a pending creation", async () => {
  let finish!: () => void;
  const pending = new Promise<void>((resolve) => {
    finish = resolve;
  });
  let delayed = false,
    posts = 0;
  reply = async (url, request) => {
    if (url.pathname.endsWith("/authorize/space")) return json({ allowed: true });
    if (request.method === "POST" && url.pathname.endsWith("/folders")) {
      posts++;
      if (delayed) {
        await pending;
        return json(folder, 201);
      }
      return json({ detail: "expired" }, 401);
    }
    return standard(url);
  };
  await click("rework.resources.action.refresh");
  await click("rework.resources.menu.newFolder");
  typeFolderName("Late folder");
  await click("rework.resources.folderModal.create");
  expect(posts).toBe(1);
  delayed = true;
  await click("rework.resources.folderModal.create");
  await act(async () => navigate(`/team/${secondSpace}/resources`));
  await flush();
  const before = requests.length;
  await act(async () => finish());
  await flush();
  expect(requests).toHaveLength(before);
  expect(host.textContent).not.toContain("Late folder");
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});
