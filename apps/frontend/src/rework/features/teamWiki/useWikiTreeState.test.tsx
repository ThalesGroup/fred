// @vitest-environment happy-dom
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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WikiPageSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const user = vi.hoisted(() => ({ id: "alice" }));
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserId: () => user.id },
}));

import { useWikiTreeState, type WikiTreeState } from "./useWikiTreeState";
import { RULES_PAGE_SLUG } from "./wikiTree";

function page(id: string, parent: string | null = null): WikiPageSummary {
  return { page_id: id, slug: id, title: id, kind: "page", parent_page_id: parent, position: 0 } as WikiPageSummary;
}

const PAGES = [page("a"), page("a1", "a"), page("a1x", "a1"), page("b")];

describe("useWikiTreeState", () => {
  let container: HTMLDivElement;
  let root: Root;
  let state: WikiTreeState;

  function Probe({ spaceId, slug, pages }: { spaceId: string; slug?: string; pages: WikiPageSummary[] }) {
    state = useWikiTreeState(spaceId, pages, slug);
    return null;
  }

  const render = (slug?: string, spaceId = "space-1", pages = PAGES) =>
    act(() => {
      root.render(<Probe spaceId={spaceId} slug={slug} pages={pages} />);
    });

  const remount = (slug?: string, spaceId = "space-1", pages = PAGES) => {
    act(() => root.unmount());
    root = createRoot(container);
    render(slug, spaceId, pages);
  };

  const store = (spaces: Record<string, unknown>) =>
    localStorage.setItem("localHook:team-wiki:tree:alice", JSON.stringify(spaces));

  beforeEach(() => {
    localStorage.clear();
    user.id = "alice";
    container = document.createElement("div");
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
  });

  it("starts fully collapsed, with the first page as home", () => {
    render();
    expect([...state.expanded]).toEqual([]);
    expect(state.homeSlug).toBe("a");
  });

  it("keeps expanded pages and the last page opened across a remount", () => {
    render("b");
    act(() => state.toggle("a"));
    remount();
    expect([...state.expanded]).toEqual(["a"]);
    expect(state.homeSlug).toBe("b");
  });

  it("remembers the page id and resolves it to the slug the server returns now", () => {
    const named = { ...page("p1"), slug: "secret-title" };
    render("secret-title", "space-1", [page("a"), named]);
    expect(localStorage.getItem("localHook:team-wiki:tree:alice")).not.toContain("secret-title");
    remount(undefined, "space-1", [page("a"), { ...named, slug: "renamed" }]);
    expect(state.homeSlug).toBe("renamed");
  });

  it("falls back to the first page when the last one is not in the tree", () => {
    store({ "space-1": { expanded: [], lastPage: "gone" } });
    render();
    expect(state.homeSlug).toBe("a");
  });

  it("does not take a stored slug for a page id", () => {
    const named = { ...page("p1"), slug: "secret-title" };
    store({ "space-1": { expanded: [], lastPage: "secret-title" } });
    render(undefined, "space-1", [page("a"), named]);
    expect(state.homeSlug).toBe("a");
  });

  it("goes home to the first page after the reader asks for the wiki root", () => {
    render("b");
    act(() => state.forgetLastPage());
    remount();
    expect(state.homeSlug).toBe("a");
  });

  it("remembers the rules page, but a wiki without pages has no home", () => {
    render(RULES_PAGE_SLUG);
    remount();
    expect(state.homeSlug).toBe(RULES_PAGE_SLUG);
    remount(undefined, "space-1", []);
    expect(state.homeSlug).toBeNull();
  });

  it("expands the ancestors of a nested page opened by link", () => {
    render("a1x");
    expect([...state.expanded].sort()).toEqual(["a", "a1"]);
  });

  it("lets the reader fold an ancestor of the page they are on", () => {
    render("a1x");
    act(() => state.toggle("a"));
    render("a1x");
    expect(state.expanded.has("a")).toBe(false);
  });

  it("keeps a separate state per space and per user", () => {
    render("b");
    act(() => state.toggle("a"));
    remount(undefined, "space-2");
    expect([...state.expanded]).toEqual([]);
    user.id = "bob";
    remount();
    expect([...state.expanded]).toEqual([]);
    expect(state.homeSlug).toBe("a");
  });
});
