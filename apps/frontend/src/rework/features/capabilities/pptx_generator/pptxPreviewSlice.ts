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

// Which deck the preview pane renders, shared by chat cards and the side panel
// (far apart in the tree). Opening the panel is not this slice's job: cards
// dispatch the capability-agnostic `requestSidePanelOpen`.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { PptxGeneratedPartData } from "./types";

export interface PptxPreviewState {
  /** The conversation this state belongs to; a write from another one replaces it. */
  sessionId: string | null;
  /** The deck the pane renders. Only an explicit open moves it: the pane keys its
   *  pdf.js worker on it, and that lifecycle does not survive a churning value. */
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
    /** Every rendered card registers its deck (how the launcher knows one exists);
     *  it seeds `current` only while the pane is empty, so re-renders can't move it. */
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

/** Did the registered conversation produce a deck? Derived from `current`, which
 *  every reducer sets in lockstep, so there is no separate flag to keep in sync. */
export const selectPptxPreviewProduced = (state: PptxPreviewRootState): boolean => state.pptxPreview.current !== null;

/** The conversation this state belongs to, or null. */
export const selectPptxPreviewSessionId = (state: PptxPreviewRootState): string | null => state.pptxPreview.sessionId;

export default pptxPreviewSlice.reducer;
