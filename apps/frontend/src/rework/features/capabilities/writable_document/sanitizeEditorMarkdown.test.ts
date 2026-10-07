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
import { sanitizeEditorMarkdown } from "./sanitizeEditorMarkdown";

describe("sanitizeEditorMarkdown", () => {
  it.each([
    ["literal comparison", "Latency (<3ms).", String.raw`Latency (\<3ms).`],
    ["multiple text nodes", "**a <3**\n\nb <4", String.raw`**a \<3**` + "\n\n" + String.raw`b \<4`],
    ["already escaped text", String.raw`Latency (\<3ms).`, String.raw`Latency (\<3ms).`],
    ["literal backslash", String.raw`a \\<3`, String.raw`a \\\<3`],
    ["inline code", "Use `<3ms` here.", "Use `<3ms` here."],
    ["fenced code", "```text\n<3ms\n```", "```text\n<3ms\n```"],
    ["indented code", "    <3ms", "    <3ms"],
    ["HTML and entities", "k<sub>safe</sub> &lt;3", "k<sub>safe</sub> &lt;3"],
    [
      "HTML block and attributes",
      '<div class="note">\nReal tags\n</div>\n\nLatency <3ms.',
      '<div class="note">\nReal tags\n</div>\n\nLatency \\<3ms.',
    ],
    ["link label and destination", "[a <3](https://example.test/a<3)", String.raw`[a \<3](https://example.test/a<3)`],
    ["image alt and destination", "![a <3](https://example.test/a<3)", String.raw`![a \<3](https://example.test/a<3)`],
    ["URL autolink", "<https://example.test/a(b)>", "[https://example.test/a(b)](<https://example.test/a(b)>)"],
    ["email autolink", "<user@example.test>", "[user@example.test](<mailto:user@example.test>)"],
    [
      "comparison inside HTML",
      '<div title="a <3">Latency <3ms.</div>',
      String.raw`<div title="a <3">Latency \<3ms.</div>`,
    ],
    [
      "reference image",
      "![a <3][image]\n\n[image]: https://example.test/img.png",
      String.raw`![a \<3][image]` + "\n\n[image]: https://example.test/img.png",
    ],
    [
      "URL formatting characters",
      "<https://example.test/a*b*c>",
      String.raw`[https://example.test/a\*b\*c](<https://example.test/a*b*c>)`,
    ],
    [
      "URL literal entity",
      "<https://example.test/?q=&amp;>",
      String.raw`[https://example.test/?q=\&amp;](<https://example.test/?q=\&amp;>)`,
    ],
    ["code inside HTML", "<div>\n```text\n<foo>\n<3ms\n```\n</div>", "<div>\n```text\n<foo>\n<3ms\n```\n</div>"],
    ["inline code inside HTML", "<div>`<foo> <3ms`</div>", "<div>`<foo> <3ms`</div>"],
    ["ordinary Markdown", "# Title\n\n**Text**", "# Title\n\n**Text**"],
  ])("preserves %s", (_label, markdown, expected) => {
    const sanitized = sanitizeEditorMarkdown(markdown);
    expect(sanitized).toBe(expected);
    expect(sanitizeEditorMarkdown(sanitized)).toBe(sanitized);
  });
});
