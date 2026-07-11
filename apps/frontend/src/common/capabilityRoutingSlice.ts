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

// Capability routing state (AGENT-CAPABILITY-RFC §9.1).
//
// Holds the ingress-relative base URL of each capability's auto-mounted router,
// keyed by capability id. Control-plane hands these out on the template catalog
// (`available_capabilities[].route_base_url`, template-bound) and on
// `ExecutionPreparation` (instance-bound); the host dispatches
// `setCapabilityBaseUrls` when either lands, and every per-capability RTK slice
// resolves its base URL from here (`createCapabilityBaseQuery`). No proxy — the
// browser calls the pod directly.

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export interface CapabilityRoutingState {
  /** capability id → ingress-relative router base URL (`/pod/.../capabilities/{id}`). */
  baseUrls: Record<string, string>;
}

const initialState: CapabilityRoutingState = { baseUrls: {} };

export const capabilityRoutingSlice = createSlice({
  name: "capabilityRouting",
  initialState,
  reducers: {
    /** Merge in a batch of capability id → base URL entries; nulls are ignored. */
    setCapabilityBaseUrls(state, action: PayloadAction<Record<string, string | null | undefined>>) {
      for (const [id, url] of Object.entries(action.payload)) {
        if (url) state.baseUrls[id] = url;
      }
    },
  },
});

export const { setCapabilityBaseUrls } = capabilityRoutingSlice.actions;

/** The base URL for one capability's router, or undefined when not yet known. */
export function selectCapabilityBaseUrl(
  state: { capabilityRouting: CapabilityRoutingState },
  capabilityId: string,
): string | undefined {
  return state.capabilityRouting.baseUrls[capabilityId];
}
