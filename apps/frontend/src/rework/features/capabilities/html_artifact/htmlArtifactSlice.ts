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

// html_artifact live-snapshot routing state.
//
// The `html_artifact` chat part lives in the message stream; this slice is the
// cross-component bus the chat cards and the viewer pane share (mirrors
// pptPreviewSlice / writableDocumentSlice). A card renderer — rendered deep in the
// conversation thread — feeds every rendered part in via `upsertFromPart`; the pane
// (far away in the tree) reads the merged live set without prop-drilling.
// `selectedId` is the artifact the pane shows, driven from a card's Open button or
// the pane's artifact switcher.
//
// There is no owned table in v1 (read-only), so this slice is the sole source: the
// markup rides inline on the part. Cards mount in message order, so overwriting per
// artifact_id ("last rendered wins") lands the latest revision — the last message's
// card upserts last, and a live revise upserts after any history replay.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { HtmlArtifactPartData } from "./types";

export interface HtmlArtifactState {
  /** The session these live snapshots belong to; a change resets the map (below). */
  sessionId: string | null;
  /** Latest live snapshot per artifact_id, fed from streamed chat parts. */
  liveById: Record<string, HtmlArtifactPartData>;
  /** The artifact_id the pane currently shows, or null. */
  selectedId: string | null;
}

// Local root-state shape — avoids a circular import with common/store.tsx. The
// store registers this reducer under the `htmlArtifact` key.
interface HtmlArtifactRootState {
  htmlArtifact: HtmlArtifactState;
}

const initialState: HtmlArtifactState = { sessionId: null, liveById: {}, selectedId: null };

export const htmlArtifactSlice = createSlice({
  name: "htmlArtifact",
  initialState,
  reducers: {
    /**
     * Record one streamed snapshot, overwriting the entry for its artifact_id
     * (last rendered wins — see the module note). A snapshot from a different
     * session resets the map first, so artifacts from a previous session never
     * linger as phantom entries when the user switches conversations.
     */
    upsertFromPart(state, action: PayloadAction<{ sessionId: string; art: HtmlArtifactPartData }>) {
      const { sessionId, art } = action.payload;
      if (state.sessionId !== sessionId) {
        state.sessionId = sessionId;
        state.liveById = {};
        state.selectedId = null;
      }
      state.liveById[art.artifact_id] = art;
    },

    /** Set the pane's active artifact (a card's Open button or the pane's switcher). */
    selectHtmlArtifact(state, action: PayloadAction<string | null>) {
      state.selectedId = action.payload;
    },

    /** Clear all live snapshots and selection (e.g. on session teardown). */
    clearHtmlArtifacts(state) {
      state.sessionId = null;
      state.liveById = {};
      state.selectedId = null;
    },
  },
});

export const { upsertFromPart, selectHtmlArtifact, clearHtmlArtifacts } = htmlArtifactSlice.actions;

// ── Selectors ─────────────────────────────────────────────────────────────────

/** The live snapshots map (stable ref between unrelated dispatches). */
export const selectHtmlArtifactsById = (state: HtmlArtifactRootState): Record<string, HtmlArtifactPartData> =>
  state.htmlArtifact.liveById;

/** The conversation the live snapshots belong to, or null. */
export const selectHtmlArtifactSessionId = (state: HtmlArtifactRootState): string | null =>
  state.htmlArtifact.sessionId;

/** The artifact_id the pane should show, or null. */
export const selectHtmlArtifactSelectedId = (state: HtmlArtifactRootState): string | null =>
  state.htmlArtifact.selectedId;

export default htmlArtifactSlice.reducer;
