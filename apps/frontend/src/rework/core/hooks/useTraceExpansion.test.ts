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
import { resolveTraceExpanded } from "./useTraceExpansion";

describe("resolveTraceExpanded", () => {
  it("opens while the turn streams and collapses once it is done (no user input yet)", () => {
    expect(resolveTraceExpanded(null, null, false)).toBe(true);
    expect(resolveTraceExpanded(null, null, true)).toBe(false);
  });

  it("lets the stored preference override the auto behaviour in both directions", () => {
    // Collapsed for good: even a streaming turn stays hidden.
    expect(resolveTraceExpanded(null, false, false)).toBe(false);
    // Always shown: a finished turn stays open.
    expect(resolveTraceExpanded(null, true, true)).toBe(true);
  });

  it("gives this block's own toggle precedence over the stored preference", () => {
    expect(resolveTraceExpanded(true, false, true)).toBe(true);
    expect(resolveTraceExpanded(false, true, false)).toBe(false);
  });
});
