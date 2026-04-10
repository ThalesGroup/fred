import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// initialize an empty api service that we'll inject endpoints into later as needed
export const controlPlaneApi = createApi({
  reducerPath: "controlPlaneApi",
  baseQuery: createDynamicBaseQuery(),
  keepUnusedDataFor: 0,
  refetchOnMountOrArgChange: true,
  refetchOnFocus: true,
  refetchOnReconnect: true,
  tagTypes: ["ControlPlaneTeam", "ControlPlaneTeamMember", "ControlPlaneUser"],
  endpoints: () => ({}),
});
