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
import { HASH_COLOR_PALETTE_SIZE, hashColorIndex } from "./hashColorIndex";

describe("hashColorIndex", () => {
  it("is deterministic for the same id", () => {
    expect(hashColorIndex("cat-1")).toBe(hashColorIndex("cat-1"));
  });

  it("stays within the palette bounds", () => {
    for (const id of ["a", "cat-1", "prompt-42", "Analyse et synthèse", ""]) {
      const idx = hashColorIndex(id);
      expect(idx).toBeGreaterThanOrEqual(0);
      expect(idx).toBeLessThan(HASH_COLOR_PALETTE_SIZE);
    }
  });

  it("differs for at least some distinct ids (not a constant function)", () => {
    const indices = new Set(["a", "b", "c", "d", "e", "f", "g", "h"].map(hashColorIndex));
    expect(indices.size).toBeGreaterThan(1);
  });
});
