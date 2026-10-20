// common/dynamicBaseQuery.ts
// Copyright Thales 2025
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

import { fetchBaseQuery, FetchArgs, FetchBaseQueryError } from "@reduxjs/toolkit/query/react";
import type { BaseQueryFn } from "@reduxjs/toolkit/query";
import { handlePlatformAccessDenial } from "./platformAccess";
import { KeyCloakService } from "../security/KeycloakService";

/** Same as fetchBaseQuery's default, except that an array repeats its key
 *  (`a=1&a=2`), as OpenAPI query arrays and FastAPI expect, instead of `a=1,2`. */
export function serializeQueryParams(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) value.forEach((item) => search.append(key, String(item)));
    else search.append(key, String(value));
  }
  return search.toString();
}

export const createDynamicBaseQuery = (
  fetchFn?: typeof fetch,
): BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError, { retryUnauthorized?: boolean }> => {
  const raw = fetchBaseQuery({
    fetchFn,
    paramsSerializer: serializeQueryParams,
    prepareHeaders: (headers) => {
      const token = KeyCloakService.GetToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return headers;
    },
  });

  const normalizeArgs = (args: string | FetchArgs): FetchArgs => {
    if (typeof args === "string") {
      return { url: args, cache: "no-store" };
    }
    return { ...args, cache: "no-store" };
  };

  return async (args, api, extraOptions) => {
    const requestArgs = normalizeArgs(args);

    // 1) Proactively ensure token is still valid before making the request.
    const sessionIdentity = () => KeyCloakService.GetSessionIdentity?.() ?? KeyCloakService.GetUserId?.();
    const actor = sessionIdentity();
    await KeyCloakService.ensureFreshToken(30);
    if (actor !== sessionIdentity())
      return { error: { status: "CUSTOM_ERROR", error: "Account changed during request" } };

    // 2) First attempt
    let result = await raw(requestArgs, api, extraOptions);

    // 3) If unauthorized, try ONE refresh + retry
    // An endpoint that can return 401 after committed effects must expose that
    // result to its caller. Its next explicit attempt still refreshes proactively.
    if (result.error && result.error.status === 401 && extraOptions?.retryUnauthorized !== false) {
      const ok = await KeyCloakService.ensureFreshToken(0);
      if (ok) {
        if (actor !== sessionIdentity())
          return { error: { status: "CUSTOM_ERROR", error: "Account changed during request" } };
        result = await raw(requestArgs, api, extraOptions);
      }
      // 4) Still unauthorized? Clean logout to avoid a broken UI state.
      if (result.error && result.error.status === 401) {
        KeyCloakService.CallLogout();
      }
    }

    if (actor !== sessionIdentity())
      return { error: { status: "CUSTOM_ERROR", error: "Account changed during request" } };
    if (result.error) handlePlatformAccessDenial(result.error.status, result.error.data);
    return result;
  };
};
