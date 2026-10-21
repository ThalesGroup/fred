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

// Which spreadsheet the pane shows, shared by the chat cards and the pane (they
// sit far apart in the tree). Same shape as pptPreviewSlice; opening the panel
// itself goes through the capability-agnostic `requestSidePanelOpen`.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { SpreadsheetPreviewPartData } from "./types";

export interface SpreadsheetPreviewState {
  /** The conversation this state belongs to; a write from another one resets it. */
  sessionId: string | null;
  current: SpreadsheetPreviewPartData | null;
}

interface SpreadsheetPreviewRootState {
  spreadsheetPreview: SpreadsheetPreviewState;
}

const initialState: SpreadsheetPreviewState = { sessionId: null, current: null };

type Payload = PayloadAction<{ sessionId: string; preview: SpreadsheetPreviewPartData }>;

export const spreadsheetPreviewSlice = createSlice({
  name: "spreadsheetPreview",
  initialState,
  reducers: {
    /** Every rendered card registers its file; it fills the pane only when empty. */
    registerSpreadsheet(state, action: Payload) {
      if (state.sessionId !== action.payload.sessionId) {
        state.sessionId = action.payload.sessionId;
        state.current = null;
      }
      state.current ??= action.payload.preview;
    },
    /** Show this file in the pane: a card's preview button, or a live creation. */
    openSpreadsheet(state, action: Payload) {
      state.sessionId = action.payload.sessionId;
      state.current = action.payload.preview;
    },
  },
});

export const { registerSpreadsheet, openSpreadsheet } = spreadsheetPreviewSlice.actions;

export const selectSpreadsheetPreview = (state: SpreadsheetPreviewRootState) => state.spreadsheetPreview;

export default spreadsheetPreviewSlice.reducer;
