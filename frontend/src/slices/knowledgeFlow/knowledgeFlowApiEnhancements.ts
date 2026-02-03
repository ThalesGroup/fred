import { knowledgeFlowApi } from "./knowledgeFlowOpenApi";

/**
 * Enhance auto-generated endpoints with cache tags for proper invalidation.
 * This file is manually maintained and should be updated when new endpoints need cache management.
 */
export const enhancedKnowledgeFlowApi = knowledgeFlowApi.enhanceEndpoints({
  endpoints: {
    getTeamKnowledgeFlowV1TeamsTeamIdGet: {
      providesTags: (_, __, arg) => [{ type: "Team" as const, id: arg.teamId }],
    },
    updateTeamKnowledgeFlowV1TeamsTeamIdPatch: {
      invalidatesTags: (_, __, arg) => [{ type: "Team" as const, id: arg.teamId }],
    },
  },
});

// Re-export all hooks from the enhanced API
export const { useGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery, useUpdateTeamKnowledgeFlowV1TeamsTeamIdPatchMutation } =
  enhancedKnowledgeFlowApi;
