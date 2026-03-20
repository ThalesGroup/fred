import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// initialize an empty api service that we'll inject endpoints into later as needed
export const knowledgeFlowApi = createApi({
  baseQuery: createDynamicBaseQuery({ backend: "knowledge" }),
  // todo: in future, use reverse proxy to avoid dynamic base query:
  // baseQuery: fetchBaseQuery({ baseUrl: "/" }),
  // todo: remove this to improv app performance. Stale data should be handled with cache invalidation, not with timeouts.
  keepUnusedDataFor: 0,
  refetchOnMountOrArgChange: true,
  refetchOnFocus: true,
  refetchOnReconnect: true,

  endpoints: () => ({}),
  reducerPath: "knowledgeFlowApi",
  tagTypes: ["BenchRun", "Team", "TeamMember"],
});
