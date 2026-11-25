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
import { hasSameMarkdownContent } from "./markdownSyntax";

describe("the rendered Markdown contract during visual editing", () => {
  it.each([
    ["Before\n\n<!-- retain -->\n\nAfter", "Before\n\nAfter"],
    ["$$ y = x $$", "$$ y \\= x $$"],
    ["A[^1]\n\n[^1]: Footnote", "A\\[^1]\n\n\\[^1]: Footnote"],
    [":::details[Title]\nBody\n:::", "Title\n\nBody"],
  ])("rejects loss of comments, math, notes and directives: %s", (before, after) => {
    expect(hasSameMarkdownContent(before, after)).toBe(false);
  });

  it.each([
    ["# Title\n\n- One\n- Two", "Title\n=====\n\n* One\n* Two"],
    ["| A | B |\n| - | - |\n| x | y |", "| A   | B   |\n| --- | --- |\n| x   | y   |"],
    ["- [x] Done\n- [ ] Next", "* [x] Done\n* [ ] Next"],
    ["<u>Underlined</u>", "<u>Underlined</u>\n"],
    ["Cells D4:D5", "Cells D4\\:D5"],
  ])("accepts supported prose formatting: %s", (before, after) => {
    expect(hasSameMarkdownContent(before, after)).toBe(true);
  });
});
