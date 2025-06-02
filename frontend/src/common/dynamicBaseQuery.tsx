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

// common/dynamicBaseQuery.ts

import { fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import { getConfig } from "./config";
import { KeyCloakService } from "../security/KeycloakService";

/**
 * Options to select which backend to use for the baseQuery.
 */
interface DynamicBaseQueryOptions {
  backend: "api" | "knowledge";
}

/**
 * Factory that creates a dynamic baseQuery for the correct backend,
 * handling Authorization automatically.
 *
 * @param options - backend selection ("api" or "knowledge")
 * @returns a baseQuery function ready for RTK Query
 */
export const createDynamicBaseQuery = (options: DynamicBaseQueryOptions) => {
  return async (args, api, extraOptions) => {
    // ❗❗ Only access the config when the request is actually made
    const baseUrl =
      options.backend === "knowledge"
        ? import.meta.env.VITE_BACKEND_URL_KNOWLEDGE || getConfig().backend_url_knowledge
        : import.meta.env.VITE_BACKEND_URL_API || getConfig().backend_url_api;

    if (!baseUrl) {
      throw new Error(`Backend URL missing for ${options.backend} backend.`);
    }

    const rawBaseQuery = fetchBaseQuery({
      baseUrl,
      prepareHeaders: (headers) => {
        const token = KeyCloakService.GetToken();
        if (token) {
          headers.set("Authorization", `Bearer ${token}`);
        }
        return headers;
      },
    });

    return rawBaseQuery(args, api, extraOptions);
  };
};
