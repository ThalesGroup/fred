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

import type { DocumentMetadata, TaskSummary } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { TERMINAL_STATES, type TaskViewModel } from "../../../../features/tasks/taskTypes";
import { collectDescendantDocUids, type TagNode } from "../../../../../shared/utils/tagTree.ts";
import { deriveDocStatus } from "./deriveDocStatus.ts";

/** A document a folder chip stands for: its uid, and the name to show on hover. */
export interface FailedDoc {
  uid: string;
  name: string;
}

/** What a folder row shows, summarizing everything under it (#2384). */
export interface FolderRollup {
  processing: boolean;
  failed: FailedDoc[];
  justDone: boolean;
}

/**
 * The latest terminal outcome of each document's ingestion.
 *
 * `failed` carries the documents to flag; `resolved` carries those whose last
 * word was `succeeded` or `cancelled`. Both matter: a document can accumulate
 * several terminal tasks — a failed run then a successful re-upload of the same
 * file, since uids are content-derived — and nothing ever removes the old one
 * from the Redux store (`taskEvicted` is only dispatched by `TaskTray`, which is
 * currently unmounted). Ranking them is what stops a folder being flagged with a
 * failure the user has already repaired.
 *
 * `resolved` is not the complement of `failed`: it is only ever consulted to
 * clear a failure another source still believes in.
 */
export interface DocOutcomes {
  failed: Map<string, string>;
  resolved: Set<string>;
}

interface RankedOutcome {
  uid: string;
  state: string;
  name: string;
  /** Comparable only against outcomes from the SAME clock — see below. */
  at: number;
}

/** Keep the newest terminal outcome per document within one clock domain.
 *  An unrankable timestamp sorts as `-Infinity` so it can be superseded, rather
 *  than pinning whichever entry happened to be seen first. */
function rankByUid(entries: RankedOutcome[]): Map<string, RankedOutcome> {
  const byUid = new Map<string, RankedOutcome>();
  for (const entry of entries) {
    if (!TERMINAL_STATES.has(entry.state as never)) continue;
    const previous = byUid.get(entry.uid);
    if (previous && entry.at < previous.at) continue;
    byUid.set(entry.uid, entry);
  }
  return byUid;
}

const rankable = (value: number): number => (Number.isNaN(value) ? Number.NEGATIVE_INFINITY : value);

/**
 * Rank every feed's terminal tasks down to one outcome per document.
 *
 * `history` is the server's own record (`GET /tasks`), timestamped by the
 * server. `live` is this session's Redux store, timestamped by the browser's
 * `Date.now()` — a different clock, which a skewed laptop can put minutes
 * behind. The two are therefore ranked separately and never compared: a live
 * entry simply wins, which is correct by construction since it was observed
 * after the page (and the history it loaded) did.
 */
export function resolveDocOutcomes(history: TaskSummary[], live: TaskViewModel[]): DocOutcomes {
  const fromHistory = rankByUid(
    history.flatMap((task) =>
      task.target?.type === "document" && task.target.id
        ? [
            {
              uid: task.target.id,
              state: task.state,
              name: task.target.label || task.target.id,
              at: rankable(Date.parse(task.updated_at)),
            },
          ]
        : [],
    ),
  );
  const fromLive = rankByUid(
    live.flatMap((task) =>
      task.target?.type === "document" && task.target.id
        ? [
            {
              uid: task.target.id,
              state: task.state,
              name: task.target.label || task.target.id,
              at: task.terminalAt ?? task.registeredAt,
            },
          ]
        : [],
    ),
  );

  const failed = new Map<string, string>();
  const resolved = new Set<string>();
  for (const [uid, outcome] of new Map([...fromHistory, ...fromLive])) {
    if (outcome.state === "failed") failed.set(uid, outcome.name);
    // `cancelled` is not a failure — the user stopped it on purpose — but it
    // does resolve one, which is why it lands here rather than being ignored.
    else resolved.add(uid);
  }
  return { failed, resolved };
}

/**
 * The failed documents of every already-loaded page, grouped by tag id.
 *
 * This is the half that survives a page reload for folders the user has opened,
 * and the only one that knows about a document the task feed never covered.
 * `deriveDocStatus` owns the "which stages mean failed" rule — asking it with no
 * live task is deliberate: a failed task is never in the ACTIVE feed, so the
 * live map could add nothing, and staying off it keeps this derivation out of
 * the per-SSE-event churn.
 */
export function collectFailedDocsByTag(
  pages: Record<string, { docs: DocumentMetadata[] }>,
  displayName: (doc: DocumentMetadata) => string,
): Map<string, FailedDoc[]> {
  const byTag = new Map<string, FailedDoc[]>();
  for (const [tagId, page] of Object.entries(pages)) {
    const failed = page.docs
      .filter((doc) => deriveDocStatus(doc).status === "failed")
      .map((doc) => ({ uid: doc.identity.document_uid, name: displayName(doc) }));
    if (failed.length > 0) byTag.set(tagId, failed);
  }
  return byTag;
}

/**
 * Which visible child folder each document sits under.
 *
 * Built once per tag tree so the rollup below is a lookup rather than a walk —
 * walking each subtree per recompute re-reads the team's whole corpus at the
 * Corpus root. Subtrees are disjoint (a document is tagged into exactly one
 * folder), so one pass fills it.
 */
export function indexFoldersByDocUid(childFolders: TagNode[]): Map<string, string> {
  const byUid = new Map<string, string>();
  for (const node of childFolders) {
    for (const uid of collectDescendantDocUids(node)) byUid.set(uid, node.full);
  }
  return byUid;
}

export interface FolderRollupInput {
  childFolders: TagNode[];
  /** Descendant tag ids per folder — shared with the folder-size column. */
  tagIdsByFolder: Map<string, string[]>;
  folderByDocUid: Map<string, string>;
  /** Tags whose already-loaded page shows a processing row. */
  pendingTagIds: string[];
  failedDocsByTagId: Map<string, FailedDoc[]>;
  /** Documents with a live (non-terminal) ingestion task. */
  activeDocUids: Iterable<string>;
  outcomes: DocOutcomes;
  /** Documents that finished during THIS browser session. */
  justCompletedDocUids: Set<string>;
}

/**
 * Summarize each visible child folder from every available source.
 *
 * One ranking rule governs both failure sources: `outcomes.resolved` clears a
 * snapshot-reported failure just as it clears a task-reported one. Without that
 * the snapshot half would keep a folder flagged after a cancelled ingestion (the
 * backend erases the half-built document, but the loaded page still carries its
 * stale `failed` stage) with no way to clear it short of a refetch.
 */
export function buildFolderRollups(input: FolderRollupInput): Map<string, FolderRollup> {
  const { childFolders, tagIdsByFolder, folderByDocUid, pendingTagIds, failedDocsByTagId } = input;
  const { activeDocUids, outcomes, justCompletedDocUids } = input;

  const pending = new Set(pendingTagIds);
  const failedByFolder = new Map<string, Map<string, FailedDoc>>();
  const rollups = new Map<string, FolderRollup>();

  for (const node of childFolders) {
    const tagIds = tagIdsByFolder.get(node.full) ?? [];
    rollups.set(node.full, { processing: tagIds.some((id) => pending.has(id)), failed: [], justDone: false });
    failedByFolder.set(
      node.full,
      new Map(
        tagIds
          .flatMap((id) => failedDocsByTagId.get(id) ?? [])
          .filter((doc) => !outcomes.resolved.has(doc.uid))
          .map((doc) => [doc.uid, doc] as const),
      ),
    );
  }

  // Everything below is driven by the (small) task-derived id sets, resolved
  // through folderByDocUid — no subtree walk.
  for (const uid of activeDocUids) {
    const rollup = rollups.get(folderByDocUid.get(uid) ?? "");
    if (rollup) rollup.processing = true;
  }
  for (const [uid, name] of outcomes.failed) {
    const failed = failedByFolder.get(folderByDocUid.get(uid) ?? "");
    if (failed && !failed.has(uid)) failed.set(uid, { uid, name });
  }
  for (const uid of justCompletedDocUids) {
    const rollup = rollups.get(folderByDocUid.get(uid) ?? "");
    if (rollup) rollup.justDone = true;
  }
  for (const [full, rollup] of rollups) rollup.failed = [...(failedByFolder.get(full)?.values() ?? [])];
  return rollups;
}
