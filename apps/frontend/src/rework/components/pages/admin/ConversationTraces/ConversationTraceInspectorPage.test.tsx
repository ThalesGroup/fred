// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { configureStore } from "@reduxjs/toolkit";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import ConversationTraceInspectorPage from "./ConversationTraceInspectorPage";

const traceId = "1".repeat(32);
const spanId = (id: number) => id.toString(16).padStart(16, "0");
const ref = (id: number) => id.toString(16).padStart(32, "0");
const leftTask = ref(10);
const rightTask = ref(11);
const leftWrite = ref(12);
const rightWrite = ref(13);
const rightAttempt = ref(14);

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
vi.mock("../../../../../common/dynamicBaseQuery", () => ({
  createDynamicBaseQuery:
    () =>
    async ({ url }: { url: string }) => {
      if (url.includes("/spans/")) {
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
        return {
          data: [
            {
              ref: rightAttempt,
              call_id: "model-right",
              attempt: 1,
              model: "test-model",
              status: 200,
              duration_ms: 10,
              request_bytes: 20,
              response_bytes: 20,
              completeness: "complete",
            },
          ],
        };
      }
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
              outcome: "completed",
              availability: "captured",
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

it("nests interleaved Deep calls under the task span that ran them and preserves HTTP deep links", async () => {
  const store = configureStore({
    reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
    middleware: (getDefault) => getDefault().concat(enhancedControlPlaneApi.middleware),
  });
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
