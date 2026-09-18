// @vitest-environment happy-dom
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

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { rememberPanelClosed, rememberPanelOpen, wasPanelOpen } from "./capabilityPanelMemory";

// happy-dom exposes no localStorage here, so the suite brings its own: the
// module under test reads the global, and that is exactly what we exercise.
function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => {
      map.set(k, v);
    },
    removeItem: (k: string) => {
      map.delete(k);
    },
    clear: () => map.clear(),
    key: (i: number) => [...map.keys()][i] ?? null,
    get length() {
      return map.size;
    },
  } as Storage;
}

const PANEL = "writable_document:writable_document_pane";
const OTHER = "ppt_filler:ppt_preview_pane";

describe("capabilityPanelMemory", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("answers 'not open' for a conversation nothing was ever recorded for", () => {
    expect(wasPanelOpen("s1", PANEL)).toBe(false);
  });

  it("records an open panel, scoped to one conversation and one panel", () => {
    rememberPanelOpen("s1", PANEL);

    expect(wasPanelOpen("s1", PANEL)).toBe(true);
    expect(wasPanelOpen("s2", PANEL)).toBe(false);
    expect(wasPanelOpen("s1", OTHER)).toBe(false);
  });

  it("drops the record when the user closes the panel again", () => {
    rememberPanelOpen("s1", PANEL);
    rememberPanelClosed("s1", PANEL);

    expect(wasPanelOpen("s1", PANEL)).toBe(false);
  });

  it("survives a reload — the record is what restores the panel on re-entry", () => {
    rememberPanelOpen("s1", PANEL);

    expect(localStorage.getItem("capability-panel:open")).toContain("s1|" + PANEL);
  });

  it("evicts the oldest records rather than growing without bound", () => {
    for (let i = 0; i < 60; i++) rememberPanelOpen(`s${i}`, PANEL);

    expect(wasPanelOpen("s0", PANEL)).toBe(false);
    expect(wasPanelOpen("s59", PANEL)).toBe(true);
  });

  it("re-opening an already-recorded panel keeps it recent instead of duplicating it", () => {
    rememberPanelOpen("s1", PANEL);
    for (let i = 0; i < 49; i++) rememberPanelOpen(`f${i}`, PANEL);
    rememberPanelOpen("s1", PANEL);
    for (let i = 0; i < 48; i++) rememberPanelOpen(`g${i}`, PANEL);

    expect(wasPanelOpen("s1", PANEL)).toBe(true);
  });

  it("degrades to the default — closed — when storage is blocked", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    });

    expect(() => rememberPanelOpen("s1", PANEL)).not.toThrow();
    expect(wasPanelOpen("s1", PANEL)).toBe(false);
  });

  it("degrades the same way when the browser exposes no storage at all", () => {
    vi.stubGlobal("localStorage", undefined);

    expect(() => rememberPanelOpen("s1", PANEL)).not.toThrow();
    expect(wasPanelOpen("s1", PANEL)).toBe(false);
  });
});
