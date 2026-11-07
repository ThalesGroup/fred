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

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useLocalStorageState } from "../../../hooks/useLocalStorageState";
import { KeyCloakService } from "../../../security/KeycloakService";
import type { WikiPageSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { ancestorsOf, buildWikiTree, RULES_PAGE_SLUG } from "./wikiTree";

interface SpaceTreeState {
  expanded: string[];
  /** A page id, or RULES_PAGE_SLUG: a slug can keep a trace of a title, and this outlives the session. */
  lastPage: string | null;
}

const NO_SPACES: Record<string, SpaceTreeState> = {};
const NO_STATE: SpaceTreeState = { expanded: [], lastPage: null };

export interface WikiTreeState {
  /** Where the wiki's root leads: the last page still in the tree, else the first. Null without pages. */
  homeSlug: string | null;
  expanded: ReadonlySet<string>;
  toggle: (pageId: string) => void;
  expand: (pageIds: readonly string[]) => void;
  /** Called when the reader asks for the wiki's root, so it opens on the first page. */
  forgetLastPage: () => void;
}

/**
 * The rail's expanded pages and the last page opened, kept in this browser.
 * Keyed by user because localStorage is shared by whoever signs in here, then
 * by space because page ids only mean something inside one wiki.
 */
export function useWikiTreeState(
  spaceId: string,
  pages: readonly WikiPageSummary[],
  urlSlug: string | undefined,
): WikiTreeState {
  const userId = KeyCloakService.GetUserId() ?? "anonymous";
  const [bySpace, setBySpace] = useLocalStorageState<Record<string, SpaceTreeState>>(
    `team-wiki:tree:${userId}`,
    NO_SPACES,
  );
  const stored = bySpace[spaceId] ?? NO_STATE;

  const pageIds = useMemo(() => new Set(pages.map((page) => page.page_id)), [pages]);
  const expanded = useMemo(() => new Set(stored.expanded), [stored.expanded]);

  const update = useCallback(
    (change: (current: SpaceTreeState) => Partial<SpaceTreeState>) =>
      setBySpace((all) => {
        const current = all[spaceId] ?? NO_STATE;
        return { ...all, [spaceId]: { ...current, ...change(current) } };
      }),
    [setBySpace, spaceId],
  );

  // Ids of deleted pages are dropped on the next write rather than kept forever.
  const live = useCallback((ids: Iterable<string>) => [...ids].filter((id) => pageIds.has(id)), [pageIds]);

  const toggle = useCallback(
    (pageId: string) =>
      update(({ expanded: current }) => ({
        expanded: current.includes(pageId) ? live(current.filter((id) => id !== pageId)) : live([...current, pageId]),
      })),
    [update, live],
  );

  const expand = useCallback(
    (ids: readonly string[]) => {
      if (ids.every((id) => expanded.has(id))) return;
      update(({ expanded: current }) => ({ expanded: live(new Set([...current, ...ids])) }));
    },
    [expanded, update, live],
  );

  const forgetLastPage = useCallback(() => update(() => ({ lastPage: null })), [update]);

  const lastSlug =
    stored.lastPage === RULES_PAGE_SLUG
      ? RULES_PAGE_SLUG
      : pages.find((page) => page.page_id === stored.lastPage)?.slug;
  const firstSlug = useMemo(() => buildWikiTree(pages)[0]?.page.slug ?? null, [pages]);
  const homeSlug = firstSlug && (lastSlug ?? firstSlug);

  // Recorded when the open page changes only: forgetting the last page must not
  // be undone by the URL it is leaving.
  const openPage = urlSlug === RULES_PAGE_SLUG ? RULES_PAGE_SLUG : pages.find((page) => page.slug === urlSlug)?.page_id;
  useEffect(() => {
    if (spaceId && openPage) update(() => ({ lastPage: openPage }));
  }, [spaceId, openPage, update]);

  // Once per page opened, so a reader can still fold an ancestor of the page they are on.
  const revealed = useRef<string | null>(null);
  useEffect(() => {
    const target = `${spaceId}/${urlSlug}`;
    if (!urlSlug || revealed.current === target || !pages.some((page) => page.slug === urlSlug)) return;
    revealed.current = target;
    expand(ancestorsOf(pages, urlSlug).map((page) => page.page_id));
  }, [spaceId, urlSlug, pages, expand]);

  return { homeSlug, expanded, toggle, expand, forgetLastPage };
}
