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

import type { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import type { MaterialIconType } from "@shared/utils/Type.ts";
import { HELP_SECTIONS, type HelpLang } from "./manifest";

/** Parsed frontmatter of one help page. */
export interface HelpPageMeta {
  /** Page id = file name without `.md`; `index` is the section landing page. */
  id: string;
  sectionId: string;
  lang: HelpLang;
  title: string;
  /** Sidebar position within the section (index page is always first). */
  order: number;
  /** One-line summary, surfaced by search results. */
  description?: string;
  /** Sidebar icon (Material Symbols name). Defaults to `article`. */
  icon: MaterialIconType;
}

export interface HelpPage {
  meta: HelpPageMeta;
  /** Markdown body, frontmatter stripped, asset URLs resolved. */
  body: string;
}

export interface HelpSectionTree {
  id: string;
  titleKey: string;
  icon: IconProps;
  /** Landing page first, then the section's pages sorted by `order`, `title`. */
  pages: HelpPageMeta[];
}

// The whole corpus ships (raw) inside the lazy-loaded Help Center chunk: it
// powers the sidebar (titles), the pages, and later the search index from a
// single source. Revisit per-page lazy imports only if the corpus outgrows
// a few hundred KB.
const pageModules = import.meta.glob("./content/*/*/*.md", {
  eager: true,
  query: "?raw",
  import: "default",
}) as Record<string, string>;

// Images referenced from markdown as `assets/<file>` resolve to their built
// URL through this map (single tree shared by both languages).
const assetModules = import.meta.glob("./content/assets/**", {
  eager: true,
  query: "?url",
  import: "default",
}) as Record<string, string>;

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/;

/**
 * Parse the tiny frontmatter dialect used by help pages: one `key: value`
 * per line, string values, no nesting. Unknown keys are ignored so authors
 * can annotate freely without breaking the loader.
 */
export function parseFrontmatter(raw: string): { fields: Record<string, string>; body: string } {
  const match = FRONTMATTER_RE.exec(raw);
  if (!match) return { fields: {}, body: raw };
  const fields: Record<string, string> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const sep = line.indexOf(":");
    if (sep === -1) continue;
    const key = line.slice(0, sep).trim();
    const value = line.slice(sep + 1).trim();
    if (key) fields[key] = value;
  }
  return { fields, body: raw.slice(match[0].length) };
}

/** Rewrite `](assets/…)` image/link targets to their built asset URLs. */
export function resolveAssetUrls(body: string): string {
  return body.replace(/\]\(assets\/([^)\s]+)\)/g, (whole, file: string) => {
    const url = assetModules[`./content/assets/${file}`];
    return url ? `](${url})` : whole;
  });
}

interface StoredPage {
  meta: HelpPageMeta;
  rawBody: string;
}

function buildStore(): Map<string, StoredPage> {
  const store = new Map<string, StoredPage>();
  for (const [path, raw] of Object.entries(pageModules)) {
    // ./content/<lang>/<sectionId>/<pageId>.md
    const segments = path.split("/");
    const lang = segments[2] as HelpLang;
    const sectionId = segments[3];
    const id = segments[4].replace(/\.md$/, "");
    const { fields, body } = parseFrontmatter(raw);
    const meta: HelpPageMeta = {
      id,
      sectionId,
      lang,
      title: fields.title ?? id,
      order: Number.isFinite(Number(fields.order)) ? Number(fields.order) : 999,
      description: fields.description || undefined,
      icon: (fields.icon as MaterialIconType) || "article",
    };
    store.set(`${lang}/${sectionId}/${id}`, { meta, rawBody: body });
  }
  return store;
}

const pages = buildStore();

/** All sections (manifest order) with their pages for one language. */
export function getHelpTree(lang: HelpLang): HelpSectionTree[] {
  return HELP_SECTIONS.map((section) => {
    const sectionPages = [...pages.values()]
      .filter((p) => p.meta.lang === lang && p.meta.sectionId === section.id)
      .map((p) => p.meta)
      .sort((a, b) => {
        if (a.id === "index") return -1;
        if (b.id === "index") return 1;
        return a.order - b.order || a.title.localeCompare(b.title);
      });
    return { id: section.id, titleKey: section.titleKey, icon: section.icon, pages: sectionPages };
  });
}

/** One page's meta + renderable body, or null when it doesn't exist. */
export function getHelpPage(lang: HelpLang, sectionId: string, pageId: string): HelpPage | null {
  const stored = pages.get(`${lang}/${sectionId}/${pageId}`);
  if (!stored) return null;
  return { meta: stored.meta, body: resolveAssetUrls(stored.rawBody) };
}

/** Every page of one language with its meta + raw markdown body — the source
 *  the search index is built from (see `search.ts`). */
export function getHelpPagesForLang(lang: HelpLang): { meta: HelpPageMeta; body: string }[] {
  return [...pages.values()].filter((p) => p.meta.lang === lang).map((p) => ({ meta: p.meta, body: p.rawBody }));
}

/** Canonical in-app path of a help page (index pages use the bare section URL). */
export function helpPagePath(lang: HelpLang, sectionId: string, pageId: string): string {
  return pageId === "index" ? `/help/${lang}/${sectionId}` : `/help/${lang}/${sectionId}/${pageId}`;
}
