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

// writable_document live-snapshot routing state.
//
// The `writable_document` chat part lives in the message stream; this slice is the
// cross-component bus the chat cards and the editor pane share (mirrors
// pptPreviewSlice). A card renderer — rendered deep in the conversation thread —
// feeds every rendered part in via `upsertFromPart`; the pane (far away in the
// tree) reads the merged live set without prop-drilling. `selectedId` is the tab
// the pane shows, driven from either a card's Open button or the pane's tab strip.
//
// Why the live set matters even though the pane also lists documents from the API:
// a LIVE agent write reaches the stream (a part) before the list query refetches,
// so the pane must merge the live snapshot to update the editor immediately (the
// "newest updated_at wins" rule; see useWritableDocuments).

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { WritableDocumentPartData } from "./types";
import { tsMs } from "./writableDocumentUtils";

export interface WritableDocumentState {
  /** The session these live snapshots belong to; a change resets the map (below). */
  sessionId: string | null;
  /** Newest live snapshot per document_id, fed from streamed chat parts. */
  liveById: Record<string, WritableDocumentPartData>;
  /** The document_id the pane currently shows, or null. */
  selectedId: string | null;
}

// Local root-state shape — avoids a circular import with common/store.tsx. The
// store registers this reducer under the `writableDocument` key.
interface WritableDocumentRootState {
  writableDocument: WritableDocumentState;
}

const initialState: WritableDocumentState = { sessionId: null, liveById: {}, selectedId: null };

export const writableDocumentSlice = createSlice({
  name: "writableDocument",
  initialState,
  reducers: {
    /**
     * Record one streamed snapshot, keeping the NEWEST `updated_at` per document_id
     * (a stale re-render or history-replay part never masks a fresher agent write).
     * A snapshot from a different session resets the map first, so live docs from a
     * previous session never linger as phantom tabs when the user switches sessions.
     */
    upsertFromPart(state, action: PayloadAction<{ sessionId: string; doc: WritableDocumentPartData }>) {
      const { sessionId, doc } = action.payload;
      if (state.sessionId !== sessionId) {
        state.sessionId = sessionId;
        state.liveById = {};
        state.selectedId = null;
      }
      const existing = state.liveById[doc.document_id];
      if (!existing || tsMs(doc.updated_at) >= tsMs(existing.updated_at)) {
        state.liveById[doc.document_id] = doc;
      }
    },

    /** Set the pane's active document (a card's Open button or the pane's tab strip). */
    selectWritableDocument(state, action: PayloadAction<string | null>) {
      state.selectedId = action.payload;
    },

    /** Clear all live snapshots and selection (e.g. on session teardown). */
    clearWritableDocuments(state) {
      state.sessionId = null;
      state.liveById = {};
      state.selectedId = null;
    },
  },
});

export const { upsertFromPart, selectWritableDocument, clearWritableDocuments } = writableDocumentSlice.actions;

// ── Selectors ─────────────────────────────────────────────────────────────────

/** The live snapshots map (stable ref between unrelated dispatches). */
export const selectWritableDocumentsById = (
  state: WritableDocumentRootState,
): Record<string, WritableDocumentPartData> => state.writableDocument.liveById;

/** The document_id the pane should show, or null. */
export const selectWritableDocumentSelectedId = (state: WritableDocumentRootState): string | null =>
  state.writableDocument.selectedId;

export default writableDocumentSlice.reducer;
