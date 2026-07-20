// NOT GENERATED. Safe to edit.
import {
  controlPlaneApi as api,
  UploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostApiArg,
} from "./controlPlaneOpenApi";

export const enhancedControlPlaneApi = api.enhanceEndpoints({
  addTagTypes: [
    "ControlPlaneTeam",
    "ControlPlaneTeamMember",
    "ControlPlaneUser",
    "ControlPlaneSession",
    "ControlPlaneSessionAttachment",
    "ControlPlaneCapability",
  ],
  endpoints: {
    // Admin capabilities dashboard (CAPAB-01 / #1981). Every enablement mutation
    // re-reads the aggregated catalog so scope/enabled-team state stays truthful.
    getAdminCapabilitiesControlPlaneV1AdminCapabilitiesGet: {
      providesTags: [{ type: "ControlPlaneCapability" as const, id: "LIST" }],
    },
    putTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdPut: {
      invalidatesTags: [{ type: "ControlPlaneCapability", id: "LIST" }],
    },
    deleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDelete: {
      invalidatesTags: [{ type: "ControlPlaneCapability", id: "LIST" }],
    },
    putCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPut: {
      invalidatesTags: [{ type: "ControlPlaneCapability", id: "LIST" }],
    },
    putCapabilityPersonalScopeControlPlaneV1AdminCapabilitiesCapabilityIdPersonalScopePut: {
      invalidatesTags: [{ type: "ControlPlaneCapability", id: "LIST" }],
    },
    getTeamSessionsControlPlaneV1TeamsTeamIdSessionsGet: {
      providesTags: (_, __, arg) => [{ type: "ControlPlaneSession" as const, id: `LIST-${arg.teamId}` }],
    },
    postTeamSessionControlPlaneV1TeamsTeamIdSessionsPost: {
      invalidatesTags: (_, __, arg) => [{ type: "ControlPlaneSession", id: `LIST-${arg.teamId}` }],
    },
    deleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDelete: {
      invalidatesTags: (_, __, arg) => [{ type: "ControlPlaneSession", id: `LIST-${arg.teamId}` }],
    },
    patchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatch: {
      invalidatesTags: (_, __, arg) => [{ type: "ControlPlaneSession", id: `LIST-${arg.teamId}` }],
    },
    getTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGet: {
      providesTags: (result, _, arg) =>
        result
          ? [
              ...result.map((attachment) => ({
                type: "ControlPlaneSessionAttachment" as const,
                id: `${arg.sessionId}-${attachment.attachment_id}`,
              })),
              { type: "ControlPlaneSessionAttachment" as const, id: `LIST-${arg.sessionId}` },
            ]
          : [{ type: "ControlPlaneSessionAttachment" as const, id: `LIST-${arg.sessionId}` }],
    },
    postTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPost: {
      invalidatesTags: (_, __, arg) => [{ type: "ControlPlaneSessionAttachment", id: `LIST-${arg.sessionId}` }],
    },
    deleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDelete: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneSessionAttachment", id: `${arg.sessionId}-${arg.attachmentId}` },
        { type: "ControlPlaneSessionAttachment", id: `LIST-${arg.sessionId}` },
      ],
    },
    listUsersControlPlaneV1UsersGet: {
      providesTags: [{ type: "ControlPlaneUser", id: "LIST" }],
    },
    listTeamsControlPlaneV1TeamsGet: {
      providesTags: (result) =>
        result
          ? [
              ...result.map((team) => ({ type: "ControlPlaneTeam" as const, id: team.id })),
              { type: "ControlPlaneTeam" as const, id: "LIST" },
            ]
          : [{ type: "ControlPlaneTeam" as const, id: "LIST" }],
    },
    listAllTeamsControlPlaneV1TeamsAllGet: {
      providesTags: (result) =>
        result
          ? [
              ...result.map((team) => ({ type: "ControlPlaneTeam" as const, id: team.id })),
              { type: "ControlPlaneTeam" as const, id: "LIST" },
            ]
          : [{ type: "ControlPlaneTeam" as const, id: "LIST" }],
    },
    getTeamControlPlaneV1TeamsTeamIdGet: {
      providesTags: (_, __, arg) => [{ type: "ControlPlaneTeam", id: arg.teamId }],
    },
    createTeamControlPlaneV1TeamsPost: {
      invalidatesTags: [{ type: "ControlPlaneTeam", id: "LIST" }],
    },
    updateTeamControlPlaneV1TeamsTeamIdPatch: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeam", id: arg.teamId },
        { type: "ControlPlaneTeam", id: "LIST" },
      ],
    },
    uploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost: {
      query: (queryArg: UploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostApiArg) => {
        const formData = new FormData();
        formData.append("file", queryArg.bodyUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost.file);

        return {
          url: `/control-plane/v1/teams/${queryArg.teamId}/banner`,
          method: "POST",
          body: formData,
        };
      },
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeam", id: arg.teamId },
        { type: "ControlPlaneTeam", id: "LIST" },
      ],
    },
    listTeamMembersControlPlaneV1TeamsTeamIdMembersGet: {
      providesTags: (result, _, arg) =>
        result
          ? [
              ...result.map((member) => ({
                type: "ControlPlaneTeamMember" as const,
                id: `${arg.teamId}-${member.user.id}`,
              })),
              { type: "ControlPlaneTeamMember" as const, id: `LIST-${arg.teamId}` },
            ]
          : [{ type: "ControlPlaneTeamMember" as const, id: `LIST-${arg.teamId}` }],
    },
    addTeamMemberControlPlaneV1TeamsTeamIdMembersPost: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    },
    grantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPost: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `${arg.teamId}-${arg.userId}` },
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    },
    revokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDelete: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `${arg.teamId}-${arg.userId}` },
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    },
    removeTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDelete: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlaneTeamMember", id: `${arg.teamId}-${arg.userId}` },
        { type: "ControlPlaneTeamMember", id: `LIST-${arg.teamId}` },
        { type: "ControlPlaneTeam", id: arg.teamId },
      ],
    },
  },
});

export const {
  useListUsersControlPlaneV1UsersGetQuery: useListUsersQuery,
  useListTeamsControlPlaneV1TeamsGetQuery: useListTeamsQuery,
  useListAllTeamsControlPlaneV1TeamsAllGetQuery: useListAllTeamsQuery,
  useGetTeamControlPlaneV1TeamsTeamIdGetQuery: useGetTeamQuery,
  useCreateTeamControlPlaneV1TeamsPostMutation: useCreateTeamMutation,
  useUpdateTeamControlPlaneV1TeamsTeamIdPatchMutation: useUpdateTeamMutation,
  useUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostMutation: useUploadTeamBannerMutation,
  useListTeamMembersControlPlaneV1TeamsTeamIdMembersGetQuery: useListTeamMembersQuery,
  useAddTeamMemberControlPlaneV1TeamsTeamIdMembersPostMutation: useAddTeamMemberMutation,
  useSearchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGetQuery: useSearchCandidateTeamMembersQuery,
  useLazySearchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGetQuery:
    useLazySearchCandidateTeamMembersQuery,
  useGrantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPostMutation: useGrantTeamMemberRoleMutation,
  useRevokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDeleteMutation:
    useRevokeTeamMemberRoleMutation,
  useRemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteMutation: useRemoveTeamMemberMutation,
  useHandlerControlPlaneV1KpiPresetsActiveUsersOverTimeGetQuery: useActiveUsersOverTimeQuery,
  useHandlerControlPlaneV1KpiPresetsUniqueUsersTotalGetQuery: useUniqueUsersTotalQuery,
  useHandlerControlPlaneV1KpiPresetsSessionsOverTimeGetQuery: useSessionsOverTimeQuery,
  useHandlerControlPlaneV1KpiPresetsMessagesOverTimeGetQuery: useMessagesOverTimeQuery,
  useHandlerControlPlaneV1KpiPresetsSessionsByScopeGetQuery: useSessionsByScopeQuery,
  useHandlerControlPlaneV1KpiPresetsTopTeamsBySessionsGetQuery: useTopTeamsBySessionsQuery,
  useHandlerControlPlaneV1KpiPresetsAgentsTotalGetQuery: useAgentsTotalQuery,
  useHandlerControlPlaneV1KpiPresetsTopAgentsByConversationsGetQuery: useTopAgentsByConversationsQuery,
  useHandlerControlPlaneV1KpiPresetsAgentPromptLengthDistributionGetQuery: useAgentPromptLengthDistributionQuery,
  useHandlerControlPlaneV1KpiPresetsDocumentsTotalGetQuery: useDocumentsTotalQuery,
  useHandlerControlPlaneV1KpiPresetsUserTokenUsageOverTimeGetQuery: useUserTokenUsageOverTimeQuery,
  useHandlerControlPlaneV1KpiPresetsUserTokenUsageByAgentGetQuery: useUserTokenUsageByAgentQuery,
  useHandlerControlPlaneV1KpiPresetsUserTokenUsageByModelGetQuery: useUserTokenUsageByModelQuery,
  usePlatformStatsControlPlaneV1ImportExportStatsGetQuery: usePlatformStatsQuery,
  useResetPlatformDataControlPlaneV1ImportExportResetPostMutation: useResetPlatformMutation,
  // Admin capabilities dashboard (CAPAB-01 / #1981).
  useGetAdminCapabilitiesControlPlaneV1AdminCapabilitiesGetQuery: useAdminCapabilitiesQuery,
  usePutTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdPutMutation:
    useEnableTeamCapabilityMutation,
  useDeleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDeleteMutation:
    useDisableTeamCapabilityMutation,
  usePutCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPutMutation:
    useSetCapabilityDefaultOnMutation,
  usePutCapabilityPersonalScopeControlPlaneV1AdminCapabilitiesCapabilityIdPersonalScopePutMutation:
    useSetCapabilityPersonalScopeMutation,
  // Fired on demand from the disable-confirmation dialog (lazy — not on render).
  useLazyGetCapabilityRevokeImpactControlPlaneV1AdminCapabilitiesCapabilityIdRevokeImpactGetQuery:
    useLazyCapabilityRevokeImpactQuery,
} = enhancedControlPlaneApi;
