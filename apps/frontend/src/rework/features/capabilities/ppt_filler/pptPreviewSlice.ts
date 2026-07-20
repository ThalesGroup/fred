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
// The `ppt_preview` chat parts live in the message stream; this slice holds the
// small cross-component UI state the side panel and the chat cards share:
//
//   - `current`    — the preview the pane should render right now (the LATEST
//                    deck the conversation produced, unless the user explicitly
//                    selected another card).
//   - `seen`       — `(preview_id, version)` keys already folded in, so card
//                    remounts (scroll, panel toggle re-renders) can never
//                    overwrite an explicit user selection with an older deck.
//   - `autoOpened` — once-per-session-view guard: the FIRST preview to appear
//                    (live fill or history replay alike) auto-opens the panel,
//                    later ones do not — so a user who closed the panel is not
//                    fought by every subsequent card mount. Mirrors Kea's
//                    `usePptPreview` `autoOpenedRef`.
//
// The whole slice resets on `chatSessionScopeChanged` (dispatched by the chat
// page on mount and on session switch), which re-arms auto-open per
// conversation view and prevents one session's deck from leaking into another.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { chatSessionScopeChanged } from "../sessionScope";
import type { PptPreviewPartData } from "./types";

export interface PptPreviewState {
  /** The preview the side panel should render, or null before any deck exists. */
  current: PptPreviewPartData | null;
  /** `(preview_id:version)` keys already folded into this session view. */
  seen: Record<string, true>;
  /** True once the first preview of this session view requested an auto-open. */
  autoOpened: boolean;
}

// Local root-state shape — avoids a circular import with common/store.tsx. The
// store registers this reducer under the `pptPreview` key (see wiring notes).
interface PptPreviewRootState {
  pptPreview: PptPreviewState;
}

const initialState: PptPreviewState = { current: null, seen: {}, autoOpened: false };

export const previewKeyOf = (preview: PptPreviewPartData): string => `${preview.preview_id}:${preview.version}`;

export const pptPreviewSlice = createSlice({
  name: "pptPreview",
  initialState,
  reducers: {
    /**
     * Fold one `ppt_preview` part into the slice — dispatched by every chat
     * card on mount (live fill AND history replay). First sighting of a key
     * makes that deck current (cards mount in thread order, so the latest deck
     * wins); repeat sightings are no-ops. Also consumes the one auto-open
     * budget of this session view (the card checks `selectShouldAutoOpen`
     * BEFORE dispatching to know whether to request the panel).
     */
    previewSeen(state, action: PayloadAction<PptPreviewPartData>) {
      const key = previewKeyOf(action.payload);
      if (state.seen[key]) return;
      state.seen[key] = true;
      state.current = action.payload;
      state.autoOpened = true;
    },

    /**
     * Explicit user selection (a card's "Open preview" click) — always makes
     * this deck current, regardless of `seen`.
     */
    selectPreview(state, action: PayloadAction<PptPreviewPartData>) {
      state.current = action.payload;
    },
  },
  extraReducers: (builder) => {
    // New conversation view (page mount or session switch): drop the previous
    // session's deck and re-arm the auto-open guard.
    builder.addCase(chatSessionScopeChanged, () => initialState);
  },
});

export const { previewSeen, selectPreview } = pptPreviewSlice.actions;

// ── Selectors ─────────────────────────────────────────────────────────────────

/** The preview the side panel should render, or null. */
export const selectCurrentPreview = (state: PptPreviewRootState): PptPreviewPartData | null => state.pptPreview.current;

/** True while this session view still has its auto-open budget. */
export const selectShouldAutoOpen = (state: PptPreviewRootState): boolean => !state.pptPreview.autoOpened;

/** Whether this exact deck (preview_id + version) was already folded in. */
export const selectIsPreviewSeen =
  (key: string) =>
  (state: PptPreviewRootState): boolean =>
    state.pptPreview.seen[key] === true;

export default pptPreviewSlice.reducer;
