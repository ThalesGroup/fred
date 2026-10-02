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

import { describe, expect, it } from "vitest";
import {
  applyPackToggle,
  applyResourceSearchScope,
  derivePackChecked,
  includedCapabilityStatus,
  isPackSelectable,
  type CapabilitySelectionState,
} from "./toolPackLogic";
import {
  CAP_DOCUMENT_ACCESS,
  CAP_DOCUMENT_EXTRACT,
  CAP_DOCUMENT_SIMILARITY,
  CAP_DOCUMENT_SUMMARIZE,
  CAP_DOCUMENT_VERBATIM,
  CAP_PPT_FILLER,
  CAP_TABULAR,
  CAP_TEAM_WIKI,
  CAP_WRITABLE_DOCUMENT,
  DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY,
  DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL,
  TOOL_PACK_SECTIONS,
  type ToolPack,
} from "./toolPacks";

function packById(id: string): ToolPack {
  const pack = TOOL_PACK_SECTIONS.flatMap((section) => section.packs).find((item) => item.id === id);
  if (!pack) throw new Error(`unknown pack ${id}`);
  return pack;
}

const RESOURCES = packById("team_resources");
const WORD = packById("word_document");
const PPT = packById("powerpoint_document");
const REASONING = packById("reasoning");
const RESOURCE_IDS = [
  CAP_DOCUMENT_ACCESS,
  CAP_TABULAR,
  CAP_DOCUMENT_SUMMARIZE,
  CAP_DOCUMENT_SIMILARITY,
  CAP_DOCUMENT_VERBATIM,
  CAP_DOCUMENT_EXTRACT,
];
const ALL_IDS: ReadonlySet<string> = new Set([...RESOURCE_IDS, CAP_TEAM_WIKI, CAP_WRITABLE_DOCUMENT, CAP_PPT_FILLER]);

function empty(): CapabilitySelectionState {
  return { selectedCapabilityIds: [], capabilityConfigValues: {}, reasoningEnabled: false };
}

function docConfig(state: CapabilitySelectionState) {
  return state.capabilityConfigValues[CAP_DOCUMENT_ACCESS];
}

describe("combined resource pack", () => {
  it("replaces the attachments card while keeping the full resource capability list", () => {
    const ids = TOOL_PACK_SECTIONS.flatMap((section) => section.packs).map((pack) => pack.id);
    expect(ids).toContain("team_resources");
    expect(ids).not.toContain("conversation_attachments");
    expect(RESOURCES.enablesCapabilityIds).toEqual(RESOURCE_IDS);
    expect(RESOURCES.includes.map((entry) => entry.capabilityId)).toEqual(RESOURCE_IDS);
  });

  it("enables corpus and attachments together with every available member", () => {
    const seeded: CapabilitySelectionState = {
      ...empty(),
      selectedCapabilityIds: [CAP_TEAM_WIKI],
      capabilityConfigValues: { [CAP_DOCUMENT_ACCESS]: { restrict_to_folders: true } },
    };
    const on = applyPackToggle(RESOURCES, true, seeded, ALL_IDS);

    expect(on.selectedCapabilityIds).toEqual(expect.arrayContaining([...RESOURCE_IDS, CAP_TEAM_WIKI]));
    expect(docConfig(on)).toEqual({
      restrict_to_folders: true,
      [DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]: false,
      [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: true,
    });
    expect(derivePackChecked(RESOURCES, on, ALL_IDS)).toBe(true);
  });

  it("skips unavailable members without leaving the switch off", () => {
    const available = new Set([...ALL_IDS].filter((id) => id !== CAP_TABULAR));
    const on = applyPackToggle(RESOURCES, true, empty(), available);

    expect(on.selectedCapabilityIds).not.toContain(CAP_TABULAR);
    expect(on.selectedCapabilityIds).toContain(CAP_DOCUMENT_ACCESS);
    expect(derivePackChecked(RESOURCES, on, available)).toBe(true);
    expect(includedCapabilityStatus(CAP_TABULAR, available, new Set(on.selectedCapabilityIds))).toBe("unavailable");
  });

  it("cannot be selected without document access", () => {
    const available = new Set([...ALL_IDS].filter((id) => id !== CAP_DOCUMENT_ACCESS));
    expect(isPackSelectable(RESOURCES, available)).toBe(false);
    expect(applyPackToggle(RESOURCES, true, empty(), available)).toEqual(empty());
    expect(derivePackChecked(RESOURCES, empty(), available)).toBe(false);
  });

  it("turning off removes only bundle members and preserves unrelated state", () => {
    const on = applyPackToggle(
      RESOURCES,
      true,
      {
        ...empty(),
        selectedCapabilityIds: [CAP_TEAM_WIKI, CAP_WRITABLE_DOCUMENT],
        capabilityConfigValues: { [CAP_TEAM_WIKI]: { mode: "read" } },
        reasoningEnabled: true,
      },
      ALL_IDS,
    );
    const off = applyPackToggle(RESOURCES, false, on, ALL_IDS);

    expect(off.selectedCapabilityIds).toEqual([CAP_TEAM_WIKI, CAP_WRITABLE_DOCUMENT]);
    expect(off.capabilityConfigValues[CAP_TEAM_WIKI]).toEqual({ mode: "read" });
    expect(off.reasoningEnabled).toBe(true);
    expect(derivePackChecked(RESOURCES, off, ALL_IDS)).toBe(false);
  });

  it("shows a complete legacy attachments-only selection as an active pack", () => {
    const legacy: CapabilitySelectionState = {
      ...empty(),
      selectedCapabilityIds: [CAP_DOCUMENT_ACCESS, CAP_DOCUMENT_SUMMARIZE, CAP_DOCUMENT_VERBATIM, CAP_DOCUMENT_EXTRACT],
      capabilityConfigValues: {
        [CAP_DOCUMENT_ACCESS]: {
          [DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]: true,
          [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: true,
        },
      },
    };

    expect(derivePackChecked(RESOURCES, legacy, ALL_IDS)).toBe(true);
    expect(includedCapabilityStatus(CAP_DOCUMENT_VERBATIM, ALL_IDS, new Set(legacy.selectedCapabilityIds))).toBe(
      "active",
    );
    expect(includedCapabilityStatus(CAP_DOCUMENT_SIMILARITY, ALL_IDS, new Set(legacy.selectedCapabilityIds))).toBe(
      "inactive",
    );
    expect(legacy.selectedCapabilityIds).not.toContain(CAP_TABULAR);

    const combined = applyPackToggle(RESOURCES, true, legacy, ALL_IDS);
    expect(combined.selectedCapabilityIds).toEqual(expect.arrayContaining(RESOURCE_IDS));
    expect(docConfig(combined)?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]).toBe(false);
    expect(derivePackChecked(RESOURCES, combined, ALL_IDS)).toBe(true);

    const attachmentsOnly = applyResourceSearchScope(true, legacy, ALL_IDS);
    expect(attachmentsOnly.selectedCapabilityIds).toContain(CAP_TABULAR);
    expect(attachmentsOnly.selectedCapabilityIds).not.toContain(CAP_DOCUMENT_SIMILARITY);
  });

  it("shows legacy corpus-only and Advanced attachment overrides as partial", () => {
    const combined = applyPackToggle(RESOURCES, true, empty(), ALL_IDS);
    const corpusOnly: CapabilitySelectionState = {
      ...combined,
      capabilityConfigValues: {
        [CAP_DOCUMENT_ACCESS]: {
          ...docConfig(combined),
          [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: false,
        },
      },
    };
    expect(derivePackChecked(RESOURCES, corpusOnly, ALL_IDS)).toBe(false);
    expect(docConfig(corpusOnly)?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]).toBe(false);

    const missingReader = {
      ...combined,
      selectedCapabilityIds: combined.selectedCapabilityIds.filter((id) => id !== CAP_DOCUMENT_VERBATIM),
    };
    expect(derivePackChecked(RESOURCES, missingReader, ALL_IDS)).toBe(false);
  });

  it("keeps tabular available when switching to attachments-only search", () => {
    const full = applyPackToggle(
      RESOURCES,
      true,
      {
        ...empty(),
        selectedCapabilityIds: [CAP_TEAM_WIKI],
        capabilityConfigValues: {
          [CAP_DOCUMENT_ACCESS]: { bind_libraries: true, library_tag_ids: ["folder-1"] },
          [CAP_TEAM_WIKI]: { mode: "read" },
        },
      },
      ALL_IDS,
    );
    const attachmentsOnly = applyResourceSearchScope(true, full, ALL_IDS);

    expect(derivePackChecked(RESOURCES, attachmentsOnly, ALL_IDS)).toBe(true);
    expect(attachmentsOnly.selectedCapabilityIds).toEqual(
      expect.arrayContaining([
        CAP_DOCUMENT_ACCESS,
        CAP_TABULAR,
        CAP_DOCUMENT_SUMMARIZE,
        CAP_DOCUMENT_VERBATIM,
        CAP_DOCUMENT_EXTRACT,
        CAP_TEAM_WIKI,
      ]),
    );
    expect(attachmentsOnly.selectedCapabilityIds).not.toContain(CAP_DOCUMENT_SIMILARITY);
    expect(attachmentsOnly.capabilityConfigValues[CAP_TEAM_WIKI]).toEqual({ mode: "read" });
    expect(docConfig(attachmentsOnly)).toEqual({
      bind_libraries: true,
      library_tag_ids: ["folder-1"],
      [DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]: true,
      [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: true,
    });

    const restored = applyResourceSearchScope(false, attachmentsOnly, ALL_IDS);
    expect(restored.selectedCapabilityIds).toEqual(expect.arrayContaining(RESOURCE_IDS));
    expect(restored.selectedCapabilityIds).toContain(CAP_TEAM_WIKI);
    expect(docConfig(restored)).toEqual({
      bind_libraries: true,
      library_tag_ids: ["folder-1"],
      [DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]: false,
      [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: true,
    });
    expect(derivePackChecked(RESOURCES, restored, ALL_IDS)).toBe(true);
  });

  it("does not select tabular when unavailable to the team", () => {
    const available = new Set([...ALL_IDS].filter((id) => id !== CAP_TABULAR));
    const full = applyPackToggle(RESOURCES, true, empty(), available);
    const restored = applyResourceSearchScope(false, applyResourceSearchScope(true, full, available), available);

    expect(restored.selectedCapabilityIds).not.toContain(CAP_TABULAR);
    expect(restored.selectedCapabilityIds).toContain(CAP_DOCUMENT_SIMILARITY);
    expect(derivePackChecked(RESOURCES, restored, available)).toBe(true);
  });

  it("keeps an incomplete Advanced attachments-only selection separate", () => {
    const attachmentsOnly: CapabilitySelectionState = {
      ...empty(),
      selectedCapabilityIds: [CAP_DOCUMENT_ACCESS],
      capabilityConfigValues: {
        [CAP_DOCUMENT_ACCESS]: {
          [DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]: true,
          [DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]: true,
        },
      },
    };
    const afterUnrelatedToggle = applyPackToggle(WORD, true, attachmentsOnly, ALL_IDS);

    expect(afterUnrelatedToggle.selectedCapabilityIds).toContain(CAP_DOCUMENT_ACCESS);
    expect(afterUnrelatedToggle.selectedCapabilityIds).not.toContain(CAP_DOCUMENT_SIMILARITY);
    expect(afterUnrelatedToggle.selectedCapabilityIds).not.toContain(CAP_TABULAR);
    expect(docConfig(afterUnrelatedToggle)?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]).toBe(true);
    expect(derivePackChecked(RESOURCES, afterUnrelatedToggle, ALL_IDS)).toBe(false);

    const incompleteWithCorpusTool = {
      ...attachmentsOnly,
      selectedCapabilityIds: [CAP_DOCUMENT_ACCESS, CAP_TABULAR],
    };
    expect(derivePackChecked(RESOURCES, incompleteWithCorpusTool, ALL_IDS)).toBe(false);
  });
});

describe("plain packs and included capability status", () => {
  it("keeps word, PowerPoint, and reasoning independent", () => {
    let state = applyPackToggle(WORD, true, empty(), ALL_IDS);
    state = applyPackToggle(PPT, true, state, ALL_IDS);
    state = applyPackToggle(REASONING, true, state, ALL_IDS);
    expect(state.selectedCapabilityIds).toEqual([CAP_WRITABLE_DOCUMENT, CAP_PPT_FILLER]);
    expect(state.reasoningEnabled).toBe(true);

    state = applyPackToggle(WORD, false, state, ALL_IDS);
    expect(state.selectedCapabilityIds).toEqual([CAP_PPT_FILLER]);
    expect(derivePackChecked(PPT, state, ALL_IDS)).toBe(true);
    expect(derivePackChecked(REASONING, state, ALL_IDS)).toBe(true);
  });

  it("reads active, inactive, and unavailable from live selection and availability", () => {
    expect(includedCapabilityStatus(CAP_DOCUMENT_ACCESS, ALL_IDS, new Set([CAP_DOCUMENT_ACCESS]))).toBe("active");
    expect(includedCapabilityStatus(CAP_DOCUMENT_ACCESS, ALL_IDS, new Set())).toBe("inactive");
    expect(includedCapabilityStatus(CAP_DOCUMENT_ACCESS, new Set(), new Set([CAP_DOCUMENT_ACCESS]))).toBe(
      "unavailable",
    );
  });
});
