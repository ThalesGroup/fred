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

// PPT-filler preview routing state.
//
// The `ppt_preview` chat part lives in the message stream; this slice holds the
// small cross-component UI state the side panel and the chat cards share:
//
//   - `current`      — the preview the pane should render right now.
//   - `openRequestId`— a monotonic counter. Bumping it is the signal for the chat
//                      page to OPEN the ppt_filler side panel (the host owns the
//                      column's open/closed state; a slice value can't call it, so
//                      the page subscribes to this counter and opens on change).
//
// Mirrors the Kea `usePptPreview` hook's open/select behaviour, but as Redux state
// so a chat-part renderer (which is far from the panel host in the tree) can drive
// the panel without prop-drilling.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { PptPreviewPartData } from "./types";

export interface PptPreviewState {
  /** The preview the side panel should render, or null before any deck exists. */
  current: PptPreviewPartData | null;
  /** Monotonic; incrementing it asks the chat page to open the ppt_filler panel. */
  openRequestId: number;
}

// Local root-state shape — avoids a circular import with common/store.tsx. The
// store registers this reducer under the `pptPreview` key (see wiring notes).
interface PptPreviewRootState {
  pptPreview: PptPreviewState;
}

const initialState: PptPreviewState = { current: null, openRequestId: 0 };

export const pptPreviewSlice = createSlice({
  name: "pptPreview",
  initialState,
  reducers: {
    /**
     * Select this preview AND request the panel to open (bumps `openRequestId`).
     * Dispatched by a card's "Open preview" button and by the card auto-open
     * heuristic when a freshly filled deck arrives live.
     */
    openPreview(state, action: PayloadAction<PptPreviewPartData>) {
      state.current = action.payload;
      state.openRequestId += 1;
    },

    /**
     * Update the current preview WITHOUT requesting an open — e.g. a re-fill of a
     * deck whose panel is already open. The panel remounts on the new `version`;
     * the open request is not re-fired so a closed panel stays closed.
     */
    setPreview(state, action: PayloadAction<PptPreviewPartData>) {
      state.current = action.payload;
    },

    /** Clear the current preview (e.g. on session switch). */
    clearPreview(state) {
      state.current = null;
    },
  },
});

export const { openPreview, setPreview, clearPreview } = pptPreviewSlice.actions;

// ── Selectors ─────────────────────────────────────────────────────────────────

/** The preview the side panel should render, or null. */
export const selectCurrentPreview = (state: PptPreviewRootState): PptPreviewPartData | null => state.pptPreview.current;

/** The open-request counter the chat page subscribes to. */
export const selectPptOpenRequestId = (state: PptPreviewRootState): number => state.pptPreview.openRequestId;

export default pptPreviewSlice.reducer;
