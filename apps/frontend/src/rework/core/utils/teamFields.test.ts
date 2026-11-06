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
import { isValidTeamDescription } from "./teamFields.ts";

describe("isValidTeamDescription", () => {
  it("accepts the bounds and ignores surrounding whitespace", () => {
    expect(isValidTeamDescription("x".repeat(20))).toBe(true);
    expect(isValidTeamDescription(`  ${"x".repeat(500)}  `)).toBe(true);
    expect(isValidTeamDescription("x".repeat(19))).toBe(false);
    expect(isValidTeamDescription("x".repeat(501))).toBe(false);
  });

  it("counts an emoji as one character, as the API does", () => {
    // 13 letters and spaces + 4 emoji: 17 characters, though 21 UTF-16 units.
    expect(isValidTeamDescription("Support team \u{1F680}\u{1F680}\u{1F680}\u{1F680}")).toBe(false);
  });
});
