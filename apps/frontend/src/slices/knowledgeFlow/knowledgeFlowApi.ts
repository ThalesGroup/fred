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
  // So: retain the answer, and revalidate on mount only once it has aged past
  // the window below rather than on every single mount. Walking from a page to
  // the chat and back is then free, where it used to reload everything.
  //
  // The window is what bounds the staleness that buys: a change made from
  // another screen can stay invisible for that long. The resources workspace
  // carries an explicit refresh control for the times that is not good enough,
  // and the mutations that happen on a page still refetch their own lists.
  // Replacing this with real tag invalidation is still the goal (see the slice
  // README) — that is what would make the window unnecessary.
  keepUnusedDataFor: 60,
  refetchOnMountOrArgChange: 30,

  endpoints: () => ({}),
  reducerPath: "knowledgeFlowApi",
  tagTypes: ["Team", "TeamMember"],
});
