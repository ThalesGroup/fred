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
 * Pure logic for the Simple capabilities view (#2220): derive each pack's
 * on/off + available state from the form's capability selection, and compute
 * the new selection when a pack is toggled.
 *
 * The only subtle part is the two resource packs sharing `document_access`,
 * whose config is computed from their combination (see the truth table in
 * `toolPacks.ts`). Everything else is a plain add/remove of capability ids.
 *
 * These functions are pure and side-effect free so they can be unit-tested
 * against the truth table without React.
 */

import {
  CAP_DOCUMENT_ACCESS,
  CAP_DOCUMENT_SUMMARIZE,
  CAP_FILESYSTEM,
  CAP_TABULAR,
  DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY,
  DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL,
  type ToolPack,
} from "./toolPacks";

/** The slice of agent-form state the Simple view reads and writes. Mirrors the
 *  fields already held by `AgentFormBody` — no new storage. */
export interface CapabilitySelectionState {
  selectedCapabilityIds: string[];
  capabilityConfigValues: Record<string, Record<string, unknown>>;
  reasoningEnabled: boolean;
}

/** Capabilities governed by the two resource packs in Simple view. Recomputed
 *  as a set from (corpus, attachments) so shared `document_summarize` is never
 *  dropped while still required by the other pack. */
const RESOURCE_PACK_CAPABILITIES = new Set<string>([
  CAP_DOCUMENT_ACCESS,
  CAP_FILESYSTEM,
  CAP_TABULAR,
  CAP_DOCUMENT_SUMMARIZE,
]);

function documentAccessSelected(state: CapabilitySelectionState): boolean {
  return state.selectedCapabilityIds.includes(CAP_DOCUMENT_ACCESS);
}

/** Corpus is reachable when document_access is on and NOT pinned to
 *  attachments-only (default `search_attachments_only` is false). */
function corpusOn(state: CapabilitySelectionState): boolean {
  if (!documentAccessSelected(state)) return false;
  return state.capabilityConfigValues[CAP_DOCUMENT_ACCESS]?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY] !== true;
}

/** Files can be attached when document_access is on and the attach-files
 *  control is shown. */
function attachmentsOn(state: CapabilitySelectionState): boolean {
  if (!documentAccessSelected(state)) return false;
  return state.capabilityConfigValues[CAP_DOCUMENT_ACCESS]?.[DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL] === true;
}

/**
 * Recompute the resource-pack-owned capabilities for a target (corpus,
 * attachments) combination, preserving every other selected capability and all
 * config for non-resource capabilities. This is the single place the
 * `document_access` truth table is enforced.
 */
function withResourceState(
  state: CapabilitySelectionState,
  nextCorpus: boolean,
  nextAttachments: boolean,
  availableIds: ReadonlySet<string>,
): CapabilitySelectionState {
  // Keep everything the resource packs don't own (word/ppt/reasoning + any
  // capability enabled directly in the Advanced view).
  const ids = state.selectedCapabilityIds.filter((id) => !RESOURCE_PACK_CAPABILITIES.has(id));

  const add = (id: string, wanted: boolean) => {
    if (wanted && availableIds.has(id)) ids.push(id);
  };
  add(CAP_FILESYSTEM, nextCorpus);
  add(CAP_TABULAR, nextCorpus);
  // Summarize is shared by both resource packs: on when either is on.
  add(CAP_DOCUMENT_SUMMARIZE, nextCorpus || nextAttachments);

  const capabilityConfigValues = { ...state.capabilityConfigValues };
  if ((nextCorpus || nextAttachments) && availableIds.has(CAP_DOCUMENT_ACCESS)) {
    ids.push(CAP_DOCUMENT_ACCESS);
    capabilityConfigValues[CAP_DOCUMENT_ACCESS] = {
      ...(capabilityConfigValues[CAP_DOCUMENT_ACCESS] ?? {}),
      // attachments-only only when attachments are on WITHOUT corpus.
      [DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]: nextAttachments && !nextCorpus,
      [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: nextAttachments,
    };
  }

  return { ...state, selectedCapabilityIds: ids, capabilityConfigValues };
}

/** Is the pack currently active, derived from the underlying selection so the
 *  Simple and Advanced views stay in sync automatically. */
export function derivePackChecked(pack: ToolPack, state: CapabilitySelectionState): boolean {
  if (pack.kind === "reasoning") return state.reasoningEnabled;
  if (pack.documentAccessIntent === "corpus") return corpusOn(state);
  if (pack.documentAccessIntent === "attachments") return attachmentsOn(state);
  // Plain packs (word/ppt): on when their capability id is selected.
  return (
    pack.enablesCapabilityIds.length > 0 &&
    pack.enablesCapabilityIds.every((id) => state.selectedCapabilityIds.includes(id))
  );
}

/** Compute the new selection state when a pack switch is flipped. Only touches
 *  what the pack owns; everything else is preserved. */
export function applyPackToggle(
  pack: ToolPack,
  nextOn: boolean,
  state: CapabilitySelectionState,
  availableIds: ReadonlySet<string>,
): CapabilitySelectionState {
  if (pack.kind === "reasoning") {
    return { ...state, reasoningEnabled: nextOn };
  }

  if (pack.documentAccessIntent) {
    const nextCorpus = pack.documentAccessIntent === "corpus" ? nextOn : corpusOn(state);
    const nextAttachments = pack.documentAccessIntent === "attachments" ? nextOn : attachmentsOn(state);
    return withResourceState(state, nextCorpus, nextAttachments, availableIds);
  }

  // Plain packs (word/ppt): add/remove the pack's available capability ids.
  const ids = new Set(state.selectedCapabilityIds);
  for (const id of pack.enablesCapabilityIds) {
    if (nextOn) {
      if (availableIds.has(id)) ids.add(id);
    } else {
      ids.delete(id);
    }
  }
  return { ...state, selectedCapabilityIds: [...ids] };
}

/** Tri-state of an included capability, driving its badge in the pack card. */
export type IncludedCapabilityStatus = "active" | "inactive" | "unavailable";

/**
 * Status of one included capability:
 * - `unavailable`: the platform admin has not enabled it for the team (can't be
 *   activated) — feeds the pack's "missing capabilities" flag;
 * - `active`: admin-enabled AND currently selected on the agent;
 * - `inactive`: admin-enabled but not selected (e.g. turned off in the Advanced
 *   view) — available, just not on. This is why the badge reads the live
 *   selection, not only admin availability.
 */
export function includedCapabilityStatus(
  capabilityId: string,
  availableIds: ReadonlySet<string>,
  activeIds: ReadonlySet<string>,
): IncludedCapabilityStatus {
  if (!availableIds.has(capabilityId)) return "unavailable";
  return activeIds.has(capabilityId) ? "active" : "inactive";
}
