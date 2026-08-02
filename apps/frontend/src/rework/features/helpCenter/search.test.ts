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
import { extractHeadings, markdownToPlain, searchHelp } from "./search";

describe("extractHeadings", () => {
  it("collects h2/h3 with slugs and ignores h1/h4", () => {
    const md = "# Title\n\n## Créer un agent\n\ntext\n\n### Sous-section\n\n#### Ignored\n";
    expect(extractHeadings(md)).toEqual([
      { text: "Créer un agent", slug: "creer-un-agent" },
      { text: "Sous-section", slug: "sous-section" },
    ]);
  });
});

describe("markdownToPlain", () => {
  it("strips fenced code, links (keeping labels), markers and emphasis", () => {
    const md = "## Heading\n\nSee [the docs](/x) and `code`.\n\n```js\nignored()\n```\n\n- **bold** item\n";
    const plain = markdownToPlain(md);
    expect(plain).toContain("Heading");
    expect(plain).toContain("the docs");
    expect(plain).toContain("bold item");
    expect(plain).not.toContain("ignored");
    expect(plain).not.toContain("`");
    expect(plain).not.toContain("[");
    expect(plain).not.toContain("**");
  });
});

describe("searchHelp against the real corpus", () => {
  it("returns nothing for a blank query", () => {
    expect(searchHelp("fr", "")).toEqual([]);
    expect(searchHelp("fr", "   ")).toEqual([]);
  });

  it("finds the concepts page by a body term and marks the snippet", () => {
    const results = searchHelp("fr", "vocabulaire");
    const concepts = results.find((r) => r.meta.sectionId === "getting-started" && r.meta.id === "concepts");
    expect(concepts).toBeTruthy();
    expect(concepts!.snippet).toContain("<mark>");
  });

  it("ranks a title match above a body-only match", () => {
    // "concepts" is in the concepts page title; make sure it ranks first.
    const results = searchHelp("fr", "concepts");
    expect(results[0]?.meta.id).toBe("concepts");
  });

  it("returns a heading + anchor when the query hits a heading", () => {
    const results = searchHelp("fr", "Équipe");
    const withHeading = results.find((r) => r.heading);
    expect(withHeading?.heading?.slug).toBeTruthy();
  });

  it("requires every term to match (AND semantics)", () => {
    expect(searchHelp("fr", "vocabulaire zzzznope")).toEqual([]);
  });

  it("is case-insensitive", () => {
    expect(searchHelp("en", "CONCEPTS").length).toBeGreaterThan(0);
  });
});
