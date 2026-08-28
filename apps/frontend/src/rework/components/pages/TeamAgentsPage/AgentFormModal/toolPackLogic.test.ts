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
  includedCapabilityStatus,
  type CapabilitySelectionState,
} from "./toolPackLogic";
import {
  CAP_DOCUMENT_ACCESS,
  CAP_DOCUMENT_SUMMARIZE,
  CAP_PPT_FILLER,
  CAP_TABULAR,
  CAP_WRITABLE_DOCUMENT,
  DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY,
  DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL,
  TOOL_PACK_SECTIONS,
  type ToolPack,
} from "./toolPacks";

// --- helpers ---------------------------------------------------------------

function packById(id: string): ToolPack {
  const pack = TOOL_PACK_SECTIONS.flatMap((s) => s.packs).find((p) => p.id === id);
  if (!pack) throw new Error(`unknown pack ${id}`);
  return pack;
}

const TEAM_RESOURCES = packById("team_resources");
const ATTACHMENTS = packById("conversation_attachments");
const WORD = packById("word_document");
const PPT = packById("powerpoint_document");
const REASONING = packById("reasoning");

const DOCUMENT_READING = packById("document_reading");

const ALL_IDS: ReadonlySet<string> = new Set([
  CAP_DOCUMENT_ACCESS,
  CAP_DOCUMENT_SUMMARIZE,
  CAP_TABULAR,
  CAP_WRITABLE_DOCUMENT,
  CAP_PPT_FILLER,
  ...DOCUMENT_READING.enablesCapabilityIds,
]);

function empty(): CapabilitySelectionState {
  return { selectedCapabilityIds: [], capabilityConfigValues: {}, reasoningEnabled: false };
}

function docConfig(state: CapabilitySelectionState) {
  return state.capabilityConfigValues[CAP_DOCUMENT_ACCESS];
}

// --- document_access truth table ------------------------------------------

describe("resource packs — document_access truth table", () => {
  it("team resources only → corpus, no attach, corpus scope", () => {
    const s = applyPackToggle(TEAM_RESOURCES, true, empty(), ALL_IDS);
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_ACCESS);
    expect(s.selectedCapabilityIds).toEqual(expect.arrayContaining([CAP_TABULAR, CAP_DOCUMENT_SUMMARIZE]));
    expect(docConfig(s)?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]).toBe(false);
    expect(docConfig(s)?.[DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]).toBe(false);
    expect(derivePackChecked(TEAM_RESOURCES, s, ALL_IDS)).toBe(true);
    expect(derivePackChecked(ATTACHMENTS, s, ALL_IDS)).toBe(false);
  });

  it("attachments only → no corpus, attach on, attachments-only scope", () => {
    const s = applyPackToggle(ATTACHMENTS, true, empty(), ALL_IDS);
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_ACCESS);
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_SUMMARIZE);
    expect(s.selectedCapabilityIds).not.toContain(CAP_TABULAR);
    expect(docConfig(s)?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]).toBe(true);
    expect(docConfig(s)?.[DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]).toBe(true);
    expect(derivePackChecked(TEAM_RESOURCES, s, ALL_IDS)).toBe(false);
    expect(derivePackChecked(ATTACHMENTS, s, ALL_IDS)).toBe(true);
  });

  it("both on → corpus + attach, corpus scope wins over attachments-only", () => {
    let s = applyPackToggle(TEAM_RESOURCES, true, empty(), ALL_IDS);
    s = applyPackToggle(ATTACHMENTS, true, s, ALL_IDS);
    expect(docConfig(s)?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]).toBe(false);
    expect(docConfig(s)?.[DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]).toBe(true);
    expect(derivePackChecked(TEAM_RESOURCES, s, ALL_IDS)).toBe(true);
    expect(derivePackChecked(ATTACHMENTS, s, ALL_IDS)).toBe(true);
  });

  it("both off → document_access removed entirely", () => {
    const s = applyPackToggle(TEAM_RESOURCES, false, applyPackToggle(TEAM_RESOURCES, true, empty(), ALL_IDS), ALL_IDS);
    expect(s.selectedCapabilityIds).not.toContain(CAP_DOCUMENT_ACCESS);
    expect(s.selectedCapabilityIds).not.toContain(CAP_TABULAR);
    expect(s.selectedCapabilityIds).not.toContain(CAP_DOCUMENT_SUMMARIZE);
    expect(derivePackChecked(TEAM_RESOURCES, s, ALL_IDS)).toBe(false);
    expect(derivePackChecked(ATTACHMENTS, s, ALL_IDS)).toBe(false);
  });
});

describe("resource packs — shared summarize + mode transitions", () => {
  it("turning team resources OFF while attachments ON keeps summarize and flips to attachments-only", () => {
    let s = applyPackToggle(TEAM_RESOURCES, true, empty(), ALL_IDS);
    s = applyPackToggle(ATTACHMENTS, true, s, ALL_IDS); // both on
    s = applyPackToggle(TEAM_RESOURCES, false, s, ALL_IDS); // team off, attachments still on
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_ACCESS);
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_SUMMARIZE); // shared, must stay
    expect(s.selectedCapabilityIds).not.toContain(CAP_TABULAR); // team-only, removed
    expect(docConfig(s)?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]).toBe(true);
    expect(docConfig(s)?.[DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]).toBe(true);
  });

  it("turning attachments OFF while team resources ON keeps corpus and drops the attach control", () => {
    let s = applyPackToggle(TEAM_RESOURCES, true, empty(), ALL_IDS);
    s = applyPackToggle(ATTACHMENTS, true, s, ALL_IDS); // both on
    s = applyPackToggle(ATTACHMENTS, false, s, ALL_IDS); // attachments off, team still on
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_ACCESS);
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_SUMMARIZE);
    expect(docConfig(s)?.[DOC_ACCESS_SEARCH_ATTACHMENTS_ONLY]).toBe(false);
    expect(docConfig(s)?.[DOC_ACCESS_SHOW_ATTACH_FILES_CONTROL]).toBe(false);
  });
});

describe("admin availability — activate available, ignore the rest", () => {
  const NO_TABULAR: ReadonlySet<string> = new Set([...ALL_IDS].filter((id) => id !== CAP_TABULAR));

  it("skips an unavailable included capability but still activates the pack", () => {
    const s = applyPackToggle(TEAM_RESOURCES, true, empty(), NO_TABULAR);
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_ACCESS);
    expect(s.selectedCapabilityIds).toContain(CAP_DOCUMENT_SUMMARIZE);
    expect(s.selectedCapabilityIds).not.toContain(CAP_TABULAR); // admin-disabled, skipped
    expect(derivePackChecked(TEAM_RESOURCES, s, ALL_IDS)).toBe(true);
  });
});

describe("includedCapabilityStatus — badge tri-state reflects live selection", () => {
  it("unavailable when the admin has not enabled it, regardless of selection", () => {
    expect(includedCapabilityStatus(CAP_TABULAR, new Set(), new Set([CAP_TABULAR]))).toBe("unavailable");
  });

  it("active when admin-enabled AND selected", () => {
    expect(includedCapabilityStatus(CAP_DOCUMENT_SUMMARIZE, ALL_IDS, new Set([CAP_DOCUMENT_SUMMARIZE]))).toBe("active");
  });

  it("inactive when admin-enabled but NOT selected (e.g. turned off in Advanced)", () => {
    // The reported case: summarize is admin-enabled but the user deselected it,
    // so it must read inactive (grey), never active (green).
    expect(includedCapabilityStatus(CAP_DOCUMENT_SUMMARIZE, ALL_IDS, new Set([CAP_DOCUMENT_ACCESS]))).toBe("inactive");
  });
});

describe("plain packs (word / ppt) and reasoning", () => {
  it("word/ppt toggle just add/remove their capability id", () => {
    let s = applyPackToggle(WORD, true, empty(), ALL_IDS);
    expect(s.selectedCapabilityIds).toEqual([CAP_WRITABLE_DOCUMENT]);
    expect(derivePackChecked(WORD, s, ALL_IDS)).toBe(true);
    s = applyPackToggle(PPT, true, s, ALL_IDS);
    expect(s.selectedCapabilityIds).toEqual(expect.arrayContaining([CAP_WRITABLE_DOCUMENT, CAP_PPT_FILLER]));
    s = applyPackToggle(WORD, false, s, ALL_IDS);
    expect(s.selectedCapabilityIds).toEqual([CAP_PPT_FILLER]);
  });

  it("reasoning pack toggles the reasoningEnabled field", () => {
    const on = applyPackToggle(REASONING, true, empty(), ALL_IDS);
    expect(on.reasoningEnabled).toBe(true);
    expect(derivePackChecked(REASONING, on, ALL_IDS)).toBe(true);
    const off = applyPackToggle(REASONING, false, on, ALL_IDS);
    expect(off.reasoningEnabled).toBe(false);
  });

  it("toggling a resource pack preserves unrelated selections (word/ppt/reasoning)", () => {
    let s = applyPackToggle(WORD, true, empty(), ALL_IDS);
    s = applyPackToggle(REASONING, true, s, ALL_IDS);
    s = applyPackToggle(TEAM_RESOURCES, true, s, ALL_IDS);
    expect(s.selectedCapabilityIds).toContain(CAP_WRITABLE_DOCUMENT);
    expect(s.reasoningEnabled).toBe(true);
    s = applyPackToggle(TEAM_RESOURCES, false, s, ALL_IDS);
    expect(s.selectedCapabilityIds).toContain(CAP_WRITABLE_DOCUMENT); // untouched
    expect(s.reasoningEnabled).toBe(true);
  });
});

// --- partial admin availability -------------------------------------------

describe("plain packs — partial admin availability", () => {
  it("stays on when only the admin-enabled members are selectable", () => {
    // The upgrade case: a new capability joins an existing pack and no team has
    // it enabled yet. Before availability was part of the derivation, the switch
    // flipped on, failed to add the unavailable member, and read back as off.
    const partial: ReadonlySet<string> = new Set(DOCUMENT_READING.enablesCapabilityIds.slice(0, -1));

    const s = applyPackToggle(DOCUMENT_READING, true, empty(), partial);

    expect(derivePackChecked(DOCUMENT_READING, s, partial)).toBe(true);
    expect(s.selectedCapabilityIds).toEqual([...partial]);
  });

  it("is off when nothing in the pack is admin-enabled", () => {
    const none: ReadonlySet<string> = new Set<string>();

    const s = applyPackToggle(DOCUMENT_READING, true, empty(), none);

    expect(derivePackChecked(DOCUMENT_READING, s, none)).toBe(false);
  });

  it("turning it off still clears every member, available or not", () => {
    const on = applyPackToggle(DOCUMENT_READING, true, empty(), ALL_IDS);

    const off = applyPackToggle(DOCUMENT_READING, false, on, ALL_IDS);

    expect(off.selectedCapabilityIds).toEqual([]);
  });
});
