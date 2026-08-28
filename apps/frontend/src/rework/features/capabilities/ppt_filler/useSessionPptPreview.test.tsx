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

// Two things this state has to get right: the deck belongs to ONE conversation
// (without the stamp, a deck filled earlier lights the launcher up on a brand-new
// chat), and what the pane shows moves only on an explicit open - the pane keys
// its pdf.js worker on it, and that lifecycle does not survive a churning value.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { openPreview, pptPreviewSlice, registerPreview, type PptPreviewState } from "./pptPreviewSlice";
import type { PptPreviewPartData } from "./types";

const state = vi.hoisted(() => ({ session: "", ppt: null as unknown }));

vi.mock("react-router-dom", () => ({
  useSearchParams: () => [new URLSearchParams(state.session ? `session=${state.session}` : "")],
}));

vi.mock("react-redux", () => ({
  useSelector: (selector: (s: { pptPreview: unknown }) => unknown) => selector({ pptPreview: state.ppt }),
}));

const { useHasPptPreview, useSessionPptPreview } = await import("./useSessionPptPreview");

const deck: PptPreviewPartData = {
  type: "ppt_preview",
  preview_id: "deck-1",
  title: "Q3 review",
  pdf_download_url: "/fs/download/deck-1.pdf",
  version: "v1",
};

const other: PptPreviewPartData = { ...deck, preview_id: "deck-2", title: "Kickoff", version: "v9" };

/** The slice's own reducer builds the state, so the test can't drift from it. */
function sliceState(sessionId: string, ...actions: { type: string; payload: unknown }[]): PptPreviewState {
  return actions.reduce(
    (state, action) => pptPreviewSlice.reducer(state, action as never),
    pptPreviewSlice.reducer(undefined, registerPreview({ sessionId, preview: deck })),
  );
}

function read(openSession: string, ppt: PptPreviewState): PptPreviewPartData | null {
  let seen: PptPreviewPartData | null = null;
  state.session = openSession;
  state.ppt = ppt;
  function Probe() {
    seen = useSessionPptPreview();
    return null;
  }
  renderToStaticMarkup(<Probe />);
  return seen;
}

function hasDeck(openSession: string, ppt: PptPreviewState): boolean {
  let seen = false;
  state.session = openSession;
  state.ppt = ppt;
  function Probe() {
    seen = useHasPptPreview();
    return null;
  }
  renderToStaticMarkup(<Probe />);
  return seen;
}

describe("useSessionPptPreview", () => {
  it("returns the deck the open conversation registered", () => {
    expect(read("s1", sliceState("s1"))).toEqual(deck);
  });

  it("ignores a deck registered by another conversation", () => {
    expect(read("s2", sliceState("s1"))).toBeNull();
  });

  it("returns nothing while no conversation is open", () => {
    expect(read("", sliceState("s1"))).toBeNull();
  });

  it("does not move the pane when another card registers its deck", () => {
    // Registering is what lights the launcher up; moving the pane on it would
    // rebuild the pdf.js worker under a document that is still loading.
    const state = sliceState("s1", registerPreview({ sessionId: "s1", preview: other }));

    expect(read("s1", state)).toEqual(deck);
  });

  it("moves the pane on an explicit open", () => {
    const state = sliceState("s1", openPreview({ sessionId: "s1", preview: other }));

    expect(read("s1", state)).toEqual(other);
  });
});

describe("useHasPptPreview", () => {
  it("is true once the open conversation has produced a deck", () => {
    expect(hasDeck("s1", sliceState("s1"))).toBe(true);
  });

  it("ignores a deck produced by another conversation", () => {
    expect(hasDeck("s2", sliceState("s1"))).toBe(false);
  });

  it("is false before any deck", () => {
    expect(hasDeck("s1", pptPreviewSlice.reducer(undefined, { type: "init" }))).toBe(false);
  });
});
