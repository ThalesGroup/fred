import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// initialize an empty api service that we'll inject endpoints into later as needed
export const knowledgeFlowApi = createApi({
  baseQuery: createDynamicBaseQuery(),
  // Freshness here rests entirely on revalidating at every mount: not one
  // endpoint in this slice declares providesTags/invalidatesTags yet, so
  // dropping `refetchOnMountOrArgChange` would leave nothing to refresh a list
  // after a mutation. What it must NOT also do is throw the previous answer
  // away: with `keepUnusedDataFor: 0` a cache entry died with its last
  // subscriber, so every remount had no data to render and every consumer went
  // back to a full loading state — a page that briefly unmounts its own body
  // reloaded itself in full.
  //
  // So: keep revalidating on mount, but serve the cached answer while it runs.
  // Replacing the mount revalidation with real tag invalidation is still the
  // goal (see the slice README) — that is what would let this become a plain
  // cache instead of a stale-while-revalidate one.
  keepUnusedDataFor: 60,
  refetchOnMountOrArgChange: true,

  endpoints: () => ({}),
  reducerPath: "knowledgeFlowApi",
  tagTypes: ["Team", "TeamMember"],
});
