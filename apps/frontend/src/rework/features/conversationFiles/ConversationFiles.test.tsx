// @vitest-environment jsdom
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

import { act, useRef } from "react";
import { createRoot } from "react-dom/client";
import { Provider, useSelector } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, expect, it, vi } from "vitest";
import { runtimeApi } from "../../../slices/runtime/runtimeOpenApi";
import { conversationFileSlice } from "./conversationFileSlice";
import { sidePanelOpenRequestSlice } from "../capabilities/sidePanelOpenRequestSlice";
import { UiParts } from "@shared/molecules/UiParts/UiParts";
import { ConversationFilePanel } from "@shared/organisms/ConversationFilePanel/ConversationFilePanel";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en", t: (key: string) => key } }),
}));
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: {
    ensureFreshToken: async () => true,
    GetToken: () => "test",
    GetUserId: () => "alice",
    GetTokenSecondsLeft: () => 3600,
  },
}));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const mounted: (() => void)[] = [];
afterEach(() => {
  mounted.splice(0).forEach((cleanup) => cleanup());
  vi.unstubAllGlobals();
});

it.each(["s1", "constructor"])(
  "opens a historical reference for %s with current read-only content and deduplicates session/path tabs",
  async (sessionId) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              type: "conversation_file",
              session_id: sessionId,
              path: "/notes.txt",
              viewer: "text",
              editable: true,
              content: "Latest saved notes",
            }),
            { headers: { "Content-Type": "application/json" } },
          ),
      ),
    );
    const store = configureStore({
      reducer: {
        conversationFiles: conversationFileSlice.reducer,
        capabilitySidePanelOpenRequest: sidePanelOpenRequestSlice.reducer,
        [runtimeApi.reducerPath]: runtimeApi.reducer,
      },
      middleware: (getDefault) => getDefault().concat(runtimeApi.middleware),
    });
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    mounted.push(() => {
      act(() => root.unmount());
      host.remove();
    });
    const part = {
      type: "conversation_file",
      session_id: sessionId,
      path: "/notes.txt",
      viewer: "text",
      editable: true,
    };
    await act(async () => {
      root.render(
        <Provider store={store}>
          <MemoryRouter initialEntries={[`/?session=${sessionId}`]}>
            <UiParts parts={[part, part]} />
            <ConversationFilePanel
              sessionId={sessionId}
              teamId="t1"
              messagesUrl={`http://runtime.test/pod/v1/agents/sessions/${sessionId}/messages`}
              open
              onClose={() => undefined}
            />
          </MemoryRouter>
        </Provider>,
      );
    });
    const button = [...host.querySelectorAll("button")].find((node) =>
      node.textContent?.includes("conversationFiles.open"),
    );
    expect(button).toBeDefined();
    await act(async () => {
      button!.click();
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(host.textContent).toContain("Latest saved notes");
    expect(host.querySelectorAll('[role="tab"]')).toHaveLength(1);
    expect(host.querySelector('[role="textbox"]')?.getAttribute("aria-readonly")).toBe("true");
  },
);

async function panelHarness(
  messagesUrl: string | null = "http://runtime.test/pod/v1/agents/sessions/s1/messages",
  paths = ["/notes.txt"],
) {
  const store = configureStore({
    reducer: {
      conversationFiles: conversationFileSlice.reducer,
      capabilitySidePanelOpenRequest: sidePanelOpenRequestSlice.reducer,
      [runtimeApi.reducerPath]: runtimeApi.reducer,
    },
    middleware: (getDefault) => getDefault().concat(runtimeApi.middleware),
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  mounted.push(() => {
    act(() => root.unmount());
    store.dispatch(runtimeApi.util.resetApiState());
    host.remove();
  });
  const render = async (sessionId = "s1", open = true) => {
    await act(async () => {
      root.render(
        <Provider store={store}>
          <ConversationFilePanel
            sessionId={sessionId}
            teamId="t1"
            messagesUrl={messagesUrl === null ? null : messagesUrl.replaceAll("s1", sessionId)}
            open={open}
            onClose={() => undefined}
          />
        </Provider>,
      );
    });
  };
  await act(async () => {
    for (const path of paths)
      store.dispatch(
        conversationFileSlice.actions.openConversationFile({
          type: "conversation_file",
          session_id: "s1",
          path,
          viewer: "text",
          editable: true,
        }),
      );
  });
  await render();
  return { host, render };
}
const fileResponse = (content: string) =>
  new Response(
    JSON.stringify({
      type: "conversation_file",
      session_id: "s1",
      path: "/notes.txt",
      viewer: "text",
      editable: true,
      content,
    }),
    { headers: { "Content-Type": "application/json" } },
  );
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 25));
  });
}

it.each([
  [403, "denied"],
  [404, "missing"],
  [415, "unsupported"],
  [503, "unavailable"],
])("shows an actionable error for HTTP %i", async (status, key) => {
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response(JSON.stringify({ detail: "server detail" }), {
        status: Number(status),
        headers: { "Content-Type": "application/json" },
      }),
  );
  const { host } = await panelHarness();
  await settle();
  expect(host.querySelector('[role="alert"]')?.textContent).toContain(`conversationFiles.${key}`);
  expect(host.textContent).toContain("conversationFiles.retry");
  expect(host.querySelector('[role="textbox"]')).toBeNull();
});

it("reopens the same reference with current content after closing", async () => {
  let content = "First saved version";
  vi.stubGlobal("fetch", async () => fileResponse(content));
  const { host, render } = await panelHarness();
  await settle();
  expect(host.textContent).toContain("First saved version");
  await render("s1", false);
  content = "Later saved version";
  await render();
  await settle();
  expect(host.textContent).toContain("Later saved version");
  expect(host.textContent).not.toContain("First saved version");
});

it("announces loading and rejects a late response after conversation navigation", async () => {
  let finish!: (response: Response) => void;
  vi.stubGlobal(
    "fetch",
    () =>
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
  );
  const { host, render } = await panelHarness();
  expect(host.querySelector('[role="status"]')?.textContent).toContain("conversationFiles.loading");
  await render("s2");
  await act(async () => {
    finish(fileResponse("OLD SESSION SECRET"));
  });
  await settle();
  expect(host.textContent).not.toContain("OLD SESSION SECRET");
  expect(host.querySelector('[role="textbox"]')).toBeNull();
});

it("explains an unavailable historical runtime without attempting content access", async () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const { host } = await panelHarness(null);
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("conversationFiles.unavailable");
  expect(fetch).not.toHaveBeenCalled();
});

it.each([false, true])(
  "streams parent/child file selection in event order and ignores late navigation (navigate=%s)",
  async (navigate) => {
    const { controlPlaneApi } = await import("../../../slices/controlPlane/controlPlaneApi");
    const { useChatSse } = await import("../../core/hooks/useChatSse");
    const { selectSidePanelOpenRequest } = await import("../capabilities/sidePanelOpenRequestSlice");
    const NativeRequest = globalThis.Request;
    vi.stubGlobal(
      "Request",
      class extends NativeRequest {
        constructor(input: RequestInfo | URL, init?: RequestInit) {
          super(
            typeof input === "string" && input.startsWith("/") ? new URL(input, window.location.origin) : input,
            init,
          );
        }
      },
    );
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    let connected!: () => void;
    const streamReady = new Promise<void>((resolve) => {
      connected = resolve;
    });
    vi.stubGlobal("fetch", async (input: Request | string) => {
      const url = typeof input === "string" ? input : input.url;
      if (url.includes("prepare-execution"))
        return new Response(
          JSON.stringify({
            execute_stream_url: "/runtime/agents-v2/agents/execute/stream",
            chat_controls: [],
            capability_base_urls: {},
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      if (url.endsWith("execute/stream")) {
        const stream = new ReadableStream<Uint8Array>({
          start(value) {
            controller = value;
            connected();
          },
        });
        return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
      }
      return fileResponse("Content selected by native child");
    });
    const store = configureStore({
      reducer: {
        conversationFiles: conversationFileSlice.reducer,
        capabilitySidePanelOpenRequest: sidePanelOpenRequestSlice.reducer,
        [runtimeApi.reducerPath]: runtimeApi.reducer,
        [controlPlaneApi.reducerPath]: controlPlaneApi.reducer,
      },
      middleware: (getDefault) => getDefault().concat(runtimeApi.middleware, controlPlaneApi.middleware),
    });
    function LivePanel({ sessionId }: { sessionId: string }) {
      const current = useRef(sessionId);
      current.current = sessionId;
      const chat = useChatSse({ agentInstanceId: "a1", teamId: "t1", isTurnCurrent: (id) => current.current === id });
      const request = useSelector(selectSidePanelOpenRequest);
      return (
        <>
          <button onClick={() => void chat.send("review", "s1")}>Send</button>
          <ConversationFilePanel
            sessionId={sessionId}
            teamId="t1"
            messagesUrl={`http://runtime.test/pod/v1/agents/sessions/${sessionId}/messages`}
            open={request.key === "runtime:conversation-files"}
            onClose={() => undefined}
          />
        </>
      );
    }
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    mounted.push(() => {
      act(() => root.unmount());
      store.dispatch(runtimeApi.util.resetApiState());
      store.dispatch(controlPlaneApi.util.resetApiState());
      host.remove();
    });
    const render = async (sessionId: string) => {
      await act(async () => {
        root.render(
          <Provider store={store}>
            <LivePanel sessionId={sessionId} />
          </Provider>,
        );
      });
    };
    await render("s1");
    await act(async () => {
      host.querySelector("button")!.click();
      await streamReady;
    });
    if (navigate) await render("s2");
    await act(async () => {
      for (const [call_id, path] of [
        ["parent-open", "/parent.txt"],
        ["child-open", "/child.txt"],
      ])
        controller.enqueue(
          new TextEncoder().encode(
            `data: ${JSON.stringify({ kind: "tool_result", call_id, content: "File presentation requested", ui_parts: [{ type: "conversation_file", session_id: "s1", path, viewer: "text", editable: true }] })}\n\n`,
          ),
        );
      controller.close();
    });
    await settle();
    if (navigate) expect(host.querySelector("aside")?.getAttribute("aria-hidden")).toBe("true");
    else {
      expect(host.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toBe("/child.txt");
      expect(host.textContent).toContain("Content selected by native child");
    }
  },
);

it("switches opened files by keyboard and keeps their source read-only", async () => {
  vi.stubGlobal("fetch", async (input: Request) =>
    fileResponse(
      new URL(input.url).searchParams.get("path") === "/second.txt" ? "Second saved file" : "First saved file",
    ),
  );
  const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", [
    "/notes.txt",
    "/second.txt",
  ]);
  await settle();
  const tabs = host.querySelectorAll<HTMLButtonElement>('[role="tab"]');
  expect(tabs[1].getAttribute("aria-selected")).toBe("true");
  await act(async () => {
    tabs[1].focus();
    tabs[1].dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
  });
  await settle();
  expect(document.activeElement).toBe(tabs[0]);
  expect(tabs[0].getAttribute("aria-selected")).toBe("true");
  expect(host.textContent).toContain("First saved file");
  expect(host.querySelector('[role="textbox"]')?.getAttribute("aria-readonly")).toBe("true");
});
