import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

export const wfEngineDefaultNamespace = "default";

// initialize an empty api service that we'll inject endpoints into later as needed
export const knowledgeFlowApi = createApi({
  baseQuery: fetchBaseQuery({ baseUrl: "/" }),
  endpoints: () => ({}),
  reducerPath: "knowledgeFlowApi",
});
