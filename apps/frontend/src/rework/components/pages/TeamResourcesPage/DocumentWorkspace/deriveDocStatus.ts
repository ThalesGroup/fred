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

import type { DocStatus } from "@shared/atoms/DocStatusBadge/DocStatusBadge.tsx";
import type { DocumentMetadata } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";

export interface ResolvedDocStatus {
  status: DocStatus;
  progress: number | null;
}

/**
 * Collapse the internal pipeline stages into the one synthetic state the user
 * cares about ("is this document usable?"). An active task always wins, so a
 * live processing/failed run is reflected immediately; otherwise the answer is
 * read from `processing.stages`.
 *
 * - `vector === "done"` (chunked+embedded, backend `ProcessingStage.VECTORIZED`)
 *   or `sql === "done"` (tabular-indexed, `ProcessingStage.SQL_INDEXED`) each
 *   independently mean "queryable" → `ready`. A CSV/XLSX document only ever
 *   completes the `sql` stage (it's never chunked/embedded), so checking
 *   `vector` alone left every tabular document stuck at `raw` forever, even
 *   after a full page reload — this isn't a staleness gap, both stages are
 *   genuine, mutually-exclusive-per-file-type completion signals.
 * - nothing processed yet (only stored) → `raw` (a legitimate choice, not an error).
 */
const QUERYABLE_STAGES = ["vector", "sql"];

export function deriveDocStatus(doc: DocumentMetadata, task?: TaskViewModel): ResolvedDocStatus {
  if (task) {
    if (task.state === "failed") return { status: "failed", progress: null };
    // pending / running / cancelling — a live ingestion is in flight.
    return { status: "processing", progress: task.progress };
  }

  const stages = doc.processing?.stages ?? {};
  const values = Object.values(stages);

  if (values.some((s) => s === "failed")) return { status: "failed", progress: null };
  if (values.some((s) => s === "in_progress")) return { status: "processing", progress: null };
  if (QUERYABLE_STAGES.some((stage) => stages[stage] === "done")) return { status: "ready", progress: null };
  return { status: "raw", progress: null };
}
