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
  DOC_ACCESS_ATTACHMENTS,
  DOC_ACCESS_TEAM_DOCUMENTS,
  TOOL_PACK_SECTIONS,
  type DocumentSource,
  type ToolPack,
} from "./toolPacks";

/** The agent-form fields used by the Simple pack switches. */
export interface CapabilitySelectionState {
  selectedCapabilityIds: string[];
  capabilityConfigValues: Record<string, Record<string, unknown>>;
  reasoningEnabled: boolean;
}

const DOCUMENT_PACKS = TOOL_PACK_SECTIONS.flatMap((section) => section.packs).filter((pack) => pack.documentSource);

/** A source absent from the config is on, the backend default. */
function sourceOn(config: Record<string, unknown> | undefined, source: DocumentSource): boolean {
  return config?.[source] !== false;
}

/**
 * Read legacy `document_access` keys as the two sources, mirroring the backend
 * before-validator. Only key names change, so no access is granted on load.
 */
export function normalizeDocumentAccessConfig(config: Record<string, unknown>): Record<string, unknown> {
  const { show_attach_files_control: paperclip, search_attachments_only: onlyAttached, ...rest } = config;
  if (paperclip === undefined && onlyAttached === undefined) return config;
  if (DOC_ACCESS_ATTACHMENTS in rest || DOC_ACCESS_TEAM_DOCUMENTS in rest) return rest;
  const attachments = paperclip === undefined || Boolean(paperclip);
  return {
    ...rest,
    [DOC_ACCESS_ATTACHMENTS]: attachments,
    [DOC_ACCESS_TEAM_DOCUMENTS]: !(attachments && Boolean(onlyAttached)),
  };
}

/** Both sources off is rejected by the backend, so the form blocks Save. */
export function documentAccessHasNoSource(config: Record<string, unknown> | undefined): boolean {
  return !sourceOn(config, DOC_ACCESS_ATTACHMENTS) && !sourceOn(config, DOC_ACCESS_TEAM_DOCUMENTS);
}

/** Hide a pack if its switch cannot enable anything for this team. */
export function isPackSelectable(pack: ToolPack, availableIds: ReadonlySet<string>): boolean {
  if (pack.kind === "reasoning") return true;
  if (pack.documentSource) return availableIds.has(CAP_DOCUMENT_ACCESS);
  return pack.enablesCapabilityIds.some((id) => availableIds.has(id));
}

/** Read a pack's switch from the current selection, including Advanced edits. */
export function derivePackChecked(
  pack: ToolPack,
  state: CapabilitySelectionState,
  availableIds: ReadonlySet<string>,
): boolean {
  if (pack.kind === "reasoning") return state.reasoningEnabled;
  if (pack.documentSource) {
    return (
      state.selectedCapabilityIds.includes(CAP_DOCUMENT_ACCESS) &&
      sourceOn(state.capabilityConfigValues[CAP_DOCUMENT_ACCESS], pack.documentSource)
    );
  }
  const selectable = pack.enablesCapabilityIds.filter((id) => availableIds.has(id));
  return selectable.length > 0 && selectable.every((id) => state.selectedCapabilityIds.includes(id));
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
  if (pack.documentSource) return applyDocumentPackToggle(pack, pack.documentSource, nextOn, state, availableIds);

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

/**
 * A document pack sets its own source. Shared members stay while the other pack
 * is on; turning off the last pack deselects document access rather than
 * saving both sources off. The stored config (library binding) is kept.
 */
function applyDocumentPackToggle(
  pack: ToolPack,
  source: DocumentSource,
  nextOn: boolean,
  state: CapabilitySelectionState,
  availableIds: ReadonlySet<string>,
): CapabilitySelectionState {
  const config = state.capabilityConfigValues[CAP_DOCUMENT_ACCESS] ?? {};
  const selected = state.selectedCapabilityIds.includes(CAP_DOCUMENT_ACCESS);
  const ids = new Set(state.selectedCapabilityIds);
  const withConfig = (next: Record<string, unknown>): CapabilitySelectionState => ({
    ...state,
    selectedCapabilityIds: [...ids],
    capabilityConfigValues: { ...state.capabilityConfigValues, [CAP_DOCUMENT_ACCESS]: next },
  });

  if (nextOn) {
    if (!availableIds.has(CAP_DOCUMENT_ACCESS)) return state;
    for (const id of pack.enablesCapabilityIds) if (availableIds.has(id)) ids.add(id);
    const sources = selected ? {} : { [DOC_ACCESS_ATTACHMENTS]: false, [DOC_ACCESS_TEAM_DOCUMENTS]: false };
    return withConfig({ ...config, ...sources, [source]: true });
  }

  const others = DOCUMENT_PACKS.filter(
    (other) => other !== pack && selected && other.documentSource && sourceOn(config, other.documentSource),
  );
  if (others.length > 0) {
    const kept = new Set(others.flatMap((other) => other.enablesCapabilityIds));
    for (const id of pack.enablesCapabilityIds) if (!kept.has(id)) ids.delete(id);
    return withConfig({ ...config, [source]: false });
  }
  for (const id of DOCUMENT_PACKS.flatMap((documentPack) => documentPack.enablesCapabilityIds)) ids.delete(id);
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
