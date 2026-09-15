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

import type { WikiRevisionSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";

/**
 * A page's history as a timeline of events rather than a list of versions.
 *
 * A revision carries two facts that happened at different moments and, often,
 * to different people: an agent wrote the text, and later someone read it and
 * cleared the review mark. Folding the second into the first would lose both
 * its time and its author, so it becomes its own entry — one the reader can
 * neither preview nor restore, because no content of its own belongs to it.
 */
export type WikiHistoryEntry =
  | { kind: "revision"; key: string; at: string | null; revision: WikiRevisionSummary }
  | { kind: "review"; key: string; at: string; by: string; ofAgentEdit: boolean };

/** Newest first; an entry with no timestamp sorts last rather than first, where
 *  it would claim to be the most recent thing that happened. */
function byNewest(a: WikiHistoryEntry, b: WikiHistoryEntry): number {
  const at = (value: string | null) => (value ? Date.parse(value) : Number.NEGATIVE_INFINITY);
  return at(b.at) - at(a.at);
}

export function historyEntries(revisions: readonly WikiRevisionSummary[]): WikiHistoryEntry[] {
  const entries: WikiHistoryEntry[] = [];
  for (const revision of revisions) {
    entries.push({
      kind: "revision",
      key: revision.revision_id,
      at: revision.created_at ?? null,
      revision,
    });
    if (revision.reviewed_at) {
      entries.push({
        kind: "review",
        key: `${revision.revision_id}:review`,
        at: revision.reviewed_at,
        by: revision.reviewed_by ?? "",
        ofAgentEdit: revision.author_kind === "agent",
      });
    }
  }
  return entries.sort(byNewest);
}
