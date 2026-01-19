import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// initialize an empty api service that we'll inject endpoints into later as needed
export const knowledgeFlowApi = createApi({
  baseQuery: createDynamicBaseQuery({ backend: "knowledge" }),
  // todo: in future, use reverse proxy to avoid dynamic base query:
  // baseQuery: fetchBaseQuery({ baseUrl: "/" }),
  keepUnusedDataFor: 0,
  refetchOnMountOrArgChange: true,
  refetchOnFocus: true,
  refetchOnReconnect: true,
  endpoints: () => ({}),
  reducerPath: "knowledgeFlowApi",
  tagTypes: ["BenchRun"],
});
