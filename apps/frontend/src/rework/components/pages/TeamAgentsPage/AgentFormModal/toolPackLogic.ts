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

/** Pure selection logic shared by the Simple pack switches. */

import {
  CAP_DOCUMENT_ACCESS,
  CAP_DOCUMENT_SIMILARITY,
  CAP_TABULAR,
  DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY,
  DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL,
  type ToolPack,
} from "./toolPacks";

/** The agent-form fields used by the Simple pack switches. */
export interface CapabilitySelectionState {
  selectedCapabilityIds: string[];
  capabilityConfigValues: Record<string, Record<string, unknown>>;
  reasoningEnabled: boolean;
}

const CORPUS_ONLY_IDS = [CAP_DOCUMENT_SIMILARITY];

/** Hide a pack if its switch cannot enable anything for this team. */
export function isPackSelectable(pack: ToolPack, availableIds: ReadonlySet<string>): boolean {
  if (pack.kind === "reasoning") return true;
  if (pack.resourceBundle) return availableIds.has(CAP_DOCUMENT_ACCESS);
  return pack.enablesCapabilityIds.some((id) => availableIds.has(id));
}

/** Read a pack's switch from the current selection, including Advanced edits. */
export function derivePackChecked(
  pack: ToolPack,
  state: CapabilitySelectionState,
  availableIds: ReadonlySet<string>,
): boolean {
  if (pack.kind === "reasoning") return state.reasoningEnabled;

  const selectable = pack.enablesCapabilityIds.filter((id) => availableIds.has(id));
  const membersSelected = selectable.length > 0 && selectable.every((id) => state.selectedCapabilityIds.includes(id));
  if (!pack.resourceBundle) return membersSelected;

  const config = state.capabilityConfigValues[CAP_DOCUMENT_ACCESS];
  if (!availableIds.has(CAP_DOCUMENT_ACCESS) || config?.[DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL] !== true) return false;

  const searchAttachmentsOnly = config?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY] === true;
  if (!searchAttachmentsOnly) return membersSelected;

  return (
    selectable
      .filter((id) => !CORPUS_ONLY_IDS.includes(id) && id !== CAP_TABULAR)
      .every((id) => state.selectedCapabilityIds.includes(id)) &&
    CORPUS_ONLY_IDS.every((id) => !state.selectedCapabilityIds.includes(id))
  );
}

/** Toggle a pack's available members while preserving unrelated selections. */
export function applyPackToggle(
  pack: ToolPack,
  nextOn: boolean,
  state: CapabilitySelectionState,
  availableIds: ReadonlySet<string>,
): CapabilitySelectionState {
  if (pack.kind === "reasoning") {
    return { ...state, reasoningEnabled: nextOn };
  }
  if (pack.resourceBundle && nextOn && !availableIds.has(CAP_DOCUMENT_ACCESS)) return state;

  const ids = new Set(state.selectedCapabilityIds);
  for (const id of pack.enablesCapabilityIds) {
    if (nextOn) {
      if (availableIds.has(id)) ids.add(id);
    } else {
      ids.delete(id);
    }
  }

  if (pack.resourceBundle && nextOn) {
    return {
      ...state,
      selectedCapabilityIds: [...ids],
      capabilityConfigValues: {
        ...state.capabilityConfigValues,
        [CAP_DOCUMENT_ACCESS]: {
          ...state.capabilityConfigValues[CAP_DOCUMENT_ACCESS],
          [DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]: false,
          [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: true,
        },
      },
    };
  }
  return { ...state, selectedCapabilityIds: [...ids] };
}

/** Switch the active Simple pack between corpus plus attachments and attachments only. */
export function applyResourceSearchScope(
  searchAttachmentsOnly: boolean,
  state: CapabilitySelectionState,
  availableIds: ReadonlySet<string>,
): CapabilitySelectionState {
  const ids = new Set(state.selectedCapabilityIds);
  if (availableIds.has(CAP_TABULAR)) ids.add(CAP_TABULAR);
  for (const id of CORPUS_ONLY_IDS) {
    if (searchAttachmentsOnly) ids.delete(id);
    else if (availableIds.has(id)) ids.add(id);
  }
  return {
    ...state,
    selectedCapabilityIds: [...ids],
    capabilityConfigValues: {
      ...state.capabilityConfigValues,
      [CAP_DOCUMENT_ACCESS]: {
        ...state.capabilityConfigValues[CAP_DOCUMENT_ACCESS],
        [DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]: searchAttachmentsOnly,
        [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: true,
      },
    },
  };
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
