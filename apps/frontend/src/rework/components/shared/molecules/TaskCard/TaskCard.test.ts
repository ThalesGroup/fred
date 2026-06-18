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

import { describe, it, expect } from "vitest";
import { truncate } from "./TaskCard";

// ── truncate ──────────────────────────────────────────────────────────────────

describe("truncate", () => {
  it("returns the name unchanged when it fits within the limit", () => {
    expect(truncate("short.pdf")).toBe("short.pdf");
  });

  it("returns the name unchanged at exactly the limit length", () => {
    const name = "a".repeat(32);
    expect(truncate(name)).toBe(name);
  });

  it("truncates and appends ellipsis when the name exceeds the limit", () => {
    const name = "a".repeat(33);
    const result = truncate(name);
    expect(result).toHaveLength(32);
    expect(result.endsWith("…")).toBe(true);
  });

  it("respects a custom max parameter", () => {
    const result = truncate("hello world", 8);
    expect(result).toHaveLength(8);
    expect(result.endsWith("…")).toBe(true);
  });
});
