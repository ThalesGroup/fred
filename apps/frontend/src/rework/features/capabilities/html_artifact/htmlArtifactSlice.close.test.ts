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

// Closing an artifact's view hides it from the pane without dropping the snapshot,
// because the chat card's "Open preview" is the documented way back. The subtle part
// is WHEN a close is undone: a genuine new revision must reopen the view (the reader
// asked for that change), while a replay of the same content must not — cards
// remount in message order on every conversation re-render.

import { describe, expect, it } from "vitest";
import reducer, {
  closeHtmlArtifact,
  clearHtmlArtifacts,
  selectHtmlArtifact,
  upsertFromPart,
} from "./htmlArtifactSlice";
import type { HtmlArtifactPartData } from "./types";

const art = (id: string, version: string, html = "<p>x</p>"): HtmlArtifactPartData => ({
  type: "html_artifact",
  artifact_id: id,
  title: "Page",
  html,
  css: "",
  version,
});

const withTwo = () => {
  let state = reducer(undefined, upsertFromPart({ sessionId: "s1", art: art("a1", "v1") }));
  state = reducer(state, upsertFromPart({ sessionId: "s1", art: art("a2", "v1") }));
  return reducer(state, selectHtmlArtifact("a1"));
};

describe("closeHtmlArtifact", () => {
  it("hides the view but keeps the snapshot, so the card can reopen it", () => {
    const state = reducer(withTwo(), closeHtmlArtifact("a1"));

    expect(state.closedIds).toEqual({ a1: true });
    expect(state.liveById.a1).toBeDefined();
  });

  it("drops the selection when the closed one was showing", () => {
    const state = reducer(withTwo(), closeHtmlArtifact("a1"));
    expect(state.selectedId).toBeNull();
  });

  it("leaves the selection alone when another artifact was showing", () => {
    const state = reducer(withTwo(), closeHtmlArtifact("a2"));
    expect(state.selectedId).toBe("a1");
  });
});

describe("reopening", () => {
  it("selecting reopens — that is the card's Open preview button", () => {
    let state = reducer(withTwo(), closeHtmlArtifact("a1"));
    state = reducer(state, selectHtmlArtifact("a1"));

    expect(state.closedIds).toEqual({});
    expect(state.selectedId).toBe("a1");
  });

  it("a NEW revision reopens a closed view", () => {
    let state = reducer(withTwo(), closeHtmlArtifact("a1"));
    state = reducer(state, upsertFromPart({ sessionId: "s1", art: art("a1", "v2", "<p>changed</p>") }));

    expect(state.closedIds).toEqual({});
  });

  it("a replay of the SAME content does not reopen it", () => {
    let state = reducer(withTwo(), closeHtmlArtifact("a1"));
    // Same version: this is a card remounting, not a revision.
    state = reducer(state, upsertFromPart({ sessionId: "s1", art: art("a1", "v1") }));

    expect(state.closedIds).toEqual({ a1: true });
  });
});

describe("resets", () => {
  it("switching conversation forgets what was closed", () => {
    let state = reducer(withTwo(), closeHtmlArtifact("a1"));
    state = reducer(state, upsertFromPart({ sessionId: "s2", art: art("b1", "v1") }));

    expect(state.closedIds).toEqual({});
    expect(state.liveById.a1).toBeUndefined();
  });

  it("teardown clears the closed set too", () => {
    let state = reducer(withTwo(), closeHtmlArtifact("a1"));
    state = reducer(state, clearHtmlArtifacts());

    expect(state.closedIds).toEqual({});
  });
});
