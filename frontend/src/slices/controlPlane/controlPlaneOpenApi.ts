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
};
export type CreateUserRequest = {
  username: string;
  email: string;
  password: string;
  first_name?: string | null;
  last_name?: string | null;
  enabled?: boolean;
};
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
  permissions?: TeamPermission[];
};
export type UserDetails = {
  personalTeam: TeamWithPermissions;
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
} = injectedRtkApi;
