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
    "ControlPlaneRoutingPolicy",
    "ControlPlanePrompt",
  ],
  endpoints: {
    // #2148: bootstrap's `available_teams`/`active_team` are the same team
    // rows `listTeams`/`getTeam` expose — tag them the same way so every
    // existing team mutation (join, add/remove member, grant/revoke role,
    // create/update) invalidates bootstrap's cache entry too, now that
    // bootstrap no longer forces a refetch on every mount.
    getFrontendBootstrapControlPlaneV1FrontendBootstrapGet: {
      providesTags: (result) =>
        result
          ? [
              ...(result.available_teams ?? []).map((team) => ({
                type: "ControlPlaneTeam" as const,
                id: team.id,
              })),
              { type: "ControlPlaneTeam" as const, id: result.active_team.id },
              { type: "ControlPlaneTeam" as const, id: "LIST" },
            ]
          : [{ type: "ControlPlaneTeam" as const, id: "LIST" }],
    },
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
    // TEAM-09: self-service join — same tags as updateTeam so the marketplace
    // list (yourTeams/otherTeams split) and this team's own cache entry both
    // refresh with the caller now a member.
    joinTeamControlPlaneV1TeamsTeamIdJoinPost: {
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
    // Prompt library (PROMPT-09 follow-up, #2174): the single-prompt detail
    // query is shared by both the edit form and PromptViewDialog — without
    // tag invalidation, saving a prompt never refreshed that cached detail,
    // so the view dialog kept showing the pre-edit category/text forever.
    getTeamPromptsControlPlaneV1TeamsTeamIdPromptsGet: {
      providesTags: (result, _, arg) =>
        result
          ? [
              ...result.map((prompt) => ({ type: "ControlPlanePrompt" as const, id: prompt.id })),
              { type: "ControlPlanePrompt" as const, id: `LIST-${arg.teamId}` },
            ]
          : [{ type: "ControlPlanePrompt" as const, id: `LIST-${arg.teamId}` }],
    },
    getTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGet: {
      providesTags: (_, __, arg) => [{ type: "ControlPlanePrompt" as const, id: arg.promptId }],
    },
    postTeamPromptControlPlaneV1TeamsTeamIdPromptsPost: {
      invalidatesTags: (_, __, arg) => [{ type: "ControlPlanePrompt", id: `LIST-${arg.teamId}` }],
    },
    putTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPut: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlanePrompt", id: arg.promptId },
        { type: "ControlPlanePrompt", id: `LIST-${arg.teamId}` },
      ],
    },
    deleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDelete: {
      invalidatesTags: (_, __, arg) => [
        { type: "ControlPlanePrompt", id: arg.promptId },
        { type: "ControlPlanePrompt", id: `LIST-${arg.teamId}` },
      ],
    },
    // Team routing policy (TEAM-05, #2118).
    getTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGet: {
      providesTags: (_, __, arg) => [{ type: "ControlPlaneRoutingPolicy" as const, id: arg.teamId }],
    },
    updateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatch: {
      invalidatesTags: (_, __, arg) => [{ type: "ControlPlaneRoutingPolicy", id: arg.teamId }],
    },
  },
});

export const {
  useListUsersControlPlaneV1UsersGetQuery: useListUsersQuery,
  // Batch uid → display-name resolution for audit fields (#1952).
  useGetUsersByIdsControlPlaneV1UsersByIdsGetQuery: useUsersByIdsQuery,
  useListTeamsControlPlaneV1TeamsGetQuery: useListTeamsQuery,
  useListAllTeamsControlPlaneV1TeamsAllGetQuery: useListAllTeamsQuery,
  useGetTeamControlPlaneV1TeamsTeamIdGetQuery: useGetTeamQuery,
  useCreateTeamControlPlaneV1TeamsPostMutation: useCreateTeamMutation,
  useUpdateTeamControlPlaneV1TeamsTeamIdPatchMutation: useUpdateTeamMutation,
  useJoinTeamControlPlaneV1TeamsTeamIdJoinPostMutation: useJoinTeamMutation,
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
  // Team routing policy (TEAM-05, #2118).
  useGetTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGetQuery: useTeamRoutingPolicyQuery,
  useUpdateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatchMutation: useUpdateTeamRoutingPolicyMutation,
  // Routing-policy picker option set (#2167).
  useGetAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGetQuery:
    useAvailableModelProfilesQuery,
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
  // Platform-wide or team-scoped token usage (OBSERV-02 v3, F1/F2) — same
  // shape as the user_-prefixed personal presets above, different scope.
  useHandlerControlPlaneV1KpiPresetsTokenUsageOverTimeGetQuery: useTokenUsageOverTimeQuery,
  useHandlerControlPlaneV1KpiPresetsTokenUsageByAgentGetQuery: useTokenUsageByAgentQuery,
  useHandlerControlPlaneV1KpiPresetsTokenUsageByModelGetQuery: useTokenUsageByModelQuery,
  useHandlerControlPlaneV1KpiPresetsStorageByTeamGetQuery: useStorageByTeamQuery,
  useHandlerControlPlaneV1KpiPresetsTeamActivitySummaryGetQuery: useTeamActivitySummaryQuery,
  // Persisted task acknowledgement (OPS-04, TASK-EVENT-STREAM-RFC.md §2.10 rev 3).
  useAcknowledgeTaskControlPlaneV1TasksTaskIdAckPostMutation: useAcknowledgeTaskMutation,
  usePlatformStatsControlPlaneV1ImportExportStatsGetQuery: usePlatformStatsQuery,
  useResetPlatformDataControlPlaneV1ImportExportResetPostMutation: useResetPlatformMutation,
  useResetPlatformRebacControlPlaneV1ImportExportResetRebacPostMutation: useResetPlatformRebacMutation,
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
