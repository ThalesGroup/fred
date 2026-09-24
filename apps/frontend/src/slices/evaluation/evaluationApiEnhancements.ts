// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
    deleteEvaluationEvaluationV1EvaluationsEvaluationIdDelete: {
      invalidatesTags: [{ type: "Evaluation", id: "LIST" }],
    },
  },
});

export const {
  useListEvaluationsEvaluationV1EvaluationsGetQuery: useListEvaluationsQuery,
  useCreateEvaluationEvaluationV1EvaluationsPostMutation: useCreateEvaluationMutation,
  useDeleteEvaluationEvaluationV1EvaluationsEvaluationIdDeleteMutation: useDeleteEvaluationMutation,
} = enhancedEvaluationApi;
