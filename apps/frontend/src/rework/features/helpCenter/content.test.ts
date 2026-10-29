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

import { describe, expect, it, vi } from "vitest";
import {
  getHelpPage,
  getHelpPagesForLang,
  getHelpTree,
  helpPagePath,
  parseFrontmatter,
  resolveSiteName,
} from "./content";
import { HELP_LANGS, HELP_SECTIONS } from "./manifest";
import { extractHeadings } from "./search";

vi.mock("../../../common/config.tsx", () => ({
  getProperty: (key: string) => (key === "siteDisplayName" ? "Acme" : undefined),
}));

describe("parseFrontmatter", () => {
  it("splits fields from body and ignores unknown keys", () => {
    const raw = "---\ntitle: Hello\norder: 10\ncustom: noise\n---\n# Body\n";
    const { fields, body } = parseFrontmatter(raw);
    expect(fields.title).toBe("Hello");
    expect(fields.order).toBe("10");
    expect(fields.custom).toBe("noise");
    expect(body).toBe("# Body\n");
  });

  it("returns the whole text as body when there is no frontmatter", () => {
    const { fields, body } = parseFrontmatter("# Just a body");
    expect(fields).toEqual({});
    expect(body).toBe("# Just a body");
  });

  it("keeps colons inside values", () => {
    const { fields } = parseFrontmatter("---\ntitle: Ratio 16:9\n---\nbody");
    expect(fields.title).toBe("Ratio 16:9");
  });
});

describe("resolveSiteName", () => {
  it("replaces every placeholder with the given name", () => {
    expect(resolveSiteName("{{siteDisplayName}} reads; ask {{siteDisplayName}}.", "Acme")).toBe(
      "Acme reads; ask Acme.",
    );
  });
});

describe("help content corpus", () => {
  it("exposes every manifest section, in manifest order, for each language", () => {
    for (const lang of HELP_LANGS) {
      const tree = getHelpTree(lang);
      expect(tree.map((s) => s.id)).toEqual(HELP_SECTIONS.map((s) => s.id));
    }
  });

  it("has an index page in every section for each language", () => {
    for (const lang of HELP_LANGS) {
      for (const section of getHelpTree(lang)) {
        expect(section.pages[0]?.id, `${lang}/${section.id} must have an index page listed first`).toBe("index");
        expect(getHelpPage(lang, section.id, "index"), `${lang}/${section.id}/index must resolve`).not.toBeNull();
      }
    }
  });

  it("keeps page ids identical across languages (language switch mapping)", () => {
    const ids = (lang: (typeof HELP_LANGS)[number]) =>
      getHelpTree(lang).map((s) => ({ id: s.id, pages: s.pages.map((p) => p.id) }));
    expect(ids("fr")).toEqual(ids("en"));
  });

  it("points every cross-link anchor at an existing heading", () => {
    for (const lang of HELP_LANGS) {
      for (const { body } of getHelpPagesForLang(lang)) {
        for (const [, linkLang, section, page, slug] of body.matchAll(
          /\]\(\/help\/(\w+)\/([\w-]+)\/([\w-]+)#([\w-]+)\)/g,
        )) {
          const target = getHelpPage(linkLang as typeof lang, section, page);
          expect(target, `${linkLang}/${section}/${page} must exist`).not.toBeNull();
          expect(extractHeadings(target!.body).map((h) => h.slug)).toContain(slug);
        }
      }
    }
  });

  it("parses frontmatter into meta (title differs from file id)", () => {
    const page = getHelpPage("fr", "getting-started", "first-steps");
    expect(page).not.toBeNull();
    expect(page!.meta.title).toBe("Premiers pas");
    expect(page!.body).not.toContain("---\ntitle");
  });

  it("names the product only through the deployment's site name", () => {
    for (const lang of HELP_LANGS) {
      for (const { meta, body } of getHelpPagesForLang(lang)) {
        const text = `${meta.title}\n${meta.description ?? ""}\n${body}`;
        expect(text, `${lang}/${meta.sectionId}/${meta.id}`).not.toMatch(/\bFred\b|\{\{siteDisplayName\}\}/);
      }
    }
    expect(getHelpPage("en", "getting-started", "index")!.body).toContain("Acme brings together");
  });

  it("returns null for unknown pages", () => {
    expect(getHelpPage("fr", "getting-started", "nope")).toBeNull();
    expect(getHelpPage("fr", "nope", "index")).toBeNull();
  });
});

describe("helpPagePath", () => {
  it("uses the bare section URL for index pages", () => {
    expect(helpPagePath("fr", "features", "index")).toBe("/help/fr/features");
    expect(helpPagePath("en", "features", "agents")).toBe("/help/en/features/agents");
  });
});
