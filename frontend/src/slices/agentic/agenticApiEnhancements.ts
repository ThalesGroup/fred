// Copyright Thales 2025
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
//
// Enhancements over the generated agentic API. The codegen emits multipart upload
// endpoints with a plain-object body (`body: { file }`), which `fetchBaseQuery`
// JSON-stringifies — turning the `File` into `{}` and yielding a 422 (missing file)
// server-side. We override the affected `query` to build a real `FormData` so the
// request is sent as `multipart/form-data`. Mirrors `controlPlaneApiEnhancements.ts`
// (team banner upload). Import the re-exported hooks from THIS file, not the generated
// one, so the override is in effect.

import {
  agenticApi as api,
  AnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostApiArg,
} from "./agenticOpenApi";

export const enhancedAgenticApi = api.enhanceEndpoints({
  endpoints: {
    analyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePost: {
      query: (queryArg: AnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostApiArg) => {
        const formData = new FormData();
        formData.append("file", queryArg.bodyAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePost.file);

        return {
          url: `/agentic/v1/agents/ppt-filler/analyze`,
          method: "POST",
          body: formData,
        };
      },
    },
  },
});

export const {
  useAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostMutation: useAnalyzePptFillerTemplateMutation,
} = enhancedAgenticApi;
