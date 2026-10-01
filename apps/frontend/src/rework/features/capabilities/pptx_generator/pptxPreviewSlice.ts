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

// pptx_generator preview routing state (mirrors ppt_filler's pptPreviewSlice).
//
// The `pptx_generated` chat part lives in the message stream; this slice holds the
// one piece of cross-component UI state the side panel and the chat cards share:
// which deck the pane should render. A chat-part renderer sits far from the panel
// host in the tree, so Redux replaces prop-drilling.
//
// Opening the panel is NOT this slice's job: the card dispatches the
// capability-agnostic `requestSidePanelOpen` for that, and the chat page stays the
// single open-state authority.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { PptxGeneratedPartData } from "./types";

export interface PptxPreviewState {
  /** The conversation this state belongs to; a write from another one replaces it. */
  sessionId: string | null;
  /**
   * The deck the pane renders. Only an explicit open moves it: the pane keys its
   * pdf.js worker on this value, and that lifecycle does not survive a value that
   * churns with re-renders.
   */
  current: PptxGeneratedPartData | null;
}

// Local root-state shape — avoids a circular import with common/store.tsx. The
// store registers this reducer under the `pptxPreview` key.
interface PptxPreviewRootState {
  pptxPreview: PptxPreviewState;
}

const initialState: PptxPreviewState = { sessionId: null, current: null };

/** A write from another conversation starts that conversation's state from scratch. */
function rebase(state: PptxPreviewState, sessionId: string): void {
  if (state.sessionId === sessionId) return;
  state.sessionId = sessionId;
  state.current = null;
}

export const pptxPreviewSlice = createSlice({
  name: "pptxPreview",
  initialState,
  reducers: {
    /**
     * Every rendered card registers its deck, history replay included: that is how
     * the launcher knows this conversation produced one. It seeds `current` only
     * while the pane has nothing, so later re-renders cannot move what it shows.
     */
    registerPreview(state, action: PayloadAction<{ sessionId: string; preview: PptxGeneratedPartData }>) {
      rebase(state, action.payload.sessionId);
      if (state.current === null) state.current = action.payload.preview;
    },

    /** Show this deck in the pane - a card's Open button, or a live generation. */
    openPreview(state, action: PayloadAction<{ sessionId: string; preview: PptxGeneratedPartData }>) {
      rebase(state, action.payload.sessionId);
      state.current = action.payload.preview;
    },
  },
});

export const { registerPreview, openPreview } = pptxPreviewSlice.actions;

// ── Selectors ─────────────────────────────────────────────────────────────────

/** The deck the pane should render, whichever conversation it came from. */
export const selectCurrentPptxPreview = (state: PptxPreviewRootState): PptxGeneratedPartData | null =>
  state.pptxPreview.current;

/** Did the registered conversation produce a deck at all? No separate `produced`
 * flag: every reducer above sets `current` in lockstep with it, so it's fully
 * derivable and there's nothing to keep in sync by hand. */
export const selectPptxPreviewProduced = (state: PptxPreviewRootState): boolean => state.pptxPreview.current !== null;

/** The conversation this state belongs to, or null. */
export const selectPptxPreviewSessionId = (state: PptxPreviewRootState): string | null => state.pptxPreview.sessionId;

export default pptxPreviewSlice.reducer;
