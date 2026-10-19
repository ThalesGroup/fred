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

const locale = vi.hoisted(() => ({
  language: "en",
  t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: locale.t, i18n: { language: locale.language, t: locale.t } }),
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
  locale.language = "en";
  locale.t = (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key;
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
              editable: false,
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
const fileResponse = (content: string, editable = true) =>
  new Response(
    JSON.stringify({
      type: "conversation_file",
      session_id: "s1",
      path: "/notes.txt",
      viewer: "text",
      editable,
      content,
    }),
    { headers: { "Content-Type": "application/json" } },
  );
const markdownResponse = (content: string, editable = true) =>
  new Response(
    JSON.stringify({
      type: "conversation_file",
      session_id: "s1",
      path: "/report.md",
      viewer: "markdown",
      editable,
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
    let liveContent = "Content selected by native child";
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
      return fileResponse(liveContent);
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
    });
    await settle();
    if (navigate) {
      expect(host.querySelector("aside")?.getAttribute("aria-hidden")).toBe("true");
      controller.close();
    } else {
      expect(host.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toBe("/child.txt");
      expect(host.textContent).toContain("Content selected by native child");
      liveContent = "Concatenated output without another open";
      await act(async () =>
        controller.enqueue(
          new TextEncoder().encode(
            `data: ${JSON.stringify({ kind: "tool_result", call_id: "child-concat", tool_name: "concat_files", content: "Saved" })}\n\n`,
          ),
        ),
      );
      await settle();
      expect(host.textContent).toContain("Concatenated output without another open");
      liveContent = "Final saved output";
      await act(async () => {
        controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ kind: "final", content: "Done" })}\n\n`));
        controller.close();
      });
      await settle();
      expect(host.textContent).toContain("Final saved output");
    }
  },
);

it("switches opened files by keyboard and keeps their source read-only", async () => {
  vi.stubGlobal("fetch", async (input: Request) =>
    fileResponse(
      new URL(input.url).searchParams.get("path") === "/second.txt" ? "Second saved file" : "First saved file",
      false,
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

it("serializes autosaves and keeps typing during a save dirty until the next save", async () => {
  const { EditorView } = await import("@codemirror/view");
  const writes: string[] = [];
  const pending: (() => void)[] = [];
  vi.stubGlobal("fetch", async (request: Request) => {
    if (request.method === "PUT") {
      const { content } = await request.json();
      writes.push(content);
      return new Promise<Response>((resolve) => pending.push(() => resolve(fileResponse(content))));
    }
    return fileResponse("Original");
  });
  const { host } = await panelHarness();
  await settle();
  expect(host.querySelector('[role="textbox"]')?.getAttribute("aria-readonly")).toBe("false");
  const editor = EditorView.findFromDOM(host.querySelector(".cm-editor")!)!;
  await act(async () => editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: "Revision one" } }));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 700));
  });
  expect(writes).toEqual(["Revision one"]);
  await act(async () => editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: "Revision two" } }));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 700));
  });
  expect(writes).toEqual(["Revision one"]);
  await act(async () => {
    pending.shift()!();
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 700));
  });
  expect(writes).toEqual(["Revision one", "Revision two"]);
  expect(host.textContent).toContain("Revision two");
  await act(async () => {
    pending.shift()!();
  });
  await settle();
  expect(host.textContent).toContain("conversationFiles.saved");
});

it("refreshes clean source on focus without reopening and stops after close", async () => {
  let content = "Parent output";
  let reads = 0;
  vi.stubGlobal("fetch", async () => {
    reads += 1;
    return fileResponse(content);
  });
  const { host, render } = await panelHarness();
  await settle();
  content = "Native child and concatenation output";
  await act(async () => window.dispatchEvent(new Event("focus")));
  await settle();
  expect(host.textContent).toContain("Native child and concatenation output");
  await render("s1", false);
  const beforeFocus = reads;
  await act(async () => window.dispatchEvent(new Event("focus")));
  await settle();
  expect(reads).toBe(beforeFocus);
});

it("preserves a failed draft through close and refresh and reconciles after retry", async () => {
  const { EditorView } = await import("@codemirror/view");
  const { flushConversationEditors } = await import("./conversationEditors");
  let reject = true;
  let content = "Original";
  vi.stubGlobal("fetch", async (request: Request) => {
    if (request.method === "PUT") {
      if (reject) return new Response("{}", { status: 503 });
      content = (await request.json()).content;
      return fileResponse(content);
    }
    return fileResponse(content);
  });
  const { host, render } = await panelHarness();
  await settle();
  const view = EditorView.findFromDOM(host.querySelector(".cm-editor")!)!;
  await act(async () =>
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: "Unsaved human draft" } }),
  );
  await act(async () => {
    await expect(flushConversationEditors("s1")).rejects.toBeDefined();
  });
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("conversationFiles.saveFailed");
  content = "Agent wrote meanwhile";
  await render("s1", false);
  await render();
  await act(async () => window.dispatchEvent(new Event("focus")));
  await settle();
  expect(host.textContent).toContain("Unsaved human draft");
  expect(host.textContent).not.toContain("Agent wrote meanwhile");
  reject = false;
  await act(async () => {
    await flushConversationEditors("s1");
  });
  await settle();
  expect(content).toBe("Unsaved human draft");
  expect(host.textContent).toContain("conversationFiles.saved");
});

it("flushes drafts from every switched and closed editor in the conversation", async () => {
  const { EditorView } = await import("@codemirror/view");
  const { flushConversationEditors } = await import("./conversationEditors");
  const saved: Record<string, string> = { "/notes.txt": "First", "/second.txt": "Second" };
  vi.stubGlobal("fetch", async (request: Request) => {
    const path = new URL(request.url).searchParams.get("path")!;
    if (request.method === "PUT") saved[path] = (await request.json()).content;
    return fileResponse(saved[path]);
  });
  const { host, render } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", [
    "/notes.txt",
    "/second.txt",
  ]);
  await settle();
  const edit = async (insert: string) => {
    const view = EditorView.findFromDOM(host.querySelector(".cm-editor")!)!;
    await act(async () => view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert } }));
  };
  await edit("Second revised");
  await act(async () => host.querySelectorAll<HTMLButtonElement>('[role="tab"]')[0].click());
  await settle();
  await edit("First revised");
  await render("s1", false);
  await act(async () => {
    await flushConversationEditors("s1");
  });
  expect(saved).toEqual({ "/notes.txt": "First revised", "/second.txt": "Second revised" });
});

it("rejects a delayed clean refresh after typing and reconciles the completed save", async () => {
  const { EditorView } = await import("@codemirror/view");
  const { flushConversationEditors } = await import("./conversationEditors");
  let reads = 0;
  let late!: (response: Response) => void;
  let content = "Original";
  vi.stubGlobal("fetch", async (request: Request) => {
    if (request.method === "PUT") {
      content = (await request.json()).content;
      return fileResponse(content);
    }
    reads += 1;
    if (reads === 2)
      return new Promise<Response>((resolve) => {
        late = resolve;
      });
    return fileResponse(reads > 2 ? "Agent update after save" : content);
  });
  const { host } = await panelHarness();
  await settle();
  await act(async () => window.dispatchEvent(new Event("focus")));
  const view = EditorView.findFromDOM(host.querySelector(".cm-editor")!)!;
  await act(async () =>
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: "Human local buffer" } }),
  );
  await act(async () => late(fileResponse("Old refresh snapshot")));
  await settle();
  expect(host.textContent).toContain("Human local buffer");
  await act(async () => {
    await flushConversationEditors("s1");
  });
  await settle();
  expect(content).toBe("Human local buffer");
  expect(host.textContent).toContain("Agent update after save");
  expect(host.textContent).not.toContain("Old refresh snapshot");
});

it("polls visible clean views at a bounded cadence and suspends polling while hidden", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  let content = "Original";
  let reads = 0;
  const visible = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  vi.stubGlobal("fetch", async () => {
    reads += 1;
    return fileResponse(content);
  });
  try {
    const { host, render } = await panelHarness();
    await settle();
    const initialReads = reads;
    content = "Independent background output";
    visible.mockReturnValue("hidden");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(reads).toBe(initialReads);
    visible.mockReturnValue("visible");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    await settle();
    expect(host.textContent).toContain("Independent background output");
    await render("s1", false);
    const closedReads = reads;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(reads).toBe(closedReads);
  } finally {
    visible.mockRestore();
    vi.useRealTimers();
  }
});

it("lets a slow initial read finish when the visible poll fires", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  const visible = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  let finishFirst!: (response: Response) => void;
  let reads = 0;
  vi.stubGlobal("fetch", () => {
    reads += 1;
    return new Promise<Response>((resolve) => {
      if (reads === 1) finishFirst = resolve;
    });
  });
  try {
    const { host } = await panelHarness();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    await act(async () => finishFirst(fileResponse("Slow storage result")));
    await settle();
    expect(host.textContent).toContain("Slow storage result");
  } finally {
    visible.mockRestore();
    vi.useRealTimers();
  }
});

it("names the real file panel close and resize controls in French", async () => {
  const { createInstance } = await import("i18next");
  const french = (await import("../../../locales/fr/translation.json")).default;
  const i18n = createInstance();
  await i18n.init({ lng: "fr", resources: { fr: { translation: french } }, interpolation: { escapeValue: false } });
  locale.language = "fr";
  locale.t = (key: string) => String(i18n.t(key));
  vi.stubGlobal("fetch", async () => fileResponse("Notes enregistrées"));
  const { host } = await panelHarness();
  await settle();
  expect.soft(host.querySelector('button[aria-label="Fermer le panneau"]')).not.toBeNull();
  expect.soft(host.querySelector('[role="separator"]')?.getAttribute("aria-label")).toBe("Redimensionner le panneau");
});

it("renders filesystem Markdown with the existing rich editor and respects server read-only policy", async () => {
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response(
        JSON.stringify({
          type: "conversation_file",
          session_id: "s1",
          path: "/report.md",
          viewer: "markdown",
          editable: false,
          content: "# Reviewed report\n\nThe **approved** result (<3ms).",
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
  );
  const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/report.md"]);
  await settle();
  expect(host.querySelector("h1")?.textContent).toBe("Reviewed report");
  expect(host.querySelector("strong")?.textContent).toBe("approved");
  expect(host.textContent).toContain("result (<3ms).");
  expect(host.querySelector('[contenteditable="true"]')).toBeNull();
  expect(host.textContent).toContain("conversationFiles.readOnly");
});

it.each(["md", "docx"] as const)(
  "flushes a rich Markdown edit before exporting %s from the saved file",
  async (format) => {
    let content = "# Reviewed report\n\nInitial result.";
    let releaseSave!: () => void;
    let downloaded: string | undefined;
    vi.stubGlobal("fetch", async (input: Request | string, init?: RequestInit) => {
      const request = typeof input === "string" ? new Request(input, init) : input;
      if (new URL(request.url).pathname.endsWith("/export")) {
        expect(request.headers.get("Authorization")).toBe("Bearer test");
        expect(new URL(request.url).searchParams.get("path")).toBe("/report.md");
        expect(new URL(request.url).searchParams.get("team_id")).toBe("t1");
        expect(new URL(request.url).searchParams.get("format")).toBe(format);
        downloaded = content;
        return new Response(content);
      }
      if (request.method === "PUT") {
        const next = (await request.json()).content;
        await new Promise<void>((resolve) => {
          releaseSave = resolve;
        });
        content = next;
      }
      return markdownResponse(content);
    });
    vi.stubGlobal(
      "URL",
      class extends URL {
        static createObjectURL = () => "blob:test";
        static revokeObjectURL = () => undefined;
      },
    );
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    try {
      const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/report.md"]);
      await settle();
      const insertCode = host.querySelector<HTMLButtonElement>('button[aria-label="Insert Code Block"]');
      expect(insertCode).not.toBeNull();
      await act(async () => insertCode!.click());
      const download = [...host.querySelectorAll<HTMLButtonElement>("button")].find((b) =>
        b.textContent?.includes(`capability.writable_document.format.${format === "md" ? "markdown" : "word"}`),
      );
      expect(download).toBeDefined();
      await act(async () => download!.click());
      await settle();
      expect(downloaded).toBeUndefined();
      await act(async () => releaseSave());
      await settle();
      expect(downloaded).toContain("```");
      expect(downloaded).toContain("# Reviewed report");
      expect(click).toHaveBeenCalledOnce();
    } finally {
      click.mockRestore();
    }
  },
);

it("preserves rich Markdown drafts on failed export flush, refresh and retry", async () => {
  let content = "# Original report\n\nInitial result.";
  let failSave = true;
  const downloads: string[] = [];
  vi.stubGlobal("fetch", async (input: Request | string, init?: RequestInit) => {
    const request = typeof input === "string" ? new Request(input, init) : input;
    if (new URL(request.url).pathname.endsWith("/export")) {
      downloads.push(content);
      return new Response(content);
    }
    if (request.method === "PUT") {
      if (failSave) return new Response("{}", { status: 503 });
      content = (await request.json()).content;
    }
    return markdownResponse(content);
  });
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = () => "blob:test";
      static revokeObjectURL = () => undefined;
    },
  );
  const anchor = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  try {
    const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/report.md"]);
    await settle();
    await act(async () => host.querySelector<HTMLButtonElement>('button[aria-label="Insert Code Block"]')!.click());
    const download = [...host.querySelectorAll<HTMLButtonElement>("button")].find((b) =>
      b.textContent?.includes("capability.writable_document.format.word"),
    )!;
    await act(async () => download.click());
    await settle();
    expect(downloads).toEqual([]);
    expect(host.textContent).toContain("conversationFiles.exportFailed");
    expect(host.textContent).toContain("conversationFiles.saveFailed");
    content = "# Agent changed the report";
    await act(async () => window.dispatchEvent(new Event("focus")));
    await settle();
    expect(host.querySelector("h1")?.textContent).toBe("Original report");
    expect(host.querySelector(".cm-editor")).not.toBeNull();
    failSave = false;
    await act(async () => download.click());
    await settle();
    expect(downloads).toHaveLength(1);
    expect(downloads[0]).toContain("# Original report");
    expect(downloads[0]).toContain("```");
    expect(host.textContent).not.toContain("conversationFiles.exportFailed");
  } finally {
    anchor.mockRestore();
  }
});

it("refreshes clean rendered Markdown without autosaving editor normalization", async () => {
  let content = "# Before\n\nLatency <3ms.";
  const writes: string[] = [];
  vi.stubGlobal("fetch", async (request: Request) => {
    if (request.method === "PUT") writes.push((await request.json()).content);
    return markdownResponse(content);
  });
  const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/report.md"]);
  await settle();
  content = "# After agent write\n\nThe **current** report.";
  await act(async () => window.dispatchEvent(new Event("focus")));
  await settle();
  expect(host.querySelector("h1")?.textContent).toBe("After agent write");
  expect(host.querySelector("strong")?.textContent).toBe("current");
  await act(async () => new Promise((resolve) => setTimeout(resolve, 700)));
  expect(writes).toEqual([]);
});

it("names export actions and reports denied downloads in French while preserving readable Markdown", async () => {
  const { createInstance } = await import("i18next");
  const french = (await import("../../../locales/fr/translation.json")).default;
  const i18n = createInstance();
  await i18n.init({ lng: "fr", resources: { fr: { translation: french } }, interpolation: { escapeValue: false } });
  locale.language = "fr";
  locale.t = (key: string) => String(i18n.t(key));
  vi.stubGlobal("fetch", async (input: Request | string) => {
    const url = typeof input === "string" ? input : input.url;
    return url.includes("/export?")
      ? new Response("{}", { status: 403 })
      : markdownResponse("# Rapport conservé", false);
  });
  const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/report.md"]);
  await settle();
  const download = [...host.querySelectorAll<HTMLButtonElement>("button")].find(
    (b) => b.textContent === "Microsoft Word",
  )!;
  expect(download).toBeDefined();
  expect(host.querySelector('[role="group"][aria-label="Télécharger"]')).not.toBeNull();
  await act(async () => download.click());
  await settle();
  expect(host.querySelector('[role="alert"]')?.textContent).toBe(
    "Impossible d'exporter ce fichier. Vos modifications sont conservées. Réessayez.",
  );
  expect(host.querySelector("h1")?.textContent).toBe("Rapport conservé");
  expect(download.disabled).toBe(false);
});

it("exports a clean Markdown report while another file retains a failed draft", async () => {
  const { EditorView } = await import("@codemirror/view");
  let downloaded: string | undefined;
  vi.stubGlobal("fetch", async (input: Request | string) => {
    const request = typeof input === "string" ? new Request(input) : input;
    if (new URL(request.url).pathname.endsWith("/export")) {
      downloaded = "# Clean report";
      return new Response(downloaded);
    }
    if (request.method === "PUT") return new Response("{}", { status: 503 });
    return new URL(request.url).searchParams.get("path") === "/report.md"
      ? markdownResponse("# Clean report")
      : fileResponse("Original notes");
  });
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = () => "blob:test";
      static revokeObjectURL = () => undefined;
    },
  );
  const anchor = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  try {
    const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", [
      "/report.md",
      "/notes.txt",
    ]);
    await settle();
    const view = EditorView.findFromDOM(host.querySelector(".cm-editor")!)!;
    await act(async () =>
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: "Failed notes draft" } }),
    );
    await act(async () => new Promise((resolve) => setTimeout(resolve, 700)));
    expect(host.textContent).toContain("conversationFiles.saveFailed");
    await act(async () => host.querySelectorAll<HTMLButtonElement>('[role="tab"]')[0].click());
    await settle();
    const download = [...host.querySelectorAll<HTMLButtonElement>("button")].find((b) =>
      b.textContent?.includes("capability.writable_document.format.markdown"),
    )!;
    await act(async () => download.click());
    await settle();
    expect(downloaded).toBe("# Clean report");
    await act(async () => host.querySelectorAll<HTMLButtonElement>('[role="tab"]')[1].click());
    await settle();
    expect(host.textContent).toContain("Failed notes draft");
    expect(host.textContent).toContain("conversationFiles.saveFailed");
  } finally {
    anchor.mockRestore();
  }
});

it("previews authorized HTML without sanitizing the saved source and switches to editable source by keyboard", async () => {
  const original =
    '<h1>Reviewed page</h1><script>alert(1)</script><img src="https://outside.test/pixel"><button onclick="alert(2)">Run</button>';
  let content = original;
  const writes: string[] = [];
  vi.stubGlobal("fetch", async (request: Request) => {
    if (request.method === "PUT") {
      content = (await request.json()).content;
      writes.push(content);
    }
    return new Response(
      JSON.stringify({
        type: "conversation_file",
        session_id: "s1",
        path: "/page.html",
        viewer: "html",
        editable: true,
        content,
      }),
      { headers: { "Content-Type": "application/json" } },
    );
  });
  const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/page.html"]);
  await settle();
  const preview = host.querySelector<HTMLIFrameElement>("iframe[srcdoc]");
  expect(preview).not.toBeNull();
  expect(preview!.getAttribute("sandbox")).toBe("");
  expect(preview!.srcdoc).toContain("<h1>Reviewed page</h1>");
  expect(preview!.srcdoc).not.toContain("<script");
  expect(preview!.srcdoc).not.toContain("onclick");
  expect(preview!.srcdoc).toContain("default-src 'none'");
  expect(writes).toEqual([]);
  const previewTab = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
    (tab) => tab.textContent === "conversationFiles.previewView",
  );
  expect(previewTab).not.toBeNull();
  await act(async () => {
    previewTab!.focus();
    previewTab!.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  });
  const sourceTab = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
    (tab) => tab.textContent === "conversationFiles.sourceView",
  );
  expect(document.activeElement).toBe(sourceTab);
  expect(sourceTab!.getAttribute("aria-selected")).toBe("true");
  const { EditorView } = await import("@codemirror/view");
  const editor = EditorView.findFromDOM(host.querySelector(".cm-editor")!)!;
  expect(editor.state.doc.toString()).toBe(original);
  const revised = original.replace("Reviewed page", "Saved review");
  await act(async () => editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: revised } }));
  const { flushConversationEditors } = await import("./conversationEditors");
  await act(async () => {
    await flushConversationEditors("s1");
  });
  await settle();
  await act(async () => previewTab!.click());
  expect(content).toBe(revised);
  expect(writes).toEqual([revised]);
  expect(
    [...host.querySelectorAll<HTMLIFrameElement>("iframe[srcdoc]")].some((frame) =>
      frame.srcdoc.includes("<h1>Saved review</h1>"),
    ),
  ).toBe(true);
  content = "<h1>Agent refreshed preview</h1>";
  await act(async () => window.dispatchEvent(new Event("focus")));
  await settle();
  expect(
    [...host.querySelectorAll<HTMLIFrameElement>("iframe[srcdoc]")].some((frame) =>
      frame.srcdoc.includes("<h1>Agent refreshed preview</h1>"),
    ),
  ).toBe(true);
});

it("keeps failed HTML drafts across Preview/Source switches and retries the original source", async () => {
  let content = "<h1>Original</h1>";
  let failSave = true;
  vi.stubGlobal("fetch", async (request: Request) => {
    if (request.method === "PUT") {
      if (failSave) return new Response("{}", { status: 503 });
      content = (await request.json()).content;
    }
    return new Response(
      JSON.stringify({
        type: "conversation_file",
        session_id: "s1",
        path: "/page.html",
        viewer: "html",
        editable: true,
        content,
      }),
      { headers: { "Content-Type": "application/json" } },
    );
  });
  const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/page.html"]);
  await settle();
  const sourceTab = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
    (tab) => tab.textContent === "conversationFiles.sourceView",
  )!;
  await act(async () => sourceTab.click());
  const { EditorView } = await import("@codemirror/view");
  const editor = EditorView.findFromDOM(host.querySelector(".cm-editor")!)!;
  const revised = "<h1>Human draft</h1><script>retainedInSource()</script>";
  await act(async () => editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: revised } }));
  const { flushConversationEditors } = await import("./conversationEditors");
  await act(async () => {
    await expect(flushConversationEditors("s1")).rejects.toBeDefined();
  });
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("conversationFiles.saveFailed");
  expect(content).toBe("<h1>Original</h1>");
  const previewTab = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
    (tab) => tab.textContent === "conversationFiles.previewView",
  )!;
  await act(async () => previewTab.click());
  expect(host.querySelector<HTMLIFrameElement>("iframe[srcdoc]")?.srcdoc).toContain("<h1>Human draft</h1>");
  expect(host.querySelector<HTMLIFrameElement>("iframe[srcdoc]")?.srcdoc).not.toContain("retainedInSource");
  await act(async () => sourceTab.click());
  expect(EditorView.findFromDOM(host.querySelector(".cm-editor")!)!.state.doc.toString()).toBe(revised);
  failSave = false;
  const retry = host.querySelector<HTMLButtonElement>('[role="alert"] button')!;
  await act(async () => retry.click());
  await settle();
  expect(content).toBe(revised);
  expect(host.textContent).toContain("conversationFiles.saved");
});

it("labels read-only HTML Preview/Source controls in French using the current server policy", async () => {
  const { createInstance } = await import("i18next");
  const french = (await import("../../../locales/fr/translation.json")).default;
  const i18n = createInstance();
  await i18n.init({ lng: "fr", resources: { fr: { translation: french } }, interpolation: { escapeValue: false } });
  locale.language = "fr";
  locale.t = (key: string) => String(i18n.t(key));
  const fetch = vi.fn(
    async (_request: Request) =>
      new Response(
        JSON.stringify({
          type: "conversation_file",
          session_id: "s1",
          path: "/page.html",
          viewer: "html",
          editable: false,
          content: "<h1>Lecture seule</h1>",
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
  );
  vi.stubGlobal("fetch", fetch);
  const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/page.html"]);
  await settle();
  expect(host.querySelector('[role="tablist"][aria-label="Vue HTML"]')).not.toBeNull();
  expect(host.textContent).toContain("Aperçu en lecture seule");
  const sourceTab = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(
    (tab) => tab.textContent === "Source",
  )!;
  await act(async () => sourceTab.click());
  expect(host.querySelector('[role="textbox"]')?.getAttribute("aria-readonly")).toBe("true");
  await act(async () => sourceTab.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true })));
  expect(document.activeElement?.textContent).toBe("Aperçu");
  expect(host.querySelector('[role="tabpanel"][aria-labelledby] iframe')).not.toBeNull();
  expect(fetch.mock.calls.every(([request]) => (request as Request).method === "GET")).toBe(true);
});

it("names the real Markdown formatting, link and code controls in French", async () => {
  const { createInstance } = await import("i18next");
  const french = (await import("../../../locales/fr/translation.json")).default;
  const i18n = createInstance();
  await i18n.init({ lng: "fr", resources: { fr: { translation: french } }, interpolation: { escapeValue: false } });
  locale.language = "fr";
  locale.t = (key: string) => String(i18n.t(key));
  vi.stubGlobal("fetch", async () => markdownResponse("# Rapport\n\nTexte à réviser."));
  const { host } = await panelHarness("http://runtime.test/pod/v1/agents/sessions/s1/messages", ["/report.md"]);
  await settle();
  expect(host.querySelector('button[aria-label="Gras"]')).not.toBeNull();
  expect(host.querySelector('button[aria-label="Insérer un bloc de code"]')).not.toBeNull();
  const link = host.querySelector<HTMLButtonElement>('button[aria-label="Créer un lien"]');
  expect(link).not.toBeNull();
});
