import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// Empty base API. All evaluation endpoints and types are generated into
// `evaluationOpenApi.ts` from the evaluator's OpenAPI (see ./README.md) and
// injected onto this base. Do NOT hand-define endpoints or DTOs here — use the
// generated hooks/types so the client never drifts from the contract.
export const evaluationApi = createApi({
  reducerPath: "evaluationApi",
  baseQuery: createDynamicBaseQuery(),
  tagTypes: ["EvaluationCampaign", "EvaluationCase"],
  endpoints: () => ({}),
});
