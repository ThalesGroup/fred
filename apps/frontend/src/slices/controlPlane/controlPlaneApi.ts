import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// initialize an empty api service that we'll inject endpoints into later as needed
export const controlPlaneApi = createApi({
  reducerPath: "controlPlaneApi",
  baseQuery: createDynamicBaseQuery(),
  tagTypes: ["ControlPlaneTeam", "ControlPlaneTeamMember", "ControlPlaneUser"],
  endpoints: () => ({}),
});
