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

import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

// Empty base API. All evaluation endpoints and types are generated into
// `evaluationOpenApi.ts` from the evaluator's OpenAPI (see ./README.md) and
// injected onto this base. Do NOT hand-define endpoints or DTOs here — use the
// generated hooks/types so the client never drifts from the contract.
export const evaluationApi = createApi({
  reducerPath: "evaluationApi",
  baseQuery: createDynamicBaseQuery(),
  tagTypes: ["Evaluation", "EvaluationRun", "EvaluationCase"],
  endpoints: () => ({}),
});
