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

import type { FetchArgs, FetchBaseQueryError } from "@reduxjs/toolkit/query";
import {
  selectConversationFileRoute,
  type ConversationFileRootState,
} from "../../rework/features/conversationFiles/conversationFileSlice";
import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

const baseQuery = createDynamicBaseQuery();

export const runtimeApi = createApi({
  reducerPath: "runtimeApi",
  baseQuery: (args, api, options) => {
    const request = typeof args === "string" ? { url: args } : (args as FetchArgs);
    const match = /^\/pod\/v1\/agents\/sessions\/([^/]+)\/filesystem\//.exec(request.url);
    if (match) {
      const route = selectConversationFileRoute(
        api.getState() as ConversationFileRootState,
        decodeURIComponent(match[1]),
      );
      if (!route)
        return { error: { status: "CUSTOM_ERROR", error: "Conversation runtime unavailable" } as FetchBaseQueryError };
      return baseQuery({ ...request, url: request.url.replace("/pod/v1", route) }, api, options);
    }
    return baseQuery(args, api, options);
  },

  // Runtime chat/history traffic should stay explicit during the migration.
  refetchOnFocus: false,
  refetchOnReconnect: false,
  keepUnusedDataFor: 0,

  endpoints: () => ({}),
});
