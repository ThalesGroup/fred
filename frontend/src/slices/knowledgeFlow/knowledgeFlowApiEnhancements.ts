import { knowledgeFlowApi } from "./knowledgeFlowOpenApi";

/**
 * Enhance auto-generated endpoints with cache tags for proper invalidation.
 * This file is manually maintained and should be updated when new endpoints need cache management.
 */
export const enhancedKnowledgeFlowApi = knowledgeFlowApi.enhanceEndpoints({
  endpoints: {
    listTeamsKnowledgeFlowV1TeamsGet: {
      providesTags: (result) =>
        result
          ? [...result.map((team) => ({ type: "Team" as const, id: team.id })), { type: "Team" as const, id: "LIST" }]
          : [{ type: "Team" as const, id: "LIST" }],
    },
    getTeamKnowledgeFlowV1TeamsTeamIdGet: {
      providesTags: (_, __, arg) => [{ type: "Team" as const, id: arg.teamId }],
    },
    updateTeamKnowledgeFlowV1TeamsTeamIdPatch: {
      invalidatesTags: (_, __, arg) => [
        { type: "Team" as const, id: arg.teamId },
        { type: "Team" as const, id: "LIST" },
      ],
    },
  },
});

// Re-export all hooks from the enhanced API
export const {
  useListTeamsKnowledgeFlowV1TeamsGetQuery,
  useGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery,
  useUpdateTeamKnowledgeFlowV1TeamsTeamIdPatchMutation,
} = enhancedKnowledgeFlowApi;
