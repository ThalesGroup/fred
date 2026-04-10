import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

export const agenticApi = createApi({
  reducerPath: "agenticApi",
  baseQuery: createDynamicBaseQuery(),

  // Make cache/invalidation coherent across the app.
  tagTypes: ["McpServers"],

  // Defaults: conservative + predictable.
  refetchOnFocus: false,
  refetchOnReconnect: false,

  // todo: remove this to improv app performance. Stale data should be handled with cache invalidation, not with timeouts.
  // For chat, stale data causes confusion. .
  keepUnusedDataFor: 0,

  endpoints: () => ({}),
});
