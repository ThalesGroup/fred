// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { runtimeApi } from "../../slices/runtime/runtimeOpenApi";
import { useConversationFiles, workspaceFileUrl } from "./conversationFiles";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const scope = vi.hoisted(() => ({ session: "one", refresh: vi.fn() }));
vi.mock("./capabilities/useOpenSessionId", () => ({ useOpenSessionId: () => scope.session }));
vi.mock("react-router-dom", () => ({ useParams: () => ({ teamId: "team" }) }));
vi.mock("../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ currentData: [] }),
}));
vi.mock("../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useListConversationFilesQuery: () => ({ currentData: [], refetch: scope.refresh, isUninitialized: false }),
}));
vi.mock("../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "person-token",
    GetSessionIdentity: () => "alice",
    ensureFreshToken: async () => true,
  },
}));

let root: Root;
let container: HTMLDivElement;
let result: ReturnType<typeof useConversationFiles>;
let requests: Request[];
let response: () => Response | Promise<Response>;
let filesUrl: string;
let store: ReturnType<typeof configureTestStore>;
const configureTestStore = () =>
  configureStore({
    reducer: { [runtimeApi.reducerPath]: runtimeApi.reducer },
    middleware: (getDefault) => getDefault().concat(runtimeApi.middleware),
  });
function Probe() {
  result = useConversationFiles(filesUrl);
  return <>{result.workspaceFiles.map((file) => file.name).join(",")}</>;
}
async function render() {
  await act(async () =>
    root.render(
      <Provider store={store}>
        <Probe />
      </Provider>,
    ),
  );
}
const file = { path: "plan.md", name: "plan.md", size: 42, modified: "2026-11-12T08:00:00Z" };
beforeEach(() => {
  scope.session = "one";
  scope.refresh.mockClear();
  filesUrl = `${window.location.origin}/native/v1/agents/sessions/one/workspace/files`;
  store = configureTestStore();
  container = document.createElement("div");
  root = createRoot(container);
  requests = [];
  response = () => new Response(JSON.stringify([file]), { headers: { "Content-Type": "application/json" } });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      requests.push(input);
      return response();
    }),
  );
});
afterEach(() => {
  act(() => root.unmount());
  store.dispatch(runtimeApi.util.resetApiState());
  container.remove();
  vi.unstubAllGlobals();
});

it("uses the CP-selected pod with person credentials and refreshes both file sources", async () => {
  await render();
  await vi.waitFor(() => expect(result.workspaceFiles).toEqual([file]));
  expect(requests[0].url).toBe(filesUrl);
  expect(requests[0].headers.get("Authorization")).toBe("Bearer person-token");
  expect(requests[0].redirect).toBe("error");
  response = () => new Response("[]", { headers: { "Content-Type": "application/json" } });
  await act(async () => result.refetch());
  await vi.waitFor(() => expect(result.workspaceFiles).toEqual([]));
  expect(scope.refresh).toHaveBeenCalledOnce();
  expect(workspaceFileUrl(filesUrl, "plans/response plan.md")).toBe(
    filesUrl.replace("/files", "/content?path=plans%2Fresponse%20plan.md"),
  );
});

it("drops cached files after access is revoked", async () => {
  await render();
  await vi.waitFor(() => expect(result.workspaceFiles).toHaveLength(1));
  response = () => new Response("{}", { status: 404 });
  await act(async () => result.refetch());
  await vi.waitFor(() => expect(result.workspaceError).toMatchObject({ status: 404 }));
  expect(result.workspaceFiles).toEqual([]);
});

it("does not show the previous conversation while the next listing is pending", async () => {
  await render();
  await vi.waitFor(() => expect(result.workspaceFiles).toHaveLength(1));
  scope.session = "two";
  filesUrl = filesUrl.replace("/one/", "/two/");
  let finish!: (value: Response) => void;
  response = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  await render();
  expect(result.workspaceFiles).toEqual([]);
  await vi.waitFor(() => expect(requests).toHaveLength(2));
  await act(async () => finish(new Response("[]")));
});

it("never sends a person credential to an external workspace URL", async () => {
  filesUrl = "https://untrusted.invalid/workspace/files";
  await render();
  expect(requests).toEqual([]);
  expect(result.workspaceFiles).toEqual([]);
});
