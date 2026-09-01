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
import { nextBufferAction } from "./previewBuffers";

describe("nextBufferAction", () => {
  it("does nothing when there is no document", () => {
    expect(nextBufferAction("", ["", ""], ["", ""], 0)).toEqual({ kind: "none" });
  });

  it("does nothing when the front buffer already shows the document", () => {
    expect(nextBufferAction("docA", ["docA", ""], ["docA", ""], 0)).toEqual({ kind: "none" });
  });

  it("loads a fresh document into the hidden back buffer", () => {
    expect(nextBufferAction("docA", ["", ""], ["", ""], 0)).toEqual({ kind: "load", into: 1 });
  });

  it("waits (no reset) while the back buffer is still loading that document", () => {
    // srcDoc already set to docB but not painted yet — onLoad will flip; resetting
    // it would restart the load.
    expect(nextBufferAction("docB", ["docA", "docB"], ["docA", ""], 0)).toEqual({ kind: "none" });
  });

  it("flips to the back buffer when it already painted the document (the switch-back bug)", () => {
    // Front shows docB; docA is still painted in buffer 1 from an earlier view.
    // Re-selecting docA changes no srcDoc, so no onLoad fires — must flip directly,
    // not sit frozen on docB.
    expect(nextBufferAction("docA", ["docB", "docA"], ["docB", "docA"], 0)).toEqual({ kind: "flip", to: 1 });
  });

  it("toggling back and forth keeps resolving to the painted buffer, never freezing", () => {
    // buffers/painted hold [docB, docA] after both were seen once.
    const buffers: [string, string] = ["docB", "docA"];
    const painted: [string, string] = ["docB", "docA"];
    // front=0 (docB) → pick docA: flip to 1.
    expect(nextBufferAction("docA", buffers, painted, 0)).toEqual({ kind: "flip", to: 1 });
    // front=1 (docA) → pick docB: flip to 0.
    expect(nextBufferAction("docB", buffers, painted, 1)).toEqual({ kind: "flip", to: 0 });
  });
});
