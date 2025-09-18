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

// Minimal helpers for DocumentMetadata search + tag checks.

import type { DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

/** Tag IDs attached to this document (always an array). */
const _getDocTagIds = (d: DocumentMetadata): string[] => d.tags?.tag_ids ?? [];

/** Best display name for search/labeling. */
const _getDocDisplayName = (d: DocumentMetadata): string =>
  (d.identity.title?.trim() || d.identity.document_name || d.identity.document_uid);

/** Simple name-based matcher (case-insensitive). */
export const matchesDocByName = (d: DocumentMetadata, q: string): boolean => {
  if (!q) return true;
  const qn = q.toLowerCase();
  return _getDocDisplayName(d).toLowerCase().includes(qn);
};

/** Does the document have at least one of these tag IDs? */
export const docHasAnyTag = (d: DocumentMetadata, tagIds: readonly string[]): boolean => {
  const docIds = _getDocTagIds(d);
  if (docIds.length === 0 || tagIds.length === 0) return false;
  // small input: O(n*m) is fine and keeps code minimal
  return docIds.some((id) => tagIds.includes(id));
};

