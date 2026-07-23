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

import type { DocumentMetadata } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

/** A loaded document page — only the fields the refresh decision needs. */
interface LoadedPage {
  docs: DocumentMetadata[];
  offset: number;
}

/**
 * Decide which loaded pages need a metadata refetch because a document's
 * ingestion task just finished.
 *
 * A document row shows "processing" while a live task targets it, then falls back
 * to the stored `processing.stages` once the task leaves the active set. Those
 * stages were captured before the pipeline completed, so the row would read
 * "raw"/"Brut" until a manual reload. Given the docs that had a running task on
 * the previous render (`prevRunning`) and those that still do (`running`), return
 * the `{ tagId, offset }` of every loaded page holding a just-finished document —
 * exactly the pages whose stored stages are now stale.
 *
 * Pure and idempotent: when nothing transitioned (`prevRunning === running`) it
 * returns `[]`, so re-running the effect on unrelated `perTag` changes is a no-op.
 */
export function pagesToRefreshOnTaskCompletion(
  prevRunning: ReadonlySet<string | undefined>,
  running: ReadonlySet<string | undefined>,
  perTag: Record<string, LoadedPage>,
): { tagId: string; offset: number }[] {
  const finished = new Set([...prevRunning].filter((id): id is string => Boolean(id) && !running.has(id)));
  if (finished.size === 0) return [];

  const out: { tagId: string; offset: number }[] = [];
  for (const [tagId, page] of Object.entries(perTag)) {
    if (page.docs.some((doc) => finished.has(doc.identity.document_uid))) {
      out.push({ tagId, offset: page.offset });
    }
  }
  return out;
}
