// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { fetchAuthedBlob } from "./downloadUtils";

const { getToken } = vi.hoisted(() => ({ getToken: vi.fn(() => "download-test-token") }));
vi.mock("../security/KeycloakService", () => ({ KeyCloakService: { GetToken: getToken } }));

let source: Server;
let target: Server;
let origin: string;
let targetOrigin: string;
let targetRequests = 0;
let authorization: string | undefined;

async function listen(server: Server): Promise<string> {
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}

beforeAll(async () => {
  target = createServer((_request, response) => {
    targetRequests++;
    response.end("Unexpected target");
  });
  targetOrigin = await listen(target);
  source = createServer((request, response) => {
    const url = new URL(request.url!, origin);
    if (url.pathname === "/redirect") {
      authorization = request.headers.authorization;
      response.writeHead(Number(url.searchParams.get("status")), {
        Location: `${url.searchParams.get("external") === "true" ? targetOrigin : origin}/target`,
      });
      response.end();
    } else {
      targetRequests++;
      response.end("Unexpected target");
    }
  });
  origin = await listen(source);
  vi.stubGlobal("window", { location: new URL(origin) });
});

afterAll(async () => {
  vi.unstubAllGlobals();
  await Promise.all([source, target].map((server) => new Promise<void>((resolve) => server.close(() => resolve()))));
});

describe.each([false, true])("real HTTP redirects, external=%s", (external) => {
  it.each([301, 302, 303, 307, 308])("refuses HTTP %s before requesting the redirect target", async (status) => {
    targetRequests = 0;
    authorization = undefined;
    await expect(fetchAuthedBlob(`${origin}/redirect?status=${status}&external=${external}`)).rejects.toThrow();
    expect(authorization).toBe("Bearer download-test-token");
    expect(targetRequests).toBe(0);
  });
});

it("rejects an external initial destination before reading or sending credentials", async () => {
  getToken.mockClear();
  targetRequests = 0;
  await expect(fetchAuthedBlob(`${targetOrigin}/target`)).rejects.toThrow("Untrusted download destination");
  expect(targetRequests).toBe(0);
  expect(getToken).not.toHaveBeenCalled();
});
