import { controlPlaneApi as api } from "./controlPlaneApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    healthzControlPlaneV1HealthzGet: build.query<
      HealthzControlPlaneV1HealthzGetApiResponse,
      HealthzControlPlaneV1HealthzGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/healthz` }),
    }),
    readyControlPlaneV1ReadyGet: build.query<ReadyControlPlaneV1ReadyGetApiResponse, ReadyControlPlaneV1ReadyGetApiArg>(
      {
        query: () => ({ url: `/control-plane/v1/ready` }),
      },
    ),
    getPurgePolicySummaryControlPlaneV1PoliciesPurgeGet: build.query<
      GetPurgePolicySummaryControlPlaneV1PoliciesPurgeGetApiResponse,
      GetPurgePolicySummaryControlPlaneV1PoliciesPurgeGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/policies/purge` }),
    }),
    resolvePurgeControlPlaneV1PoliciesPurgeResolvePost: build.mutation<
      ResolvePurgeControlPlaneV1PoliciesPurgeResolvePostApiResponse,
      ResolvePurgeControlPlaneV1PoliciesPurgeResolvePostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/policies/purge/resolve`,
        method: "POST",
        body: queryArg.policyResolutionRequest,
      }),
    }),
    triggerLifecycleRunOnceControlPlaneV1LifecycleRunOncePost: build.mutation<
      TriggerLifecycleRunOnceControlPlaneV1LifecycleRunOncePostApiResponse,
      TriggerLifecycleRunOnceControlPlaneV1LifecycleRunOncePostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/lifecycle/run-once`,
        method: "POST",
        body: queryArg.lifecycleManagerInput,
      }),
    }),
    listUsersControlPlaneV1UsersGet: build.query<
      ListUsersControlPlaneV1UsersGetApiResponse,
      ListUsersControlPlaneV1UsersGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/users` }),
    }),
    createUserControlPlaneV1UsersPost: build.mutation<
      CreateUserControlPlaneV1UsersPostApiResponse,
      CreateUserControlPlaneV1UsersPostApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/users`, method: "POST", body: queryArg.createUserRequest }),
    }),
    getUsersByIdsControlPlaneV1UsersByIdsGet: build.query<
      GetUsersByIdsControlPlaneV1UsersByIdsGetApiResponse,
      GetUsersByIdsControlPlaneV1UsersByIdsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/users/by-ids`,
        params: {
          ids: queryArg.ids,
        },
      }),
    }),
    listPlatformRolesControlPlaneV1UsersPlatformRolesGet: build.query<
      ListPlatformRolesControlPlaneV1UsersPlatformRolesGetApiResponse,
      ListPlatformRolesControlPlaneV1UsersPlatformRolesGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/users/platform-roles` }),
    }),
    grantPlatformRoleControlPlaneV1UsersUserIdPlatformRolesPost: build.mutation<
      GrantPlatformRoleControlPlaneV1UsersUserIdPlatformRolesPostApiResponse,
      GrantPlatformRoleControlPlaneV1UsersUserIdPlatformRolesPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/users/${queryArg.userId}/platform-roles`,
        method: "POST",
        body: queryArg.grantPlatformRoleRequest,
      }),
    }),
    revokePlatformRoleControlPlaneV1UsersUserIdPlatformRolesRelationDelete: build.mutation<
      RevokePlatformRoleControlPlaneV1UsersUserIdPlatformRolesRelationDeleteApiResponse,
      RevokePlatformRoleControlPlaneV1UsersUserIdPlatformRolesRelationDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/users/${queryArg.userId}/platform-roles/${queryArg.relation}`,
        method: "DELETE",
      }),
    }),
    deleteUserControlPlaneV1UsersUserIdDelete: build.mutation<
      DeleteUserControlPlaneV1UsersUserIdDeleteApiResponse,
      DeleteUserControlPlaneV1UsersUserIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/users/${queryArg.userId}`, method: "DELETE" }),
    }),
    getUserDetailsControlPlaneV1UserGet: build.query<
      GetUserDetailsControlPlaneV1UserGetApiResponse,
      GetUserDetailsControlPlaneV1UserGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/user` }),
    }),
    validateGcuControlPlaneV1GcuPost: build.mutation<
      ValidateGcuControlPlaneV1GcuPostApiResponse,
      ValidateGcuControlPlaneV1GcuPostApiArg
    >({
      query: () => ({ url: `/control-plane/v1/gcu`, method: "POST" }),
    }),
    listTeamsControlPlaneV1TeamsGet: build.query<
      ListTeamsControlPlaneV1TeamsGetApiResponse,
      ListTeamsControlPlaneV1TeamsGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/teams` }),
    }),
    createTeamControlPlaneV1TeamsPost: build.mutation<
      CreateTeamControlPlaneV1TeamsPostApiResponse,
      CreateTeamControlPlaneV1TeamsPostApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams`, method: "POST", body: queryArg.createTeamRequest }),
    }),
    listAllTeamsControlPlaneV1TeamsAllGet: build.query<
      ListAllTeamsControlPlaneV1TeamsAllGetApiResponse,
      ListAllTeamsControlPlaneV1TeamsAllGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/teams/all` }),
    }),
    getTeamControlPlaneV1TeamsTeamIdGet: build.query<
      GetTeamControlPlaneV1TeamsTeamIdGetApiResponse,
      GetTeamControlPlaneV1TeamsTeamIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}` }),
    }),
    updateTeamControlPlaneV1TeamsTeamIdPatch: build.mutation<
      UpdateTeamControlPlaneV1TeamsTeamIdPatchApiResponse,
      UpdateTeamControlPlaneV1TeamsTeamIdPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}`,
        method: "PATCH",
        body: queryArg.updateTeamRequest,
      }),
    }),
    deleteTeamControlPlaneV1TeamsTeamIdDelete: build.mutation<
      DeleteTeamControlPlaneV1TeamsTeamIdDeleteApiResponse,
      DeleteTeamControlPlaneV1TeamsTeamIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}`, method: "DELETE" }),
    }),
    joinTeamControlPlaneV1TeamsTeamIdJoinPost: build.mutation<
      JoinTeamControlPlaneV1TeamsTeamIdJoinPostApiResponse,
      JoinTeamControlPlaneV1TeamsTeamIdJoinPostApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/join`, method: "POST" }),
    }),
    rescueTeamAdminControlPlaneV1TeamsTeamIdRescueAdminPost: build.mutation<
      RescueTeamAdminControlPlaneV1TeamsTeamIdRescueAdminPostApiResponse,
      RescueTeamAdminControlPlaneV1TeamsTeamIdRescueAdminPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/rescue-admin`,
        method: "POST",
        body: queryArg.rescueTeamAdminRequest,
      }),
    }),
    uploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPost: build.mutation<
      UploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPostApiResponse,
      UploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/avatar`,
        method: "POST",
        body: queryArg.bodyUploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPost,
      }),
    }),
    listTeamMembersControlPlaneV1TeamsTeamIdMembersGet: build.query<
      ListTeamMembersControlPlaneV1TeamsTeamIdMembersGetApiResponse,
      ListTeamMembersControlPlaneV1TeamsTeamIdMembersGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/members` }),
    }),
    addTeamMemberControlPlaneV1TeamsTeamIdMembersPost: build.mutation<
      AddTeamMemberControlPlaneV1TeamsTeamIdMembersPostApiResponse,
      AddTeamMemberControlPlaneV1TeamsTeamIdMembersPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/members`,
        method: "POST",
        body: queryArg.addTeamMemberRequest,
      }),
    }),
    searchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGet: build.query<
      SearchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGetApiResponse,
      SearchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/candidate-members`,
        params: {
          query: queryArg.query,
        },
      }),
    }),
    removeTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDelete: build.mutation<
      RemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteApiResponse,
      RemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/members/${queryArg.userId}`,
        method: "DELETE",
      }),
    }),
    grantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPost: build.mutation<
      GrantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPostApiResponse,
      GrantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/members/${queryArg.userId}/roles`,
        method: "POST",
        body: queryArg.grantTeamMemberRoleRequest,
      }),
    }),
    revokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDelete: build.mutation<
      RevokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDeleteApiResponse,
      RevokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/members/${queryArg.userId}/roles/${queryArg.relation}`,
        method: "DELETE",
      }),
    }),
    getFrontendBootstrapControlPlaneV1FrontendBootstrapGet: build.query<
      GetFrontendBootstrapControlPlaneV1FrontendBootstrapGetApiResponse,
      GetFrontendBootstrapControlPlaneV1FrontendBootstrapGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/frontend/bootstrap` }),
    }),
    getFrontendConfigControlPlaneV1FrontendConfigGet: build.query<
      GetFrontendConfigControlPlaneV1FrontendConfigGetApiResponse,
      GetFrontendConfigControlPlaneV1FrontendConfigGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/frontend/config` }),
    }),
    getTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGet: build.query<
      GetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetApiResponse,
      GetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/agent-templates`,
        params: {
          include_non_public: queryArg.includeNonPublic,
        },
      }),
    }),
    getTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGet: build.query<
      GetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetApiResponse,
      GetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances` }),
    }),
    postTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPost: build.mutation<
      PostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostApiResponse,
      PostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances`,
        method: "POST",
        body: queryArg.createAgentInstanceRequest,
      }),
    }),
    patchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatch: build.mutation<
      PatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchApiResponse,
      PatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances/${queryArg.agentInstanceId}`,
        method: "PATCH",
        body: queryArg.updateAgentInstanceRequest,
      }),
    }),
    deleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDelete: build.mutation<
      DeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteApiResponse,
      DeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances/${queryArg.agentInstanceId}`,
        method: "DELETE",
      }),
    }),
    postTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPost: build.mutation<
      PostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPostApiResponse,
      PostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances/with-assets`,
        method: "POST",
        body: queryArg.bodyPostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPost,
      }),
    }),
    patchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatch:
      build.mutation<
        PatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatchApiResponse,
        PatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatchApiArg
      >({
        query: (queryArg) => ({
          url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances/${queryArg.agentInstanceId}/with-assets`,
          method: "PATCH",
          body: queryArg.bodyPatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatch,
        }),
      }),
    getTeamPromptsControlPlaneV1TeamsTeamIdPromptsGet: build.query<
      GetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetApiResponse,
      GetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/prompts` }),
    }),
    postTeamPromptControlPlaneV1TeamsTeamIdPromptsPost: build.mutation<
      PostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostApiResponse,
      PostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts`,
        method: "POST",
        body: queryArg.createPromptRequest,
      }),
    }),
    getContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGet: build.query<
      GetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetApiResponse,
      GetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/context` }),
    }),
    getTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGet: build.query<
      GetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetApiResponse,
      GetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/${queryArg.promptId}` }),
    }),
    putTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPut: build.mutation<
      PutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutApiResponse,
      PutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/${queryArg.promptId}`,
        method: "PUT",
        body: queryArg.updatePromptRequest,
      }),
    }),
    deleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDelete: build.mutation<
      DeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteApiResponse,
      DeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/${queryArg.promptId}`,
        method: "DELETE",
      }),
    }),
    patchTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPatch: build.mutation<
      PatchTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPatchApiResponse,
      PatchTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/${queryArg.promptId}`,
        method: "PATCH",
        body: queryArg.promptScoreUpdateRequest,
      }),
    }),
    postRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePost: build.mutation<
      PostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostApiResponse,
      PostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/${queryArg.promptId}/use`,
        method: "POST",
      }),
    }),
    postPromotePromptControlPlaneV1TeamsTeamIdPromptsPromptIdPromotePost: build.mutation<
      PostPromotePromptControlPlaneV1TeamsTeamIdPromptsPromptIdPromotePostApiResponse,
      PostPromotePromptControlPlaneV1TeamsTeamIdPromptsPromptIdPromotePostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/${queryArg.promptId}/promote`,
        method: "POST",
        body: queryArg.promptPromoteRequest,
      }),
    }),
    postPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPost: build.mutation<
      PostPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPostApiResponse,
      PostPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/${queryArg.promptId}/publish`,
        method: "POST",
      }),
    }),
    postUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPost: build.mutation<
      PostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostApiResponse,
      PostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/${queryArg.promptId}/unpublish`,
        method: "POST",
      }),
    }),
    getMarketplacePromptsControlPlaneV1MarketplacePromptsGet: build.query<
      GetMarketplacePromptsControlPlaneV1MarketplacePromptsGetApiResponse,
      GetMarketplacePromptsControlPlaneV1MarketplacePromptsGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/marketplace/prompts` }),
    }),
    getMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGet: build.query<
      GetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetApiResponse,
      GetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/marketplace/prompts/${queryArg.promptId}` }),
    }),
    postMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePost: build.mutation<
      PostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostApiResponse,
      PostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/marketplace/prompts/${queryArg.promptId}/use`, method: "POST" }),
    }),
    postMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPost: build.mutation<
      PostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostApiResponse,
      PostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/marketplace/prompts/${queryArg.promptId}/import`,
        method: "POST",
        body: queryArg.marketplaceImportRequest,
      }),
    }),
    getTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGet: build.query<
      GetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetApiResponse,
      GetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/prompt-categories` }),
    }),
    postTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPost: build.mutation<
      PostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostApiResponse,
      PostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompt-categories`,
        method: "POST",
        body: queryArg.createPromptCategoryRequest,
      }),
    }),
    putTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPut: build.mutation<
      PutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutApiResponse,
      PutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompt-categories/${queryArg.categoryId}`,
        method: "PUT",
        body: queryArg.updatePromptCategoryRequest,
      }),
    }),
    deleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDelete: build.mutation<
      DeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteApiResponse,
      DeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompt-categories/${queryArg.categoryId}`,
        method: "DELETE",
      }),
    }),
    getTeamAgentInstanceRuntimeControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdRuntimeGet: build.query<
      GetTeamAgentInstanceRuntimeControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdRuntimeGetApiResponse,
      GetTeamAgentInstanceRuntimeControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdRuntimeGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances/${queryArg.agentInstanceId}/runtime`,
      }),
    }),
    postTeamSessionControlPlaneV1TeamsTeamIdSessionsPost: build.mutation<
      PostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostApiResponse,
      PostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/sessions`,
        method: "POST",
        body: queryArg.createSessionRequest,
      }),
    }),
    getTeamSessionsControlPlaneV1TeamsTeamIdSessionsGet: build.query<
      GetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetApiResponse,
      GetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/sessions` }),
    }),
    getMyInactiveSessionsControlPlaneV1MeInactiveSessionsGet: build.query<
      GetMyInactiveSessionsControlPlaneV1MeInactiveSessionsGetApiResponse,
      GetMyInactiveSessionsControlPlaneV1MeInactiveSessionsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/me/inactive-sessions`,
        params: {
          inactive_days: queryArg.inactiveDays,
        },
      }),
    }),
    postBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePost: build.mutation<
      PostBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePostApiResponse,
      PostBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/me/sessions/bulk-delete`,
        method: "POST",
        body: queryArg.bulkDeleteSessionsRequest,
      }),
    }),
    getTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGet: build.query<
      GetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetApiResponse,
      GetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/sessions/${queryArg.sessionId}` }),
    }),
    patchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatch: build.mutation<
      PatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchApiResponse,
      PatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/sessions/${queryArg.sessionId}`,
        method: "PATCH",
        body: queryArg.updateSessionRequest,
      }),
    }),
    deleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDelete: build.mutation<
      DeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteApiResponse,
      DeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/sessions/${queryArg.sessionId}`,
        method: "DELETE",
      }),
    }),
    getTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGet: build.query<
      GetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetApiResponse,
      GetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/sessions/${queryArg.sessionId}/attachments`,
      }),
    }),
    postTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPost: build.mutation<
      PostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostApiResponse,
      PostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/sessions/${queryArg.sessionId}/attachments`,
        method: "POST",
        body: queryArg.createSessionAttachmentRequest,
      }),
    }),
    deleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDelete: build.mutation<
      DeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteApiResponse,
      DeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/sessions/${queryArg.sessionId}/attachments/${queryArg.attachmentId}`,
        method: "DELETE",
      }),
    }),
    postPrepareRuntimeAgentExecutionControlPlaneV1TeamsTeamIdRuntimesRuntimeIdAgentsAgentIdPrepareExecutionPost:
      build.mutation<
        PostPrepareRuntimeAgentExecutionControlPlaneV1TeamsTeamIdRuntimesRuntimeIdAgentsAgentIdPrepareExecutionPostApiResponse,
        PostPrepareRuntimeAgentExecutionControlPlaneV1TeamsTeamIdRuntimesRuntimeIdAgentsAgentIdPrepareExecutionPostApiArg
      >({
        query: (queryArg) => ({
          url: `/control-plane/v1/teams/${queryArg.teamId}/runtimes/${queryArg.runtimeId}/agents/${queryArg.agentId}/prepare-execution`,
          method: "POST",
        }),
      }),
    postPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPost: build.mutation<
      PostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostApiResponse,
      PostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances/${queryArg.agentInstanceId}/prepare-execution`,
        method: "POST",
        params: {
          session_id: queryArg.sessionId,
        },
      }),
    }),
    bootstrapPlatformAdminControlPlaneV1BootstrapPlatformAdminPost: build.mutation<
      BootstrapPlatformAdminControlPlaneV1BootstrapPlatformAdminPostApiResponse,
      BootstrapPlatformAdminControlPlaneV1BootstrapPlatformAdminPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/bootstrap/platform-admin`,
        method: "POST",
        body: queryArg.bootstrapPlatformAdminRequest,
      }),
    }),
    getAdminCapabilitiesControlPlaneV1AdminCapabilitiesGet: build.query<
      GetAdminCapabilitiesControlPlaneV1AdminCapabilitiesGetApiResponse,
      GetAdminCapabilitiesControlPlaneV1AdminCapabilitiesGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/admin/capabilities` }),
    }),
    getCapabilityRevokeImpactControlPlaneV1AdminCapabilitiesCapabilityIdRevokeImpactGet: build.query<
      GetCapabilityRevokeImpactControlPlaneV1AdminCapabilitiesCapabilityIdRevokeImpactGetApiResponse,
      GetCapabilityRevokeImpactControlPlaneV1AdminCapabilitiesCapabilityIdRevokeImpactGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/capabilities/${queryArg.capabilityId}/revoke-impact`,
        params: {
          team_id: queryArg.teamId,
        },
      }),
    }),
    putTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdPut: build.mutation<
      PutTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdPutApiResponse,
      PutTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdPutApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/capabilities/${queryArg.capabilityId}/teams/${queryArg.teamId}`,
        method: "PUT",
        body: queryArg.enableTeamCapabilityRequest,
      }),
    }),
    deleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDelete: build.mutation<
      DeleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDeleteApiResponse,
      DeleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/capabilities/${queryArg.capabilityId}/teams/${queryArg.teamId}`,
        method: "DELETE",
        params: {
          mode: queryArg.mode,
        },
      }),
    }),
    putCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPut: build.mutation<
      PutCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPutApiResponse,
      PutCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPutApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/capabilities/${queryArg.capabilityId}/default-on`,
        method: "PUT",
        body: queryArg.setCapabilityDefaultOnRequest,
      }),
    }),
    putCapabilityPersonalScopeControlPlaneV1AdminCapabilitiesCapabilityIdPersonalScopePut: build.mutation<
      PutCapabilityPersonalScopeControlPlaneV1AdminCapabilitiesCapabilityIdPersonalScopePutApiResponse,
      PutCapabilityPersonalScopeControlPlaneV1AdminCapabilitiesCapabilityIdPersonalScopePutApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/capabilities/${queryArg.capabilityId}/personal-scope`,
        method: "PUT",
        body: queryArg.setCapabilityPersonalScopeRequest,
      }),
    }),
    patchCapabilityReasoningControlPlaneV1AdminCapabilitiesCapabilityIdReasoningPatch: build.mutation<
      PatchCapabilityReasoningControlPlaneV1AdminCapabilitiesCapabilityIdReasoningPatchApiResponse,
      PatchCapabilityReasoningControlPlaneV1AdminCapabilitiesCapabilityIdReasoningPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/capabilities/${queryArg.capabilityId}/reasoning`,
        method: "PATCH",
        body: queryArg.setModelReasoningRequest,
      }),
    }),
    getTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGet: build.query<
      GetTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGetApiResponse,
      GetTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/routing-policy` }),
    }),
    updateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatch: build.mutation<
      UpdateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatchApiResponse,
      UpdateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/routing-policy`,
        method: "PATCH",
        body: queryArg.updateTeamRoutingPolicyRequest,
      }),
    }),
    getAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGet: build.query<
      GetAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGetApiResponse,
      GetAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/routing-policy/available-models` }),
    }),
    getEffectiveChatModelControlPlaneV1TeamsTeamIdRoutingPolicyEffectiveChatModelGet: build.query<
      GetEffectiveChatModelControlPlaneV1TeamsTeamIdRoutingPolicyEffectiveChatModelGetApiResponse,
      GetEffectiveChatModelControlPlaneV1TeamsTeamIdRoutingPolicyEffectiveChatModelGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/routing-policy/effective-chat-model`,
        params: {
          agent_instance_id: queryArg.agentInstanceId,
        },
      }),
    }),
    getPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsGet: build.query<
      GetPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsGetApiResponse,
      GetPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/admin/platform/model-bindings` }),
    }),
    putPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsPut: build.mutation<
      PutPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsPutApiResponse,
      PutPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsPutApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/platform/model-bindings`,
        method: "PUT",
        body: queryArg.setPlatformModelBindingRequest,
      }),
    }),
    deletePlatformModelBindingControlPlaneV1AdminPlatformModelBindingsDelete: build.mutation<
      DeletePlatformModelBindingControlPlaneV1AdminPlatformModelBindingsDeleteApiResponse,
      DeletePlatformModelBindingControlPlaneV1AdminPlatformModelBindingsDeleteApiArg
    >({
      query: () => ({ url: `/control-plane/v1/admin/platform/model-bindings`, method: "DELETE" }),
    }),
    startTaskControlPlaneV1TasksPost: build.mutation<
      StartTaskControlPlaneV1TasksPostApiResponse,
      StartTaskControlPlaneV1TasksPostApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/tasks`, method: "POST", body: queryArg.body }),
    }),
    listTasksControlPlaneV1TasksGet: build.query<
      ListTasksControlPlaneV1TasksGetApiResponse,
      ListTasksControlPlaneV1TasksGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/tasks`,
        params: {
          scope: queryArg.scope,
          team_id: queryArg.teamId,
          kind: queryArg.kind,
          state: queryArg.state,
        },
      }),
    }),
    streamTaskEventsControlPlaneV1TasksTaskIdEventsGet: build.query<
      StreamTaskEventsControlPlaneV1TasksTaskIdEventsGetApiResponse,
      StreamTaskEventsControlPlaneV1TasksTaskIdEventsGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/tasks/${queryArg.taskId}/events` }),
    }),
    cancelTaskControlPlaneV1TasksTaskIdCancelPost: build.mutation<
      CancelTaskControlPlaneV1TasksTaskIdCancelPostApiResponse,
      CancelTaskControlPlaneV1TasksTaskIdCancelPostApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/tasks/${queryArg.taskId}/cancel`, method: "POST" }),
    }),
    acknowledgeTaskControlPlaneV1TasksTaskIdAckPost: build.mutation<
      AcknowledgeTaskControlPlaneV1TasksTaskIdAckPostApiResponse,
      AcknowledgeTaskControlPlaneV1TasksTaskIdAckPostApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/tasks/${queryArg.taskId}/ack`, method: "POST" }),
    }),
    handlerControlPlaneV1KpiPresetsActiveUsersOverTimeGet: build.query<
      HandlerControlPlaneV1KpiPresetsActiveUsersOverTimeGetApiResponse,
      HandlerControlPlaneV1KpiPresetsActiveUsersOverTimeGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/active_users_over_time`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUniqueUsersTotalGet: build.query<
      HandlerControlPlaneV1KpiPresetsUniqueUsersTotalGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUniqueUsersTotalGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/unique_users_total`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsSessionsOverTimeGet: build.query<
      HandlerControlPlaneV1KpiPresetsSessionsOverTimeGetApiResponse,
      HandlerControlPlaneV1KpiPresetsSessionsOverTimeGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/sessions_over_time`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsMessagesOverTimeGet: build.query<
      HandlerControlPlaneV1KpiPresetsMessagesOverTimeGetApiResponse,
      HandlerControlPlaneV1KpiPresetsMessagesOverTimeGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/messages_over_time`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsSessionsByScopeGet: build.query<
      HandlerControlPlaneV1KpiPresetsSessionsByScopeGetApiResponse,
      HandlerControlPlaneV1KpiPresetsSessionsByScopeGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/sessions_by_scope`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsConversationsPerUserGet: build.query<
      HandlerControlPlaneV1KpiPresetsConversationsPerUserGetApiResponse,
      HandlerControlPlaneV1KpiPresetsConversationsPerUserGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/conversations_per_user`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsConversationDepthGet: build.query<
      HandlerControlPlaneV1KpiPresetsConversationDepthGetApiResponse,
      HandlerControlPlaneV1KpiPresetsConversationDepthGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/conversation_depth`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsAgentsPerUserGet: build.query<
      HandlerControlPlaneV1KpiPresetsAgentsPerUserGetApiResponse,
      HandlerControlPlaneV1KpiPresetsAgentsPerUserGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/agents_per_user`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsConversationsPerUserTrendGet: build.query<
      HandlerControlPlaneV1KpiPresetsConversationsPerUserTrendGetApiResponse,
      HandlerControlPlaneV1KpiPresetsConversationsPerUserTrendGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/conversations_per_user_trend`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsConversationDepthTrendGet: build.query<
      HandlerControlPlaneV1KpiPresetsConversationDepthTrendGetApiResponse,
      HandlerControlPlaneV1KpiPresetsConversationDepthTrendGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/conversation_depth_trend`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsAgentsPerUserTrendGet: build.query<
      HandlerControlPlaneV1KpiPresetsAgentsPerUserTrendGetApiResponse,
      HandlerControlPlaneV1KpiPresetsAgentsPerUserTrendGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/agents_per_user_trend`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsTopTeamsBySessionsGet: build.query<
      HandlerControlPlaneV1KpiPresetsTopTeamsBySessionsGetApiResponse,
      HandlerControlPlaneV1KpiPresetsTopTeamsBySessionsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/top_teams_by_sessions`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsAgentsTotalGet: build.query<
      HandlerControlPlaneV1KpiPresetsAgentsTotalGetApiResponse,
      HandlerControlPlaneV1KpiPresetsAgentsTotalGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/agents_total`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsAgentPromptLengthDistributionGet: build.query<
      HandlerControlPlaneV1KpiPresetsAgentPromptLengthDistributionGetApiResponse,
      HandlerControlPlaneV1KpiPresetsAgentPromptLengthDistributionGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/agent_prompt_length_distribution`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsTopAgentsByConversationsGet: build.query<
      HandlerControlPlaneV1KpiPresetsTopAgentsByConversationsGetApiResponse,
      HandlerControlPlaneV1KpiPresetsTopAgentsByConversationsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/top_agents_by_conversations`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsDocumentsTotalGet: build.query<
      HandlerControlPlaneV1KpiPresetsDocumentsTotalGetApiResponse,
      HandlerControlPlaneV1KpiPresetsDocumentsTotalGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/documents_total`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserSessionsTotalGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserSessionsTotalGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserSessionsTotalGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_sessions_total`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserMessagesTotalGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserMessagesTotalGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserMessagesTotalGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_messages_total`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserAgentsUsedTotalGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserAgentsUsedTotalGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserAgentsUsedTotalGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_agents_used_total`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserTopAgentsGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserTopAgentsGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserTopAgentsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_top_agents`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserTopTeamsGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserTopTeamsGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserTopTeamsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_top_teams`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserRecentAgentsGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserRecentAgentsGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserRecentAgentsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_recent_agents`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserTokenUsageOverTimeGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserTokenUsageOverTimeGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserTokenUsageOverTimeGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_token_usage_over_time`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserTokenUsageByAgentGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserTokenUsageByAgentGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserTokenUsageByAgentGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_token_usage_by_agent`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsUserTokenUsageByModelGet: build.query<
      HandlerControlPlaneV1KpiPresetsUserTokenUsageByModelGetApiResponse,
      HandlerControlPlaneV1KpiPresetsUserTokenUsageByModelGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/user_token_usage_by_model`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsTokenUsageOverTimeGet: build.query<
      HandlerControlPlaneV1KpiPresetsTokenUsageOverTimeGetApiResponse,
      HandlerControlPlaneV1KpiPresetsTokenUsageOverTimeGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/token_usage_over_time`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsTokenUsageByAgentGet: build.query<
      HandlerControlPlaneV1KpiPresetsTokenUsageByAgentGetApiResponse,
      HandlerControlPlaneV1KpiPresetsTokenUsageByAgentGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/token_usage_by_agent`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsTokenUsageByModelGet: build.query<
      HandlerControlPlaneV1KpiPresetsTokenUsageByModelGetApiResponse,
      HandlerControlPlaneV1KpiPresetsTokenUsageByModelGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/token_usage_by_model`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    handlerControlPlaneV1KpiPresetsStorageByTeamGet: build.query<
      HandlerControlPlaneV1KpiPresetsStorageByTeamGetApiResponse,
      HandlerControlPlaneV1KpiPresetsStorageByTeamGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kpi/presets/storage_by_team`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
          team_id: queryArg.teamId,
        },
      }),
    }),
    createCampaignControlPlaneV1EvaluationCampaignsPost: build.mutation<
      CreateCampaignControlPlaneV1EvaluationCampaignsPostApiResponse,
      CreateCampaignControlPlaneV1EvaluationCampaignsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/evaluation-campaigns`,
        method: "POST",
        body: queryArg.createEvaluationCampaignRequest,
      }),
    }),
    listCampaignsControlPlaneV1EvaluationCampaignsGet: build.query<
      ListCampaignsControlPlaneV1EvaluationCampaignsGetApiResponse,
      ListCampaignsControlPlaneV1EvaluationCampaignsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/evaluation-campaigns`,
        params: {
          team_id: queryArg.teamId,
        },
      }),
    }),
    getCampaignControlPlaneV1EvaluationCampaignsCampaignIdGet: build.query<
      GetCampaignControlPlaneV1EvaluationCampaignsCampaignIdGetApiResponse,
      GetCampaignControlPlaneV1EvaluationCampaignsCampaignIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/evaluation-campaigns/${queryArg.campaignId}` }),
    }),
    listCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGet: build.query<
      ListCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGetApiResponse,
      ListCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/evaluation-campaigns/${queryArg.campaignId}/cases`,
        params: {
          offset: queryArg.offset,
          limit: queryArg.limit,
        },
      }),
    }),
    getCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGet: build.query<
      GetCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGetApiResponse,
      GetCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/evaluation-campaigns/${queryArg.campaignId}/cases/${queryArg.caseId}`,
      }),
    }),
    importSnapshotControlPlaneV1ImportExportImportPost: build.mutation<
      ImportSnapshotControlPlaneV1ImportExportImportPostApiResponse,
      ImportSnapshotControlPlaneV1ImportExportImportPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/import-export/import`,
        method: "POST",
        body: queryArg.bodyImportSnapshotControlPlaneV1ImportExportImportPost,
      }),
    }),
    exportSnapshotControlPlaneV1ImportExportExportGet: build.query<
      ExportSnapshotControlPlaneV1ImportExportExportGetApiResponse,
      ExportSnapshotControlPlaneV1ImportExportExportGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/import-export/export` }),
    }),
    platformStatsControlPlaneV1ImportExportStatsGet: build.query<
      PlatformStatsControlPlaneV1ImportExportStatsGetApiResponse,
      PlatformStatsControlPlaneV1ImportExportStatsGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/import-export/stats` }),
    }),
    resetPlatformDataControlPlaneV1ImportExportResetPost: build.mutation<
      ResetPlatformDataControlPlaneV1ImportExportResetPostApiResponse,
      ResetPlatformDataControlPlaneV1ImportExportResetPostApiArg
    >({
      query: () => ({ url: `/control-plane/v1/import-export/reset`, method: "POST" }),
    }),
    resetPlatformRebacControlPlaneV1ImportExportResetRebacPost: build.mutation<
      ResetPlatformRebacControlPlaneV1ImportExportResetRebacPostApiResponse,
      ResetPlatformRebacControlPlaneV1ImportExportResetRebacPostApiArg
    >({
      query: () => ({ url: `/control-plane/v1/import-export/reset-rebac`, method: "POST" }),
    }),
    keaMigrationDryRunControlPlaneV1KeaMigrationDryRunPost: build.mutation<
      KeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPostApiResponse,
      KeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/kea-migration/dry-run`,
        method: "POST",
        body: queryArg.bodyKeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPost,
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as controlPlaneApi };
export type HealthzControlPlaneV1HealthzGetApiResponse = /** status 200 Successful Response */ HealthResponse;
export type HealthzControlPlaneV1HealthzGetApiArg = void;
export type ReadyControlPlaneV1ReadyGetApiResponse = /** status 200 Successful Response */ ReadyResponse;
export type ReadyControlPlaneV1ReadyGetApiArg = void;
export type GetPurgePolicySummaryControlPlaneV1PoliciesPurgeGetApiResponse =
  /** status 200 Successful Response */ PolicySummaryResponse;
export type GetPurgePolicySummaryControlPlaneV1PoliciesPurgeGetApiArg = void;
export type ResolvePurgeControlPlaneV1PoliciesPurgeResolvePostApiResponse =
  /** status 200 Successful Response */ PolicyEvaluationResult;
export type ResolvePurgeControlPlaneV1PoliciesPurgeResolvePostApiArg = {
  policyResolutionRequest: PolicyResolutionRequest;
};
export type TriggerLifecycleRunOnceControlPlaneV1LifecycleRunOncePostApiResponse =
  /** status 200 Successful Response */ WorkflowStartResponse;
export type TriggerLifecycleRunOnceControlPlaneV1LifecycleRunOncePostApiArg = {
  lifecycleManagerInput: LifecycleManagerInput;
};
export type ListUsersControlPlaneV1UsersGetApiResponse = /** status 200 Successful Response */ UserSummary[];
export type ListUsersControlPlaneV1UsersGetApiArg = void;
export type CreateUserControlPlaneV1UsersPostApiResponse = /** status 201 Successful Response */ UserSummary;
export type CreateUserControlPlaneV1UsersPostApiArg = {
  createUserRequest: CreateUserRequest;
};
export type GetUsersByIdsControlPlaneV1UsersByIdsGetApiResponse = /** status 200 Successful Response */ UserSummary[];
export type GetUsersByIdsControlPlaneV1UsersByIdsGetApiArg = {
  ids: string[];
};
export type ListPlatformRolesControlPlaneV1UsersPlatformRolesGetApiResponse =
  /** status 200 Successful Response */ PlatformRolesResponse;
export type ListPlatformRolesControlPlaneV1UsersPlatformRolesGetApiArg = void;
export type GrantPlatformRoleControlPlaneV1UsersUserIdPlatformRolesPostApiResponse = unknown;
export type GrantPlatformRoleControlPlaneV1UsersUserIdPlatformRolesPostApiArg = {
  userId: string;
  grantPlatformRoleRequest: GrantPlatformRoleRequest;
};
export type RevokePlatformRoleControlPlaneV1UsersUserIdPlatformRolesRelationDeleteApiResponse = unknown;
export type RevokePlatformRoleControlPlaneV1UsersUserIdPlatformRolesRelationDeleteApiArg = {
  userId: string;
  relation: PlatformRoleRelation;
};
export type DeleteUserControlPlaneV1UsersUserIdDeleteApiResponse = unknown;
export type DeleteUserControlPlaneV1UsersUserIdDeleteApiArg = {
  userId: string;
};
export type GetUserDetailsControlPlaneV1UserGetApiResponse = /** status 200 Successful Response */ UserDetails;
export type GetUserDetailsControlPlaneV1UserGetApiArg = void;
export type ValidateGcuControlPlaneV1GcuPostApiResponse = /** status 200 Successful Response */ any;
export type ValidateGcuControlPlaneV1GcuPostApiArg = void;
export type ListTeamsControlPlaneV1TeamsGetApiResponse = /** status 200 Successful Response */ Team[];
export type ListTeamsControlPlaneV1TeamsGetApiArg = void;
export type CreateTeamControlPlaneV1TeamsPostApiResponse = /** status 201 Successful Response */ TeamWithPermissions;
export type CreateTeamControlPlaneV1TeamsPostApiArg = {
  createTeamRequest: CreateTeamRequest;
};
export type ListAllTeamsControlPlaneV1TeamsAllGetApiResponse = /** status 200 Successful Response */ Team[];
export type ListAllTeamsControlPlaneV1TeamsAllGetApiArg = void;
export type GetTeamControlPlaneV1TeamsTeamIdGetApiResponse = /** status 200 Successful Response */ TeamWithPermissions;
export type GetTeamControlPlaneV1TeamsTeamIdGetApiArg = {
  teamId: string;
};
export type UpdateTeamControlPlaneV1TeamsTeamIdPatchApiResponse =
  /** status 200 Successful Response */ TeamWithPermissions;
export type UpdateTeamControlPlaneV1TeamsTeamIdPatchApiArg = {
  teamId: string;
  updateTeamRequest: UpdateTeamRequest;
};
export type DeleteTeamControlPlaneV1TeamsTeamIdDeleteApiResponse = unknown;
export type DeleteTeamControlPlaneV1TeamsTeamIdDeleteApiArg = {
  teamId: string;
};
export type JoinTeamControlPlaneV1TeamsTeamIdJoinPostApiResponse =
  /** status 200 Successful Response */ TeamWithPermissions;
export type JoinTeamControlPlaneV1TeamsTeamIdJoinPostApiArg = {
  teamId: string;
};
export type RescueTeamAdminControlPlaneV1TeamsTeamIdRescueAdminPostApiResponse = unknown;
export type RescueTeamAdminControlPlaneV1TeamsTeamIdRescueAdminPostApiArg = {
  teamId: string;
  rescueTeamAdminRequest: RescueTeamAdminRequest;
};
export type UploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPostApiResponse = unknown;
export type UploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPostApiArg = {
  teamId: string;
  bodyUploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPost: BodyUploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPost;
};
export type ListTeamMembersControlPlaneV1TeamsTeamIdMembersGetApiResponse =
  /** status 200 Successful Response */ TeamMember[];
export type ListTeamMembersControlPlaneV1TeamsTeamIdMembersGetApiArg = {
  teamId: string;
};
export type AddTeamMemberControlPlaneV1TeamsTeamIdMembersPostApiResponse = unknown;
export type AddTeamMemberControlPlaneV1TeamsTeamIdMembersPostApiArg = {
  teamId: string;
  addTeamMemberRequest: AddTeamMemberRequest;
};
export type SearchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGetApiResponse =
  /** status 200 Successful Response */ UserSummary[];
export type SearchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGetApiArg = {
  teamId: string;
  query: string;
};
export type RemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteApiResponse =
  /** status 202 Successful Response */ RemoveTeamMemberResponse;
export type RemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteApiArg = {
  teamId: string;
  userId: string;
};
export type GrantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPostApiResponse = unknown;
export type GrantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPostApiArg = {
  teamId: string;
  userId: string;
  grantTeamMemberRoleRequest: GrantTeamMemberRoleRequest;
};
export type RevokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDeleteApiResponse = unknown;
export type RevokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDeleteApiArg = {
  teamId: string;
  userId: string;
  relation: UserTeamRelation;
};
export type GetFrontendBootstrapControlPlaneV1FrontendBootstrapGetApiResponse =
  /** status 200 Successful Response */ FrontendBootstrap;
export type GetFrontendBootstrapControlPlaneV1FrontendBootstrapGetApiArg = void;
export type GetFrontendConfigControlPlaneV1FrontendConfigGetApiResponse =
  /** status 200 Successful Response */ FrontendConfig;
export type GetFrontendConfigControlPlaneV1FrontendConfigGetApiArg = void;
export type GetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetApiResponse =
  /** status 200 Successful Response */ AgentTemplateSummary[];
export type GetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetApiArg = {
  teamId: string;
  includeNonPublic?: boolean;
};
export type GetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetApiResponse =
  /** status 200 Successful Response */ ManagedAgentInstanceSummary[];
export type GetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetApiArg = {
  teamId: string;
};
export type PostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostApiResponse =
  /** status 201 Successful Response */ ManagedAgentInstanceSummary;
export type PostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostApiArg = {
  teamId: string;
  createAgentInstanceRequest: CreateAgentInstanceRequest;
};
export type PatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchApiResponse =
  /** status 200 Successful Response */ ManagedAgentInstanceSummary;
export type PatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchApiArg = {
  teamId: string;
  agentInstanceId: string;
  updateAgentInstanceRequest: UpdateAgentInstanceRequest;
};
export type DeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteApiResponse = unknown;
export type DeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteApiArg = {
  teamId: string;
  agentInstanceId: string;
};
export type PostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPostApiResponse =
  /** status 201 Successful Response */ ManagedAgentInstanceSummary;
export type PostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPostApiArg = {
  teamId: string;
  bodyPostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPost: BodyPostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPost;
};
export type PatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatchApiResponse =
  /** status 200 Successful Response */ ManagedAgentInstanceSummary;
export type PatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatchApiArg =
  {
    teamId: string;
    agentInstanceId: string;
    bodyPatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatch: BodyPatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatch;
  };
export type GetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetApiResponse =
  /** status 200 Successful Response */ PromptSummary[];
export type GetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetApiArg = {
  teamId: string;
};
export type PostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostApiResponse =
  /** status 201 Successful Response */ PromptSummary;
export type PostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostApiArg = {
  teamId: string;
  createPromptRequest: CreatePromptRequest;
};
export type GetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetApiResponse =
  /** status 200 Successful Response */ ContextPromptSummary[];
export type GetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetApiArg = {
  teamId: string;
};
export type GetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetApiResponse =
  /** status 200 Successful Response */ PromptDetail;
export type GetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetApiArg = {
  teamId: string;
  promptId: string;
};
export type PutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutApiResponse =
  /** status 200 Successful Response */ PromptSummary;
export type PutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutApiArg = {
  teamId: string;
  promptId: string;
  updatePromptRequest: UpdatePromptRequest;
};
export type DeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteApiResponse = unknown;
export type DeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteApiArg = {
  teamId: string;
  promptId: string;
};
export type PatchTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPatchApiResponse =
  /** status 200 Successful Response */ PromptSummary;
export type PatchTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPatchApiArg = {
  teamId: string;
  promptId: string;
  promptScoreUpdateRequest: PromptScoreUpdateRequest;
};
export type PostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostApiResponse = unknown;
export type PostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostApiArg = {
  teamId: string;
  promptId: string;
};
export type PostPromotePromptControlPlaneV1TeamsTeamIdPromptsPromptIdPromotePostApiResponse =
  /** status 201 Successful Response */ PromptSummary;
export type PostPromotePromptControlPlaneV1TeamsTeamIdPromptsPromptIdPromotePostApiArg = {
  teamId: string;
  promptId: string;
  promptPromoteRequest: PromptPromoteRequest;
};
export type PostPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPostApiResponse =
  /** status 200 Successful Response */ PromptSummary;
export type PostPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPostApiArg = {
  teamId: string;
  promptId: string;
};
export type PostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostApiResponse =
  /** status 200 Successful Response */ PromptSummary;
export type PostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostApiArg = {
  teamId: string;
  promptId: string;
};
export type GetMarketplacePromptsControlPlaneV1MarketplacePromptsGetApiResponse =
  /** status 200 Successful Response */ MarketplacePromptSummary[];
export type GetMarketplacePromptsControlPlaneV1MarketplacePromptsGetApiArg = void;
export type GetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetApiResponse =
  /** status 200 Successful Response */ MarketplacePromptDetail;
export type GetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetApiArg = {
  promptId: string;
};
export type PostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostApiResponse = unknown;
export type PostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostApiArg = {
  promptId: string;
};
export type PostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostApiResponse =
  /** status 200 Successful Response */ MarketplaceImportResponse;
export type PostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostApiArg = {
  promptId: string;
  marketplaceImportRequest: MarketplaceImportRequest;
};
export type GetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetApiResponse =
  /** status 200 Successful Response */ PromptCategorySummary[];
export type GetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetApiArg = {
  teamId: string;
};
export type PostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostApiResponse =
  /** status 201 Successful Response */ PromptCategorySummary;
export type PostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostApiArg = {
  teamId: string;
  createPromptCategoryRequest: CreatePromptCategoryRequest;
};
export type PutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutApiResponse =
  /** status 200 Successful Response */ PromptCategorySummary;
export type PutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutApiArg = {
  teamId: string;
  categoryId: string;
  updatePromptCategoryRequest: UpdatePromptCategoryRequest;
};
export type DeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteApiResponse = unknown;
export type DeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteApiArg = {
  teamId: string;
  categoryId: string;
};
export type GetTeamAgentInstanceRuntimeControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdRuntimeGetApiResponse =
  /** status 200 Successful Response */ ManagedAgentRuntimeBinding;
export type GetTeamAgentInstanceRuntimeControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdRuntimeGetApiArg = {
  teamId: string;
  agentInstanceId: string;
};
export type PostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostApiResponse =
  /** status 201 Successful Response */ SessionListItem;
export type PostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostApiArg = {
  teamId: string;
  createSessionRequest: CreateSessionRequest;
};
export type GetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetApiResponse =
  /** status 200 Successful Response */ SessionListItem[];
export type GetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetApiArg = {
  teamId: string;
};
export type GetMyInactiveSessionsControlPlaneV1MeInactiveSessionsGetApiResponse =
  /** status 200 Successful Response */ InactiveSessionsResponse;
export type GetMyInactiveSessionsControlPlaneV1MeInactiveSessionsGetApiArg = {
  inactiveDays?: number;
};
export type PostBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePostApiResponse =
  /** status 200 Successful Response */ BulkDeleteSessionsResponse;
export type PostBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePostApiArg = {
  bulkDeleteSessionsRequest: BulkDeleteSessionsRequest;
};
export type GetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetApiResponse =
  /** status 200 Successful Response */ SessionListItem;
export type GetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetApiArg = {
  teamId: string;
  sessionId: string;
};
export type PatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchApiResponse =
  /** status 200 Successful Response */ SessionListItem;
export type PatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchApiArg = {
  teamId: string;
  sessionId: string;
  updateSessionRequest: UpdateSessionRequest;
};
export type DeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteApiResponse = unknown;
export type DeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteApiArg = {
  teamId: string;
  sessionId: string;
};
export type GetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetApiResponse =
  /** status 200 Successful Response */ SessionAttachmentSummary[];
export type GetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetApiArg = {
  teamId: string;
  sessionId: string;
};
export type PostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostApiResponse =
  /** status 201 Successful Response */ SessionAttachmentSummary;
export type PostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostApiArg = {
  teamId: string;
  sessionId: string;
  createSessionAttachmentRequest: CreateSessionAttachmentRequest;
};
export type DeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteApiResponse =
  unknown;
export type DeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteApiArg = {
  teamId: string;
  sessionId: string;
  attachmentId: string;
};
export type PostPrepareRuntimeAgentExecutionControlPlaneV1TeamsTeamIdRuntimesRuntimeIdAgentsAgentIdPrepareExecutionPostApiResponse =
  /** status 200 Successful Response */ RuntimeAgentExecutionPreparation;
export type PostPrepareRuntimeAgentExecutionControlPlaneV1TeamsTeamIdRuntimesRuntimeIdAgentsAgentIdPrepareExecutionPostApiArg =
  {
    teamId: string;
    runtimeId: string;
    agentId: string;
  };
export type PostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostApiResponse =
  /** status 200 Successful Response */ ExecutionPreparation;
export type PostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostApiArg = {
  teamId: string;
  agentInstanceId: string;
  sessionId?: string | null;
};
export type BootstrapPlatformAdminControlPlaneV1BootstrapPlatformAdminPostApiResponse =
  /** status 200 Successful Response */ BootstrapPlatformAdminResponse;
export type BootstrapPlatformAdminControlPlaneV1BootstrapPlatformAdminPostApiArg = {
  bootstrapPlatformAdminRequest: BootstrapPlatformAdminRequest;
};
export type GetAdminCapabilitiesControlPlaneV1AdminCapabilitiesGetApiResponse =
  /** status 200 Successful Response */ CapabilityEnablementList;
export type GetAdminCapabilitiesControlPlaneV1AdminCapabilitiesGetApiArg = void;
export type GetCapabilityRevokeImpactControlPlaneV1AdminCapabilitiesCapabilityIdRevokeImpactGetApiResponse =
  /** status 200 Successful Response */ CapabilityImpactPreview;
export type GetCapabilityRevokeImpactControlPlaneV1AdminCapabilitiesCapabilityIdRevokeImpactGetApiArg = {
  capabilityId: string;
  /** Preview one team's disable. Omit for a platform-wide default-off preview. */
  teamId?: string | null;
};
export type PutTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdPutApiResponse =
  /** status 200 Successful Response */ TeamCapabilityEnablementResult;
export type PutTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdPutApiArg = {
  capabilityId: string;
  teamId: string;
  enableTeamCapabilityRequest: EnableTeamCapabilityRequest;
};
export type DeleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDeleteApiResponse =
  /** status 200 Successful Response */ TeamCapabilityEnablementResult;
export type DeleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDeleteApiArg = {
  capabilityId: string;
  teamId: string;
  /** `disable` writes an explicit opt-out (tri-state 'disabled'); `default` clears both the grant and the opt-out so the platform default applies (tri-state 'default'). Both suspend dependent instances when the team loses access. */
  mode?: "disable" | "default";
};
export type PutCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPutApiResponse =
  /** status 200 Successful Response */ CapabilityDefaultOnResult;
export type PutCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPutApiArg = {
  capabilityId: string;
  setCapabilityDefaultOnRequest: SetCapabilityDefaultOnRequest;
};
export type PutCapabilityPersonalScopeControlPlaneV1AdminCapabilitiesCapabilityIdPersonalScopePutApiResponse =
  /** status 200 Successful Response */ CapabilityPersonalScopeResult;
export type PutCapabilityPersonalScopeControlPlaneV1AdminCapabilitiesCapabilityIdPersonalScopePutApiArg = {
  capabilityId: string;
  setCapabilityPersonalScopeRequest: SetCapabilityPersonalScopeRequest;
};
export type PatchCapabilityReasoningControlPlaneV1AdminCapabilitiesCapabilityIdReasoningPatchApiResponse =
  /** status 200 Successful Response */ ModelReasoningResult;
export type PatchCapabilityReasoningControlPlaneV1AdminCapabilitiesCapabilityIdReasoningPatchApiArg = {
  capabilityId: string;
  setModelReasoningRequest: SetModelReasoningRequest;
};
export type GetTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGetApiResponse =
  /** status 200 Successful Response */ TeamRoutingPolicy;
export type GetTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGetApiArg = {
  teamId: string;
};
export type UpdateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatchApiResponse =
  /** status 200 Successful Response */ TeamRoutingPolicy;
export type UpdateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatchApiArg = {
  teamId: string;
  updateTeamRoutingPolicyRequest: UpdateTeamRoutingPolicyRequest;
};
export type GetAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGetApiResponse =
  /** status 200 Successful Response */ AvailableModelProfileList;
export type GetAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGetApiArg = {
  teamId: string;
};
export type GetEffectiveChatModelControlPlaneV1TeamsTeamIdRoutingPolicyEffectiveChatModelGetApiResponse =
  /** status 200 Successful Response */ EffectiveChatModel;
export type GetEffectiveChatModelControlPlaneV1TeamsTeamIdRoutingPolicyEffectiveChatModelGetApiArg = {
  teamId: string;
  agentInstanceId: string;
};
export type GetPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsGetApiResponse =
  /** status 200 Successful Response */ PlatformModelBinding;
export type GetPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsGetApiArg = void;
export type PutPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsPutApiResponse =
  /** status 200 Successful Response */ PlatformModelBinding;
export type PutPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsPutApiArg = {
  setPlatformModelBindingRequest: SetPlatformModelBindingRequest;
};
export type DeletePlatformModelBindingControlPlaneV1AdminPlatformModelBindingsDeleteApiResponse =
  /** status 200 Successful Response */ PlatformModelBinding;
export type DeletePlatformModelBindingControlPlaneV1AdminPlatformModelBindingsDeleteApiArg = void;
export type StartTaskControlPlaneV1TasksPostApiResponse = /** status 202 Successful Response */ StartTaskResponse;
export type StartTaskControlPlaneV1TasksPostApiArg = {
  body:
    | ({
        kind: "ingestion";
      } & StartIngestionRequest)
    | ({
        kind: "evaluation";
      } & StartEvaluationRequest)
    | ({
        kind: "migration";
      } & StartMigrationRequest)
    | ({
        kind: "erasure";
      } & StartErasureRequest);
};
export type ListTasksControlPlaneV1TasksGetApiResponse = /** status 200 Successful Response */ TaskListResponse;
export type ListTasksControlPlaneV1TasksGetApiArg = {
  scope?: string;
  teamId?: string | null;
  kind?: string | null;
  state?: string | null;
};
export type StreamTaskEventsControlPlaneV1TasksTaskIdEventsGetApiResponse = /** status 200 Successful Response */ any;
export type StreamTaskEventsControlPlaneV1TasksTaskIdEventsGetApiArg = {
  taskId: string;
};
export type CancelTaskControlPlaneV1TasksTaskIdCancelPostApiResponse = /** status 202 Successful Response */ {
  [key: string]: any;
};
export type CancelTaskControlPlaneV1TasksTaskIdCancelPostApiArg = {
  taskId: string;
};
export type AcknowledgeTaskControlPlaneV1TasksTaskIdAckPostApiResponse =
  /** status 200 Successful Response */ AcknowledgeTaskResponse;
export type AcknowledgeTaskControlPlaneV1TasksTaskIdAckPostApiArg = {
  taskId: string;
};
export type HandlerControlPlaneV1KpiPresetsActiveUsersOverTimeGetApiResponse =
  /** status 200 Successful Response */ TimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsActiveUsersOverTimeGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUniqueUsersTotalGetApiResponse =
  /** status 200 Successful Response */ ScalarResponse;
export type HandlerControlPlaneV1KpiPresetsUniqueUsersTotalGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsSessionsOverTimeGetApiResponse =
  /** status 200 Successful Response */ TimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsSessionsOverTimeGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsMessagesOverTimeGetApiResponse =
  /** status 200 Successful Response */ TimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsMessagesOverTimeGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsSessionsByScopeGetApiResponse =
  /** status 200 Successful Response */ LabelValueResponse;
export type HandlerControlPlaneV1KpiPresetsSessionsByScopeGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsConversationsPerUserGetApiResponse =
  /** status 200 Successful Response */ DistributionResponse;
export type HandlerControlPlaneV1KpiPresetsConversationsPerUserGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsConversationDepthGetApiResponse =
  /** status 200 Successful Response */ DistributionResponse;
export type HandlerControlPlaneV1KpiPresetsConversationDepthGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsAgentsPerUserGetApiResponse =
  /** status 200 Successful Response */ DistributionResponse;
export type HandlerControlPlaneV1KpiPresetsAgentsPerUserGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsConversationsPerUserTrendGetApiResponse =
  /** status 200 Successful Response */ TimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsConversationsPerUserTrendGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsConversationDepthTrendGetApiResponse =
  /** status 200 Successful Response */ TimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsConversationDepthTrendGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsAgentsPerUserTrendGetApiResponse =
  /** status 200 Successful Response */ TimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsAgentsPerUserTrendGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsTopTeamsBySessionsGetApiResponse =
  /** status 200 Successful Response */ LabelValueResponse;
export type HandlerControlPlaneV1KpiPresetsTopTeamsBySessionsGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsAgentsTotalGetApiResponse =
  /** status 200 Successful Response */ ScalarWithDeltaResponse;
export type HandlerControlPlaneV1KpiPresetsAgentsTotalGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsAgentPromptLengthDistributionGetApiResponse =
  /** status 200 Successful Response */ LabelValueResponse;
export type HandlerControlPlaneV1KpiPresetsAgentPromptLengthDistributionGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsTopAgentsByConversationsGetApiResponse =
  /** status 200 Successful Response */ MultiSeriesTimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsTopAgentsByConversationsGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsDocumentsTotalGetApiResponse =
  /** status 200 Successful Response */ ScalarWithDeltaResponse;
export type HandlerControlPlaneV1KpiPresetsDocumentsTotalGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserSessionsTotalGetApiResponse =
  /** status 200 Successful Response */ ScalarWithDeltaResponse;
export type HandlerControlPlaneV1KpiPresetsUserSessionsTotalGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserMessagesTotalGetApiResponse =
  /** status 200 Successful Response */ ScalarWithDeltaResponse;
export type HandlerControlPlaneV1KpiPresetsUserMessagesTotalGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserAgentsUsedTotalGetApiResponse =
  /** status 200 Successful Response */ ScalarWithDeltaResponse;
export type HandlerControlPlaneV1KpiPresetsUserAgentsUsedTotalGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserTopAgentsGetApiResponse =
  /** status 200 Successful Response */ UserTopAgentsResponse;
export type HandlerControlPlaneV1KpiPresetsUserTopAgentsGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserTopTeamsGetApiResponse =
  /** status 200 Successful Response */ LabelValueResponse;
export type HandlerControlPlaneV1KpiPresetsUserTopTeamsGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserRecentAgentsGetApiResponse =
  /** status 200 Successful Response */ UserRecentAgentsResponse;
export type HandlerControlPlaneV1KpiPresetsUserRecentAgentsGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserTokenUsageOverTimeGetApiResponse =
  /** status 200 Successful Response */ TimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsUserTokenUsageOverTimeGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserTokenUsageByAgentGetApiResponse =
  /** status 200 Successful Response */ LabelValueResponse;
export type HandlerControlPlaneV1KpiPresetsUserTokenUsageByAgentGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsUserTokenUsageByModelGetApiResponse =
  /** status 200 Successful Response */ LabelValueResponse;
export type HandlerControlPlaneV1KpiPresetsUserTokenUsageByModelGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsTokenUsageOverTimeGetApiResponse =
  /** status 200 Successful Response */ TimeSeriesResponse;
export type HandlerControlPlaneV1KpiPresetsTokenUsageOverTimeGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsTokenUsageByAgentGetApiResponse =
  /** status 200 Successful Response */ LabelValueResponse;
export type HandlerControlPlaneV1KpiPresetsTokenUsageByAgentGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsTokenUsageByModelGetApiResponse =
  /** status 200 Successful Response */ LabelValueResponse;
export type HandlerControlPlaneV1KpiPresetsTokenUsageByModelGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type HandlerControlPlaneV1KpiPresetsStorageByTeamGetApiResponse =
  /** status 200 Successful Response */ TeamStorageResponse;
export type HandlerControlPlaneV1KpiPresetsStorageByTeamGetApiArg = {
  /** Start of the time range (ISO 8601 datetime). Defaults to 30 days ago. */
  since?: string | null;
  /** End of the time range (ISO 8601 datetime). Defaults to now. */
  until?: string | null;
  /** Scope the query to one team instead of the whole platform. Requires can_read_members on that team. Only accepted for presets whose underlying data actually carries a team dimension — others reject it with 400. */
  teamId?: string | null;
};
export type CreateCampaignControlPlaneV1EvaluationCampaignsPostApiResponse =
  /** status 202 Successful Response */ CampaignCreatedResponse;
export type CreateCampaignControlPlaneV1EvaluationCampaignsPostApiArg = {
  createEvaluationCampaignRequest: CreateEvaluationCampaignRequest;
};
export type ListCampaignsControlPlaneV1EvaluationCampaignsGetApiResponse =
  /** status 200 Successful Response */ EvaluationCampaignListResponse;
export type ListCampaignsControlPlaneV1EvaluationCampaignsGetApiArg = {
  teamId: string;
};
export type GetCampaignControlPlaneV1EvaluationCampaignsCampaignIdGetApiResponse =
  /** status 200 Successful Response */ EvaluationCampaignResponse;
export type GetCampaignControlPlaneV1EvaluationCampaignsCampaignIdGetApiArg = {
  campaignId: string;
};
export type ListCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGetApiResponse =
  /** status 200 Successful Response */ EvaluationCaseListResponse;
export type ListCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGetApiArg = {
  campaignId: string;
  offset?: number;
  limit?: number;
};
export type GetCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGetApiResponse =
  /** status 200 Successful Response */ EvaluationCaseResponse;
export type GetCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGetApiArg = {
  campaignId: string;
  caseId: string;
};
export type ImportSnapshotControlPlaneV1ImportExportImportPostApiResponse =
  /** status 202 Successful Response */ ImportLaunchResponse;
export type ImportSnapshotControlPlaneV1ImportExportImportPostApiArg = {
  bodyImportSnapshotControlPlaneV1ImportExportImportPost: BodyImportSnapshotControlPlaneV1ImportExportImportPost;
};
export type ExportSnapshotControlPlaneV1ImportExportExportGetApiResponse = /** status 200 Successful Response */ any;
export type ExportSnapshotControlPlaneV1ImportExportExportGetApiArg = void;
export type PlatformStatsControlPlaneV1ImportExportStatsGetApiResponse =
  /** status 200 Successful Response */ PlatformStats;
export type PlatformStatsControlPlaneV1ImportExportStatsGetApiArg = void;
export type ResetPlatformDataControlPlaneV1ImportExportResetPostApiResponse =
  /** status 202 Successful Response */ ResetLaunchResponse;
export type ResetPlatformDataControlPlaneV1ImportExportResetPostApiArg = void;
export type ResetPlatformRebacControlPlaneV1ImportExportResetRebacPostApiResponse =
  /** status 202 Successful Response */ ResetLaunchResponse;
export type ResetPlatformRebacControlPlaneV1ImportExportResetRebacPostApiArg = void;
export type KeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPostApiResponse =
  /** status 200 Successful Response */ KeaDryRunResponse;
export type KeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPostApiArg = {
  bodyKeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPost: BodyKeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPost;
};
export type HealthResponse = {
  status?: "ok";
  service?: "control-plane";
};
export type ReadyResponse = {
  status?: "ready";
  service?: "control-plane";
  scheduler_enabled: boolean;
  loaded_config_file?: string | null;
  loaded_env_file?: string | null;
};
export type PurgeMode = "deferred_delete" | "immediate_delete";
export type PolicySummaryResponse = {
  mode: PurgeMode;
  retention: string;
  retention_seconds: number;
  cancel_on_rejoin: boolean;
  matched_rule_id?: string | null;
  matched_rule_specificity?: number;
  team_delete_grace?: string | null;
  max_idle?: string | null;
  default_rule_count: number;
  catalog_path: string;
};
export type PolicyEvaluationResult = {
  mode: PurgeMode;
  retention: string;
  retention_seconds: number;
  cancel_on_rejoin: boolean;
  matched_rule_id?: string | null;
  matched_rule_specificity?: number;
  team_delete_grace?: string | null;
  max_idle?: string | null;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: any;
  ctx?: object;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type LifecycleTrigger = "member_removed" | "member_rejoined" | "user_deleted";
export type PolicyResolutionRequest = {
  team_id?: string | null;
  trigger?: LifecycleTrigger;
};
export type SchedulerBackend = "temporal" | "memory";
export type LifecycleManagerResult = {
  scanned?: number;
  deleted?: number;
  dry_run_actions?: number;
};
export type WorkflowStartResponse = {
  status?: "queued" | "completed";
  backend: SchedulerBackend;
  workflow_id?: string | null;
  run_id?: string | null;
  result?: LifecycleManagerResult | null;
};
export type LifecycleManagerInput = {
  dry_run?: boolean;
  batch_size?: number;
};
export type UserSummary = {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
  username?: string | null;
  email?: string | null;
};
export type CreateUserRequest = {
  username: string;
  email: string;
  password: string;
  first_name?: string | null;
  last_name?: string | null;
  enabled?: boolean;
};
export type PlatformRoleRelation = "platform_admin" | "platform_observer";
export type PlatformRoleHolder = {
  user: UserSummary;
  relations: PlatformRoleRelation[];
  is_bootstrap_root?: boolean;
};
export type PlatformRolesResponse = {
  holders: PlatformRoleHolder[];
  caller_is_bootstrap_root: boolean;
};
export type GrantPlatformRoleRequest = {
  relation: PlatformRoleRelation;
};
export type GcuVersionsType = "v1";
export type UserTeamRelation = "team_admin" | "team_editor" | "team_analyst" | "team_member";
export type JoiningMode = "open" | "invite_only";
export type TeamVisibility = "public" | "private";
export type TeamPermission =
  | "can_read"
  | "can_update_info"
  | "can_update_resources"
  | "can_update_agents"
  | "can_read_members"
  | "can_administer_members"
  | "can_administer_editors"
  | "can_administer_analysts"
  | "can_administer_admins"
  | "can_read_conversations"
  | "can_use_team_agents"
  | "can_run_evaluations"
  | "can_manage_evaluation_corpus"
  | "can_read_conversations_for_evaluation";
export type RetentionFieldView = {
  platform_max?: string | null;
  team_value?: string | null;
  effective?: string | null;
  source: "platform" | "team";
  would_exceed?: boolean;
};
export type TeamRetentionView = {
  team_delete_grace: RetentionFieldView;
  max_idle: RetentionFieldView;
};
export type TeamWithPermissions = {
  id: string;
  name: string;
  member_count?: number | null;
  admins?: UserSummary[];
  is_member?: boolean;
  my_relations?: UserTeamRelation[];
  description?: string | null;
  joining_mode?: JoiningMode;
  visibility?: TeamVisibility;
  avatar_image_url?: string | null;
  max_resources_storage_size?: number | null;
  current_resources_storage_size?: number | null;
  permissions?: TeamPermission[];
  retention?: TeamRetentionView | null;
};
export type UserDetails = {
  cguValidated: GcuVersionsType | null;
  personalTeam: TeamWithPermissions;
  currentUser?: UserSummary | null;
};
export type Team = {
  id: string;
  name: string;
  member_count?: number | null;
  admins?: UserSummary[];
  is_member?: boolean;
  my_relations?: UserTeamRelation[];
  description?: string | null;
  joining_mode?: JoiningMode;
  visibility?: TeamVisibility;
  avatar_image_url?: string | null;
  max_resources_storage_size?: number | null;
  current_resources_storage_size?: number | null;
};
export type CreateTeamRequest = {
  name: string;
  initial_team_admin_ids: string[];
};
export type UpdateTeamRequest = {
  description?: string | null;
  joining_mode?: JoiningMode | null;
  visibility?: TeamVisibility | null;
  avatar_image_url?: string | null;
  team_delete_grace?: string | null;
  max_idle?: string | null;
};
export type RescueTeamAdminRequest = {
  user_id: string;
};
export type BodyUploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPost = {
  /** Avatar image file (max 5MB, JPEG/PNG/WebP) */
  file: string;
};
export type TeamMember = {
  type?: "user";
  relations: UserTeamRelation[];
  user: UserSummary;
};
export type AddTeamMemberRequest = {
  user_id: string;
  relation: UserTeamRelation;
};
export type RemoveTeamMemberResponse = {
  status?: "accepted";
  team_id: string;
  user_id: string;
  sessions_enqueued: number;
  scheduled_delete_at: string;
  policy_mode: string;
  retention_seconds: number;
  matched_rule_id?: string | null;
};
export type GrantTeamMemberRoleRequest = {
  relation: UserTeamRelation;
};
export type FrontendFeatureFlags = {
  enableK8Features?: boolean;
  enableElecWarfare?: boolean;
  /** Show Mon espace/Espace d'équipe/Agents tabs on the Resources page, not just Corpus d'équipe. */
  enableAllResourceSpaces?: boolean;
  /** Show the Information Systems (SI) team nav entry and page — rags-services CRUD (#2307). */
  enableInformationSystems?: boolean;
};
export type PermissionSummary = {
  /** OpenFGA-derived platform-admin flag (organization `can_manage_platform`). The single source of truth for gating admin-only UI surfaces — never derive admin UI access from Keycloak roles directly. */
  is_platform_admin?: boolean;
  /** OpenFGA-derived platform-observer flag (organization `platform_observer` relation, checked directly). Grants read-only platform observability surfaces without full platform-admin rights. */
  is_platform_observer?: boolean;
};
export type UploadWarning = {
  /** Visual severity variant of the banner. */
  severity?: "info" | "warning" | "error" | "success";
  /** Locale → message map (e.g. {"en": "...", "fr": "..."}). */
  messages?: {
    [key: string]: string;
  };
};
export type FrontendBootstrap = {
  current_user: UserSummary;
  active_team: TeamWithPermissions;
  available_teams?: Team[];
  gcu_version?: string | null;
  feature_flags: FrontendFeatureFlags;
  permissions: PermissionSummary;
  /** Deployer-configured banner for upload surfaces (document upload drawer, chat attachments), from `platform.frontend.upload_warning` (MIGR-01.01). `None` when the deployment configures none — the frontend then renders nothing. Deliberately on the authenticated bootstrap, not the pre-auth `FrontendConfig`: upload surfaces only render post-auth, and `FrontendConfig` stays minimal. */
  upload_warning?: UploadWarning | null;
};
export type FrontendUserAuthConfig = {
  enabled: boolean;
  realm_url?: string | null;
  client_id?: string | null;
};
export type InfoBannerLink = {
  /** Link target URL. */
  url: string;
  /** Locale → label map (e.g. {"en": "...", "fr": "..."}). */
  labels?: {
    [key: string]: string;
  };
};
export type InfoBanner = {
  /** Banner background CSS color. */
  color?: string;
  /** Seconds after which the banner hides itself, measured from app load. Omit for a persistent banner — the default. */
  auto_hide_seconds?: number | null;
  /** Locale → title map (e.g. {"en": "...", "fr": "..."}). */
  titles?: {
    [key: string]: string;
  };
  /** Locale → message map (e.g. {"en": "...", "fr": "..."}). */
  messages?: {
    [key: string]: string;
  };
  /** Links rendered on the right side of the banner. */
  links?: InfoBannerLink[];
};
export type FrontendConfig = {
  user_auth: FrontendUserAuthConfig;
  gcu_version?: string | null;
  /** Whether POST /bootstrap/platform-admin (AUTHZ-07) has ever succeeded on this deployment. True once the durable PlatformBootstrapStore marker is set, permanently — never re-derived from live OpenFGA state, so removing every platform_admin relation later does not flip this back to False (same rationale as BootstrapAlreadyCompletedError). Not sensitive: it reveals only 'has anyone ever bootstrapped this instance', never who, never the secret, never any identity — safe on this public/unauthenticated surface, same as gcu_version. */
  root_bootstrap_completed: boolean;
  /** The authoritative frontend gating decision for BootstrapGuard — true only when `security.user.enabled AND security.rebac.enabled AND NOT root_bootstrap_completed`. Deliberately distinct from `root_bootstrap_completed`, which stays the truthful durable historical marker and is never reinterpreted: on deployments where user authentication or ReBAC is disabled, `root_bootstrap_completed` is still False on a fresh database even though `POST /bootstrap/platform-admin` deliberately refuses with 503 there, so the frontend must not treat 'not completed' alone as 'must show the bootstrap page'. The frontend must gate on this field, not re-derive the ReBAC/auth predicate itself. */
  root_bootstrap_required: boolean;
  /** Deployer-configured global announcement banner, from `platform.frontend.info_banner`. `None` when the deployment configures none — the frontend then renders nothing. Deliberately on this public pre-auth surface, not the authenticated `FrontendBootstrap`: the banner shows on every page, including the GCU-acceptance and root-bootstrap screens, which render before `/frontend/bootstrap` can succeed. Carries only deployer-authored announcement content — never anything sensitive. */
  info_banner?: InfoBanner | null;
};
export type ManagedAgentUiHints = {
  multiline?: boolean;
  max_lines?: number;
  placeholder?: string | null;
  markdown?: boolean;
  textarea?: boolean;
  group?: string | null;
  hide?: boolean;
  widget?: string | null;
  visible_when?: string | null;
  advanced?: boolean;
};
export type ManagedAgentFieldSpec = {
  key: string;
  type: string;
  title: string;
  description?: string | null;
  description_by_lang?: {
    [key: string]: string;
  } | null;
  required?: boolean;
  default?: any | null;
  default_by_lang?: {
    [key: string]: string;
  } | null;
  enum?: string[] | null;
  min?: number | null;
  max?: number | null;
  pattern?: string | null;
  item_type?: string | null;
  ui?: ManagedAgentUiHints;
};
export type UiHints = {
  multiline?: boolean;
  max_lines?: number;
  placeholder?: string | null;
  markdown?: boolean;
  textarea?: boolean;
  group?: string | null;
  hide?: boolean;
  /** Names a frontend form widget to render this field instead of the type-derived default input. Resolved first against the owning capability plugin's `configWidgets` (custom widgets, AGENT-CAPABILITY-RFC §9 item 4, #1903), then against stock widgets — known stock ids: 'document_libraries' (library/document tree picker for an array of library tag ids). Unknown ids fall back to the default input, so older frontends degrade gracefully. */
  widget?: string | null;
  /** Key of a sibling field in the same form: this field is only shown while that sibling's effective value (current input or its declared default) is truthy. Display-only — the value is kept, and backends must not rely on the field being hidden. */
  visible_when?: string | null;
  /** Renders the field inside the form's collapsed 'Advanced settings' disclosure instead of the main section. Display-only. */
  advanced?: boolean;
};
export type FieldSpec = {
  key: string;
  type:
    | "string"
    | "text"
    | "text-multiline"
    | "number"
    | "integer"
    | "boolean"
    | "select"
    | "array"
    | "object"
    | "prompt"
    | "secret"
    | "url";
  title: string;
  description?: string | null;
  description_by_lang?: {
    [key: string]: string;
  } | null;
  required?: boolean;
  default?:
    | string
    | number
    | number
    | boolean
    | (string | number | number | boolean)[]
    | {
        [key: string]: string | number | number | boolean;
      }
    | null;
  default_by_lang?: {
    [key: string]: string;
  } | null;
  enum?: string[] | null;
  min?: number | null;
  max?: number | null;
  pattern?: string | null;
  item_type?:
    | (
        | "string"
        | "text"
        | "text-multiline"
        | "number"
        | "integer"
        | "boolean"
        | "select"
        | "array"
        | "object"
        | "prompt"
        | "secret"
        | "url"
      )
    | null;
  ui?: UiHints;
};
export type AssetSlot = {
  key: string;
  accepted_types: string[];
  min_count?: number;
  max_count?: number | null;
};
export type TeamScopePolicy = "default_on" | "admin_gated";
export type CapabilityCatalogEntry = {
  id: string;
  version: string;
  /** i18n key */
  name: string;
  /** i18n key */
  description: string;
  /** Material Symbols name; see CapabilityManifest.icon */
  icon: string;
  config_fields?: FieldSpec[];
  team_settings_fields?: FieldSpec[];
  assets?: AssetSlot[];
  team_scope?: TeamScopePolicy;
  kind?: "tool" | "agent" | "model";
  execution_models?: ("react" | "graph")[];
  route_base_url?: string | null;
  default_capability_ids?: string[];
  model_profile_ids?: string[];
  model_chat_profile_ids?: string[];
  model_thinking_profile_ids?: string[];
  model_display_name?: string | null;
};
export type AgentTemplateSummary = {
  template_id: string;
  source_runtime_id: string;
  source_agent_id: string;
  display_name: string;
  description: string;
  description_by_lang?: {
    [key: string]: string;
  } | null;
  category: string;
  tags?: string[];
  capabilities?: string[];
  team_instantiable?: boolean;
  status?: "available" | "unavailable";
  /** Tunable field descriptors declared by the template. The frontend renders these dynamically at enrollment time. Empty when the template declares no tunable fields. */
  default_tuning_fields?: ManagedAgentFieldSpec[];
  /** Capabilities installed on this template's source pod (#1974/#1978, RFC AGENT-CAPABILITY §3.8), aggregated from the pod's manifest advertisement. MCP servers surface here as ordinary capabilities keyed by their plain catalog server id (#1988). Drives the one Tools tab in agent creation; config_fields render through the metadata-driven form. */
  available_capabilities?: CapabilityCatalogEntry[];
};
export type SuspensionReason = "capability_unavailable" | "capability_access_revoked" | "capability_config_invalid";
export type ManagedAgentInstanceSummary = {
  agent_instance_id: string;
  team_id: string;
  template_id: string;
  display_name: string;
  description?: string | null;
  /** Short one-line summary of what this agent does, distinct from the longer `description` — shown on the agent card so a teammate can recall the agent's purpose without reading the full description. Server-set to `display_name` at enrollment until independently edited (#2076). */
  role: string;
  /** User-authored intended-use statement (purpose, target/impacted users, data handled, outputs, error impact) captured in the agent form's Engagement tab, used to screen for platform/organization risk (#2105). Empty for agents enrolled before #2105 until independently edited — required at creation and enforced by the agent edit form on save, but omittable on `UpdateAgentInstanceRequest` (like `role`) so partial updates such as the enable/disable toggle are unaffected. */
  usage_statement?: string;
  /** Whether this agent offers the per-question reasoning toggle in its chat composer (REASON-01 level 3). A plain agent property edited in the General section of the agent form, NOT a capability — reasoning is a property of how the model is called, not a tool the agent can use. False for every agent enrolled before REASON-01 until independently edited. */
  reasoning_enabled?: boolean;
  /** Whether a new conversation with this agent starts with the composer's reasoning toggle already ON (REASON-01 Amendment B). Only meaningful while `reasoning_enabled` is true — with no toggle offered there is nothing to preselect. The user can still switch it off per question. */
  reasoning_default_on?: boolean;
  status: "enabled" | "disabled";
  /** Platform-forced suspension reason (#1975, RFC §3.9), or null when the instance is not suspended. Distinct from `status` (the editor's enable/disable toggle): a suspended instance is hidden from chat-only members and shows editors a warning with a locked enable toggle. One of capability_unavailable / capability_access_revoked / capability_config_invalid. */
  suspension_reason?: SuspensionReason | null;
  created_at?: string | null;
  updated_at?: string | null;
  created_by?: string | null;
  /** Uid of the last user who edited the instance (#1952). Server-authoritative and read-only; null when the instance was never user-edited (seed/startup saves have no acting user). */
  updated_by?: string | null;
  /** Current user-set values for this instance's tunable fields. Keyed by ManagedAgentFieldSpec.key. Empty when no fields have been customised. */
  tuning_field_values?: {
    [key: string]:
      | string
      | number
      | number
      | boolean
      | (string | number | number | boolean)[]
      | {
          [key: string]: string | number | number | boolean;
        };
  };
  /** Capability activation policy for this instance (#1974). Null means inherit the template default selection; [] means no capabilities; a non-empty list means exactly that set. */
  selected_capability_ids?: string[] | null;
  /** Per-capability stored config envelopes ({'schema_version', 'config'}) keyed by capability id, as validated by the pod at save time. The edit form re-renders the capability's config_fields from the inner 'config' object. */
  capability_config?: {
    [key: string]: {
      [key: string]: any;
    };
  };
  /** ok when the pod is reachable at listing time; unavailable when the pod cannot be contacted. */
  runtime_status?: "ok" | "unavailable";
  /** Non-empty when stored MCP server IDs are absent from the live pod catalog. Admin must delete and recreate the instance to resolve. */
  catalog_warnings?: string[];
};
export type CreateAgentInstanceRequest = {
  /** Composite template identity: '{source_runtime_id}:{source_agent_id}'. Obtained from GET /teams/{team_id}/agent-templates. */
  template_id: string;
  display_name: string;
  description?: string | null;
  /** Optional short one-line summary of what this agent does. Defaults to `display_name` when omitted (#2076). */
  role?: string | null;
  /** Required intended-use statement (purpose, target/impacted users, data handled, outputs, error impact) — used to screen for platform/organization risk (#2105). Hard-required at creation, unlike the optional `role`. */
  usage_statement: string;
  /** Optional initial values for the template's tunable fields. Keys must match ManagedAgentFieldSpec.key values from the template. Unknown keys are ignored. Known values are validated against the declared field type and constraints. */
  tuning_field_values?: {
    [key: string]:
      | string
      | number
      | number
      | boolean
      | (string | number | number | boolean)[]
      | {
          [key: string]: string | number | number | boolean;
        };
  } | null;
  /** Optional capability activation policy (#1974). None means inherit the template default selection; [] means activate no capabilities; a non-empty list means activate exactly that set. IDs not advertised by the template's source pod are rejected with HTTP 422. */
  capability_ids?: string[] | null;
  /** Optional per-capability configuration values keyed by capability id (the capability's config_fields values). Each selected capability's slice is round-tripped to the source pod for validation; the pod-returned stored envelope is persisted verbatim. Values for unselected capabilities are ignored. */
  capability_config_values?: {
    [key: string]: {
      [key: string]: any;
    };
  } | null;
  /** Offer the per-question reasoning toggle in this agent's chat composer (REASON-01 level 3). A plain agent property alongside role/description — NOT a capability, because reasoning is a property of how the model is called rather than a tool the agent can use. Defaults to False: enabling it only makes the composer toggle appear, and the user still has to flip it per question. */
  reasoning_enabled?: boolean;
  /** Start every new conversation with this agent's reasoning toggle already ON (REASON-01 Amendment B). Read only when `reasoning_enabled` is true; it seeds the composer's initial value and nothing more — the user can switch it off for any question. Defaults to False, the platform behaviour before this field existed. */
  reasoning_default_on?: boolean;
};
export type UpdateAgentInstanceRequest = {
  display_name?: string | null;
  description?: string | null;
  /** Short one-line summary of what this agent does. Omit to leave the current role unchanged (#2076). */
  role?: string | null;
  /** Intended-use statement (#2105). Omit to leave the current value unchanged — same convention as `role`, so partial updates like the enable/disable toggle (which PATCHes only `status`) are not forced to resupply it. The agent edit form always submits it (enforced client-side, same as `display_name`), so in practice every full-form save keeps this current, including for agents enrolled before #2105 whose stored value starts out empty. */
  usage_statement?: string | null;
  /** Set to 'enabled' or 'disabled' to toggle the instance. None leaves the current status unchanged. */
  status?: ("enabled" | "disabled") | null;
  /** Replaces the stored field values for this instance. Keys must match ManagedAgentFieldSpec.key values frozen at enrollment. Unknown keys are ignored. Known values are validated against the declared field type and constraints. Omit the field to leave existing values unchanged; pass null to clear the stored agent tuning values. */
  tuning_field_values?: {
    [key: string]:
      | string
      | number
      | number
      | boolean
      | (string | number | number | boolean)[]
      | {
          [key: string]: string | number | number | boolean;
        };
  } | null;
  /** Replaces the capability activation policy (#1974). Omit to leave the current selection unchanged; pass null to reset to the template default; pass [] to deactivate all capabilities; pass a non-empty list to activate exactly that set. IDs not advertised by the source pod are rejected with HTTP 422. */
  capability_ids?: string[] | null;
  /** Replaces the per-capability configuration values (keyed by capability id). Omit to keep the stored configs; pass null to reset every selected capability to its defaults. Each selected capability's effective config is re-validated by the source pod and the returned stored envelope is persisted verbatim. */
  capability_config_values?: {
    [key: string]: {
      [key: string]: any;
    };
  } | null;
  /** Offer the per-question reasoning toggle in this agent's chat composer (REASON-01 level 3). Omit to leave the current setting unchanged — same convention as `role`, so a partial update such as the enable/disable toggle is not forced to resupply it. */
  reasoning_enabled?: boolean | null;
  /** Start new conversations with the reasoning toggle already ON (REASON-01 Amendment B). Omit to leave the current setting unchanged. Written independently of `reasoning_enabled`: withdrawing the offer leaves this value stored but inert, so re-offering reasoning restores the author's original default. */
  reasoning_default_on?: boolean | null;
};
export type BodyPostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPost = {
  /** CreateAgentInstanceRequest as a JSON object string */
  request: string;
  /** One '{capability_id}:{slot_key}' reference per uploaded file, aligned by index with asset_files. */
  asset_slots?: string[];
  asset_files?: string[];
};
export type BodyPatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatch =
  {
    /** UpdateAgentInstanceRequest as a JSON object string */
    request: string;
    /** One '{capability_id}:{slot_key}' reference per uploaded file, aligned by index with asset_files. */
    asset_slots?: string[];
    asset_files?: string[];
  };
export type PromptSummary = {
  id: string;
  name: string;
  description?: string | null;
  category_id?: string | null;
  emoji?: string | null;
  tags?: string[];
  text_preview?: string | null;
  created_by?: string | null;
  version?: number;
  published?: boolean;
  import_count?: number;
  session_count?: number;
  score?: number | null;
  avg_input_tokens?: number | null;
  avg_output_tokens?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};
export type CreatePromptRequest = {
  name: string;
  description?: string | null;
  category_id?: string | null;
  emoji?: string | null;
  tags?: string[];
  text: string;
};
export type ContextPromptSummary = {
  id: string;
  name: string;
  description?: string | null;
  scope: "personal" | "team";
  category_id?: string | null;
  version: number;
  session_count: number;
  score?: number | null;
};
export type PromptDetail = {
  id: string;
  name: string;
  description?: string | null;
  category_id?: string | null;
  emoji?: string | null;
  tags?: string[];
  text_preview?: string | null;
  created_by?: string | null;
  version?: number;
  published?: boolean;
  import_count?: number;
  session_count?: number;
  score?: number | null;
  avg_input_tokens?: number | null;
  avg_output_tokens?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  team_id: string;
  text: string;
};
export type UpdatePromptRequest = {
  name: string;
  description?: string | null;
  category_id?: string | null;
  emoji?: string | null;
  tags?: string[];
  text: string;
};
export type PromptScoreUpdateRequest = {
  score: number;
};
export type PromptPromoteRequest = {
  target_team_id: string;
};
export type MarketplacePromptSummary = {
  id: string;
  name: string;
  description?: string | null;
  category_id?: string | null;
  emoji?: string | null;
  tags?: string[];
  text_preview?: string | null;
  created_by?: string | null;
  version?: number;
  published?: boolean;
  import_count?: number;
  session_count?: number;
  score?: number | null;
  avg_input_tokens?: number | null;
  avg_output_tokens?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  team_id: string;
  team_name: string;
};
export type MarketplacePromptDetail = {
  id: string;
  name: string;
  description?: string | null;
  category_id?: string | null;
  emoji?: string | null;
  tags?: string[];
  text_preview?: string | null;
  created_by?: string | null;
  version?: number;
  published?: boolean;
  import_count?: number;
  session_count?: number;
  score?: number | null;
  avg_input_tokens?: number | null;
  avg_output_tokens?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  team_id: string;
  text: string;
  team_name: string;
};
export type MarketplaceImportResult = {
  team_id: string;
  prompt?: PromptSummary | null;
  error?: string | null;
};
export type MarketplaceImportResponse = {
  results: MarketplaceImportResult[];
};
export type MarketplaceImportRequest = {
  target_team_ids: string[];
};
export type PromptCategorySummary = {
  id: string;
  team_id: string;
  name: string;
  created_at?: string | null;
  updated_at?: string | null;
};
export type CreatePromptCategoryRequest = {
  name: string;
};
export type UpdatePromptCategoryRequest = {
  name: string;
};
export type ManagedAgentTuning = {
  role: string;
  description: string;
  /** User-authored statement of the intended use case for this agent instance (purpose, target users/impacted parties, data handled, outputs, error impact) — used to screen for platform/organization risk (#2105). Defaults to '' so pre-#2105 rows without this key in their stored tuning_json still deserialize; the product-facing requiredness is enforced by the API layer (CreateAgentInstanceRequest and the agent form), not by this default. */
  usage_statement?: string;
  tags?: string[];
  fields?: ManagedAgentFieldSpec[];
  /** Does this agent OFFER per-question reasoning (REASON-01 level 3, `MODEL-REASONING-ENABLEMENT-RFC.md` §6)? A first-class agent property, deliberately NOT a capability: reasoning is a property of how the model is called, not a tool the agent can use, so it belongs next to role/description rather than in the tool picker.
    
    True only means the chat composer OFFERS the toggle — it never turns reasoning on by itself. The user still has to flip it per question (level 4, default off), and a platform admin still has to have enabled the model's reasoning (level 2, a ceiling). */
  reasoning_enabled?: boolean;
  /** When this agent offers reasoning, does a NEW conversation start with the composer toggle already ON (REASON-01 Amendment B)? Seeds `params.default` on the emitted `reasoning_toggle` control; the user can still flip it off per question — this decides where the switch starts, never where it stays.
    
    Meaningless unless `reasoning_enabled` is True: with the offer off no control is emitted at all, so no default can apply. The value is kept rather than reset in that case, so an author who turns the offer back on recovers their choice.
    
    Defaults to False, matching the hardcoded default this field replaces: `AGENT-THINKING-API-RFC.md` Amendment C measured reasoning re-issuing duplicate tool calls on this stack, so starting ON is an opt-in an author makes deliberately. */
  reasoning_default_on?: boolean;
  /** Capability activation policy (#1974, RFC AGENT-CAPABILITY §3.8). None means inherit the template default selection; [] means activate no capabilities; a non-empty list means activate exactly that set. Validated at save time against the capabilities the instance's bound pod advertises (unknown ids -> HTTP 422). */
  selected_capability_ids?: string[] | null;
  /** Per-capability stored config keyed by capability id. Each slice is the pod-validated {'schema_version', 'config'} envelope returned by the pod's validate-config round-trip, persisted VERBATIM — opaque to control-plane; the pod is the schema authority (RFC §3.8). Asset binaries never appear here — only KF storage keys. */
  capability_config?: {
    [key: string]: {
      [key: string]: any;
    };
  };
  /** User-set agent tuning values keyed by ManagedAgentFieldSpec.key. Only keys present in `fields` are stored. Frozen snapshot — not re-merged when the template evolves. */
  values?: {
    [key: string]:
      | string
      | number
      | number
      | boolean
      | (string | number | number | boolean)[]
      | {
          [key: string]: string | number | number | boolean;
        };
  };
};
export type ModelBindingSettings = {
  base_url?: string | null;
  azure_endpoint?: string | null;
  azure_openai_api_version?: string | null;
  azure_ad_client_id?: string | null;
  azure_ad_client_scope?: string | null;
  azure_apim_base_url?: string | null;
  azure_apim_resource_path?: string | null;
  azure_tenant_id?: string | null;
  project?: string | null;
  location?: string | null;
  model_family?: ("mistral" | "llama" | "anthropic" | "claude") | null;
  temperature?: number | null;
  max_tokens?: number | null;
  top_p?: number | null;
  max_retries?: number | null;
  streaming?: boolean | null;
  stream_usage?: boolean | null;
  request_timeout?: number | null;
  reasoning_effort?: string | null;
};
export type ModelBinding = {
  provider: "anthropic" | "azure-apim" | "azure-openai" | "ollama" | "openai" | "vertex-ai" | "vertex-ai-model-garden";
  name: string;
  settings?: ModelBindingSettings;
};
export type ManagedAgentRuntimeBinding = {
  agent_instance_id: string;
  template_agent_id: string;
  display_name: string;
  owner_scope?: "team";
  owner_user_id?: string | null;
  owner_team_id: string;
  enabled?: boolean;
  tuning: ManagedAgentTuning;
  team_capability_settings?: {
    [key: string]: {
      [key: string]: any;
    };
  };
  reasoning_enabled_model_ids?: string[];
  platform_chat_model_binding?: ModelBinding | null;
};
export type SessionListItem = {
  session_id: string;
  team_id: string;
  agent_instance_id?: string | null;
  title?: string | null;
  /** Ordered prompt-library ids attached to this session as chat context (personal/team prompt UUIDs or 'default:{category}'). Empty when none are attached. Concatenated in order as conversation context at execution time. */
  context_prompt_ids?: string[];
  created_at?: string | null;
  updated_at?: string | null;
};
export type CreateSessionRequest = {
  /** Frontend-generated UUID. */
  session_id: string;
  agent_instance_id?: string | null;
  title?: string | null;
};
export type InactiveSessionItem = {
  session_id: string;
  team_id: string;
  title?: string | null;
  agent_name?: string | null;
  updated_at?: string | null;
};
export type InactiveSessionsResponse = {
  sessions: InactiveSessionItem[];
};
export type BulkDeleteSessionsResponse = {
  deleted: string[];
  failed: string[];
};
export type BulkDeleteSessionRef = {
  session_id: string;
  team_id: string;
};
export type BulkDeleteSessionsRequest = {
  sessions: BulkDeleteSessionRef[];
};
export type UpdateSessionRequest = {
  /** Frontend-observed last activity timestamp. Used only for control-plane session metadata freshness, not runtime message history. */
  updated_at?: string | null;
  /** Human-readable session title shown in the sidebar. */
  title?: string | null;
  /** Full ordered replacement set of prompt-library ids to attach as chat context (personal/team prompt UUIDs or 'default:{category}'). The server diffs against the current set: removed ids are detached, new ids attached, order rewritten. An empty list clears the context. Omit the field entirely to leave the context unchanged (e.g. on a freshness-only PATCH); a present null is treated as a clear. */
  context_prompt_ids?: string[] | null;
};
export type SessionAttachmentSummary = {
  attachment_id: string;
  name: string;
  mime?: string | null;
  size_bytes?: number | null;
  summary_md: string;
  document_uid?: string | null;
  storage_key?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};
export type CreateSessionAttachmentRequest = {
  attachment_id: string;
  name: string;
  mime?: string | null;
  size_bytes?: number | null;
  summary_md: string;
  document_uid?: string | null;
  storage_key?: string | null;
};
export type RuntimeAgentExecutionPreparation = {
  runtime_id: string;
  agent_id: string;
  team_id: string;
  /** Ingress-relative URL for POST /agents/evaluate. */
  evaluate_url: string;
};
export type ChatControlDescriptor = {
  capability_id: string;
  widget: string;
  params?: {
    [key: string]: any;
  } | null;
};
export type ExecutionPreparation = {
  agent_instance_id: string;
  team_id: string;
  runtime_id: string;
  execution_transport?: "sse";
  /** Ingress-relative URL for non-streaming execution. */
  execute_url: string;
  /** Ingress-relative URL for SSE streaming execution. */
  execute_stream_url: string;
  /** RFC 6570 Level 1 URI Template for runtime history. Example: /runtime/agents-v2/agents/sessions/{session_id}/messages */
  messages_url_template: string;
  supports_streaming?: boolean;
  supports_hitl?: boolean;
  supports_ui_parts?: boolean;
  /** Maximum Unicode code points accepted in one submitted chat message, as advertised by the selected runtime pod. Null when an older runtime does not publish the policy. */
  max_chat_input_chars?: number | null;
  /** Computed chat-time composer controls for this instance (CAPAB-01 #1976, RFC §3.3/§3.7), evaluated per capability on the pod at session prep and flattened in capability-registration then returned-list order. Supersedes the retired `effective_chat_options`: the composer resolves each `widget` id against the owning capability's plugin registry (§9) and silently skips unknown ids. Never persisted — a cache-aside projection of stored config. */
  chat_controls?: ChatControlDescriptor[];
  runtime_display_name?: string | null;
  max_session_idle_seconds?: number | null;
  /** Resolved text of the session's context prompt, if one is set. The runtime injects this as a conversation-level context. Null when no context prompt is configured for the session. */
  context_prompt_text?: string | null;
  /** Ingress-relative base URL of each selected capability's auto-mounted router, keyed by capability id (AGENT-CAPABILITY-RFC §9.1, #1979). The instance-bound (in-session) counterpart of the template catalog's route_base_url: the frontend calls these pod routes directly (no proxy), with the same bearer it already uses for execution. */
  capability_base_urls?: {
    [key: string]: string;
  };
  /** Team's default chat model profile id, resolved from its stored TeamRoutingPolicy at session prep (TEAM-ROUTING-POLICY-RFC.md §8.2, TEAM-05, #2118). Null when the team has no routing policy — the runtime then uses its own deployment default. The frontend folds this onto RuntimeContext exactly like context_prompt_text (same three-hop channel, same 'resolved once per session, not re-fetched per turn' contract). */
  chat_default_profile_id?: string | null;
  /** Team's per-agent model-profile overrides (agent_id -> profile_id), same resolution notes as chat_default_profile_id above. */
  agent_profile_overrides?: {
    [key: string]: string;
  };
  /** kind="model" capability ids whose reasoning a platform admin has switched on (REASON-01, `MODEL-REASONING-ENABLEMENT-RFC.md` §5.5). Resolved once here at session prep and folded onto RuntimeContext by the frontend, exactly like chat_default_profile_id — the same three-hop channel, deliberately not a per-turn lookup. GLOBAL, not per team: an activation ('does this model run with reasoning'), not a permission — per-team model access is untouched (§5.1). **Empty means no model reasons** (§5.6, off by default); the runtime strips the reasoning settings for every model absent from this list at client construction (§5.6.2). */
  reasoning_enabled_model_ids?: string[];
};
export type BootstrapPlatformAdminResponse = {
  /** Keycloak sub granted platform_admin — always the calling JWT's own sub, never an arbitrary third party (RFC Part 8, §42.2). */
  user_id: string;
  username: string;
};
export type BootstrapPlatformAdminRequest = {
  /** The one-time root-bootstrap secret. */
  token: string;
};
export type ImpactedInstanceSummary = {
  agent_instance_id: string;
  team_id: string;
  display_name: string;
};
export type CapabilityEnablementItem = {
  id: string;
  /** i18n key */
  name: string;
  version: string;
  icon: string;
  team_scope: TeamScopePolicy;
  /** Whether the platform-wide default_on marker is set. */
  default_on: boolean;
  /** Teams carrying an explicit `enabled` grant. */
  enabled_team_ids?: string[];
  /** Teams carrying an explicit `disabled` opt-out (the tri-state 'disabled' position). For a default_on capability it also subtracts from the inherited roster. */
  disabled_team_ids?: string[];
  /** Platform-wide team count — the denominator for a default_on capability's inherited access. Counts every team in the org, not just the ones the calling admin belongs to. */
  total_team_count?: number;
  /** Platform-wide personal-space count (= realm user count; one personal space per user) — the denominator for personal-class access (RFC §8.4), as total_team_count is for default_on. */
  total_personal_space_count?: number;
  /** Personal-space class position (RFC §8.4): `enabled` = usable by all personal spaces (`personal_on` tuple present); `disabled` = blocked for all personal spaces (`personal_disabled` present); `default` = neither, personal spaces follow `default_on` like any team. */
  personal_scope?: "enabled" | "disabled" | "default";
  /** The enable-with-settings form (rendered like config fields). */
  team_settings_fields?: FieldSpec[];
  /** "tool": a pod-advertised capability. "agent": a control-plane-side projection of an agent template into this same catalog (CAPAB-01, RFC §8.6) — every team's access to every agent is an explicit admin grant, exactly like a tool. "model": a pod-advertised projection of one models_catalog.yaml (provider, name) pair (OBSERV-02 v3, RFC §8.7). */
  kind?: "tool" | "agent" | "model";
  /** For a `kind="agent"` row: the template's default tool/MCP capability ids (RFC §8.6 `depends_on` gate, GitHub #2004 item 5). Enabling the agent for a team 409s unless each of these is already usable by that team - exposed so the admin UI can disable the grant up front and explain why (GitHub #2408). Always empty for `kind="tool"`/`"model"`. */
  default_capability_ids?: string[];
  /** Agent instances this capability breaks AT REST, across every team (#1975 health). DERIVED per request — `suspension_reason` records why an instance is suspended, never which capability did it, so an instance broken by capa1 while also selecting capa2 must not count against capa2. An instance is counted when it selects this capability AND its team lacks `can_use` on it OR its pod no longer advertises it. */
  suspended_instances?: number;
  /** Instances selecting this capability whose runtime pod was unreachable, so their health is UNKNOWN rather than broken. Kept separate from `suspended_instances`: the reconciliation sweep skips an unreachable pod rather than suspending on a transient outage (#1975, RFC §3.9), and this count reports the same way. */
  health_unknown_instances?: number;
  /** The agents behind `suspended_instances`, named for the health-column drill-down (which agents, in which team). Same derivation as the count — one entry per (instance, this capability) the instance is broken by at rest. Empty for a healthy capability; carries `team_id` so the admin surface can group by team. */
  suspended_instance_details?: ImpactedInstanceSummary[];
  /** For a `kind="model"` row: the models_catalog.yaml profile ids of this model that declare `supports_thinking` (REASON-01, `MODEL-REASONING-ENABLEMENT-RFC.md` §5.3). Always empty for other kinds. **The admin row renders a reasoning control only when this is non-empty** — aptitude is not an administrator's choice, nobody can make a model reason that cannot. */
  thinking_profile_ids?: string[];
  /** Whether this model's thinking-capable profiles may run with reasoning on, platform-wide (REASON-01 §5). GLOBAL, with no subject: an activation, not a permission — per-team model access remains the untouched ReBAC `can_use` axis (§5.1/§5.4). No stored row means `false` (§5.6): enabling a model and enabling its reasoning are two separate admin actions, in that order. */
  reasoning_enabled?: boolean;
};
export type CapabilityEnablementList = {
  items?: CapabilityEnablementItem[];
};
export type CapabilityImpactPreview = {
  capability_id: string;
  /** Agents that work today and would be suspended by this change. Excludes agents already broken by this capability — revoking it again does not newly break them. */
  suspended_instances?: number;
  /** Selecting instances whose pod is unreachable (impact unknown). */
  health_unknown_instances?: number;
  /** The affected agents, for the admin drill-down. */
  instances?: ImpactedInstanceSummary[];
};
export type TeamCapabilityEnablementResult = {
  capability_id: string;
  team_id: string;
  enabled: boolean;
  settings?: {
    [key: string]: any;
  };
  /** Dependent agent instances suspended by this change (#1975). */
  suspended_instances?: number;
  /** Dependent agent instances whose suspension this GRANT cleared (#1975). Only availability suspensions are cleared; an instance still missing another capability stays suspended, and a `capability_config_invalid` one is never touched here (RFC §3.9). */
  revived_instances?: number;
};
export type EnableTeamCapabilityRequest = {
  settings?: {
    [key: string]: any;
  };
};
export type CapabilityDefaultOnResult = {
  capability_id: string;
  default_on: boolean;
  suspended_instances?: number;
  /** Dependent instances revived by turning default-on ON (#1975). */
  revived_instances?: number;
  /** True when switching this model OFF also switched its reasoning off (REASON-01, MODEL-REASONING-ENABLEMENT-RFC.md §5.7). Reported so the admin sees the second state change instead of discovering it later in the row. */
  reasoning_disabled?: boolean;
};
export type SetCapabilityDefaultOnRequest = {
  default_on: boolean;
};
export type CapabilityPersonalScopeResult = {
  capability_id: string;
  scope: "enabled" | "disabled" | "default";
  /** Dependent PERSONAL-space instances suspended by this change (#1975). */
  suspended_instances?: number;
  /** Dependent PERSONAL-space instances whose suspension this GRANT cleared (#1975). Only availability suspensions are cleared; an instance still missing another capability stays suspended, and a `capability_config_invalid` one is never touched here (RFC §3.9). */
  revived_instances?: number;
};
export type SetCapabilityPersonalScopeRequest = {
  scope: "enabled" | "disabled" | "default";
};
export type ModelReasoningResult = {
  capability_id: string;
  reasoning_enabled: boolean;
};
export type SetModelReasoningRequest = {
  reasoning_enabled: boolean;
};
export type TeamRoutingPolicy = {
  team_id: string;
  version: number;
  chat_default_profile_id?: string | null;
  agent_profile_overrides?: {
    [key: string]: string;
  };
};
export type UpdateTeamRoutingPolicyRequest = {
  chat_default_profile_id?: string | null;
  agent_profile_overrides?: {
    [key: string]: string;
  };
};
export type AvailableModelProfile = {
  profile_id: string;
  capability_id: string;
  /** i18n key, same as CapabilityCatalogEntry.name */
  name: string;
};
export type AvailableModelProfileList = {
  profiles?: AvailableModelProfile[];
};
export type EffectiveChatModel = {
  /** The concrete model name. `capability_id` below identifies the `(provider, name)` pair uniquely for a caller that needs to join against team enablement or the models admin view. */
  name?: string | null;
  /** The ops-authored `model_display_name` for this model, when the pod catalog names one. `None` leaves the frontend on its name/id prettifying fallback — the same fallback the composer already had. */
  display_name?: string | null;
  /** The `(provider, name)`-keyed `kind="model"` capability id, so the caller can join this against team enablement and the models admin view. `None` for an unresolved model. */
  capability_id?: string | null;
  /** False when the resolved model is not `can_use`-enabled for this team, in which case the turn fails before the LLM call (`ModelNotUsableError`). Reported rather than hidden so the composer can say WHY a turn will fail instead of letting the user discover an opaque error — the same diagnosability rule REASON-01 §8 applies to the reasoning control. Always True for a platform binding, which bypasses team enablement by design: the operator is the authority on what is reachable. */
  enabled_for_team?: boolean;
  /** Whether reasoning actually runs on THIS model — i.e. whether a platform admin switched its reasoning on (REASON-01 §5). The composer must not offer the reasoning toggle when this is False: `RoutedChatModelFactory` STRIPS the reasoning settings for a model absent from `reasoning_enabled_model_ids` (§5.6.2), so the toggle would be inert and the turn would silently not reason.
    
    Needed because the reasoning control is emitted from the PLATFORM list — 'some model has reasoning on' — while routing may land on a different model entirely. With reasoning enabled on Mistral Small and a team override routing to Mistral Medium, the composer used to render 'Mistral Medium · Élevé' and offer the toggle while the pod ran no reasoning at all. */
  reasoning_enabled?: boolean;
};
export type PlatformModelBinding = {
  model_capability?: "chat";
  binding?: ModelBinding | null;
  updated_by?: string | null;
  updated_at?: string | null;
};
export type SetPlatformModelBindingRequest = {
  binding: ModelBinding;
};
export type StartTaskResponse = {
  task_id: string;
};
export type IngestionProcessingProfile = "fast" | "medium" | "rich";
export type StartIngestionParams = {
  resource_ids: string[];
  profile?: IngestionProcessingProfile;
};
export type StartIngestionRequest = {
  kind?: "ingestion";
  params: StartIngestionParams;
};
export type StartEvaluationParams = {
  campaign_id: string;
};
export type StartEvaluationRequest = {
  kind?: "evaluation";
  params: StartEvaluationParams;
};
export type StartMigrationRequest = {
  kind?: "migration";
};
export type ErasureReason = "user_deleted" | "member_removed" | "idle_expired";
export type StartErasureRequest = {
  kind?: "erasure";
  reason: ErasureReason;
};
export type TaskState = "pending" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled";
export type TaskTarget = {
  type: string;
  id: string;
  label: string;
};
export type RepairVectorMetadataResult = {
  source_tag: string;
  metadata_documents?: number;
  already_done?: number;
  eligible_with_vectors_and_content?: number;
  repaired?: number;
  missing_vectors?: number;
  missing_content?: number;
  tabular_excluded?: number;
  failed_or_running_excluded?: number;
  errors?: number;
};
export type IngestionDetail = {
  processed: number;
  total: number;
  failed: number;
  preview: number;
  vectorized: number;
  sql_indexed: number;
  result?: RepairVectorMetadataResult | null;
};
export type EvaluationDetail = {
  campaign_id: string;
  completed: number;
  total: number;
  passed: number;
  failed: number;
  execution_errors: number;
  scoring_errors: number;
};
export type TaskLogDetail = {
  level: "info" | "warn" | "error";
  message: string;
};
export type MigrationResult = {
  import_id: string;
  source_platform: string;
  identities_created?: number;
  users_processed?: number;
  users_skipped?: string[];
  teams_imported?: number;
  teams_skipped?: number;
  teams_provisioned?: number;
  team_roles_granted?: number;
  team_roles_skipped?: number;
  platform_roles_granted?: number;
  agents_imported?: number;
  agents_skipped?: number;
  agents_gap?: number;
  tags_imported?: number;
  tags_skipped?: number;
  docs_imported?: number;
  docs_skipped?: number;
  warnings?: string[];
};
export type MigrationDetail = {
  step_id: string;
  processed: number;
  total: number;
  failed: number;
  result?: MigrationResult | null;
};
export type ErasureDetail = {
  reason?: ErasureReason | null;
  stores_ok?: number;
  stores_total?: number;
  attempts?: number;
};
export type TaskSummary = {
  task_id: string;
  kind: string;
  state: TaskState;
  progress?: number | null;
  step?: string | null;
  error?: string | null;
  target?: TaskTarget | null;
  created_by?: string | null;
  team_id?: string | null;
  created_at: string;
  updated_at: string;
  scheduled_for?: string | null;
  detail?: IngestionDetail | EvaluationDetail | TaskLogDetail | MigrationDetail | ErasureDetail | null;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
};
export type TaskListResponse = {
  tasks: TaskSummary[];
};
export type AcknowledgeTaskResponse = {
  task_id: string;
  acknowledged_at: string;
  acknowledged_by: string | null;
};
export type TimeSeriesPoint = {
  date: string;
  value: number;
  co2e_grams?: number | null;
  kwh?: number | null;
  cost_usd?: number | null;
};
export type TimeSeriesResponse = {
  rows: TimeSeriesPoint[];
  since: string;
  until: string;
  interval: string;
  window?: string | null;
};
export type ScalarResponse = {
  value: number;
  since: string;
  until: string;
};
export type LabelValuePoint = {
  label: string;
  value: number;
  co2e_grams?: number | null;
  kwh?: number | null;
  cost_usd?: number | null;
};
export type LabelValueResponse = {
  rows: LabelValuePoint[];
  since: string;
  until: string;
};
export type DistributionResponse = {
  rows: LabelValuePoint[];
  median?: number | null;
  since: string;
  until: string;
};
export type ScalarWithDeltaResponse = {
  value?: number | null;
  delta?: number | null;
  unavailable?: boolean;
  since: string;
  until: string;
};
export type MultiSeriesPoint = {
  date: string;
  values: {
    [key: string]: number;
  };
};
export type MultiSeriesTimeSeriesResponse = {
  rows: MultiSeriesPoint[];
  series: string[];
  since: string;
  until: string;
  interval: string;
};
export type UserTopAgentRow = {
  agent_instance_id: string;
  agent_name: string;
  team_id?: string | null;
  value: number;
};
export type UserTopAgentsResponse = {
  rows: UserTopAgentRow[];
  since: string;
  until: string;
};
export type UserRecentAgentRow = {
  agent_instance_id: string;
  agent_name: string;
  team_id?: string | null;
  last_used: string;
};
export type UserRecentAgentsResponse = {
  rows: UserRecentAgentRow[];
  since: string;
  until: string;
};
export type TeamStorageRow = {
  team_id: string;
  label: string;
  used_bytes: number;
  quota_bytes?: number | null;
};
export type TeamStorageResponse = {
  rows: TeamStorageRow[];
  since: string;
  until: string;
};
export type CampaignCreatedResponse = {
  campaign_id: string;
  task_id: string | null;
  state: string;
};
export type ManagedInstanceTarget = {
  kind: "managed_instance";
  agent_instance_id: string;
};
export type RuntimeAgentTarget = {
  kind: "runtime_agent";
  runtime_id: string;
  agent_id: string;
};
export type EvaluationCaseInput = {
  external_id?: string | null;
  input: string;
  expected_output?: string | null;
  tags?: string[];
};
export type EvaluationDataset = {
  name: string;
  version?: string | null;
  cases: EvaluationCaseInput[];
};
export type EvaluationExecutionOptions = {
  max_concurrency?: number;
  case_timeout_seconds?: number;
};
export type CreateEvaluationCampaignRequest = {
  name: string;
  team_id: string;
  target: ManagedInstanceTarget | RuntimeAgentTarget;
  dataset: EvaluationDataset;
  profile?: string;
  judge_profile_id: string;
  execution?: EvaluationExecutionOptions;
};
export type EvaluationCampaignResponse = {
  schema_version?: "1";
  campaign_id: string;
  task_id: string | null;
  name: string;
  team_id: string;
  created_by: string;
  target: ManagedInstanceTarget | RuntimeAgentTarget;
  dataset_name: string;
  dataset_version: string | null;
  profile: string;
  judge_profile_id: string;
  operational_state: string;
  verdict: string;
  total_cases: number;
  completed_cases: number;
  passed_cases: number;
  failed_cases: number;
  execution_error_cases: number;
  scoring_error_cases: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};
export type EvaluationCampaignListResponse = {
  campaigns: EvaluationCampaignResponse[];
  total: number;
};
export type EvaluationMetricResultResponse = {
  name: string;
  provider: string;
  score: number | null;
  threshold: number | null;
  verdict: "passed" | "failed" | "skipped" | "error";
  explanation: string | null;
  error: string | null;
};
export type EvaluationCaseResponse = {
  case_id: string;
  campaign_id: string;
  external_id: string | null;
  status: string;
  outcome: string | null;
  verdict: string;
  input: string;
  expected_output: string | null;
  actual_output: string | null;
  profile: string | null;
  latency_ms: number | null;
  execution_error: string | null;
  scoring_errors: string[];
  metrics: EvaluationMetricResultResponse[];
  started_at: string | null;
  completed_at: string | null;
};
export type EvaluationCaseListResponse = {
  cases: EvaluationCaseResponse[];
  total: number;
};
export type ImportLaunchResponse = {
  task_id: string;
  import_id: string;
  target: TaskTarget;
};
export type BodyImportSnapshotControlPlaneV1ImportExportImportPost = {
  file: string;
  label?: string | null;
  realm_file?: string | null;
};
export type TeamStats = {
  team_id: string;
  name: string;
  admins: number;
  editors: number;
  analysts: number;
  members: number;
  total_members: number;
  agents: number;
  prompts: number;
};
export type PlatformStats = {
  teams: number;
  distinct_users: number;
  total_agents: number;
  total_prompts: number;
  per_team: TeamStats[];
};
export type ResetLaunchResponse = {
  task_id: string;
};
export type KeaUserResolutionView = {
  kea_sub: string;
  kea_username: string;
  outcome: string;
  swift_sub: string | null;
};
export type KeaDryRunResponse = {
  source_platform: string;
  agents_mapped: number;
  agents_ignored: number;
  agents_gap: number;
  agents_gap_templates: string[];
  teams_total: number;
  teams_orphan_dropped: string[];
  teams_admin_less: string[];
  users_matched: KeaUserResolutionView[];
  users_relinked: KeaUserResolutionView[];
  users_pending: KeaUserResolutionView[];
  team_member_grants_ready: number;
  team_member_grants_pending: number;
  platform_role_grants_ready: number;
  summary_lines: string[];
};
export type BodyKeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPost = {
  file: string;
  realm_file?: string | null;
};
export const {
  useHealthzControlPlaneV1HealthzGetQuery,
  useLazyHealthzControlPlaneV1HealthzGetQuery,
  useReadyControlPlaneV1ReadyGetQuery,
  useLazyReadyControlPlaneV1ReadyGetQuery,
  useGetPurgePolicySummaryControlPlaneV1PoliciesPurgeGetQuery,
  useLazyGetPurgePolicySummaryControlPlaneV1PoliciesPurgeGetQuery,
  useResolvePurgeControlPlaneV1PoliciesPurgeResolvePostMutation,
  useTriggerLifecycleRunOnceControlPlaneV1LifecycleRunOncePostMutation,
  useListUsersControlPlaneV1UsersGetQuery,
  useLazyListUsersControlPlaneV1UsersGetQuery,
  useCreateUserControlPlaneV1UsersPostMutation,
  useGetUsersByIdsControlPlaneV1UsersByIdsGetQuery,
  useLazyGetUsersByIdsControlPlaneV1UsersByIdsGetQuery,
  useListPlatformRolesControlPlaneV1UsersPlatformRolesGetQuery,
  useLazyListPlatformRolesControlPlaneV1UsersPlatformRolesGetQuery,
  useGrantPlatformRoleControlPlaneV1UsersUserIdPlatformRolesPostMutation,
  useRevokePlatformRoleControlPlaneV1UsersUserIdPlatformRolesRelationDeleteMutation,
  useDeleteUserControlPlaneV1UsersUserIdDeleteMutation,
  useGetUserDetailsControlPlaneV1UserGetQuery,
  useLazyGetUserDetailsControlPlaneV1UserGetQuery,
  useValidateGcuControlPlaneV1GcuPostMutation,
  useListTeamsControlPlaneV1TeamsGetQuery,
  useLazyListTeamsControlPlaneV1TeamsGetQuery,
  useCreateTeamControlPlaneV1TeamsPostMutation,
  useListAllTeamsControlPlaneV1TeamsAllGetQuery,
  useLazyListAllTeamsControlPlaneV1TeamsAllGetQuery,
  useGetTeamControlPlaneV1TeamsTeamIdGetQuery,
  useLazyGetTeamControlPlaneV1TeamsTeamIdGetQuery,
  useUpdateTeamControlPlaneV1TeamsTeamIdPatchMutation,
  useDeleteTeamControlPlaneV1TeamsTeamIdDeleteMutation,
  useJoinTeamControlPlaneV1TeamsTeamIdJoinPostMutation,
  useRescueTeamAdminControlPlaneV1TeamsTeamIdRescueAdminPostMutation,
  useUploadTeamAvatarControlPlaneV1TeamsTeamIdAvatarPostMutation,
  useListTeamMembersControlPlaneV1TeamsTeamIdMembersGetQuery,
  useLazyListTeamMembersControlPlaneV1TeamsTeamIdMembersGetQuery,
  useAddTeamMemberControlPlaneV1TeamsTeamIdMembersPostMutation,
  useSearchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGetQuery,
  useLazySearchCandidateTeamMembersControlPlaneV1TeamsTeamIdCandidateMembersGetQuery,
  useRemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteMutation,
  useGrantTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesPostMutation,
  useRevokeTeamMemberRoleControlPlaneV1TeamsTeamIdMembersUserIdRolesRelationDeleteMutation,
  useGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery,
  useLazyGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery,
  useGetFrontendConfigControlPlaneV1FrontendConfigGetQuery,
  useLazyGetFrontendConfigControlPlaneV1FrontendConfigGetQuery,
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  useLazyGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
  usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation,
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
  usePostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPostMutation,
  usePatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatchMutation,
  useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery,
  useLazyGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery,
  usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation,
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery,
  useLazyGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery,
  useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
  usePutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutMutation,
  useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation,
  usePatchTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPatchMutation,
  usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation,
  usePostPromotePromptControlPlaneV1TeamsTeamIdPromptsPromptIdPromotePostMutation,
  usePostPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPostMutation,
  usePostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostMutation,
  useGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery,
  useLazyGetMarketplacePromptsControlPlaneV1MarketplacePromptsGetQuery,
  useGetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetQuery,
  useLazyGetMarketplacePromptDetailControlPlaneV1MarketplacePromptsPromptIdGetQuery,
  usePostMarketplacePromptUseControlPlaneV1MarketplacePromptsPromptIdUsePostMutation,
  usePostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostMutation,
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery,
  useLazyGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery,
  usePostTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesPostMutation,
  usePutTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdPutMutation,
  useDeleteTeamPromptCategoryControlPlaneV1TeamsTeamIdPromptCategoriesCategoryIdDeleteMutation,
  useGetTeamAgentInstanceRuntimeControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdRuntimeGetQuery,
  useLazyGetTeamAgentInstanceRuntimeControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdRuntimeGetQuery,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
  useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery,
  useLazyGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery,
  useGetMyInactiveSessionsControlPlaneV1MeInactiveSessionsGetQuery,
  useLazyGetMyInactiveSessionsControlPlaneV1MeInactiveSessionsGetQuery,
  usePostBulkDeleteMySessionsControlPlaneV1MeSessionsBulkDeletePostMutation,
  useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  useLazyGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation,
  useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery,
  useLazyGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery,
  usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation,
  useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation,
  usePostPrepareRuntimeAgentExecutionControlPlaneV1TeamsTeamIdRuntimesRuntimeIdAgentsAgentIdPrepareExecutionPostMutation,
  usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation,
  useBootstrapPlatformAdminControlPlaneV1BootstrapPlatformAdminPostMutation,
  useGetAdminCapabilitiesControlPlaneV1AdminCapabilitiesGetQuery,
  useLazyGetAdminCapabilitiesControlPlaneV1AdminCapabilitiesGetQuery,
  useGetCapabilityRevokeImpactControlPlaneV1AdminCapabilitiesCapabilityIdRevokeImpactGetQuery,
  useLazyGetCapabilityRevokeImpactControlPlaneV1AdminCapabilitiesCapabilityIdRevokeImpactGetQuery,
  usePutTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdPutMutation,
  useDeleteTeamCapabilityControlPlaneV1AdminCapabilitiesCapabilityIdTeamsTeamIdDeleteMutation,
  usePutCapabilityDefaultOnControlPlaneV1AdminCapabilitiesCapabilityIdDefaultOnPutMutation,
  usePutCapabilityPersonalScopeControlPlaneV1AdminCapabilitiesCapabilityIdPersonalScopePutMutation,
  usePatchCapabilityReasoningControlPlaneV1AdminCapabilitiesCapabilityIdReasoningPatchMutation,
  useGetTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGetQuery,
  useLazyGetTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyGetQuery,
  useUpdateTeamRoutingPolicyControlPlaneV1TeamsTeamIdRoutingPolicyPatchMutation,
  useGetAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGetQuery,
  useLazyGetAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGetQuery,
  useGetEffectiveChatModelControlPlaneV1TeamsTeamIdRoutingPolicyEffectiveChatModelGetQuery,
  useLazyGetEffectiveChatModelControlPlaneV1TeamsTeamIdRoutingPolicyEffectiveChatModelGetQuery,
  useGetPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsGetQuery,
  useLazyGetPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsGetQuery,
  usePutPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsPutMutation,
  useDeletePlatformModelBindingControlPlaneV1AdminPlatformModelBindingsDeleteMutation,
  useStartTaskControlPlaneV1TasksPostMutation,
  useListTasksControlPlaneV1TasksGetQuery,
  useLazyListTasksControlPlaneV1TasksGetQuery,
  useStreamTaskEventsControlPlaneV1TasksTaskIdEventsGetQuery,
  useLazyStreamTaskEventsControlPlaneV1TasksTaskIdEventsGetQuery,
  useCancelTaskControlPlaneV1TasksTaskIdCancelPostMutation,
  useAcknowledgeTaskControlPlaneV1TasksTaskIdAckPostMutation,
  useHandlerControlPlaneV1KpiPresetsActiveUsersOverTimeGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsActiveUsersOverTimeGetQuery,
  useHandlerControlPlaneV1KpiPresetsUniqueUsersTotalGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUniqueUsersTotalGetQuery,
  useHandlerControlPlaneV1KpiPresetsSessionsOverTimeGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsSessionsOverTimeGetQuery,
  useHandlerControlPlaneV1KpiPresetsMessagesOverTimeGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsMessagesOverTimeGetQuery,
  useHandlerControlPlaneV1KpiPresetsSessionsByScopeGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsSessionsByScopeGetQuery,
  useHandlerControlPlaneV1KpiPresetsConversationsPerUserGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsConversationsPerUserGetQuery,
  useHandlerControlPlaneV1KpiPresetsConversationDepthGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsConversationDepthGetQuery,
  useHandlerControlPlaneV1KpiPresetsAgentsPerUserGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsAgentsPerUserGetQuery,
  useHandlerControlPlaneV1KpiPresetsConversationsPerUserTrendGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsConversationsPerUserTrendGetQuery,
  useHandlerControlPlaneV1KpiPresetsConversationDepthTrendGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsConversationDepthTrendGetQuery,
  useHandlerControlPlaneV1KpiPresetsAgentsPerUserTrendGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsAgentsPerUserTrendGetQuery,
  useHandlerControlPlaneV1KpiPresetsTopTeamsBySessionsGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsTopTeamsBySessionsGetQuery,
  useHandlerControlPlaneV1KpiPresetsAgentsTotalGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsAgentsTotalGetQuery,
  useHandlerControlPlaneV1KpiPresetsAgentPromptLengthDistributionGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsAgentPromptLengthDistributionGetQuery,
  useHandlerControlPlaneV1KpiPresetsTopAgentsByConversationsGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsTopAgentsByConversationsGetQuery,
  useHandlerControlPlaneV1KpiPresetsDocumentsTotalGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsDocumentsTotalGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserSessionsTotalGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserSessionsTotalGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserMessagesTotalGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserMessagesTotalGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserAgentsUsedTotalGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserAgentsUsedTotalGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserTopAgentsGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserTopAgentsGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserTopTeamsGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserTopTeamsGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserRecentAgentsGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserRecentAgentsGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserTokenUsageOverTimeGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserTokenUsageOverTimeGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserTokenUsageByAgentGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserTokenUsageByAgentGetQuery,
  useHandlerControlPlaneV1KpiPresetsUserTokenUsageByModelGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsUserTokenUsageByModelGetQuery,
  useHandlerControlPlaneV1KpiPresetsTokenUsageOverTimeGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsTokenUsageOverTimeGetQuery,
  useHandlerControlPlaneV1KpiPresetsTokenUsageByAgentGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsTokenUsageByAgentGetQuery,
  useHandlerControlPlaneV1KpiPresetsTokenUsageByModelGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsTokenUsageByModelGetQuery,
  useHandlerControlPlaneV1KpiPresetsStorageByTeamGetQuery,
  useLazyHandlerControlPlaneV1KpiPresetsStorageByTeamGetQuery,
  useCreateCampaignControlPlaneV1EvaluationCampaignsPostMutation,
  useListCampaignsControlPlaneV1EvaluationCampaignsGetQuery,
  useLazyListCampaignsControlPlaneV1EvaluationCampaignsGetQuery,
  useGetCampaignControlPlaneV1EvaluationCampaignsCampaignIdGetQuery,
  useLazyGetCampaignControlPlaneV1EvaluationCampaignsCampaignIdGetQuery,
  useListCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGetQuery,
  useLazyListCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGetQuery,
  useGetCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGetQuery,
  useLazyGetCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGetQuery,
  useImportSnapshotControlPlaneV1ImportExportImportPostMutation,
  useExportSnapshotControlPlaneV1ImportExportExportGetQuery,
  useLazyExportSnapshotControlPlaneV1ImportExportExportGetQuery,
  usePlatformStatsControlPlaneV1ImportExportStatsGetQuery,
  useLazyPlatformStatsControlPlaneV1ImportExportStatsGetQuery,
  useResetPlatformDataControlPlaneV1ImportExportResetPostMutation,
  useResetPlatformRebacControlPlaneV1ImportExportResetRebacPostMutation,
  useKeaMigrationDryRunControlPlaneV1KeaMigrationDryRunPostMutation,
} = injectedRtkApi;
