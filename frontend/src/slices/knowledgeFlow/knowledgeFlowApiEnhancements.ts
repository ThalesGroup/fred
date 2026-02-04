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
    uploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPost: {
      query: (queryArg) => {
        const formData = new FormData();
        formData.append('file', queryArg.bodyUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPost.file);

        return {
          url: `/knowledge-flow/v1/teams/${queryArg.teamId}/banner`,
          method: "POST",
          body: formData,
        };
      },
      invalidatesTags: (_, __, arg) => [
        { type: "Team" as const, id: arg.teamId },
        { type: "Team" as const, id: "LIST" },
      ],
    },
    listTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGet: {
      providesTags: (result, _, arg) =>
        result
          ? [
              ...result.map((member) => ({ type: "TeamMember" as const, id: `${arg.teamId}-${member.user.id}` })),
              { type: "TeamMember" as const, id: `LIST-${arg.teamId}` },
            ]
          : [{ type: "TeamMember" as const, id: `LIST-${arg.teamId}` }],
    },
    updateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatch: {
      invalidatesTags: (_, __, arg) => [
        { type: "TeamMember" as const, id: `${arg.teamId}-${arg.userId}` },
        { type: "TeamMember" as const, id: `LIST-${arg.teamId}` },
      ],
    },
    removeTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDelete: {
      invalidatesTags: (_, __, arg) => [
        { type: "TeamMember" as const, id: `${arg.teamId}-${arg.userId}` },
        { type: "TeamMember" as const, id: `LIST-${arg.teamId}` },
      ],
    },
  },
});

// Re-export all hooks from the enhanced API
export const {
  useListTeamsKnowledgeFlowV1TeamsGetQuery,
  useGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery,
  useUpdateTeamKnowledgeFlowV1TeamsTeamIdPatchMutation,
  useUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPostMutation,
  useListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetQuery,
  useUpdateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatchMutation,
  useRemoveTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDeleteMutation,
} = enhancedKnowledgeFlowApi;
