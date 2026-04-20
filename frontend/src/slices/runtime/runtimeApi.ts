import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

export const runtimeApi = createApi({
  reducerPath: "runtimeApi",
  baseQuery: createDynamicBaseQuery(),

  // Runtime chat/history traffic should stay explicit during the migration.
  refetchOnFocus: false,
  refetchOnReconnect: false,
  keepUnusedDataFor: 0,

  endpoints: () => ({}),
});
