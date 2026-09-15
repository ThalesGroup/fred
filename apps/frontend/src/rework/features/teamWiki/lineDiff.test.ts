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
import { diffStat, lineDiff } from "./lineDiff";

const ops = (before: string, after: string) => lineDiff(before, after).map((l) => `${l.op[0]}:${l.text}`);

describe("lineDiff", () => {
  it("marks an appended line as the only change", () => {
    expect(ops("a\nb", "a\nb\nc")).toEqual(["s:a", "s:b", "a:c"]);
  });

  it("marks a removed line without touching its neighbours", () => {
    expect(ops("a\nb\nc", "a\nc")).toEqual(["s:a", "r:b", "s:c"]);
  });

  // The case the approval modal exists for: an agent rewrites one sentence in
  // the middle of a page. Showing that as "everything removed, everything
  // added" would make an approver read the whole page to find the change.
  it("keeps a changed line paired with the line it replaces", () => {
    expect(ops("intro\nold line\nend", "intro\nnew line\nend")).toEqual([
      "s:intro",
      "r:old line",
      "a:new line",
      "s:end",
    ]);
  });

  it("treats a new page as all additions", () => {
    expect(ops("", "a\nb")).toEqual(["a:a", "a:b"]);
  });

  it("returns nothing for two empty documents", () => {
    expect(lineDiff("", "")).toEqual([]);
  });

  it("counts what changed", () => {
    expect(diffStat(lineDiff("a\nb", "a\nc\nd"))).toEqual({ added: 2, removed: 1 });
  });
});

// A wiki page is capped at 100 000 characters, which is tens of thousands of
// lines. The pairing pass is quadratic, so past a point it has to stop being
// clever rather than take the approver's tab down.
describe("lineDiff on a document too large to pair", () => {
  it("still returns the whole change, and returns it quickly", () => {
    const before = Array.from({ length: 4000 }, (_, i) => `line ${i}`).join("\n");
    const after = `${before}\nlast`;

    const started = Date.now();
    const lines = lineDiff(before, after);
    const elapsed = Date.now() - started;

    expect(lines.filter((l) => l.op === "removed")).toHaveLength(4000);
    expect(lines.filter((l) => l.op === "added")).toHaveLength(4001);
    // The pairing pass on 4000x4001 would allocate 16M cells; the guard means
    // this is two array maps.
    expect(elapsed).toBeLessThan(1000);
  });
});
