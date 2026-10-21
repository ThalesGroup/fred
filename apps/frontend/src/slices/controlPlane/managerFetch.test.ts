// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, it, vi } from "vitest";
import { fetchBaseQuery } from "@reduxjs/toolkit/query";
import { managerFetch } from "./managerFetch";

afterEach(() => vi.unstubAllGlobals());

it.each([true, false])("bounds all bytes before RTK clones a raw preview (known size=%s)", async (knownSize) => {
  let consumed = 0;
  let cancelled = false;
  const block = new Uint8Array(64 * 1024);
  const body = new ReadableStream(
    {
      pull(controller) {
        if (consumed === 12 * 1024 * 1024) return controller.close();
        consumed += block.length;
        controller.enqueue(block);
      },
      cancel() {
        cancelled = true;
      },
    },
    { highWaterMark: 0 },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body, { headers: knownSize ? { "Content-Length": String(12 * 1024 * 1024) } : {} })),
  );
  const query = fetchBaseQuery({ fetchFn: managerFetch });
  const controller = new AbortController();
  const result = await query(
    { url: "http://localhost/control-plane/v1/documents/id/preview?artifact=raw", responseHandler: "text" },
    {
      signal: controller.signal,
      abort: () => controller.abort(),
      endpoint: "preview",
      type: "query",
      getState: () => ({}),
      dispatch: vi.fn(),
      extra: undefined,
    },
    {},
  );
  expect(cancelled).toBe(true);
  expect(consumed).toBeLessThanOrEqual(knownSize ? 0 : 8 * 1024 * 1024 + block.length);
  expect(result.error?.status).toBe("FETCH_ERROR");
  expect(result.error).not.toHaveProperty("data");
});

it("preserves the complete bounded response and status", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("Bonjour", { status: 200, headers: { "Content-Type": "text/plain" } })),
  );
  const response = await managerFetch("http://localhost/control-plane/v1/documents/id/preview?artifact=raw");
  expect(await response.text()).toBe("Bonjour");
  expect(response.status).toBe(200);
});
