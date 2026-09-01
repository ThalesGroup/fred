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

// Folder rename is a path-PREFIX rewrite: renaming a corpus folder must update
// every tag at-or-under it (the tag ending there AND every descendant), or the
// descendants keep the old path and re-materialize the old folder — the rename
// then appears to do nothing. These cover the two helpers that make that correct.

import { describe, expect, it } from "vitest";
import { buildTree, collectDescendantTags, findNode, fullPath, rewriteTagUnderFolder } from "./tagTree";

// A folder ("Reports") that has BOTH its own tag and nested sub-folders — the
// exact shape whose rename previously touched only the one terminating tag.
const tags = [
  { id: "t-reports", name: "Reports", path: "", type: "document", item_ids: ["d0"] },
  { id: "t-q1", name: "Q1", path: "Reports", type: "document", item_ids: ["d1"] },
  { id: "t-jan", name: "Jan", path: "Reports/Q1", type: "document", item_ids: ["d2"] },
  { id: "t-other", name: "Other", path: "", type: "document", item_ids: ["d3"] },
] as never;

describe("collectDescendantTags", () => {
  it("returns the node's own tag plus every descendant, and nothing outside it", () => {
    const node = findNode(buildTree(tags), "Reports");
    const ids = collectDescendantTags(node).map((t) => t.id);
    expect(new Set(ids)).toEqual(new Set(["t-reports", "t-q1", "t-jan"]));
    expect(ids).not.toContain("t-other");
  });
});

describe("rewriteTagUnderFolder", () => {
  it("renames the folder's own tag (leaf of the rename)", () => {
    const tag = { name: "Reports", path: "" };
    expect(rewriteTagUnderFolder(tag, "Reports", "Rapports")).toEqual({ name: "Rapports", path: "" });
  });

  it("rewrites the old prefix of a descendant tag, preserving its deeper path", () => {
    expect(rewriteTagUnderFolder({ name: "Q1", path: "Reports" }, "Reports", "Rapports")).toEqual({
      name: "Q1",
      path: "Rapports",
    });
    expect(rewriteTagUnderFolder({ name: "Jan", path: "Reports/Q1" }, "Reports", "Rapports")).toEqual({
      name: "Jan",
      path: "Rapports/Q1",
    });
  });

  it("handles renaming a nested folder (parent path preserved)", () => {
    // Rename Reports/Q1 -> Reports/Trimestre1.
    expect(rewriteTagUnderFolder({ name: "Q1", path: "Reports" }, "Reports/Q1", "Reports/Trimestre1")).toEqual({
      name: "Trimestre1",
      path: "Reports",
    });
    expect(rewriteTagUnderFolder({ name: "Jan", path: "Reports/Q1" }, "Reports/Q1", "Reports/Trimestre1")).toEqual({
      name: "Jan",
      path: "Reports/Trimestre1",
    });
  });

  it("moves the WHOLE subtree so the old folder no longer re-materializes", () => {
    const node = findNode(buildTree(tags), "Reports");
    const renamed = collectDescendantTags(node).map((t) => rewriteTagUnderFolder(t, "Reports", "Rapports"));
    // Every rewritten tag now lives under the new name; none references the old.
    for (const r of renamed) {
      expect(fullPath(r).startsWith("Rapports")).toBe(true);
      expect(fullPath(r).startsWith("Reports")).toBe(false);
    }
  });
});
