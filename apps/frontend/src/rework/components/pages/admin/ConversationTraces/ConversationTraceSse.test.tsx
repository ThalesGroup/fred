// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom

import { configureStore } from "@reduxjs/toolkit";
import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";
import { expect, it, vi } from "vitest";
import type { TraceSseLane, TraceSseSegment } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const requests = vi.hoisted(() => ({
  headers: 0,
  blocked: undefined as Promise<void> | undefined,
  segments: undefined as TraceSseSegment[] | undefined,
  pageCalls: [] as string[],
  frameCalls: [] as string[],
  inFlightPages: 0,
  peakPageConcurrency: 0,
  denyPage: undefined as number | undefined,
  laneTimes: new Map<string, number[]>(),
}));
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
      if (url.includes("/sse-frames/")) {
        requests.pageCalls.push(url);
        requests.inFlightPages++;
        requests.peakPageConcurrency = Math.max(requests.peakPageConcurrency, requests.inFlightPages);
        await new Promise((resolve) => setTimeout(resolve, 1));
        requests.inFlightPages--;
        const page = Number(url.slice(url.lastIndexOf("/") + 1));
        if (page === requests.denyPage) return { error: { status: 403 } };
        const path = url.split("/");
        const ref = path[path.length - 2];
        const times = requests.laneTimes.get(ref) ?? [ref === "d".repeat(32) ? 3205 : page * 10 + 5];
        return {
          data: {
            start_index: page * 256,
            frames: times.map((at_ms) => ({ at_ms, kind: "text", offset: page, size: 10 })),
          },
        };
      }
      if (url.split("/sse/")[1]?.split("/").length === 3) {
        requests.frameCalls.push(url);
        return { data: { data: btoa("data: fixture\n\n") } };
      }
      if (requests.segments) return { data: requests.segments };
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
    await act(async () => window.dispatchEvent(new Event("focus")));
    expect(requests.headers).toBe(2);
    expect(host.textContent).not.toContain(protectedHeader);
    await toggle(false);
    await act(async () => window.dispatchEvent(new Event("focus")));
    expect(requests.headers).toBe(2);
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

it("loads both tracks and later attempts with stable frame ordinals and enforces consent", async () => {
  const ref = "f".repeat(32);
  const outgoingRef = "e".repeat(32);
  const laterRef = "d".repeat(32);
  const pageCount = 313;
  const lastPage = pageCount - 1;
  const published: TraceSseSegment[] = [
    {
      observed_through_rank: 1,
      outgoing: {
        ref: outgoingRef,
        started_ms: 0,
        end_ms: 3250,
        headers_ms: null,
        last_event_ms: 5,
        longest_gap: null,
        availability: "captured",
        ending: "completed",
        frame_count: 1,
        page_starts_ms: [5],
      },
      provider: [
        {
          ref,
          started_ms: 0,
          end_ms: 3150,
          headers_ms: null,
          last_event_ms: 3125,
          longest_gap: null,
          availability: "partial",
          ending: "truncated",
          frame_count: lastPage * 256 + 1,
          page_starts_ms: Array.from({ length: pageCount }, (_, page) => page * 10 + 5),
        },
        {
          ref: laterRef,
          started_ms: 3200,
          end_ms: 3250,
          headers_ms: null,
          last_event_ms: 3205,
          longest_gap: null,
          availability: "captured",
          ending: "completed",
          frame_count: 1,
          page_starts_ms: [3205],
        },
      ],
    },
  ];
  requests.segments = [];
  const store = configureStore({
    reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
    middleware: (getDefault) => getDefault().concat(enhancedControlPlaneApi.middleware),
  });
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  const settle = () =>
    act(async () => {
      await Promise.all(store.dispatch(enhancedControlPlaneApi.util.getRunningQueriesThunk()));
    });
  const render = (access: "shared" | "masked", capture_status: "saving" | "complete" = "complete") =>
    act(async () => {
      root.render(
        <Provider store={store}>
          <StrictMode>
            <ConversationTraceSse
              key={access}
              sessionId="session"
              cutoffRank={1}
              turn={{
                exchange_id: "exchange",
                turn_number: 1,
                started_at: "2026-11-19T12:00:00Z",
                duration_ms: 3250,
                outcome: "failed",
                availability: "partial",
                capture_status,
                call_ids: [],
                trace_id: null,
                span_id: null,
                access,
              }}
            />
          </StrictMode>
        </Provider>,
      );
    });
  try {
    await render("masked", "saving");
    await settle();
    expect(host.querySelector('[data-track="provider"]')).toBeNull();

    requests.segments = published;
    await render("masked");
    await settle();
    expect(requests.pageCalls).toHaveLength(0);
    expect(host.textContent).toContain("maskedFrameIndex");

    await render("shared");
    const rows = () => [...host.querySelectorAll<HTMLButtonElement>("li button")];
    await vi.waitFor(
      async () => {
        await settle();
        expect(rows()).toHaveLength(pageCount + 2);
      },
      { timeout: 4000 },
    );
    expect(requests.pageCalls).toHaveLength(pageCount + 2);
    expect(requests.peakPageConcurrency).toBeGreaterThan(1);
    expect(requests.peakPageConcurrency).toBeLessThanOrEqual(4);
    expect(requests.pageCalls).toContainEqual(expect.stringMatching(new RegExp(`/${laterRef}/0$`)));
    expect(requests.frameCalls).toHaveLength(0);
    expect(host.querySelectorAll('[data-track="provider"] button')).toHaveLength(pageCount + 1);
    expect(host.querySelectorAll('[data-track="outgoing"] button')).toHaveLength(1);
    const firstEvent = rows()[0];
    await act(async () => {
      window.dispatchEvent(new Event("blur"));
      window.dispatchEvent(new Event("focus"));
    });
    expect(rows()[0]).toBe(firstEvent);
    expect(requests.pageCalls).toHaveLength(pageCount + 2);
    const lastFailedEvent = rows().find((button) => button.textContent?.includes("3.125 sec"))!;
    await act(async () => lastFailedEvent.click());
    expect(requests.frameCalls).toEqual([expect.stringMatching(new RegExp(`/${ref}/79872$`))]);

    const zoomEnd = host.querySelector('[role="slider"][aria-label="zoomEnd"]')!;
    act(() => zoomEnd.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true })));
    expect(zoomEnd.getAttribute("aria-valuenow")).toBe("100");
    expect(requests.pageCalls).toHaveLength(pageCount + 2);
    expect(rows()).toHaveLength(11);
    expect(host.querySelectorAll('[data-track="outgoing"] button')).toHaveLength(1);

    await render("masked");
    expect(host.querySelector("li button")).toBeNull();
    expect(host.textContent).toContain("maskedFrameIndex");

    requests.pageCalls.length = 0;
    requests.denyPage = 4;
    await render("shared");
    await vi.waitFor(async () => {
      await settle();
      expect(host.textContent).toContain("frameIndexUnavailable");
    });
    expect(requests.pageCalls).toHaveLength(8);
    expect(rows()).toHaveLength(0);
  } finally {
    act(() => root.unmount());
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
    requests.segments = undefined;
    requests.pageCalls.length = 0;
    requests.frameCalls.length = 0;
    requests.peakPageConcurrency = 0;
    requests.denyPage = undefined;
  }
});

it("scopes outgoing markers to the selected attempt and navigates events by lane or list order", async () => {
  function lane(ref: string, started_ms: number, end_ms: number, times: number[]): TraceSseLane {
    requests.laneTimes.set(ref, times);
    return {
      ref,
      started_ms,
      end_ms,
      headers_ms: null,
      last_event_ms: times[times.length - 1] ?? null,
      longest_gap: null,
      availability: "captured",
      ending: "completed",
      frame_count: times.length,
      page_starts_ms: times.slice(0, 1),
    };
  }
  const first = lane("first", 0, 10, [2, 5]);
  const second = lane("second", 20, 30, [21, 25]);
  const outer = lane("outer", 40, 80, [44, 75]);
  const inner = lane("inner", 50, 60, [53]);
  requests.segments = [
    { observed_through_rank: 1, provider: [first, second], outgoing: lane("outgoing", 0, 35, [3, 6, 22, 27, 35]) },
    { observed_through_rank: 2, provider: [outer, inner], outgoing: lane("overlap", 40, 85, [45, 54, 76, 85]) },
  ];
  const store = configureStore({
    reducer: { [enhancedControlPlaneApi.reducerPath]: enhancedControlPlaneApi.reducer },
    middleware: (getDefault) => getDefault().concat(enhancedControlPlaneApi.middleware),
  });
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  const render = (attemptRef?: string) =>
    act(async () => {
      root.render(
        <Provider store={store}>
          <ConversationTraceSse
            sessionId="session"
            cutoffRank={2}
            attemptRef={attemptRef}
            turn={{
              exchange_id: "exchange",
              turn_number: 1,
              started_at: "2026-11-19T12:00:00Z",
              duration_ms: 35,
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
  const dots = (source: string) => host.querySelectorAll<HTMLButtonElement>(`[data-track="${source}"] button`);
  const expectDots = (provider: number, outgoing: number) =>
    vi.waitFor(async () => {
      await act(async () => {
        await Promise.all(store.dispatch(enhancedControlPlaneApi.util.getRunningQueriesThunk()));
      });
      expect(dots("provider")).toHaveLength(provider);
      expect(dots("outgoing")).toHaveLength(outgoing);
    });
  const rows = () => Array.from(host.querySelectorAll<HTMLButtonElement>("li button"));
  const activeRow = () => rows().findIndex((button) => button.getAttribute("aria-pressed") === "true");
  const press = (key: string) =>
    act(() => document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true })));
  try {
    await render(first.ref);
    await expectDots(2, 2);
    act(() => dots("outgoing")[0].click());
    expect(activeRow()).toBe(1);
    expect(document.activeElement).toBe(rows()[1]);
    press("ArrowRight");
    expect(activeRow()).toBe(3);
    press("ArrowUp");
    expect(activeRow()).toBe(2);
    press("ArrowLeft");
    expect(activeRow()).toBe(0);
    press("ArrowDown");
    expect(activeRow()).toBe(1);
    await render(second.ref);
    await expectDots(2, 3);
    expect(activeRow()).toBe(-1);
    expect(rows()[0].tabIndex).toBe(0);
    await render(inner.ref);
    await expectDots(1, 0);
    await render();
    await expectDots(7, 9);
  } finally {
    act(() => root.unmount());
    store.dispatch(enhancedControlPlaneApi.util.resetApiState());
    host.remove();
    requests.segments = undefined;
    requests.laneTimes.clear();
    requests.pageCalls.length = 0;
    requests.frameCalls.length = 0;
  }
});
