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

/**
 * Build one stable key for a library-id selection list.
 *
 * Why this exists:
 * - React effects should track the semantic library set, not a fresh array identity
 * - the composer document fetch hook should not re-run just because a fallback `[]` was re-created
 *
 * How to use:
 * - pass the effective library id list used for metadata browsing
 * - use the returned string in `useMemo` / `useEffect` dependencies
 */
export function buildLibrarySelectionKey(libraryIds: string[]): string {
  return Array.from(new Set(libraryIds)).sort().join("|");
}

/**
 * Convert one stable library selection key back into ids.
 *
 * Why this exists:
 * - document fetch hooks may depend on one string key for stability
 * - callers still need the list form for browse-by-tag requests
 *
 * How to use:
 * - pass the string from `buildLibrarySelectionKey(...)`
 * - receive the original ordered ids, or `[]` for the empty key
 */
export function parseLibrarySelectionKey(libraryKey: string): string[] {
  return libraryKey ? libraryKey.split("|") : [];
}

/**
 * Keep only document UIDs that still exist in the currently visible metadata set.
 *
 * Why this exists:
 * - changing libraries can invalidate a previously selected document set
 * - reconciliation should be deterministic and easy to test without React state
 *
 * How to use:
 * - pass the current selected document uids and the currently available document uids
 * - compare the returned array with the input before mutating state
 */
export function reconcileSelectedDocumentUids(
  selectedDocumentUids: string[],
  availableDocumentUids: string[],
): string[] {
  if (selectedDocumentUids.length === 0) return selectedDocumentUids;
  const allowed = new Set(availableDocumentUids);
  return selectedDocumentUids.filter((uid) => allowed.has(uid));
}

interface DocumentScopeStateParams {
  showLibraries: boolean;
  showDocuments: boolean;
  effectiveLibraryIds: string[];
}

interface DocumentScopeState {
  hasDocumentScope: boolean;
  showSelectLibraryFirst: boolean;
  showDocumentConfigurationWarning: boolean;
}

/**
 * Derive the document-picker state from the resolved library scope.
 *
 * Why this exists:
 * - the Documents chip must stay interactive even when no document scope is available
 * - the empty-scope reason matters for UX: "pick a library" is different from "agent misconfigured"
 *
 * How to use:
 * - pass the resolved chat-option flags plus the effective library ids
 * - render the returned booleans directly inside the popover state machine
 */
export function resolveDocumentScopeState({
  showLibraries,
  showDocuments,
  effectiveLibraryIds,
}: DocumentScopeStateParams): DocumentScopeState {
  const hasDocumentScope = effectiveLibraryIds.length > 0;
  return {
    hasDocumentScope,
    showSelectLibraryFirst: showDocuments && showLibraries && !hasDocumentScope,
    showDocumentConfigurationWarning: showDocuments && !showLibraries && !hasDocumentScope,
  };
}
