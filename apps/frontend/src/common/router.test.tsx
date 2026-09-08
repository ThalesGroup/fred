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

// Regression coverage for the MUI-purge route cleanup (#2296/#2297): the
// removed `/monitoring/*`, `/test-renderer`, and `/tools` routes must stay
// gone (no accidental re-add, no dangling reference to a deleted page
// component), and unknown paths must still resolve to the catch-all
// PageError rather than a hard crash.

import type { ReactElement } from "react";
import type { RouteObject } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { PageError } from "@components/pages/PageError/PageError.tsx";
import { FrontendFeatureGate } from "@core/guards/FrontendFeatureGate.tsx";

// router.tsx reads getConfig() at module scope (for `basename`), which
// throws unless loadConfig() already ran — stub it the same way the real
// bootstrap does, without pulling in the network call.
vi.mock("./config", () => ({
  getConfig: () => ({ frontend_basename: "/" }),
}));

// router.tsx also builds `router = createBrowserRouter(routes, ...)` at
// module scope, right alongside the `routes` export this test actually
// wants — createBrowserRouter eagerly creates a browser History, which
// needs `document` and blows up under this repo's DOM-less test
// environment. Stub it so importing the module for `routes` doesn't require
// jsdom (not a project dependency).
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, createBrowserRouter: () => ({}) };
});

const { routes } = await import("./router");

// Paths that used to exist (removed by 5e758208 and #2296) and must never
// come back without an explicit product decision — see FRONTEND-BACKLOG.md
// and FRONTEND-AUTHZ-PATTERN.md's "Historical note".
const REMOVED_PATHS = [
  "monitoring/kpis",
  "monitoring/runtime",
  "monitoring/data",
  "monitoring/rebac-backfill",
  "monitoring/processors",
  "monitoring/processors/runs/:runId",
  "test-renderer",
  "tools",
];

function collectPaths(items: RouteObject[]): string[] {
  return items.flatMap((route) => [
    ...(route.path !== undefined ? [route.path] : []),
    ...(route.children ? collectPaths(route.children) : []),
  ]);
}

describe("router", () => {
  const allPaths = collectPaths(routes);

  it.each(REMOVED_PATHS)("does not register the removed route %s", (removedPath) => {
    expect(allPaths).not.toContain(removedPath);
  });

  it("still falls back to PageError for unknown paths under the main layout", () => {
    const mainLayout = routes.find((route) => route.path === "/");
    const catchAll = mainLayout?.children?.find((route) => route.path === "*");

    expect(catchAll).toBeDefined();
    expect(catchAll?.element).toEqual(<PageError />);
  });

  it("registers one generic team application index and wildcard host", () => {
    expect(allPaths.filter((path) => path === "team/:teamId/apps")).toHaveLength(1);
    expect(allPaths.filter((path) => path === "team/:teamId/apps/:appId/*")).toHaveLength(1);
  });

  it.each(["team/:teamId/apps", "team/:teamId/apps/:appId/*"])(
    "gates the application route %s on the deployment switch",
    (path) => {
      const mainLayout = routes.find((route) => route.path === "/");
      const applicationRoute = mainLayout?.children?.find((route) => route.path === path);
      const element = applicationRoute?.element as ReactElement<{ flag: string; fallback: ReactElement }>;

      expect(element.type).toBe(FrontendFeatureGate);
      expect(element.props.flag).toBe("enableApplications");
      expect(element.props.fallback.type).toBe(PageError);
    },
  );
});
