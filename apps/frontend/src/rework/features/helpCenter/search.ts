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

import { getHelpPagesForLang, type HelpPageMeta } from "./content";
import type { HelpLang } from "./manifest";
import { slugifyHeading } from "@shared/molecules/MarkdownRenderer/HeadingWithAnchor";

/** One h2/h3 heading found in a page body, with its anchor slug. */
interface HelpHeading {
  text: string;
  slug: string;
}

/** A page turned into searchable material — parsed once, then reused. */
interface HelpSearchEntry {
  meta: HelpPageMeta;
  headings: HelpHeading[];
  /** Body text, markdown syntax stripped, lowercased for matching. */
  plain: string;
}

export interface HelpSearchResult {
  meta: HelpPageMeta;
  /** Best-matching heading, when the query hit a heading rather than body/meta. */
  heading?: HelpHeading;
  /** Snippet around the first match, with the matched run wrapped in <mark>. */
  snippet: string;
}

// Field weights — a query term is worth more in a title than in the body
// (RFC §2.5: frontmatter title/description, then headings, then body).
const WEIGHT_TITLE = 8;
const WEIGHT_DESCRIPTION = 4;
const WEIGHT_HEADING = 3;
const WEIGHT_BODY = 1;

const MAX_RESULTS = 20;
const SNIPPET_RADIUS = 60;

/** Collect h2/h3 headings (the ones MarkdownRenderer anchors) from raw markdown. */
export function extractHeadings(markdown: string): HelpHeading[] {
  const headings: HelpHeading[] = [];
  const re = /^(#{2,3})\s+(.+?)\s*#*$/gm;
  let match: RegExpExecArray | null;
  while ((match = re.exec(markdown)) !== null) {
    const text = match[2].trim();
    headings.push({ text, slug: slugifyHeading(text) });
  }
  return headings;
}

/**
 * Reduce markdown to plain prose for matching/snippets: drop frontmatter,
 * fenced code, headings/blockquote/list markers, links (keep the label),
 * emphasis and inline code. Good enough for substring search over docs —
 * not a full markdown parser.
 */
export function markdownToPlain(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`[^`]*`/g, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s{0,3}>\s?/gm, "")
    .replace(/^\s{0,3}[-*+]\s+/gm, "")
    .replace(/[*_~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

const indexCache = new Map<HelpLang, HelpSearchEntry[]>();

/** Build (once per language, then cached) the searchable entries. Called
 *  lazily on first search so it never costs anything until used. */
function getIndex(lang: HelpLang): HelpSearchEntry[] {
  const cached = indexCache.get(lang);
  if (cached) return cached;
  const entries = getHelpPagesForLang(lang).map(({ meta, body }) => ({
    meta,
    headings: extractHeadings(body),
    plain: markdownToPlain(body),
  }));
  indexCache.set(lang, entries);
  return entries;
}

/** Count non-overlapping occurrences of `term` in the already-lowercased `haystack`. */
function countOccurrences(haystack: string, term: string): number {
  if (!term) return 0;
  let count = 0;
  let from = 0;
  for (;;) {
    const at = haystack.indexOf(term, from);
    if (at === -1) return count;
    count += 1;
    from = at + term.length;
  }
}

/** A snippet of `plain` around the first `term` match, with the run marked.
 *  Returns null when the term isn't in the body. Escapes HTML so the marked
 *  string is safe to inject. */
function buildSnippet(plain: string, term: string): string | null {
  const at = plain.toLowerCase().indexOf(term);
  if (at === -1) return null;
  const start = Math.max(0, at - SNIPPET_RADIUS);
  const end = Math.min(plain.length, at + term.length + SNIPPET_RADIUS);
  const escape = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const before = (start > 0 ? "…" : "") + escape(plain.slice(start, at));
  const hit = escape(plain.slice(at, at + term.length));
  const after = escape(plain.slice(at + term.length, end)) + (end < plain.length ? "…" : "");
  return `${before}<mark>${hit}</mark>${after}`;
}

/**
 * Rank every page of `lang` against `query`. Each whitespace-separated term
 * must appear somewhere in the page (AND semantics); score sums weighted
 * field hits across terms. Ties break on the manifest-independent title.
 */
export function searchHelp(lang: HelpLang, query: string): HelpSearchResult[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return [];

  const results: (HelpSearchResult & { score: number })[] = [];

  for (const entry of getIndex(lang)) {
    const title = entry.meta.title.toLowerCase();
    const descriptionLower = (entry.meta.description ?? "").toLowerCase();
    const headingText = entry.headings.map((h) => h.text.toLowerCase());

    let score = 0;
    let matchedEveryTerm = true;
    let bestHeading: HelpHeading | undefined;
    // First term that matched anywhere — drives which run the snippet highlights.
    let snippetTerm: string | undefined;

    for (const term of terms) {
      let termScore = 0;
      termScore += countOccurrences(title, term) * WEIGHT_TITLE;
      termScore += countOccurrences(descriptionLower, term) * WEIGHT_DESCRIPTION;
      headingText.forEach((text, i) => {
        const hits = countOccurrences(text, term);
        if (hits > 0) {
          termScore += hits * WEIGHT_HEADING;
          if (!bestHeading) bestHeading = entry.headings[i];
        }
      });
      termScore += countOccurrences(entry.plain.toLowerCase(), term) * WEIGHT_BODY;

      if (termScore === 0) {
        matchedEveryTerm = false;
        break;
      }
      if (!snippetTerm) snippetTerm = term;
      score += termScore;
    }

    if (!matchedEveryTerm) continue;

    // Snippet around the matched run — from the body when the term is there,
    // else from the description (still highlighted), else the plain description.
    const description = entry.meta.description ?? "";
    const snippet =
      (snippetTerm && (buildSnippet(entry.plain, snippetTerm) || buildSnippet(description, snippetTerm))) ||
      description;
    results.push({ meta: entry.meta, heading: bestHeading, snippet, score });
  }

  return results
    .sort((a, b) => b.score - a.score || a.meta.title.localeCompare(b.meta.title))
    .slice(0, MAX_RESULTS)
    .map(({ score: _score, ...result }) => result);
}
