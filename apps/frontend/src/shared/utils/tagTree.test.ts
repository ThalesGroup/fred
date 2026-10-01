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
import { buildTree, withoutMachineWritten } from "./tagTree";

// A Knowledge Base marks the library root it writes and nothing below it, so
// hiding a synchronized library from the corpus is also a path-prefix problem:
// drop the marked root alone and buildTree raises it straight back up out of
// its descendants' paths.
describe("withoutMachineWritten", () => {
  const corpus = [
    { id: "t-reports", name: "Reports", path: "", type: "document", item_ids: [] },
    { id: "t-lib", name: "WebDav-1", path: "", type: "document", item_ids: [], synchronized_by: "knowledge_base:i1" },
    { id: "t-guides", name: "guides", path: "WebDav-1", type: "document", item_ids: [] },
    { id: "t-deep", name: "réunions", path: "WebDav-1/Documents partagés", type: "document", item_ids: [] },
  ] as never;

  it("drops the marked library and everything nested under it", () => {
    const kept = withoutMachineWritten(corpus).map((t: { id: string }) => t.id);
    expect(kept).toEqual(["t-reports"]);
  });

  it("leaves no synthetic folder behind for the library it dropped", () => {
    // The regression this exists for: filtering only the marked tag left
    // "WebDav-1/guides" in, and the tree grew a "WebDav-1" node from its path.
    const tree = buildTree(withoutMachineWritten(corpus));
    expect([...tree.children.keys()]).toEqual(["Reports"]);
  });

  it("returns a corpus with no machine-written library untouched", () => {
    const humanOnly = [{ id: "t-reports", name: "Reports", path: "", type: "document", item_ids: [] }] as never;
    expect(withoutMachineWritten(humanOnly)).toBe(humanOnly);
  });

  it("does not drop a folder whose name merely starts like the library's", () => {
    const lookalike = [
      { id: "t-lib", name: "Docs", path: "", type: "document", item_ids: [], synchronized_by: "knowledge_base:i1" },
      { id: "t-other", name: "Docs-archive", path: "", type: "document", item_ids: [] },
    ] as never;
    expect(withoutMachineWritten(lookalike).map((t: { id: string }) => t.id)).toEqual(["t-other"]);
  });
});
