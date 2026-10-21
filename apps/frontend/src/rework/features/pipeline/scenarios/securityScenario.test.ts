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

import { describe, expect, it } from "vitest";
import { collect, signal } from "./fakePlatform";
import { runsActiveContent, securityScenario, type HeaderMap, type SecurityDeps } from "./securityScenario";

const HARDENED: HeaderMap = {
  "content-security-policy": "default-src 'self'; frame-ancestors 'self'",
  "x-content-type-options": "nosniff",
  "referrer-policy": "same-origin",
  "strict-transport-security": "max-age=31536000",
};

function deps(overrides: Partial<SecurityDeps> = {}, stream?: HeaderMap): SecurityDeps & { libraries: Set<string> } {
  const libraries = new Set<string>();
  return {
    libraries,
    origin: { https: true, local: false },
    headersOf: async (path) => {
      if (path === "/") return { status: 200, headers: HARDENED, body: "" };
      if (path.includes("/raw_content/stream/"))
        return {
          status: 200,
          headers: stream ?? { "content-type": "image/svg+xml", "content-disposition": "attachment" },
          body: "",
        };
      if (path.includes("/raw_content/"))
        return { status: 200, headers: { "content-disposition": 'attachment; filename="x.svg"' }, body: "" };
      return { status: 404, headers: {}, body: '{"detail":"Not found"}' };
    },
    token: async () => "token",
    createLibrary: async (name) => {
      libraries.add(name);
      return name;
    },
    deleteLibrary: async (id) => {
      libraries.delete(id);
    },
    ingest: async () => "doc-1",
    ...overrides,
  };
}

async function run(d: SecurityDeps) {
  const r = collect();
  await securityScenario(d, r.report, signal);
  return r;
}

describe("securityScenario", () => {
  it("passes on a hardened deployment and deletes its folder", async () => {
    const d = deps();
    const r = await run(d);
    expect(r.steps.filter((s) => s.status !== "passed").map((s) => `${s.id}:${s.status}`)).toEqual([]);
    expect(d.libraries.size).toBe(0);
  });

  it("fails when an SVG preview is served inline without a sandbox", async () => {
    const d = deps({}, { "content-type": "image/svg+xml", "content-disposition": 'inline; filename="x.svg"' });
    expect((await run(d)).status("inline-active-content")).toBe("failed");
  });

  it("accepts an inline preview under a sandbox policy, or of an inert type", () => {
    expect(runsActiveContent({ "content-type": "image/svg+xml", "content-security-policy": "sandbox" })).toBe(false);
    expect(runsActiveContent({ "content-type": "application/pdf", "content-disposition": "inline" })).toBe(false);
    expect(runsActiveContent({ "content-type": "text/html; charset=utf-8" })).toBe(true);
  });

  it("only skips missing page headers, and fails plain HTTP off localhost", async () => {
    const bare = deps({
      origin: { https: false, local: false },
      headersOf: async (path) =>
        path === "/" ? { status: 200, headers: {}, body: "" } : { status: 404, headers: {}, body: "" },
    });
    const r = await run(bare);
    expect(r.status("page-headers")).toBe("skipped");
    expect(r.status("transport")).toBe("failed");
    expect((await run(deps({ origin: { https: false, local: true } }))).status("transport")).toBe("skipped");
  });

  it("fails when an error body carries a stack trace", async () => {
    const leaky = deps();
    const base = leaky.headersOf;
    leaky.headersOf = async (path, token) =>
      path.startsWith("/control-plane/v1/teams/")
        ? { status: 500, headers: {}, body: 'Traceback (most recent call last):\n  File "/app/x.py", line 3' }
        : base(path, token);
    expect((await run(leaky)).status("error-bodies")).toBe("failed");
  });

  it("skips the SVG checks when SVG cannot be ingested, and still cleans up", async () => {
    const d = deps({
      ingest: async () => {
        throw new Error("no processor for .svg");
      },
    });
    const r = await run(d);
    expect(r.status("upload-svg")).toBe("skipped");
    expect(r.status("inline-active-content")).toBe("skipped");
    expect(d.libraries.size).toBe(0);
  });
  it.each([
    ["sandbox allow-scripts allow-same-origin", true],
    ["SANDBOX allow-scripts allow-same-origin; default-src 'self'", true],
    ["sandbox allow-scripts allow-same-origin; sandbox", true],
    ["sandbox allow-scripts", false],
    ["sandbox allow-same-origin", false],
    ["sandbox", false],
    ["sandbox allow-scripts allow-same-origin, sandbox", false],
    ["default-src 'self'; sandbox allow-scripts allow-same-origin, default-src 'none'", true],
  ])("checks enforced sandbox restrictions in %s", (policy, active) => {
    expect(runsActiveContent({ "content-type": "image/svg+xml", "content-security-policy": policy })).toBe(active);
  });
  it("does not treat a report-only sandbox as protection", () => {
    expect(
      runsActiveContent({ "content-type": "image/svg+xml", "content-security-policy-report-only": "sandbox" }),
    ).toBe(true);
  });
  it("fails the scenario for a sandbox permitting script and platform origin", async () => {
    const d = deps(
      {},
      { "content-type": "image/svg+xml", "content-security-policy": "sandbox allow-scripts allow-same-origin" },
    );
    expect((await run(d)).status("inline-active-content")).toBe("failed");
    expect(d.libraries.size).toBe(0);
  });
});
