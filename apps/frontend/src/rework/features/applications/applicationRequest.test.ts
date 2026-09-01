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

import { describe, expect, it, vi } from "vitest";
import { createApplicationRequest } from "./applicationRequest.ts";

function dependencies(responses: Response[]) {
  const fetchMock = vi.fn(async () => responses.shift() ?? new Response(null, { status: 500 }));
  const ensureFreshToken = vi.fn(async () => true);
  const getToken = vi.fn(() => "token-1" as string | null);
  const logout = vi.fn();
  return { fetch: fetchMock as unknown as typeof fetch, ensureFreshToken, getToken, logout };
}

describe("createApplicationRequest", () => {
  it("derives the service URL and injects the current bearer without exposing it", async () => {
    const response = new Response(new Uint8Array([1, 2, 3]), { status: 200 });
    const deps = dependencies([response]);
    const request = createApplicationRequest("example-app", "team a", deps);
    const signal = new AbortController().signal;

    const result = await request("operations/run?mode=full", {
      method: "POST",
      headers: { "content-type": "application/octet-stream", "x-correlation-id": "safe" },
      body: new Uint8Array([4, 5]),
      signal,
    });

    expect(result).toBe(response);
    expect(deps.ensureFreshToken).toHaveBeenCalledWith(30);
    expect(deps.fetch).toHaveBeenCalledOnce();
    const [url, init] = vi.mocked(deps.fetch).mock.calls[0];
    expect(url).toBe("/app-services/example-app/teams/team%20a/operations/run?mode=full");
    expect(init?.signal).toBe(signal);
    expect(init?.credentials).toBe("omit");
    expect(init?.cache).toBe("no-store");
    const headers = init?.headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer token-1");
    expect(headers.get("x-correlation-id")).toBe("safe");
  });

  it.each(["Authorization", "authorization", "Cookie", "Host", "Proxy-Authorization", "X-Fred-Team-Id"])(
    "rejects the protected %s header before sending",
    async (header) => {
      const deps = dependencies([new Response(null, { status: 200 })]);
      const request = createApplicationRequest("example-app", "team-1", deps);

      await expect(request("resource", { headers: { [header]: "override" } })).rejects.toThrow(TypeError);
      expect(deps.fetch).not.toHaveBeenCalled();
    },
  );

  it("refreshes once after a 401 and rebuilds the bearer from the new token", async () => {
    const deps = dependencies([new Response(null, { status: 401 }), new Response(null, { status: 204 })]);
    deps.getToken.mockReturnValueOnce("old-token").mockReturnValueOnce("new-token");
    const request = createApplicationRequest("example-app", "team-1", deps);

    const response = await request("resource");

    expect(response.status).toBe(204);
    expect(deps.ensureFreshToken.mock.calls).toEqual([[30], [0]]);
    expect(deps.fetch).toHaveBeenCalledTimes(2);
    const firstHeaders = vi.mocked(deps.fetch).mock.calls[0][1]?.headers as Headers;
    const secondHeaders = vi.mocked(deps.fetch).mock.calls[1][1]?.headers as Headers;
    expect(firstHeaders.get("authorization")).toBe("Bearer old-token");
    expect(secondHeaders.get("authorization")).toBe("Bearer new-token");
    expect(deps.logout).not.toHaveBeenCalled();
  });

  it("logs out after the retry is still unauthorized", async () => {
    const deps = dependencies([new Response(null, { status: 401 }), new Response(null, { status: 401 })]);
    const request = createApplicationRequest("example-app", "team-1", deps);

    const response = await request("resource");

    expect(response.status).toBe(401);
    expect(deps.fetch).toHaveBeenCalledTimes(2);
    expect(deps.logout).toHaveBeenCalledOnce();
  });

  it("does not retry or log out for an ordinary application error", async () => {
    const unavailable = new Response("down", { status: 503 });
    const deps = dependencies([unavailable]);
    const request = createApplicationRequest("example-app", "team-1", deps);

    expect(await request("resource")).toBe(unavailable);
    expect(deps.fetch).toHaveBeenCalledOnce();
    expect(deps.logout).not.toHaveBeenCalled();
  });

  it("returns multipart and streaming responses unchanged", async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new Uint8Array([7]));
        controller.close();
      },
    });
    const streaming = new Response(stream, { headers: { "content-type": "application/octet-stream" } });
    const deps = dependencies([streaming]);

    const result = await createApplicationRequest("example-app", "team-1", deps)("stream");

    expect(result).toBe(streaming);
    expect(new Uint8Array(await result.arrayBuffer())).toEqual(new Uint8Array([7]));
  });
});
