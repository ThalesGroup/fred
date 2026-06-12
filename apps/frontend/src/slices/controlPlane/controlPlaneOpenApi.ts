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
    uploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost: build.mutation<
      UploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostApiResponse,
      UploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/banner`,
        method: "POST",
        body: queryArg.bodyUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost,
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
    removeTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDelete: build.mutation<
      RemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteApiResponse,
      RemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/members/${queryArg.userId}`,
        method: "DELETE",
      }),
    }),
    updateTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdPatch: build.mutation<
      UpdateTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdPatchApiResponse,
      UpdateTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/members/${queryArg.userId}`,
        method: "PATCH",
        body: queryArg.updateTeamMemberRequest,
      }),
    }),
    getFrontendBootstrapControlPlaneV1FrontendBootstrapGet: build.query<
      GetFrontendBootstrapControlPlaneV1FrontendBootstrapGetApiResponse,
      GetFrontendBootstrapControlPlaneV1FrontendBootstrapGetApiArg
    >({
      query: () => ({ url: `/control-plane/v1/frontend/bootstrap` }),
    }),
    getTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGet: build.query<
      GetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetApiResponse,
      GetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/teams/${queryArg.teamId}/agent-templates` }),
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
    getTeamPromptsControlPlaneV1TeamsTeamIdPromptsGet: build.query<
      GetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetApiResponse,
      GetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts`,
        params: {
          lang: queryArg.lang,
        },
      }),
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
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/prompts/context`,
        params: {
          lang: queryArg.lang,
        },
      }),
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
    getAgentInstanceRuntimeControlPlaneV1AgentInstancesAgentInstanceIdRuntimeGet: build.query<
      GetAgentInstanceRuntimeControlPlaneV1AgentInstancesAgentInstanceIdRuntimeGetApiResponse,
      GetAgentInstanceRuntimeControlPlaneV1AgentInstancesAgentInstanceIdRuntimeGetApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/agent-instances/${queryArg.agentInstanceId}/runtime` }),
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
    postPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPost: build.mutation<
      PostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostApiResponse,
      PostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/teams/${queryArg.teamId}/agent-instances/${queryArg.agentInstanceId}/prepare-execution`,
        method: "POST",
        params: {
          session_id: queryArg.sessionId,
          action: queryArg.action,
        },
      }),
    }),
    startTaskControlPlaneV1TasksPost: build.mutation<
      StartTaskControlPlaneV1TasksPostApiResponse,
      StartTaskControlPlaneV1TasksPostApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/tasks`, method: "POST", body: queryArg.startIngestionRequest }),
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
export type UploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostApiResponse = unknown;
export type UploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostApiArg = {
  teamId: string;
  bodyUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost: BodyUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost;
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
export type RemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteApiResponse =
  /** status 202 Successful Response */ RemoveTeamMemberResponse;
export type RemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteApiArg = {
  teamId: string;
  userId: string;
};
export type UpdateTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdPatchApiResponse = unknown;
export type UpdateTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdPatchApiArg = {
  teamId: string;
  userId: string;
  updateTeamMemberRequest: UpdateTeamMemberRequest;
};
export type GetFrontendBootstrapControlPlaneV1FrontendBootstrapGetApiResponse =
  /** status 200 Successful Response */ FrontendBootstrap;
export type GetFrontendBootstrapControlPlaneV1FrontendBootstrapGetApiArg = void;
export type GetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetApiResponse =
  /** status 200 Successful Response */ AgentTemplateSummary[];
export type GetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetApiArg = {
  teamId: string;
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
export type GetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetApiResponse =
  /** status 200 Successful Response */ PromptSummary[];
export type GetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetApiArg = {
  teamId: string;
  lang?: string;
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
  lang?: string;
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
export type GetAgentInstanceRuntimeControlPlaneV1AgentInstancesAgentInstanceIdRuntimeGetApiResponse =
  /** status 200 Successful Response */ ManagedAgentRuntimeBinding;
export type GetAgentInstanceRuntimeControlPlaneV1AgentInstancesAgentInstanceIdRuntimeGetApiArg = {
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
export type PostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostApiResponse =
  /** status 200 Successful Response */ ExecutionPreparation;
export type PostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostApiArg = {
  teamId: string;
  agentInstanceId: string;
  sessionId?: string | null;
  action?: ExecutionGrantAction;
};
export type StartTaskControlPlaneV1TasksPostApiResponse = /** status 202 Successful Response */ StartTaskResponse;
export type StartTaskControlPlaneV1TasksPostApiArg = {
  startIngestionRequest: StartIngestionRequest;
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
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type LifecycleTrigger = "member_removed" | "member_rejoined";
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
export type GcuVersionsType = "v1";
export type TeamPermission =
  | "can_read"
  | "can_update_info"
  | "can_update_resources"
  | "can_update_agents"
  | "can_read_members"
  | "can_administer_members"
  | "can_administer_managers"
  | "can_administer_owners"
  | "can_read_conversations";
export type TeamWithPermissions = {
  id: string;
  name: string;
  member_count?: number | null;
  owners?: UserSummary[];
  is_member?: boolean;
  description?: string | null;
  is_private?: boolean;
  banner_image_url?: string | null;
  max_resources_storage_size?: number | null;
  current_resources_storage_size?: number | null;
  permissions?: TeamPermission[];
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
  owners?: UserSummary[];
  is_member?: boolean;
  description?: string | null;
  is_private?: boolean;
  banner_image_url?: string | null;
  max_resources_storage_size?: number | null;
  current_resources_storage_size?: number | null;
};
export type UpdateTeamRequest = {
  description?: string | null;
  is_private?: boolean | null;
  banner_image_url?: string | null;
};
export type BodyUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPost = {
  /** Banner image file (max 5MB, JPEG/PNG/WebP) */
  file: Blob;
};
export type UserTeamRelation = "owner" | "manager" | "member";
export type TeamMember = {
  type?: "user";
  relation: UserTeamRelation;
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
export type UpdateTeamMemberRequest = {
  relation: UserTeamRelation;
};
export type FrontendFeatureFlags = {
  enableK8Features?: boolean;
  enableElecWarfare?: boolean;
};
export type FrontendUiSettings = {
  siteDisplayName?: string;
  agentsNicknameSingular?: string;
  agentsNicknamePlural?: string;
};
export type PermissionSummary = {
  items?: string[];
  can_view_team_agents?: boolean;
  can_manage_team_agents?: boolean;
  can_manage_mcp_servers?: boolean;
  can_view_feedback?: boolean;
  can_submit_feedback?: boolean;
  can_create_sessions?: boolean;
};
export type FrontendBootstrap = {
  current_user: UserSummary;
  active_team: TeamWithPermissions;
  available_teams?: Team[];
  gcu_version?: string | null;
  feature_flags: FrontendFeatureFlags;
  ui_settings: FrontendUiSettings;
  permissions: PermissionSummary;
};
export type ManagedAgentUiHints = {
  multiline?: boolean;
  max_lines?: number;
  placeholder?: string | null;
  markdown?: boolean;
  textarea?: boolean;
  group?: string | null;
  hide?: boolean;
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
export type ManagedMcpServerRef = {
  id: string;
  display_name?: string;
  require_tools?: string[];
  config_fields?: ManagedAgentFieldSpec[];
  /** When True the server is part of the template's canonical tool set. The frontend renders its toggle as read-only; the operator can configure its config_fields but cannot remove the server. */
  locked?: boolean;
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
  /** MCP server references advertised by this template. Empty when the template declares no MCP dependencies. */
  mcp_servers?: ManagedMcpServerRef[];
};
export type EffectiveChatOptions = {
  attach_files?: boolean;
  libraries_selection?: boolean;
  search_policy_selection?: boolean;
  default_search_policy?: "strict" | "hybrid" | "semantic";
  rag_scope_selection?: boolean;
  default_search_rag_scope?: "corpus_only" | "hybrid" | "general_only";
  /** When non-null, the agent is configured to use exactly these library IDs. The frontend must render the library picker as read-only and send exactly this list in RuntimeContext.selected_document_libraries_ids. Null means the user can freely select from all available libraries. */
  bound_library_ids?: string[] | null;
};
export type ManagedAgentInstanceSummary = {
  agent_instance_id: string;
  team_id: string;
  template_id: string;
  display_name: string;
  description?: string | null;
  status: "enabled" | "disabled";
  created_at?: string | null;
  updated_at?: string | null;
  created_by?: string | null;
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
  /** Per-server MCP configuration values keyed first by server id and then by ManagedAgentFieldSpec.key. Empty when no MCP options have been customised. */
  mcp_config_values?: {
    [key: string]: {
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
  /** Admin-chosen MCP server activation policy for this instance. Null means inherit the template default selection (all declared servers active); [] means activate no MCP servers; a non-empty list means activate exactly that subset. */
  selected_mcp_server_ids?: string[] | null;
  /** ok when the pod is reachable at listing time; unavailable when the pod cannot be contacted. */
  runtime_status?: "ok" | "unavailable";
  /** Non-empty when stored MCP server IDs are absent from the live pod catalog. Admin must delete and recreate the instance to resolve. */
  catalog_warnings?: string[];
  /** Resolved chat affordances for this instance, computed from active MCP server config_fields and tuning values. Tells the frontend which composer controls to show without waiting for prepare-execution. */
  effective_chat_options?: EffectiveChatOptions;
};
export type CreateAgentInstanceRequest = {
  /** Composite template identity: '{source_runtime_id}:{source_agent_id}'. Obtained from GET /teams/{team_id}/agent-templates. */
  template_id: string;
  display_name: string;
  description?: string | null;
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
  /** Optional per-server MCP configuration values keyed first by server id and then by ManagedAgentFieldSpec.key. Only selected or inherited-active servers may be configured; unknown server ids or option keys are rejected with HTTP 422. */
  mcp_config_values?: {
    [key: string]: {
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
  } | null;
  /** Optional MCP server activation policy for this instance. None means inherit the template default selection (all declared servers active); [] means activate no MCP servers; a non-empty list means activate exactly that subset. Unknown IDs are rejected with HTTP 422. */
  mcp_server_ids?: string[] | null;
};
export type UpdateAgentInstanceRequest = {
  display_name?: string | null;
  description?: string | null;
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
  /** Replaces the stored per-server MCP configuration values. Omit the field to leave the current MCP config unchanged; pass null to clear all stored MCP config for the instance. */
  mcp_config_values?: {
    [key: string]: {
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
  } | null;
  /** Replaces the MCP server activation policy for this instance. Omit the field to leave the current selection unchanged; pass null to reset to the template default selection (all declared servers active); pass [] to activate no MCP servers; pass a non-empty list to activate exactly that subset. Unknown IDs are rejected with HTTP 422. */
  mcp_server_ids?: string[] | null;
};
export type PromptCategory =
  | "doc-assist"
  | "summary"
  | "extraction"
  | "writing"
  | "analysis"
  | "monitoring"
  | "migration"
  | "conversational"
  | "integration"
  | "other";
export type PromptSummary = {
  id: string;
  name: string;
  description?: string | null;
  category?: PromptCategory | null;
  emoji?: string | null;
  tags?: string[];
  text_preview?: string | null;
  is_default?: boolean;
  created_by?: string | null;
  version?: number;
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
  category?: PromptCategory;
  emoji?: string | null;
  tags?: string[];
  text: string;
};
export type ContextPromptSummary = {
  id: string;
  name: string;
  description?: string | null;
  scope: "personal" | "team" | "default";
  version: number;
  session_count: number;
  score?: number | null;
  text?: string | null;
};
export type PromptDetail = {
  id: string;
  name: string;
  description?: string | null;
  category?: PromptCategory | null;
  emoji?: string | null;
  tags?: string[];
  text_preview?: string | null;
  is_default?: boolean;
  created_by?: string | null;
  version?: number;
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
  category?: PromptCategory;
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
export type ManagedAgentTuning = {
  role: string;
  description: string;
  tags?: string[];
  fields?: ManagedAgentFieldSpec[];
  mcp_servers?: ManagedMcpServerRef[];
  /** Admin-chosen MCP server activation policy. None means inherit the template default selection (all declared servers active); [] means activate no MCP servers; a non-empty list means activate exactly that subset. */
  selected_mcp_server_ids?: string[] | null;
  /** Per-server MCP configuration values keyed first by server id and then by ManagedAgentFieldSpec.key. Only keys declared by the matching server's config_fields are stored. */
  mcp_config_values?: {
    [key: string]: {
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
export type ManagedAgentRuntimeBinding = {
  agent_instance_id: string;
  template_agent_id: string;
  owner_scope?: "team";
  owner_user_id?: string | null;
  owner_team_id: string;
  enabled?: boolean;
  tuning: ManagedAgentTuning;
};
export type SessionListItem = {
  session_id: string;
  team_id: string;
  agent_instance_id?: string | null;
  title?: string | null;
  context_prompt_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};
export type CreateSessionRequest = {
  /** Frontend-generated UUID. */
  session_id: string;
  agent_instance_id?: string | null;
  title?: string | null;
};
export type UpdateSessionRequest = {
  /** Frontend-observed last activity timestamp. Used only for control-plane session metadata freshness, not runtime message history. */
  updated_at?: string | null;
  /** Human-readable session title shown in the sidebar. */
  title?: string | null;
  /** Library prompt to use as chat context for this session. Null clears the current context. Send the sentinel value '__clear__' or omit the field entirely to leave it unchanged. */
  context_prompt_id?: string | null;
  /** Set to true to explicitly clear context_prompt_id to null. */
  clear_context_prompt?: boolean;
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
export type ExecutionGrantAction = "execute" | "resume";
export type ExecutionGrant = {
  user_id: string;
  team_id: string;
  agent_instance_id: string;
  action: ExecutionGrantAction;
  /** Intended runtime service/endpoint URL or identifier. */
  audience: string;
  /** Grant issuance time as a Unix timestamp. */
  issued_at: number;
  /** Grant expiry time as a Unix timestamp. */
  expires_at: number;
  /** Optional permission scopes granted for this execution. */
  scopes?: string[];
  trace_id?: string | null;
  correlation_id?: string | null;
  /** Optional logical storage scope name for session state. MUST NOT be a raw connection string, secret, or infrastructure credential. */
  storage_scope?: string | null;
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
  execution_grant: ExecutionGrant;
  supports_streaming?: boolean;
  supports_hitl?: boolean;
  supports_ui_parts?: boolean;
  /** Resolved chat-option surface derived from the stored managed-agent configuration. The frontend should render only the affordances enabled here rather than hard-code agent- or tool-specific rules. */
  effective_chat_options?: EffectiveChatOptions;
  expires_at: string;
  runtime_display_name?: string | null;
  grant_refresh_required?: boolean;
  max_session_idle_seconds?: number | null;
  /** Resolved text of the session's context prompt, if one is set. The runtime injects this as a conversation-level context. Null when no context prompt is configured for the session. */
  context_prompt_text?: string | null;
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
export type TaskState = "pending" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled";
export type TaskTarget = {
  type: string;
  id: string;
  label: string;
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
};
export type TaskListResponse = {
  tasks: TaskSummary[];
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
  useDeleteUserControlPlaneV1UsersUserIdDeleteMutation,
  useGetUserDetailsControlPlaneV1UserGetQuery,
  useLazyGetUserDetailsControlPlaneV1UserGetQuery,
  useValidateGcuControlPlaneV1GcuPostMutation,
  useListTeamsControlPlaneV1TeamsGetQuery,
  useLazyListTeamsControlPlaneV1TeamsGetQuery,
  useGetTeamControlPlaneV1TeamsTeamIdGetQuery,
  useLazyGetTeamControlPlaneV1TeamsTeamIdGetQuery,
  useUpdateTeamControlPlaneV1TeamsTeamIdPatchMutation,
  useUploadTeamBannerControlPlaneV1TeamsTeamIdBannerPostMutation,
  useListTeamMembersControlPlaneV1TeamsTeamIdMembersGetQuery,
  useLazyListTeamMembersControlPlaneV1TeamsTeamIdMembersGetQuery,
  useAddTeamMemberControlPlaneV1TeamsTeamIdMembersPostMutation,
  useRemoveTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdDeleteMutation,
  useUpdateTeamMemberControlPlaneV1TeamsTeamIdMembersUserIdPatchMutation,
  useGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery,
  useLazyGetFrontendBootstrapControlPlaneV1FrontendBootstrapGetQuery,
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  useLazyGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useLazyGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation,
  usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation,
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation,
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
  useGetAgentInstanceRuntimeControlPlaneV1AgentInstancesAgentInstanceIdRuntimeGetQuery,
  useLazyGetAgentInstanceRuntimeControlPlaneV1AgentInstancesAgentInstanceIdRuntimeGetQuery,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
  useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery,
  useLazyGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery,
  useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  useLazyGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation,
  useGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery,
  useLazyGetTeamSessionAttachmentsControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsGetQuery,
  usePostTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsPostMutation,
  useDeleteTeamSessionAttachmentControlPlaneV1TeamsTeamIdSessionsSessionIdAttachmentsAttachmentIdDeleteMutation,
  usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation,
  useStartTaskControlPlaneV1TasksPostMutation,
  useListTasksControlPlaneV1TasksGetQuery,
  useLazyListTasksControlPlaneV1TasksGetQuery,
  useStreamTaskEventsControlPlaneV1TasksTaskIdEventsGetQuery,
  useLazyStreamTaskEventsControlPlaneV1TasksTaskIdEventsGetQuery,
  useCancelTaskControlPlaneV1TasksTaskIdCancelPostMutation,
  useCreateCampaignControlPlaneV1EvaluationCampaignsPostMutation,
  useListCampaignsControlPlaneV1EvaluationCampaignsGetQuery,
  useLazyListCampaignsControlPlaneV1EvaluationCampaignsGetQuery,
  useGetCampaignControlPlaneV1EvaluationCampaignsCampaignIdGetQuery,
  useLazyGetCampaignControlPlaneV1EvaluationCampaignsCampaignIdGetQuery,
  useListCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGetQuery,
  useLazyListCasesControlPlaneV1EvaluationCampaignsCampaignIdCasesGetQuery,
  useGetCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGetQuery,
  useLazyGetCaseControlPlaneV1EvaluationCampaignsCampaignIdCasesCaseIdGetQuery,
} = injectedRtkApi;
