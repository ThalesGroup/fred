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

interface TeamTreeState {
  expanded: string[];
  lastSlug: string | null;
}

const NO_TEAMS: Record<string, TeamTreeState> = {};
const NO_STATE: TeamTreeState = { expanded: [], lastSlug: null };

export interface WikiTreeState {
  /** The page shown: the URL's, else the last one opened, else the first root. */
  activeSlug: string | null;
  expanded: ReadonlySet<string>;
  toggle: (pageId: string) => void;
  expand: (pageIds: readonly string[]) => void;
  /** Called when the reader asks for the wiki's root, so it opens on the first page. */
  forgetLastPage: () => void;
}

/**
 * The rail's expanded pages and the last page opened, kept in this browser.
 * Keyed by user because localStorage is shared by whoever signs in here, then
 * by team because page ids only mean something inside one wiki.
 */
export function useWikiTreeState(
  teamId: string,
  pages: readonly WikiPageSummary[],
  urlSlug: string | undefined,
): WikiTreeState {
  const userId = KeyCloakService.GetUserId() ?? "anonymous";
  const [byTeam, setByTeam] = useLocalStorageState<Record<string, TeamTreeState>>(`team-wiki:tree:${userId}`, NO_TEAMS);
  const stored = byTeam[teamId] ?? NO_STATE;

  const pageIds = useMemo(() => new Set(pages.map((page) => page.page_id)), [pages]);
  const expanded = useMemo(() => new Set(stored.expanded), [stored.expanded]);

  const update = useCallback(
    (change: (current: TeamTreeState) => Partial<TeamTreeState>) =>
      setByTeam((all) => {
        const current = all[teamId] ?? NO_STATE;
        return { ...all, [teamId]: { ...current, ...change(current) } };
      }),
    [setByTeam, teamId],
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

  const forgetLastPage = useCallback(() => update(() => ({ lastSlug: null })), [update]);

  const lastSlug =
    stored.lastSlug && (stored.lastSlug === RULES_PAGE_SLUG || pages.some((page) => page.slug === stored.lastSlug))
      ? stored.lastSlug
      : null;
  const firstSlug = useMemo(() => buildWikiTree(pages)[0]?.page.slug ?? null, [pages]);
  const activeSlug = urlSlug ?? lastSlug ?? firstSlug;

  // Recorded on navigation only: forgetting the last page must not be undone by
  // the URL it is leaving.
  useEffect(() => {
    if (urlSlug) update(() => ({ lastSlug: urlSlug }));
  }, [urlSlug, update]);

  // Once per page opened, so a reader can still fold an ancestor of the page they are on.
  const revealed = useRef<string | null>(null);
  useEffect(() => {
    const target = `${teamId}/${activeSlug}`;
    if (!activeSlug || revealed.current === target || !pages.some((page) => page.slug === activeSlug)) return;
    revealed.current = target;
    expand(ancestorsOf(pages, activeSlug).map((page) => page.page_id));
  }, [teamId, activeSlug, pages, expand]);

  return { activeSlug, expanded, toggle, expand, forgetLastPage };
}
