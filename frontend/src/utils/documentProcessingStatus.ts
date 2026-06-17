// Copyright Thales 2025
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

import { DocumentMetadata, ProcessingStatus } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

/**
 * Overall, user-facing processing status derived from the per-stage statuses
 * returned by the backend in `doc.processing.stages`.
 *
 * This is the single source of truth for both:
 *  - the status atom shown on each library row, and
 *  - the library's live polling (it keeps refreshing while any document is
 *    non-terminal, i.e. "pending" or "processing").
 *
 * The mapping mirrors the backend progress semantics:
 *  - "ready":      content is queryable (vector OR sql stage done) — backend `fully_processed`.
 *  - "failed":     a stage failed and the document is not fully processed — backend `has_failed`.
 *  - "processing": at least one stage is actively running.
 *  - "pending":    saved/queued but processing has not started yet.
 */
export type DocumentOverallStatus = "ready" | "processing" | "pending" | "failed";

export function getDocumentProcessingStatus(doc: DocumentMetadata): DocumentOverallStatus {
  const stages = doc.processing?.stages ?? {};
  const values: ProcessingStatus[] = Object.values(stages);

  // Ready mirrors backend "fully_processed": vector or sql indexing completed.
  if (stages["vector"] === "done" || stages["sql"] === "done") return "ready";
  // Failed mirrors backend "has_failed": a stage failed and not fully processed.
  if (values.some((s) => s === "failed")) return "failed";
  // Something is actively running.
  if (values.some((s) => s === "in_progress")) return "processing";
  // Saved/queued, nothing started yet (or only raw available).
  return "pending";
}

/** Terminal = no longer changing; the library can stop polling for this document. */
export function isDocumentProcessingTerminal(doc: DocumentMetadata): boolean {
  const status = getDocumentProcessingStatus(doc);
  return status === "ready" || status === "failed";
}

/** True when at least one document is still pending/processing and worth polling for. */
export function hasNonTerminalDocuments(docs: DocumentMetadata[]): boolean {
  return docs.some((doc) => !isDocumentProcessingTerminal(doc));
}
