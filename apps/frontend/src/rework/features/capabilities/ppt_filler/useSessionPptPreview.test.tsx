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

// The registered deck is global state but belongs to ONE conversation. Without
// the session stamp a deck filled in a previous conversation would light the
// launcher up on a brand-new chat, which is the whole thing this scoping exists
// to prevent.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { pptPreviewSlice, setPreview, type PptPreviewState } from "./pptPreviewSlice";
import type { PptPreviewPartData } from "./types";

const state = vi.hoisted(() => ({ session: "", ppt: null as unknown }));

vi.mock("react-router-dom", () => ({
  useSearchParams: () => [new URLSearchParams(state.session ? `session=${state.session}` : "")],
}));

vi.mock("react-redux", () => ({
  useSelector: (selector: (s: { pptPreview: unknown }) => unknown) => selector({ pptPreview: state.ppt }),
}));

const { useSessionPptPreview } = await import("./useSessionPptPreview");

const deck: PptPreviewPartData = {
  type: "ppt_preview",
  preview_id: "deck-1",
  title: "Q3 review",
  pdf_download_url: "/fs/download/deck-1.pdf",
  version: "v1",
};

/** The slice's own reducer builds the state, so the test can't drift from it. */
function sliceState(sessionId: string): PptPreviewState {
  return pptPreviewSlice.reducer(undefined, setPreview({ sessionId, preview: deck }));
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
});
