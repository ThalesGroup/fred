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
import {
  applicationRouteBasePath,
  applicationRouteTarget,
  applicationServiceUrl,
  normalizeApplicationRelativePath,
} from "./applicationPath.ts";

describe("application paths", () => {
  it("derives both route and service roots from host-owned ids", () => {
    expect(applicationRouteBasePath("team a", "example-app")).toBe("/team/team%20a/apps/example-app");
    expect(applicationServiceUrl("example-app", "team a", "items/42?view=full")).toBe(
      "/app-services/example-app/teams/team%20a/items/42?view=full",
    );
  });

  it("keeps relative navigation inside the application route", () => {
    const base = "/team/team-1/apps/example-app";
    expect(applicationRouteTarget(base, "details/42?tab=history")).toBe(
      "/team/team-1/apps/example-app/details/42?tab=history",
    );
    expect(applicationRouteTarget(base, "?tab=history")).toBe("/team/team-1/apps/example-app?tab=history");
  });

  it.each([
    "/absolute",
    "//elsewhere.example/path",
    "https://elsewhere.example/path",
    "../outside",
    "safe/../../outside",
    "%2e%2e/outside",
    "%252e%252e/outside",
    "%25252e%25252e/outside",
    "%252e%252e%252f%25",
    "safe/%2foutside",
    "safe/%255coutside",
    "safe\\outside",
    "./inside",
    "broken/%zz",
    "inside#fragment",
  ])("rejects an escaping or malformed path: %s", (path) => {
    expect(() => normalizeApplicationRelativePath(path)).toThrow(TypeError);
    expect(() => applicationRouteTarget("/team/team-1/apps/example-app", path)).toThrow(TypeError);
  });

  it("allows encoded ordinary path data and arbitrary query values", () => {
    expect(normalizeApplicationRelativePath("folders/My%20Docs?return=https://example.test/a/../b")).toBe(
      "folders/My%20Docs?return=https://example.test/a/../b",
    );
    expect(normalizeApplicationRelativePath("reports/100%25-complete")).toBe("reports/100%25-complete");
  });
});
