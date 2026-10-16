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
import { Navigate } from "react-router-dom";

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

describe("bounded Fred router", () => {
  it("registers only the implemented journey, inside admission guards", () => {
    expect(collectPaths(routes)).toEqual(["/", "home", "team/:teamId/resources", "admin", "admin/provisioning", "*"]);
  });
  it("redirects unknown destinations home without mounting their old components", () => {
    const catchAll = routes[0].children?.find((route) => route.path === "*");
    expect(catchAll?.element).toEqual(<Navigate to="/home" replace />);
  });
});
