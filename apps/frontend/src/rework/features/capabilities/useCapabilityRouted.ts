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

// "Is this capability's own router reachable yet?" - the skip guard every query
// on a capability API needs.
//
// `createCapabilityBaseQuery` resolves the pod's base URL from
// `capabilityRoutingSlice` AT REQUEST TIME and fails loudly when it is not there
// yet. On a hard page load the catalog/prep answer lands after the first render,
// so a query fired before it gets that failure cached against unchanged args and
// never retries - the capability then looks empty for the rest of the page load,
// while a client-side navigation into the same conversation works (routing is
// already in the store). Skipping until the base URL exists turns that into a
// normal deferred fetch: RTK Query fires it the moment the guard flips.

import { useSelector } from "react-redux";
import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "../../../common/capabilityRoutingSlice";

export function useCapabilityRouted(capabilityId: string): boolean {
  return useSelector(
    (state: { capabilityRouting: CapabilityRoutingState }) =>
      selectCapabilityBaseUrl(state, capabilityId) !== undefined,
  );
}
