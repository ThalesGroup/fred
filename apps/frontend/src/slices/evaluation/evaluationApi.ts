import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// initialize an empty api service that we'll inject endpoints into later as needed
export const evaluationApi = createApi({
  reducerPath: "evaluationApi",
  baseQuery: createDynamicBaseQuery(),
  tagTypes: ["EvaluationCampaign", "EvaluationCase"],
  endpoints: () => ({}),
});
