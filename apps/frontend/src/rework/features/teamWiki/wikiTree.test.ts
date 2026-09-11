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
import type { WikiPageSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { ancestorsOf, buildWikiTree, canHaveChild, findRulesPage, moveTargets, visibleNodes } from "./wikiTree";

function page(id: string, overrides: Partial<WikiPageSummary> = {}): WikiPageSummary {
  return {
    page_id: id,
    slug: id,
    title: id,
    kind: "page",
    parent_page_id: null,
    position: 0,
    needs_review: false,
    ...overrides,
  } as WikiPageSummary;
}

describe("buildWikiTree", () => {
  it("returns nothing for an empty wiki", () => {
    expect(buildWikiTree([])).toEqual([]);
  });

  it("nests children under their parent and records depth", () => {
    const tree = buildWikiTree([
      page("root"),
      page("child", { parent_page_id: "root" }),
      page("grandchild", { parent_page_id: "child" }),
    ]);
    expect(tree).toHaveLength(1);
    expect(tree[0].depth).toBe(0);
    expect(tree[0].children[0].page.page_id).toBe("child");
    expect(tree[0].children[0].depth).toBe(1);
    expect(tree[0].children[0].children[0].depth).toBe(2);
  });

  it("orders siblings by position, then title", () => {
    const tree = buildWikiTree([
      page("b", { position: 1, title: "B" }),
      page("a", { position: 0, title: "A" }),
      page("c", { position: 0, title: "C" }),
    ]);
    expect(tree.map((n) => n.page.page_id)).toEqual(["a", "c", "b"]);
  });

  it("keeps the rules page out of the tree", () => {
    const pages = [page("root"), page("rules", { kind: "rules", slug: "__rules__" })];
    expect(buildWikiTree(pages).map((n) => n.page.page_id)).toEqual(["root"]);
    expect(findRulesPage(pages)?.page_id).toBe("rules");
  });

  // A page whose parent is gone must stay visible. Dropping it would make it
  // unreachable from the sidebar while it still exists and still holds its
  // slug — which reads as data loss rather than as the inconsistency it is.
  it("surfaces an orphan at the top level instead of dropping it", () => {
    const tree = buildWikiTree([page("root"), page("orphan", { parent_page_id: "gone" })]);
    expect(tree.map((n) => n.page.page_id).sort()).toEqual(["orphan", "root"]);
  });

  // Only the broken link is promoted. Flattening the whole subtree under it
  // would scatter an intact hierarchy across the top level, which looks far
  // more like corruption than the single missing parent actually is.
  it("promotes only the orphan itself, keeping its own children nested", () => {
    const tree = buildWikiTree([
      page("orphan", { parent_page_id: "gone" }),
      page("child", { parent_page_id: "orphan" }),
      page("grandchild", { parent_page_id: "child" }),
    ]);
    expect(tree).toHaveLength(1);
    expect(tree[0].page.page_id).toBe("orphan");
    expect(tree[0].children[0].page.page_id).toBe("child");
    expect(tree[0].children[0].children[0].page.page_id).toBe("grandchild");
  });

  it("does not hang on a parent cycle", () => {
    const tree = buildWikiTree([page("a", { parent_page_id: "b" }), page("b", { parent_page_id: "a" })]);
    expect(tree).toHaveLength(2);
  });
});

describe("visibleNodes", () => {
  it("hides the subtree of a collapsed node", () => {
    const tree = buildWikiTree([
      page("root"),
      page("child", { parent_page_id: "root" }),
      page("grandchild", { parent_page_id: "child" }),
    ]);
    expect(visibleNodes(tree, new Set()).map((n) => n.page.page_id)).toEqual(["root", "child", "grandchild"]);
    expect(visibleNodes(tree, new Set(["child"])).map((n) => n.page.page_id)).toEqual(["root", "child"]);
  });
});

describe("ancestorsOf", () => {
  it("returns the chain outermost first", () => {
    const pages = [
      page("root"),
      page("child", { parent_page_id: "root" }),
      page("grandchild", { parent_page_id: "child" }),
    ];
    expect(ancestorsOf(pages, "grandchild").map((p) => p.page_id)).toEqual(["root", "child"]);
    expect(ancestorsOf(pages, "root")).toEqual([]);
    expect(ancestorsOf(pages, "missing")).toEqual([]);
  });
});

describe("canHaveChild", () => {
  it("allows a child up to the cap and refuses one past it", () => {
    expect(canHaveChild(0)).toBe(true);
    expect(canHaveChild(2)).toBe(true);
    // A child of a depth-3 page would sit at 4, which the server refuses.
    expect(canHaveChild(3)).toBe(false);
  });
});

describe("moveTargets", () => {
  it("offers every other page when the tree is shallow", () => {
    const pages = [page("a"), page("b"), page("c")];
    expect(moveTargets(pages, "a").map((t) => t.page.page_id)).toEqual(["b", "c"]);
  });

  it("never offers the page itself or one of its own descendants", () => {
    const pages = [page("root"), page("child", { parent_page_id: "root" }), page("other")];
    expect(moveTargets(pages, "root").map((t) => t.page.page_id)).toEqual(["other"]);
  });

  it("names a target by its full path, so two same-named pages are distinguishable", () => {
    const pages = [
      page("a", { title: "Onboarding" }),
      page("b", { title: "Notes", parent_page_id: "a" }),
      page("moving", { title: "Moving" }),
    ];
    expect(moveTargets(pages, "moving").map((t) => t.path)).toEqual(["Onboarding", "Onboarding / Notes"]);
  });

  // The move carries the subtree with it: a destination that fits the page
  // itself can still push its deepest child past the cap.
  it("drops a destination that would push the moved subtree past the depth cap", () => {
    const pages = [
      page("l0"),
      page("l1", { parent_page_id: "l0" }),
      page("l2", { parent_page_id: "l1" }),
      page("moving"),
      page("kid", { parent_page_id: "moving" }),
    ];
    // "moving" is one level tall, so it fits under l0 (depth 0 -> lands at 1,
    // kid at 2) and under l1 (lands at 2, kid at 3) but not under l2, whose
    // child would sit at 3 with the kid at 4.
    expect(moveTargets(pages, "moving").map((t) => t.page.page_id)).toEqual(["l0", "l1"]);
  });

  it("returns nothing for a page the tree does not contain", () => {
    expect(moveTargets([page("a")], "ghost")).toEqual([]);
  });
});
