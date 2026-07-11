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

// Per-capability dynamic base query (AGENT-CAPABILITY-RFC §9.1).
//
// The exact `createDynamicBaseQuery` idiom (bearer + one-shot 401 refresh),
// except the base URL is resolved PER CAPABILITY from `capabilityRoutingSlice`
// state at request time — control-plane populated it from the catalog/prep.
// A capability whose base URL is not yet known fails the request loudly rather
// than silently hitting the frontend origin.

import { fetchBaseQuery, type FetchArgs, type FetchBaseQueryError } from "@reduxjs/toolkit/query/react";
import type { BaseQueryFn } from "@reduxjs/toolkit/query";
import { KeyCloakService } from "../security/KeycloakService";
import { selectCapabilityBaseUrl, type CapabilityRoutingState } from "./capabilityRoutingSlice";

export const createCapabilityBaseQuery = (
  capabilityId: string,
): BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> => {
  const normalizeArgs = (args: string | FetchArgs): FetchArgs =>
    typeof args === "string" ? { url: args, cache: "no-store" } : { ...args, cache: "no-store" };

  return async (args, api, extraOptions) => {
    const baseUrl = selectCapabilityBaseUrl(
      api.getState() as { capabilityRouting: CapabilityRoutingState },
      capabilityId,
    );
    if (!baseUrl) {
      return {
        error: {
          status: "CUSTOM_ERROR",
          error: `No base URL known for capability "${capabilityId}" (catalog/preparation not loaded)`,
        } satisfies FetchBaseQueryError,
      };
    }
    const raw = fetchBaseQuery({
      baseUrl,
      prepareHeaders: (headers) => {
        const token = KeyCloakService.GetToken();
        if (token) headers.set("Authorization", `Bearer ${token}`);
        return headers;
      },
    });

    const requestArgs = normalizeArgs(args);
    await KeyCloakService.ensureFreshToken(30);
    let result = await raw(requestArgs, api, extraOptions);
    if (result.error && result.error.status === 401) {
      const ok = await KeyCloakService.ensureFreshToken(0);
      if (ok) result = await raw(requestArgs, api, extraOptions);
      if (result.error && result.error.status === 401) KeyCloakService.CallLogout();
    }
    return result;
  };
};
