// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { configureStore } from "@reduxjs/toolkit";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { expect, it, vi } from "vitest";

const requests = vi.hoisted(() => ({ headers: 0, blocked: undefined as Promise<void> | undefined }));
const protectedHeader = "fictional-upstream-id";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../../../common/dynamicBaseQuery", () => ({
  createDynamicBaseQuery:
    () =>
    async ({ url }: { url: string }) => {
      if (url.includes("/sse-headers/")) {
        requests.headers++;
        if (requests.blocked) {
          await requests.blocked;
          return { error: { status: 403 } };
        }
        return { data: { headers: { "x-request-id": protectedHeader } } };
      }
      return {
        data: [
          {
            observed_through_rank: 1,
            provider: [],
            outgoing: {
              ref: "0".repeat(32),
              started_ms: 0,
              headers_ms: 5,
              headers_available: true,
              end_ms: 10,
              last_event_ms: null,
              longest_gap: null,
              availability: "empty",
              ending: "completed",
              frame_count: 0,
              frames: [],
            },
          },
        ],
      };
    },
}));

import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { ConversationTraceSse } from "./ConversationTraceSse";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("hides protected SSE headers during reauthorization and after revocation", async () => {
  const store = configureStore({
    reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
    middleware: (getDefault) => getDefault().concat(enhancedControlPlaneApi.middleware),
  });
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const revocation = { finish: () => {} };
  const revoked = new Promise<void>((resolve) => {
    revocation.finish = resolve;
  });
  try {
    await act(async () => {
      root.render(
        <Provider store={store}>
          <ConversationTraceSse
            sessionId="session"
            cutoffRank={1}
            turn={{
              exchange_id: "exchange",
              turn_number: 1,
              started_at: "2026-11-19T12:00:00Z",
              duration_ms: 10,
              outcome: "completed",
              availability: "captured",
              call_ids: [],
              trace_id: null,
              span_id: null,
              access: "shared",
            }}
          />
        </Provider>,
      );
    });
    const details = host.querySelector("details")!;
    const toggle = (open: boolean) =>
      act(async () => {
        details.open = open;
        details.dispatchEvent(new Event("toggle"));
      });
    await toggle(true);
    expect(host.textContent).toContain(protectedHeader);
    requests.blocked = revoked;
    await act(async () => {
      store.dispatch(
        enhancedControlPlaneApi.util.invalidateTags([{ type: "ConversationTraceConsent", id: "session" }]),
      );
    });
    expect(requests.headers).toBe(2);
    expect(host.textContent).not.toContain(protectedHeader);
    await toggle(false);
    await toggle(true);
    expect(requests.headers).toBe(3);
    expect(host.textContent).not.toContain(protectedHeader);
    await act(async () => {
      const pending = store.dispatch(enhancedControlPlaneApi.util.getRunningQueriesThunk());
      revocation.finish();
      await Promise.all(pending);
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(host.textContent).toContain("headersUnavailable");
    expect(host.textContent).not.toContain(protectedHeader);
  } finally {
    revocation.finish();
    act(() => root.unmount());
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
  }
});
