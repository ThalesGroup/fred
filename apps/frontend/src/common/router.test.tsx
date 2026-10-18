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

import type { RouteObject } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { PageError } from "@components/pages/PageError/PageError";

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

function collectPaths(items: RouteObject[]): string[] {
  return items.flatMap((route) => [
    ...(route.path !== undefined ? [route.path] : []),
    ...(route.children ? collectPaths(route.children) : []),
  ]);
}

describe("Fred UI parity during manager reconstruction", () => {
  it("retains all product routes instead of removing features without Rust APIs", () => {
    expect(collectPaths(routes)).toEqual([
      "/platform-access-denied",
      "/join/:token",
      "/",
      "home",
      "team/:teamId/agents",
      "team/:teamId/managed-chat/:agentInstanceId",
      "team/:teamId/prompts",
      "team/:teamId/resources",
      "team/:teamId/knowledge-bases",
      "team/:teamId/knowledge-bases/:instanceId",
      "team/:teamId/wiki",
      "team/:teamId/wiki/:slug",
      "team/:teamId/apps",
      "team/:teamId/apps/:appId/*",
      "team/:teamId/usage",
      "team/:teamId/settings",
      "team/:teamId/settings/:section",
      "team/:teamId",
      "marketplace/teams",
      "marketplace/prompts",
      "marketplace/agents",
      "admin",
      "admin/organizations",
      "admin/provisioning",
      "admin/platform-prompt",
      "admin/teams",
      "admin/platform-access",
      "admin/platform-roles",
      "admin/tasks",
      "admin/analytics",
      "admin/features",
      "admin/annonces",
      "admin/interface",
      "admin/marketplaces",
      "admin/self-test",
      "admin/corpus-audit",
      "admin/migration",
      "dev/tasks",
      "dev/library",
      "*",
      "/bootstrap",
      "/documents/:uid",
      "/gcu",
      "/gdpr",
      "/release-notes",
      "/help",
      "/help/:lang/:sectionId?/:pageId?",
      "/ppt-filler-help",
      "/settings",
      "unauthorized",
    ]);
  });
  it("keeps account/legal pages outside the sidebar while retaining admission guards", () => {
    const guarded = routes[0];
    expect(guarded.element).toBeDefined();
    const main = guarded.children?.find((route) => route.path === "/");
    for (const path of ["/settings", "/gcu", "/gdpr", "/release-notes"]) {
      expect(guarded.children?.some((route) => route.path === path)).toBe(true);
      expect(main?.children?.some((route) => route.path === path)).toBe(false);
    }
    expect(main?.children?.find((route) => route.path === "*")?.element).toEqual(<PageError />);
  });
});
