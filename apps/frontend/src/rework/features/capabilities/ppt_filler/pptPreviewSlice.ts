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
// one piece of cross-component UI state the side panel and the chat cards share:
// which deck the pane should render. A chat-part renderer sits far from the panel
// host in the tree, so Redux replaces prop-drilling (mirrors writableDocumentSlice).
//
// Opening the panel is NOT this slice's job: the card dispatches the
// capability-agnostic `requestSidePanelOpen` for that, and the chat page stays the
// single open-state authority.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { PptPreviewPartData } from "./types";

export interface PptPreviewState {
  /** The conversation `current` belongs to; a write from another one replaces it. */
  sessionId: string | null;
  /** The deck the side panel should render, or null before any deck exists. */
  current: PptPreviewPartData | null;
}

// Local root-state shape — avoids a circular import with common/store.tsx. The
// store registers this reducer under the `pptPreview` key (see wiring notes).
interface PptPreviewRootState {
  pptPreview: PptPreviewState;
}

const initialState: PptPreviewState = { sessionId: null, current: null };

export const pptPreviewSlice = createSlice({
  name: "pptPreview",
  initialState,
  reducers: {
    /**
     * Register the deck a rendered `ppt_preview` card refers to, stamped with the
     * conversation it came from. Every card mount writes here - history replay
     * included - so the pane and its launcher know a conversation produced a deck
     * without the card having to open anything.
     */
    setPreview(state, action: PayloadAction<{ sessionId: string; preview: PptPreviewPartData }>) {
      state.sessionId = action.payload.sessionId;
      state.current = action.payload.preview;
    },
  },
});

export const { setPreview } = pptPreviewSlice.actions;

// ── Selectors ─────────────────────────────────────────────────────────────────

/** The registered deck, whichever conversation it came from (scope with the hook). */
export const selectCurrentPreview = (state: PptPreviewRootState): PptPreviewPartData | null => state.pptPreview.current;

/** The conversation the registered deck belongs to, or null. */
export const selectPptPreviewSessionId = (state: PptPreviewRootState): string | null => state.pptPreview.sessionId;

export default pptPreviewSlice.reducer;
