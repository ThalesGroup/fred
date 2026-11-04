// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { runtimeApi } from "./runtimeApi";
import type { GetRuntimeInstanceSkillDetailApiArg, GetRuntimeInstanceSkillDetailApiResponse } from "./runtimeOpenApi";

// The preparation response owns the pod route; the generated contract owns its
// parameters and response. No default pod or browser-provided source is inferred.
const preview = runtimeApi.injectEndpoints({
  endpoints: (build) => ({
    weaverSkillDetail: build.query<
      GetRuntimeInstanceSkillDetailApiResponse,
      GetRuntimeInstanceSkillDetailApiArg & { urlTemplate: string }
    >({
      query: ({ urlTemplate, skillName, spaceId, agentInstanceId }) => ({
        url: urlTemplate.replace("{skill_name}", encodeURIComponent(skillName)),
        params: { space_id: spaceId, agent_instance_id: agentInstanceId },
      }),
    }),
  }),
});
export const { useWeaverSkillDetailQuery } = preview;
