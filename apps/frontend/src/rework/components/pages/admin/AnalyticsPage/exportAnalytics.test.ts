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

import { afterEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({ downloadFile: vi.fn(), access: vi.fn(), fresh: vi.fn(async () => true) }));
vi.mock("../../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "tok", ensureFreshToken: h.fresh },
}));
vi.mock("../../../../../common/platformAccess", () => ({ handlePlatformAccessResponse: h.access }));
vi.mock("../../../../../utils/downloadUtils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../../../utils/downloadUtils")>()),
  downloadFile: h.downloadFile,
}));

import { exportAnalytics } from "./exportAnalytics";

const workbook = new Blob(["xlsx"]);

function respond(init: ResponseInit & { disposition?: string }) {
  const headers = new Headers(init.disposition ? { "Content-Disposition": init.disposition } : {});
  const fetchMock = vi.fn().mockResolvedValue(new Response(workbook, { ...init, headers }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("exportAnalytics", () => {
  it("requests the scope and period with the bearer token and saves the named file", async () => {
    const fetchMock = respond({
      status: 200,
      disposition: 'attachment; filename="analytics_2-teams_2026-09-26_2026-10-25.xlsx"',
    });

    await exportAnalytics({
      since: "2026-09-25T22:00:00.000Z",
      until: "2026-10-25T22:00:00.000Z",
      teamIds: ["t-a", "t-b"],
      tz: "Europe/Paris",
      lang: "en",
    });

    const [url, init] = fetchMock.mock.calls[0];
    const query = new URL(url, "http://host").searchParams;
    expect(new URL(url, "http://host").pathname).toBe("/control-plane/v1/kpi/analytics/export");
    expect(query.getAll("team_ids")).toEqual(["t-a", "t-b"]);
    expect([query.get("since"), query.get("tz"), query.get("lang")]).toEqual([
      "2026-09-25T22:00:00.000Z",
      "Europe/Paris",
      "en",
    ]);
    expect(init.headers).toEqual({ Authorization: "Bearer tok" });
    expect(h.fresh).toHaveBeenCalledWith(30);
    expect(h.access).toHaveBeenCalledOnce();
    expect(h.downloadFile).toHaveBeenCalledExactlyOnceWith(
      expect.any(Blob),
      "analytics_2-teams_2026-09-26_2026-10-25.xlsx",
    );
  });

  it("sends the user filter when one applies", async () => {
    const fetchMock = respond({ status: 200 });
    await exportAnalytics({ userFilter: '{"conditions":[]}', lang: "fr" });
    const query = new URL(fetchMock.mock.calls[0][0], "http://host").searchParams;
    expect(query.get("user_filter")).toBe('{"conditions":[]}');
  });

  it("falls back to a generic filename", async () => {
    respond({ status: 200 });
    await exportAnalytics({});
    expect(h.downloadFile).toHaveBeenCalledWith(expect.any(Blob), "analytics.xlsx");
  });

  it("throws on an error status and saves nothing", async () => {
    respond({ status: 403 });
    await expect(exportAnalytics({ lang: "fr" })).rejects.toThrow("403");
    expect(h.downloadFile).not.toHaveBeenCalled();
  });
});
