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

import type { WikiRevisionList, WikiRevisionSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";

/**
 * A page's history, accumulated client-side across one or more bounded
 * server requests. Presentation state only — the server never returns more
 * than one page at a time (WIKI-05), so "everything loaded so far" has to be
 * kept somewhere while the reader walks backward through it.
 */
export interface HistoryPages {
  revisions: WikiRevisionSummary[];
  contents: Record<string, string>;
  /** `cursor` to request the next, older page; `null` at the end of history. */
  nextCursor: string | null;
}

export const emptyHistoryPages: HistoryPages = { revisions: [], contents: {}, nextCursor: null };

/**
 * Folds one server response into the accumulated state.
 *
 * `fetchedWithCursor` is `undefined` exactly when `page` is a BASE page (the
 * newest one, `cursor` omitted from the request) — which happens both on the
 * very first load and every time the underlying query is invalidated (a
 * restore, an edit, another viewer's write) while the reader is still parked
 * on it. Either way the right move is the same: replace outright, never mix
 * a fresh base page with an older tail accumulated before it. Any other
 * cursor is an explicit "load older" continuing the existing walk, so its
 * revisions are appended — deduplicated, since a retry of an in-flight
 * request must not double an already-merged page.
 */
export function mergeHistoryPage(
  state: HistoryPages,
  fetchedWithCursor: string | undefined,
  page: WikiRevisionList,
): HistoryPages {
  if (fetchedWithCursor === undefined) {
    return { revisions: page.revisions, contents: page.contents, nextCursor: page.next_cursor ?? null };
  }

  const seen = new Set(state.revisions.map((revision) => revision.revision_id));
  const fresh = page.revisions.filter((revision) => !seen.has(revision.revision_id));
  return {
    revisions: [...state.revisions, ...fresh],
    contents: { ...state.contents, ...page.contents },
    nextCursor: page.next_cursor ?? null,
  };
}
