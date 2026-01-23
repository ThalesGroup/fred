import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

export const agenticApi = createApi({
  reducerPath: "agenticApi",
  baseQuery: createDynamicBaseQuery({ backend: "api" }),

  // Make cache/invalidation coherent across the app.
  tagTypes: ["McpServers"],

  // Defaults: conservative + predictable.
  refetchOnFocus: false,
  refetchOnReconnect: false,

  // For chat, stale data causes confusion. .
  keepUnusedDataFor: 0,

  endpoints: () => ({}),
});
