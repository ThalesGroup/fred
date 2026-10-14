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
  derivePackChecked,
  applyDocumentAccessConfigChange,
  includedCapabilityStatus,
  isPackSelectable,
  normalizeDocumentAccessConfig,
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
  TOOL_PACK_SECTIONS,
  type ToolPack,
} from "./toolPacks";

function packById(id: string): ToolPack {
  const pack = TOOL_PACK_SECTIONS.flatMap((section) => section.packs).find((item) => item.id === id);
  if (!pack) throw new Error(`unknown pack ${id}`);
  return pack;
}

const ATTACHMENTS = packById("attachments");
const TEAM_DOCUMENTS = packById("team_documents");
const WORD = packById("word_document");
const PPT = packById("powerpoint_document");
const SHARED_IDS = [
  CAP_DOCUMENT_ACCESS,
  CAP_TABULAR,
  CAP_DOCUMENT_SUMMARIZE,
  CAP_DOCUMENT_VERBATIM,
  CAP_DOCUMENT_EXTRACT,
];
const TEAM_DOCUMENT_IDS = [...SHARED_IDS, CAP_DOCUMENT_SIMILARITY];
const ALL_IDS: ReadonlySet<string> = new Set([
  ...TEAM_DOCUMENT_IDS,
  CAP_TEAM_WIKI,
  CAP_WRITABLE_DOCUMENT,
  CAP_PPT_FILLER,
]);

function empty(): CapabilitySelectionState {
  return { selectedCapabilityIds: [], capabilityConfigValues: {} };
}

function sources(state: CapabilitySelectionState) {
  const config = state.capabilityConfigValues[CAP_DOCUMENT_ACCESS];
  return { attachments: config?.attachments, team_documents: config?.team_documents };
}

function sorted(ids: string[]): string[] {
  return [...ids].sort();
}

describe("document pack registry", () => {
  it("offers Attachments and Team documents instead of one resource card", () => {
    const section = TOOL_PACK_SECTIONS.find((item) => item.id === "data_knowledge");
    const ids = section?.packs.map((pack) => pack.id);
    expect(ids).toEqual(["attachments", "team_documents", "team_wiki"]);
    expect(ATTACHMENTS.documentSource).toBe("attachments");
    expect(TEAM_DOCUMENTS.documentSource).toBe("team_documents");
  });

  it("lists every granted capability, similarity under Team documents only", () => {
    expect(sorted(ATTACHMENTS.enablesCapabilityIds)).toEqual(sorted(SHARED_IDS));
    expect(sorted(ATTACHMENTS.includes.map((entry) => entry.capabilityId))).toEqual(sorted(SHARED_IDS));
    expect(sorted(TEAM_DOCUMENTS.enablesCapabilityIds)).toEqual(sorted(TEAM_DOCUMENT_IDS));
    expect(sorted(TEAM_DOCUMENTS.includes.map((entry) => entry.capabilityId))).toEqual(sorted(TEAM_DOCUMENT_IDS));
  });
});

describe("document packs", () => {
  it("turns on attachments alone, without similarity", () => {
    const state = applyPackToggle(ATTACHMENTS, true, empty(), ALL_IDS);
    expect(sorted(state.selectedCapabilityIds)).toEqual(sorted(SHARED_IDS));
    expect(sources(state)).toEqual({ attachments: true, team_documents: false });
    expect(derivePackChecked(ATTACHMENTS, state, ALL_IDS)).toBe(true);
    expect(derivePackChecked(TEAM_DOCUMENTS, state, ALL_IDS)).toBe(false);
  });

  it("turns on team documents alone, with similarity", () => {
    const state = applyPackToggle(TEAM_DOCUMENTS, true, empty(), ALL_IDS);
    expect(sorted(state.selectedCapabilityIds)).toEqual(sorted(TEAM_DOCUMENT_IDS));
    expect(sources(state)).toEqual({ attachments: false, team_documents: true });
    expect(derivePackChecked(ATTACHMENTS, state, ALL_IDS)).toBe(false);
    expect(derivePackChecked(TEAM_DOCUMENTS, state, ALL_IDS)).toBe(true);
  });

  it("turns on both sources when both packs are on", () => {
    let state = applyPackToggle(ATTACHMENTS, true, empty(), ALL_IDS);
    state = applyPackToggle(TEAM_DOCUMENTS, true, state, ALL_IDS);
    expect(sources(state)).toEqual({ attachments: true, team_documents: true });
    expect(sorted(state.selectedCapabilityIds)).toEqual(sorted(TEAM_DOCUMENT_IDS));
  });

  it("keeps the shared members when attachments goes off and team documents stays", () => {
    let state = applyPackToggle(ATTACHMENTS, true, empty(), ALL_IDS);
    state = applyPackToggle(TEAM_DOCUMENTS, true, state, ALL_IDS);
    state = applyPackToggle(ATTACHMENTS, false, state, ALL_IDS);
    expect(sorted(state.selectedCapabilityIds)).toEqual(sorted(TEAM_DOCUMENT_IDS));
    expect(sources(state)).toEqual({ attachments: false, team_documents: true });
  });

  it("withdraws only similarity when team documents goes off and attachments stays", () => {
    let state = applyPackToggle(TEAM_DOCUMENTS, true, empty(), ALL_IDS);
    state = applyPackToggle(ATTACHMENTS, true, state, ALL_IDS);
    state = applyPackToggle(TEAM_DOCUMENTS, false, state, ALL_IDS);
    expect(sorted(state.selectedCapabilityIds)).toEqual(sorted(SHARED_IDS));
    expect(sources(state)).toEqual({ attachments: true, team_documents: false });
  });

  it("deselects document access and its members when the last pack goes off, keeping the config", () => {
    const seeded: CapabilitySelectionState = {
      ...empty(),
      selectedCapabilityIds: [CAP_TEAM_WIKI],
      capabilityConfigValues: { [CAP_TEAM_WIKI]: { mode: "read" } },
    };
    let state = applyPackToggle(TEAM_DOCUMENTS, true, seeded, ALL_IDS);
    state = {
      ...state,
      capabilityConfigValues: {
        ...state.capabilityConfigValues,
        [CAP_DOCUMENT_ACCESS]: { ...state.capabilityConfigValues[CAP_DOCUMENT_ACCESS], library_tag_ids: ["lib-1"] },
      },
    };
    state = applyPackToggle(TEAM_DOCUMENTS, false, state, ALL_IDS);

    expect(state.selectedCapabilityIds).toEqual([CAP_TEAM_WIKI]);
    expect(state.capabilityConfigValues[CAP_TEAM_WIKI]).toEqual({ mode: "read" });
    // No both-off config: the capability is deselected, both sources reset, library scope kept.
    expect(state.capabilityConfigValues[CAP_DOCUMENT_ACCESS]).toMatchObject({
      attachments: true,
      team_documents: true,
      library_tag_ids: ["lib-1"],
    });
    expect(derivePackChecked(TEAM_DOCUMENTS, state, ALL_IDS)).toBe(false);

    state = applyPackToggle(TEAM_DOCUMENTS, true, state, ALL_IDS);
    expect(state.capabilityConfigValues[CAP_DOCUMENT_ACCESS]).toMatchObject({ library_tag_ids: ["lib-1"] });
  });

  it("skips members the team cannot use", () => {
    const available = new Set([CAP_DOCUMENT_ACCESS, CAP_DOCUMENT_VERBATIM]);
    const state = applyPackToggle(TEAM_DOCUMENTS, true, empty(), available);
    expect(sorted(state.selectedCapabilityIds)).toEqual(sorted([CAP_DOCUMENT_ACCESS, CAP_DOCUMENT_VERBATIM]));
    expect(derivePackChecked(TEAM_DOCUMENTS, state, available)).toBe(true);
  });

  it("cannot be selected without document access", () => {
    const available = new Set([CAP_DOCUMENT_SUMMARIZE, CAP_DOCUMENT_VERBATIM]);
    expect(isPackSelectable(ATTACHMENTS, available)).toBe(false);
    expect(isPackSelectable(TEAM_DOCUMENTS, available)).toBe(false);
    expect(applyPackToggle(ATTACHMENTS, true, empty(), available)).toEqual(empty());
  });

  it("stays on when only a shared capability is cleared in Advanced", () => {
    let state = applyPackToggle(ATTACHMENTS, true, empty(), ALL_IDS);
    state = {
      ...state,
      selectedCapabilityIds: state.selectedCapabilityIds.filter((id) => id !== CAP_DOCUMENT_SUMMARIZE),
    };
    expect(derivePackChecked(ATTACHMENTS, state, ALL_IDS)).toBe(true);
    expect(includedCapabilityStatus(CAP_DOCUMENT_SUMMARIZE, ALL_IDS, new Set(state.selectedCapabilityIds))).toBe(
      "inactive",
    );
  });

  it("reads both packs off once document access is cleared in Advanced", () => {
    let state = applyPackToggle(ATTACHMENTS, true, empty(), ALL_IDS);
    state = applyPackToggle(TEAM_DOCUMENTS, true, state, ALL_IDS);
    state = { ...state, selectedCapabilityIds: state.selectedCapabilityIds.filter((id) => id !== CAP_DOCUMENT_ACCESS) };
    expect(derivePackChecked(ATTACHMENTS, state, ALL_IDS)).toBe(false);
    expect(derivePackChecked(TEAM_DOCUMENTS, state, ALL_IDS)).toBe(false);
  });

  it("reads an absent source as on, the backend default", () => {
    const state = { ...empty(), selectedCapabilityIds: [CAP_DOCUMENT_ACCESS] };
    expect(derivePackChecked(ATTACHMENTS, state, ALL_IDS)).toBe(true);
    expect(derivePackChecked(TEAM_DOCUMENTS, state, ALL_IDS)).toBe(true);
  });
});

describe("normalizeDocumentAccessConfig", () => {
  it.each([
    [{ show_attach_files_control: false }, { attachments: false, team_documents: true }],
    [
      { show_attach_files_control: false, search_attachments_only: true },
      { attachments: false, team_documents: true },
    ],
    [
      { show_attach_files_control: true, search_attachments_only: true },
      { attachments: true, team_documents: false },
    ],
    [
      { show_attach_files_control: true, search_attachments_only: false },
      { attachments: true, team_documents: true },
    ],
    [{ search_attachments_only: true }, { attachments: true, team_documents: false }],
  ])("maps legacy %o", (legacy, expected) => {
    expect(normalizeDocumentAccessConfig({ ...legacy, bind_libraries: true })).toEqual({
      ...expected,
      bind_libraries: true,
    });
  });

  it("lets the new keys win over leftover legacy keys", () => {
    expect(normalizeDocumentAccessConfig({ team_documents: false, search_attachments_only: false })).toEqual({
      team_documents: false,
    });
  });

  it("leaves a config without legacy keys untouched", () => {
    const config = { bind_libraries: false };
    expect(normalizeDocumentAccessConfig(config)).toBe(config);
  });

  it("shows a legacy attachments-only agent with Attachments on and Team documents off", () => {
    const state: CapabilitySelectionState = {
      ...empty(),
      selectedCapabilityIds: [CAP_DOCUMENT_ACCESS, CAP_DOCUMENT_SUMMARIZE],
      capabilityConfigValues: {
        [CAP_DOCUMENT_ACCESS]: normalizeDocumentAccessConfig({
          show_attach_files_control: true,
          search_attachments_only: true,
        }),
      },
    };
    expect(derivePackChecked(ATTACHMENTS, state, ALL_IDS)).toBe(true);
    expect(derivePackChecked(TEAM_DOCUMENTS, state, ALL_IDS)).toBe(false);
  });
});

describe("applyDocumentAccessConfigChange", () => {
  const selected = (config: Record<string, unknown>) => ({
    selectedCapabilityIds: [CAP_DOCUMENT_ACCESS, "other"],
    capabilityConfigValues: { [CAP_DOCUMENT_ACCESS]: config },
  });

  it("keeps the capability while a source stays on", () => {
    const next = applyDocumentAccessConfigChange(
      selected({ attachments: true, team_documents: true }),
      "attachments",
      false,
    );
    expect(next.selectedCapabilityIds).toContain(CAP_DOCUMENT_ACCESS);
    expect(next.capabilityConfigValues[CAP_DOCUMENT_ACCESS]).toMatchObject({
      attachments: false,
      team_documents: true,
    });
  });

  it("deselects the capability when the last source goes off, and resets both sources", () => {
    const next = applyDocumentAccessConfigChange(
      selected({ attachments: false, team_documents: true, bind_libraries: true }),
      "team_documents",
      false,
    );
    expect(next.selectedCapabilityIds).toEqual(["other"]);
    expect(next.capabilityConfigValues[CAP_DOCUMENT_ACCESS]).toEqual({
      attachments: true,
      team_documents: true,
      bind_libraries: true,
    });
  });
});

describe("plain packs and included capability status", () => {
  it("keeps word and PowerPoint independent", () => {
    let state = applyPackToggle(WORD, true, empty(), ALL_IDS);
    state = applyPackToggle(PPT, true, state, ALL_IDS);
    expect(state.selectedCapabilityIds).toEqual([CAP_WRITABLE_DOCUMENT, CAP_PPT_FILLER]);

    state = applyPackToggle(WORD, false, state, ALL_IDS);
    expect(state.selectedCapabilityIds).toEqual([CAP_PPT_FILLER]);
    expect(derivePackChecked(PPT, state, ALL_IDS)).toBe(true);
  });

  it("reads active, inactive, and unavailable from live selection and availability", () => {
    expect(includedCapabilityStatus(CAP_DOCUMENT_ACCESS, ALL_IDS, new Set([CAP_DOCUMENT_ACCESS]))).toBe("active");
    expect(includedCapabilityStatus(CAP_DOCUMENT_ACCESS, ALL_IDS, new Set())).toBe("inactive");
    expect(includedCapabilityStatus(CAP_DOCUMENT_ACCESS, new Set(), new Set([CAP_DOCUMENT_ACCESS]))).toBe(
      "unavailable",
    );
  });
});
