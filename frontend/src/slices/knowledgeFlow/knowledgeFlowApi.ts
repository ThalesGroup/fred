import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// initialize an empty api service that we'll inject endpoints into later as needed
export const knowledgeFlowApi = createApi({
  baseQuery: createDynamicBaseQuery({ backend: "knowledge" }),
  // todo: in future, use reverse proxy to avoid dynamic base query:
  // baseQuery: fetchBaseQuery({ baseUrl: "/" }),
  endpoints: () => ({}),
  reducerPath: "knowledgeFlowApi",
});
