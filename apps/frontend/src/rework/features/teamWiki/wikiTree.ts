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

// The wiki's page tree, assembled from the flat list the API returns.
//
// The API is flat on purpose (the depth cap keeps the list small, and a flat
// payload keeps the response stable if nesting rules change), so the shape the
// sidebar renders is built here — as pure functions, because every interesting
// case is a data case: an orphan, a cycle, the rules page.

import type { WikiPageSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";

/** Reserved slug of the rules page — must match the backend's RULES_PAGE_SLUG. */
export const RULES_PAGE_SLUG = "__rules__";

/** Mirrors the backend's MAX_PAGE_DEPTH. A root sits at depth 0, so 3 allows
 *  four levels and a child of a depth-3 page is refused. */
export const MAX_PAGE_DEPTH = 3;

/** Can a page at this depth take a child without the server refusing it? */
export function canHaveChild(depth: number): boolean {
  return depth + 1 <= MAX_PAGE_DEPTH;
}

export interface WikiTreeNode {
  page: WikiPageSummary;
  depth: number;
  children: WikiTreeNode[];
}

/** The rules page, which the tree never contains — it has its own entry. */
export function findRulesPage(pages: readonly WikiPageSummary[]): WikiPageSummary | null {
  return pages.find((page) => page.kind === "rules" || page.slug === RULES_PAGE_SLUG) ?? null;
}

/**
 * The flat page list as a tree, ordered by `position` then title.
 *
 * A page whose IMMEDIATE parent is missing from the list is treated as a root
 * rather than dropped. Losing a page from the sidebar because its parent
 * vanished would make it unreachable and look like data loss; showing it at the
 * top level makes it visible and fixable. Only that page is promoted — its own
 * children stay nested under it, so an intact subtree is not flattened along
 * with the one broken link above it.
 *
 * A page caught in a parent cycle is promoted for the same reason: the backend
 * forbids cycles, but no client should hang on one.
 */
export function buildWikiTree(pages: readonly WikiPageSummary[]): WikiTreeNode[] {
  const ordinary = pages.filter((page) => page.kind !== "rules" && page.slug !== RULES_PAGE_SLUG);
  const byId = new Map(ordinary.map((page) => [page.page_id, page]));

  const isInCycle = (page: WikiPageSummary): boolean => {
    let cursor = page.parent_page_id;
    const seen = new Set<string>([page.page_id]);
    while (cursor) {
      if (seen.has(cursor)) return true;
      const parent = byId.get(cursor);
      if (!parent) return false; // a missing ancestor is not a cycle
      seen.add(cursor);
      cursor = parent.parent_page_id;
    }
    return false;
  };

  const childrenOf = new Map<string, WikiPageSummary[]>();
  const roots: WikiPageSummary[] = [];
  for (const page of ordinary) {
    const parentId = page.parent_page_id;
    if (!parentId || !byId.has(parentId) || isInCycle(page)) {
      roots.push(page);
      continue;
    }
    const siblings = childrenOf.get(parentId) ?? [];
    siblings.push(page);
    childrenOf.set(parentId, siblings);
  }

  const order = (list: WikiPageSummary[]): WikiPageSummary[] =>
    [...list].sort((a, b) => (a.position ?? 0) - (b.position ?? 0) || a.title.localeCompare(b.title));

  const build = (page: WikiPageSummary, depth: number): WikiTreeNode => ({
    page,
    depth,
    children: order(childrenOf.get(page.page_id) ?? []).map((child) => build(child, depth + 1)),
  });

  return order(roots).map((page) => build(page, 0));
}

/** Flatten a tree back to render order, dropping the subtrees of collapsed nodes. */
export function visibleNodes(nodes: readonly WikiTreeNode[], collapsed: ReadonlySet<string>): WikiTreeNode[] {
  const out: WikiTreeNode[] = [];
  const walk = (list: readonly WikiTreeNode[]) => {
    for (const node of list) {
      out.push(node);
      if (!collapsed.has(node.page.page_id)) walk(node.children);
    }
  };
  walk(nodes);
  return out;
}

/** Ancestor chain of `slug`, outermost first, for the breadcrumb. */
export function ancestorsOf(pages: readonly WikiPageSummary[], slug: string): WikiPageSummary[] {
  const bySlug = pages.find((page) => page.slug === slug);
  if (!bySlug) return [];
  const byId = new Map(pages.map((page) => [page.page_id, page]));
  const chain: WikiPageSummary[] = [];
  const seen = new Set<string>([bySlug.page_id]);
  let cursor = bySlug.parent_page_id;
  while (cursor && !seen.has(cursor)) {
    const parent = byId.get(cursor);
    if (!parent) break;
    chain.unshift(parent);
    seen.add(cursor);
    cursor = parent.parent_page_id;
  }
  return chain;
}

/** A page a subtree may legally be moved under, with the path that names it. */
export interface WikiMoveTarget {
  page: WikiPageSummary;
  /** Root-first path, e.g. `"Onboarding / Tooling"` — a flat list of bare
   *  titles cannot tell two pages named "Notes" apart. */
  path: string;
}

/** How many levels sit below this node — 0 for a leaf. */
function subtreeHeight(node: WikiTreeNode): number {
  return node.children.length === 0 ? 0 : 1 + Math.max(...node.children.map(subtreeHeight));
}

/**
 * The pages `pageId` may be moved under, mirroring the server's three refusals:
 * itself, its own descendants, and any destination deep enough to push the
 * moved subtree's lowest page past the cap.
 *
 * Duplicated from the backend deliberately: the server stays the gate, and this
 * only spares the user a destination that would come back as an error. Returned
 * in tree order, so the select reads like the rail.
 */
export function moveTargets(pages: readonly WikiPageSummary[], pageId: string): WikiMoveTarget[] {
  const candidates: (WikiMoveTarget & { depth: number })[] = [];
  let height: number | null = null;

  const walk = (nodes: readonly WikiTreeNode[], trail: readonly string[]) => {
    for (const node of nodes) {
      const path = [...trail, node.page.title];
      // The moved page and everything under it are skipped whole: a page cannot
      // be its own parent, nor a child of its own child.
      if (node.page.page_id === pageId) {
        height = subtreeHeight(node);
        continue;
      }
      candidates.push({ page: node.page, path: path.join(" / "), depth: node.depth });
      walk(node.children, path);
    }
  };
  walk(buildWikiTree(pages), []);

  if (height === null) return [];
  const moved = height;
  return candidates
    .filter((candidate) => candidate.depth + 1 + moved <= MAX_PAGE_DEPTH)
    .map(({ page, path }) => ({ page, path }));
}
