// NOT GENERATED. Safe to edit.
import { evaluationApi as api } from "./evaluationOpenApi";

export const enhancedEvaluationApi = api.enhanceEndpoints({
  endpoints: {
    listEvaluationsEvaluationV1EvaluationsGet: {
      providesTags: [{ type: "Evaluation" as const, id: "LIST" }],
    },
    createEvaluationEvaluationV1EvaluationsPost: {
      invalidatesTags: [{ type: "Evaluation", id: "LIST" }],
    },
  },
});

export const {
  useListEvaluationsEvaluationV1EvaluationsGetQuery: useListEvaluationsQuery,
  useCreateEvaluationEvaluationV1EvaluationsPostMutation: useCreateEvaluationMutation,
} = enhancedEvaluationApi;
