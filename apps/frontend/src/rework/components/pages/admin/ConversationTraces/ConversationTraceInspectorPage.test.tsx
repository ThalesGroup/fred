// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { configureStore } from "@reduxjs/toolkit";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import ConversationTraceInspectorPage from "./ConversationTraceInspectorPage";
import ConversationTraceListPage from "./ConversationTraceListPage";
import { TRACE_LIST_PATH } from "./traceControls";

const traceId = "1".repeat(32);
const spanId = (id: number) => id.toString(16).padStart(16, "0");
const ref = (id: number) => id.toString(16).padStart(32, "0");
const leftTask = ref(10);
const rightTask = ref(11);
const leftWrite = ref(12);
const rightWrite = ref(13);
const rightAttempt = ref(14);
const earlierAttempt = ref(16);
const catalogPath = "/control-plane/v1" + TRACE_LIST_PATH;
const catalogRequest = vi.fn();

function span(id: number, parent: number, name: string, attribute: string, value: string) {
  return {
    traceId,
    spanId: spanId(id),
    parentSpanId: parent ? spanId(parent) : undefined,
    name,
    startTimeUnixNano: String(id * 1000),
    endTimeUnixNano: "10000",
    attributes: [{ key: attribute, value: { stringValue: value } }],
  };
}

const tools = [
  { ref: leftTask, call_id: "task-left", tool_name: "task" },
  { ref: rightTask, call_id: "task-right", tool_name: "task" },
  { ref: rightWrite, call_id: "write-right", tool_name: "write_file" },
  { ref: leftWrite, call_id: "write-left", tool_name: "write_file" },
].map((tool) => ({
  ...tool,
  source: "native",
  outcome: "success",
  attempt: 1,
  duration_ms: 10,
  observed_through_rank: 1,
  completeness: "complete",
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "Agent", agentsNicknamePlural: "Agents" }),
}));
vi.mock("../../../../../common/dynamicBaseQuery", () => ({
  createDynamicBaseQuery:
    () =>
    async ({ url, params }: { url: string; params?: Record<string, unknown> }) => {
      const interrupted = url.includes("/interrupted");
      if (url === catalogPath) {
        catalogRequest(params);
        return {
          data: {
            conversations: [
              {
                session_id: "session",
                title: params?.cursor ? "Second page conversation" : "First page conversation",
                user_display_name: "Support user",
                team_name: "Team",
                agent_display_name: "Deep",
                outcome: "completed",
                availability: "captured",
                access: "shared",
                latest_started_at: "2026-11-19T12:00:00Z",
              },
            ],
            next_cursor: params?.cursor ? null : "session|first",
          },
        };
      }
      if (url === catalogPath + "/settings") return { data: { enabled: false } };
      if (url === catalogPath + "/teams") return { data: [] };
      if (url.includes("/spans/")) {
        if (interrupted) return { data: [] };
        return {
          data: [
            span(1, 0, "agent.stream", "fred.capture.ref", "capture"),
            span(2, 1, "task", "fred.evidence.ref", leftTask),
            span(3, 1, "task", "fred.evidence.ref", rightTask),
            span(4, 3, "model", "fred.call.id", "model-right"),
            span(5, 3, "write_file", "fred.evidence.ref", rightWrite),
            span(6, 2, "write_file", "fred.evidence.ref", leftWrite),
          ],
        };
      }
      if (url.includes("/http/")) {
        const attempt = {
          ref: rightAttempt,
          call_id: "model-right",
          attempt: 1,
          model: "test-model",
          status: 200,
          duration_ms: 10,
          request_bytes: 20,
          response_bytes: 20,
          completeness: "complete",
        };
        if (!interrupted) return { data: [attempt] };
        return {
          data: [
            { ...attempt, ref: earlierAttempt, call_id: "model-left" },
            ...Array.from({ length: 120 }, (_, index) => ({
              ...attempt,
              ref: ref(index + 100),
              call_id: "earlier-model-" + index,
            })),
            { ...attempt, failure_stage: "response_body" },
          ],
        };
      }
      if (url.includes("/sse/")) return { data: [] };
      if (url.includes("/model/")) {
        return {
          data: [
            {
              ref: ref(15),
              call_id: "model-right",
              model: "test-model",
              observed_through_rank: 1,
              completeness: "complete",
            },
          ],
        };
      }
      if (url.includes("/tool/")) return { data: tools };
      return {
        data: {
          session_id: "session",
          team_id: "team",
          agent_display_name: "Deep",
          retained_after_delete: true,
          next_cursor: null,
          turns: [
            {
              exchange_id: "exchange",
              turn_number: 1,
              started_at: "2026-11-19T12:00:00Z",
              outcome: interrupted ? "failed" : "completed",
              failure_category: interrupted ? "stream_interrupted" : null,
              availability: interrupted ? "partial" : "captured",
              access: "masked",
              trace_id: traceId,
              span_id: spanId(1),
              call_ids: [],
            },
          ],
        },
      };
    },
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function createStore() {
  return configureStore({
    reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
    middleware: (getDefault) => getDefault().concat(enhancedControlPlaneApi.middleware),
  });
}

it("nests interleaved Deep calls under the task span that ran them and preserves HTTP deep links", async () => {
  const store = createStore();
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const link = (call: string) => host.querySelector<HTMLAnchorElement>(`nav a[href*="call=${call}"]`);

  try {
    await act(async () => {
      root.render(
        <Provider store={store}>
          <MemoryRouter
            initialEntries={[`/admin/conversation-traces/session?turn=exchange&call=${rightAttempt}&view=http`]}
          >
            <Routes>
              <Route path="/admin/conversation-traces/:sessionId" element={<ConversationTraceInspectorPage />} />
            </Routes>
          </MemoryRouter>
        </Provider>,
      );
    });
    await act(async () => {
      await Promise.all(store.dispatch(enhancedControlPlaneApi.util.getRunningQueriesThunk()));
    });
    await act(async () => {
      await Promise.all(store.dispatch(enhancedControlPlaneApi.util.getRunningQueriesThunk()));
    });

    const leftBranch = link(leftTask)?.closest("li");
    const rightBranch = link(rightTask)?.closest("li");
    expect(leftBranch?.contains(link(leftWrite))).toBe(true);
    expect(rightBranch?.contains(link(rightWrite))).toBe(true);
    expect(leftBranch?.contains(link(rightWrite))).toBe(false);
    expect(rightBranch?.contains(link(leftWrite))).toBe(false);
    expect(rightBranch?.contains(link(rightAttempt))).toBe(true);
    expect(link(rightAttempt)?.getAttribute("aria-current")).toBe("true");
    expect(host.querySelector('nav a[href*="view=history"]')?.textContent).toContain("savedHistory");
  } finally {
    act(() => root.unmount());
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
  }
});

it("opens the interrupted HTTP 200 attempt and links back to it from the turn summary", async () => {
  const store = createStore();
  const pathname = TRACE_LIST_PATH + "/interrupted";
  const router = createMemoryRouter(
    [{ path: TRACE_LIST_PATH + "/:sessionId", element: <ConversationTraceInspectorPage /> }],
    { initialEntries: [pathname] },
  );
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  const settle = () =>
    act(async () => {
      await Promise.all(store.dispatch(enhancedControlPlaneApi.util.getRunningQueriesThunk()));
    });

  try {
    await act(async () =>
      root.render(
        <Provider store={store}>
          <RouterProvider router={router} />
        </Provider>,
      ),
    );
    await settle();
    const failedLink = host.querySelector(`a[aria-current="true"][href*="call=${rightAttempt}"]`);
    expect(failedLink?.textContent).toContain("http.stage.response_body");
    expect(failedLink?.textContent).toContain("200");
    expect(host.querySelector(`a[href*="call=${earlierAttempt}"]`)).toBeNull();
    const previous = [...host.querySelectorAll<HTMLButtonElement>('nav[aria-label="callPages"] button')].find(
      (button) => button.textContent === "previous",
    );
    expect(previous?.disabled).toBe(false);
    await act(async () => previous!.click());
    expect(host.querySelector(`a[aria-current="true"][href*="call=${rightAttempt}"]`)).toBeNull();

    await act(async () => router.navigate(pathname + "?turn=exchange&view=history"));
    await settle();
    const jump = [...host.querySelectorAll<HTMLAnchorElement>("a")].find((link) =>
      link.textContent?.endsWith("jumpToFailedCall"),
    );
    expect(jump?.href).toContain(`call=${rightAttempt}`);
  } finally {
    act(() => root.unmount());
    router.dispose();
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
  }
});

it("restores catalog filters, sort, search and page through either return path", async () => {
  const store = createStore();
  const router = createMemoryRouter(
    [
      { path: TRACE_LIST_PATH, element: <ConversationTraceListPage /> },
      { path: TRACE_LIST_PATH + "/:sessionId", element: <ConversationTraceInspectorPage /> },
    ],
    { initialEntries: [TRACE_LIST_PATH] },
  );
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const catalogLink = () => host.querySelector<HTMLAnchorElement>(`a[href="${TRACE_LIST_PATH}/session"]`);
  const searchInput = () => host.querySelector<HTMLInputElement>('input[type="search"]')!;
  const settleCatalog = () =>
    act(async () => {
      await Promise.all(store.dispatch(enhancedControlPlaneApi.util.getRunningQueriesThunk()));
    });
  const click = async (element: HTMLElement | null | undefined) => {
    expect(element).toBeTruthy();
    await act(async () => element!.click());
    await settleCatalog();
  };
  const button = (label: string) =>
    [...host.querySelectorAll("button")].find((item) =>
      [...item.childNodes].some((node) => node.textContent === label),
    );
  const typeSearch = async (value: string) => {
    vi.useFakeTimers();
    try {
      await act(async () => {
        const input = searchInput();
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await act(async () => vi.advanceTimersByTimeAsync(250));
    } finally {
      vi.useRealTimers();
    }
    await settleCatalog();
  };

  try {
    await act(async () => {
      root.render(
        <Provider store={store}>
          <RouterProvider router={router} />
        </Provider>,
      );
    });
    await settleCatalog();
    expect(button("quickStatus.failed")?.getAttribute("aria-pressed")).toBe("true");
    expect(button("consentOptions.shared")?.getAttribute("aria-pressed")).toBe("true");
    await click(button("quickStatus.all"));
    await click(button("consentOptions.all"));
    await click(button("conversation"));
    await typeSearch("Support ");
    expect(searchInput().value).toBe("Support ");
    await typeSearch(searchInput().value + "user");
    await click(button("next"));
    const filteredSearch = router.state.location.search;
    expect(new URLSearchParams(filteredSearch)).toEqual(
      new URLSearchParams({ status: "all", consent: "all", sort: "title", direction: "asc", q: "Support user" }),
    );

    await click(catalogLink());
    await act(async () => router.navigate(-1));
    await settleCatalog();
    expect(catalogLink()?.textContent).toContain("Second page conversation");

    await click(catalogLink());
    await click(host.querySelector<HTMLAnchorElement>('nav a[href*="view=history"]'));
    const breadcrumb = host.querySelector<HTMLAnchorElement>('a[href*="status=all"]');
    await click(breadcrumb);
    expect(router.state.location.search).toBe(filteredSearch);
    expect(searchInput().value).toBe("Support user");
    expect(catalogLink()?.textContent).toContain("Second page conversation");
    expect(catalogRequest).toHaveBeenLastCalledWith(
      expect.objectContaining({
        outcomes: undefined,
        consent: "all",
        sort: "title",
        direction: "asc",
        query: "Support user",
        cursor: "session|first",
      }),
    );
    await click(button("previous"));
    expect(catalogLink()?.textContent).toContain("First page conversation");

    await act(async () => router.navigate(TRACE_LIST_PATH + filteredSearch));
    await settleCatalog();
    expect(button("quickStatus.all")?.getAttribute("aria-pressed")).toBe("true");
    expect(searchInput().value).toBe("Support user");
    expect(catalogRequest).toHaveBeenLastCalledWith(
      expect.objectContaining({ sort: "title", query: "Support user", cursor: undefined }),
    );

    await typeSearch("");
    expect(new URLSearchParams(router.state.location.search).has("q")).toBe(false);
    await typeSearch("Support user");
    await act(async () => router.navigate(TRACE_LIST_PATH));
    await settleCatalog();
    expect(button("quickStatus.failed")?.getAttribute("aria-pressed")).toBe("true");
    expect(searchInput().value).toBe("");
  } finally {
    act(() => root.unmount());
    router.dispose();
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
  }
});
