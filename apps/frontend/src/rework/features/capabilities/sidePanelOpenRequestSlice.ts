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

// Capability side-panel open requests (#1903, RFC §9 item 3).
//
// Why this exists:
// - the side-panel column's open state is owned by the chat page (one push
//   drawer at a time), but a capability's chat-part renderer — rendered deep
//   inside the conversation thread — may need to OPEN its own panel (e.g. the
//   ppt_filler preview card opening the PDF pane after a fill)
// - this tiny slice is the capability-agnostic signal: a renderer dispatches
//   `requestSidePanelOpen`, the page watches `requestId` and opens the named
//   panel. The page stays the single open-state authority.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export interface SidePanelOpenRequestState {
  /** `${capabilityId}:${widget}` of the panel to open, or null before any request. */
  key: string | null;
  /** Monotonic counter — a change signals one request, even for the same key. */
  requestId: number;
}

const initialState: SidePanelOpenRequestState = { key: null, requestId: 0 };

export const sidePanelOpenRequestSlice = createSlice({
  name: "capabilitySidePanelOpenRequest",
  initialState,
  reducers: {
    requestSidePanelOpen(state, action: PayloadAction<{ capabilityId: string; widget: string }>) {
      state.key = `${action.payload.capabilityId}:${action.payload.widget}`;
      state.requestId += 1;
    },
  },
});

export const { requestSidePanelOpen } = sidePanelOpenRequestSlice.actions;

export const selectSidePanelOpenRequest = (state: {
  capabilitySidePanelOpenRequest: SidePanelOpenRequestState;
}): SidePanelOpenRequestState => state.capabilitySidePanelOpenRequest;
