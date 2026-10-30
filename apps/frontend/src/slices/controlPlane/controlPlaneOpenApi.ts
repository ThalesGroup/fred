import { controlPlaneApi as api } from "./controlPlaneApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    organizationRegistry: build.query<OrganizationRegistryApiResponse, OrganizationRegistryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/organizations`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    createOrganization: build.mutation<CreateOrganizationApiResponse, CreateOrganizationApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/organizations`,
        method: "POST",
        body: queryArg.createOrganization,
      }),
    }),
    searchOrganizationCandidates: build.query<
      SearchOrganizationCandidatesApiResponse,
      SearchOrganizationCandidatesApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/organizations/candidates`,
        params: {
          query: queryArg.query,
        },
      }),
    }),
    getOrganization: build.query<GetOrganizationApiResponse, GetOrganizationApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/admin/organizations/${queryArg.id}` }),
    }),
    updateOrganization: build.mutation<UpdateOrganizationApiResponse, UpdateOrganizationApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/organizations/${queryArg.id}`,
        method: "PATCH",
        body: queryArg.updateOrganization,
      }),
    }),
    teamRegistry: build.query<TeamRegistryApiResponse, TeamRegistryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/teams`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    executeStream: build.mutation<ExecuteStreamApiResponse, ExecuteStreamApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/agents/execute/stream`,
        method: "POST",
        body: queryArg.executeRequest,
      }),
    }),
    authorizeDocument: build.mutation<AuthorizeDocumentApiResponse, AuthorizeDocumentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/authorize/document`,
        method: "POST",
        body: queryArg.authorizeDocument,
      }),
    }),
    authorizePlatform: build.mutation<AuthorizePlatformApiResponse, AuthorizePlatformApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/authorize/platform`,
        method: "POST",
        body: queryArg.platformCheck,
      }),
    }),
    authorizeScope: build.mutation<AuthorizeScopeApiResponse, AuthorizeScopeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/authorize/scope`,
        method: "POST",
        body: queryArg.authorizeScope,
      }),
    }),
    authorizeSpace: build.mutation<AuthorizeSpaceApiResponse, AuthorizeSpaceApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/authorize/space`, method: "POST", body: queryArg.spaceCheck }),
    }),
    bootstrapPlatformAdmin: build.mutation<BootstrapPlatformAdminApiResponse, BootstrapPlatformAdminApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/bootstrap/platform-admin`,
        method: "POST",
        body: queryArg.bootstrapRequest,
      }),
    }),
    deletionStatus: build.query<DeletionStatusApiResponse, DeletionStatusApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/deletions/${queryArg.operationId}` }),
    }),
    cleanup: build.query<CleanupApiResponse, CleanupApiArg>({
      query: () => ({ url: `/control-plane/v1/document-processing/cleanup` }),
    }),
    cleaned: build.mutation<CleanedApiResponse, CleanedApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/cleanup`,
        method: "POST",
        body: queryArg.cleaned,
      }),
    }),
    retrievalWork: build.query<RetrievalWorkApiResponse, RetrievalWorkApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/retrievable/${queryArg.id}`,
        params: {
          operation_id: queryArg.operationId,
        },
      }),
    }),
    confirmRetrievable: build.mutation<ConfirmRetrievableApiResponse, ConfirmRetrievableApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/retrievable/${queryArg.id}`,
        method: "POST",
        body: queryArg.retrievalConfirmation,
      }),
    }),
    abandon: build.mutation<AbandonApiResponse, AbandonApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/abandon`,
        method: "POST",
        body: queryArg.failure,
      }),
    }),
    claim: build.mutation<ClaimApiResponse, ClaimApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/claim`,
        method: "POST",
        body: queryArg.claim,
      }),
    }),
    commit: build.mutation<CommitApiResponse, CommitApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/commit`,
        method: "POST",
        body: queryArg.commit,
      }),
    }),
    original: build.query<OriginalApiResponse, OriginalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/original`,
        params: {
          generation: queryArg.generation,
        },
      }),
    }),
    vectors: build.mutation<VectorsApiResponse, VectorsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/vectors`,
        method: "POST",
        body: queryArg.vectorPlan,
      }),
    }),
    work: build.query<WorkApiResponse, WorkApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/document-processing/${queryArg.id}/work` }),
    }),
    receipt: build.query<ReceiptApiResponse, ReceiptApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/document-uploads/${queryArg.id}` }),
    }),
    acknowledge: build.mutation<AcknowledgeApiResponse, AcknowledgeApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/document-uploads/${queryArg.id}/acknowledgment`, method: "PUT" }),
    }),
    deleteDocument: build.mutation<DeleteDocumentApiResponse, DeleteDocumentApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/documents/${queryArg.id}`, method: "DELETE" }),
    }),
    content: build.query<ContentApiResponse, ContentApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/documents/${queryArg.id}/content` }),
    }),
    preview: build.query<PreviewApiResponse, PreviewApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/preview`,
        params: {
          artifact: queryArg.artifact,
        },
      }),
    }),
    history: build.query<HistoryApiResponse, HistoryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/processing`,
        params: {
          before: queryArg.before,
        },
      }),
    }),
    start: build.mutation<StartApiResponse, StartApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/processing`,
        method: "POST",
        body: queryArg.start,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
      }),
    }),
    setRetrievable: build.mutation<SetRetrievableApiResponse, SetRetrievableApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/retrievable`,
        method: "PUT",
        body: queryArg.setRetrievable,
      }),
    }),
    createFolder: build.mutation<CreateFolderApiResponse, CreateFolderApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/folders`, method: "POST", body: queryArg.createFolder }),
    }),
    deleteFolder: build.mutation<DeleteFolderApiResponse, DeleteFolderApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/folders/${queryArg.id}`, method: "DELETE" }),
    }),
    renameFolder: build.mutation<RenameFolderApiResponse, RenameFolderApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/folders/${queryArg.id}`,
        method: "PATCH",
        body: queryArg.rename,
      }),
    }),
    upload: build.mutation<UploadApiResponse, UploadApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/folders/${queryArg.id}/documents`,
        method: "POST",
        body: queryArg.fileUpload,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
        params: {
          retry_of: queryArg.retryOf,
          profile: queryArg.profile,
        },
      }),
    }),
    preflight: build.mutation<PreflightApiResponse, PreflightApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/folders/${queryArg.id}/documents/preflight`,
        method: "POST",
        body: queryArg.preflight,
      }),
    }),
    frontendConfig: build.query<FrontendConfigApiResponse, FrontendConfigApiArg>({
      query: () => ({ url: `/control-plane/v1/frontend/config` }),
    }),
    acceptTerms: build.mutation<AcceptTermsApiResponse, AcceptTermsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/gcu`, method: "POST", body: queryArg.termsRequest }),
    }),
    health: build.query<HealthApiResponse, HealthApiArg>({
      query: () => ({ url: `/control-plane/v1/healthz` }),
    }),
    importBlueprint: build.mutation<ImportBlueprintApiResponse, ImportBlueprintApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/import-export/import`,
        method: "POST",
        body: queryArg.provisioningUpload,
      }),
    }),
    me: build.query<MeApiResponse, MeApiArg>({
      query: () => ({ url: `/control-plane/v1/me` }),
    }),
    onboardingStatus: build.query<OnboardingStatusApiResponse, OnboardingStatusApiArg>({
      query: () => ({ url: `/control-plane/v1/me/onboarding` }),
    }),
    createPersonalSpace: build.mutation<CreatePersonalSpaceApiResponse, CreatePersonalSpaceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/me/personal-space`,
        method: "POST",
        body: queryArg.createPersonalSpace,
      }),
    }),
    mySpaces: build.query<MySpacesApiResponse, MySpacesApiArg>({
      query: () => ({ url: `/control-plane/v1/me/spaces` }),
    }),
    organizationAgents: build.query<OrganizationAgentsApiResponse, OrganizationAgentsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/organizations/${queryArg.organizationId}/agents` }),
    }),
    setOrganizationAgentDefault: build.mutation<
      SetOrganizationAgentDefaultApiResponse,
      SetOrganizationAgentDefaultApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/agents/${queryArg.agentId}/default-on`,
        method: "PUT",
        body: queryArg.setDefaultOnRequest,
      }),
    }),
    organizationCapabilities: build.query<OrganizationCapabilitiesApiResponse, OrganizationCapabilitiesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/organizations/${queryArg.organizationId}/capabilities` }),
    }),
    refreshOrganizationCapabilities: build.mutation<
      RefreshOrganizationCapabilitiesApiResponse,
      RefreshOrganizationCapabilitiesApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/capabilities/${queryArg.runtimeId}/refresh`,
        method: "POST",
      }),
    }),
    setOrganizationCapabilityDefault: build.mutation<
      SetOrganizationCapabilityDefaultApiResponse,
      SetOrganizationCapabilityDefaultApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/capabilities/${queryArg.runtimeId}/${queryArg.capabilityId}/default-on`,
        method: "PUT",
        body: queryArg.setDefaultOnRequest,
      }),
    }),
    organizationCapabilityRevokeImpact: build.query<
      OrganizationCapabilityRevokeImpactApiResponse,
      OrganizationCapabilityRevokeImpactApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/capabilities/${queryArg.runtimeId}/${queryArg.capabilityId}/revoke-impact`,
      }),
    }),
    organizationModelPolicy: build.query<OrganizationModelPolicyApiResponse, OrganizationModelPolicyApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-policy` }),
    }),
    replaceOrganizationModelPolicy: build.mutation<
      ReplaceOrganizationModelPolicyApiResponse,
      ReplaceOrganizationModelPolicyApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-policy`,
        method: "PUT",
        body: queryArg.replaceModelPolicy,
      }),
    }),
    refreshModelSource: build.mutation<RefreshModelSourceApiResponse, RefreshModelSourceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-sources/${queryArg.sourceId}/refresh`,
        method: "POST",
      }),
    }),
    organizationModels: build.query<OrganizationModelsApiResponse, OrganizationModelsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/organizations/${queryArg.organizationId}/models` }),
    }),
    organizationSupervision: build.query<OrganizationSupervisionApiResponse, OrganizationSupervisionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/supervision`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    teamSupervision: build.query<TeamSupervisionApiResponse, TeamSupervisionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/supervision/teams/${queryArg.teamId}`,
      }),
    }),
    createSpace: build.mutation<CreateSpaceApiResponse, CreateSpaceApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces`, method: "POST", body: queryArg.createSpace }),
    }),
    deleteSpace: build.mutation<DeleteSpaceApiResponse, DeleteSpaceApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}`, method: "DELETE" }),
    }),
    receipts: build.query<ReceiptsApiResponse, ReceiptsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/document-uploads`,
        params: {
          before: queryArg.before,
          before_key: queryArg.beforeKey,
          limit: queryArg.limit,
        },
      }),
    }),
    entries: build.query<EntriesApiResponse, EntriesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/entries`,
        params: {
          parent_id: queryArg.parentId,
          search: queryArg.search,
          order: queryArg.order,
          offset: queryArg.offset,
          limit: queryArg.limit,
        },
      }),
    }),
    grant: build.mutation<GrantApiResponse, GrantApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/roles/${queryArg.role}/${queryArg.user}`,
        method: "PUT",
      }),
    }),
    revoke: build.mutation<RevokeApiResponse, RevokeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/roles/${queryArg.role}/${queryArg.user}`,
        method: "DELETE",
      }),
    }),
    summary: build.query<SummaryApiResponse, SummaryApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/storage` }),
    }),
    listAgentInstances: build.query<ListAgentInstancesApiResponse, ListAgentInstancesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances` }),
    }),
    createAgentInstance: build.mutation<CreateAgentInstanceApiResponse, CreateAgentInstanceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances`,
        method: "POST",
        body: queryArg.createAgentInstanceRequest,
      }),
    }),
    getAgentInstance: build.query<GetAgentInstanceApiResponse, GetAgentInstanceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances/${queryArg.agentInstanceId}`,
      }),
    }),
    deleteAgentInstance: build.mutation<DeleteAgentInstanceApiResponse, DeleteAgentInstanceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances/${queryArg.agentInstanceId}`,
        method: "DELETE",
      }),
    }),
    updateAgentInstance: build.mutation<UpdateAgentInstanceApiResponse, UpdateAgentInstanceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances/${queryArg.agentInstanceId}`,
        method: "PATCH",
        body: queryArg.updateAgentInstanceRequest,
      }),
    }),
    prepareExecution: build.mutation<PrepareExecutionApiResponse, PrepareExecutionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances/${queryArg.agentInstanceId}/prepare-execution`,
        method: "POST",
        params: {
          session_id: queryArg.sessionId,
          model_source_id: queryArg.modelSourceId,
          model_upstream_id: queryArg.modelUpstreamId,
        },
      }),
    }),
    resolveRuntime: build.query<ResolveRuntimeApiResponse, ResolveRuntimeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances/${queryArg.agentInstanceId}/runtime`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          conversation: queryArg.conversation,
        },
      }),
    }),
    spaceAgentTemplates: build.query<SpaceAgentTemplatesApiResponse, SpaceAgentTemplatesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-templates` }),
    }),
    listSessions: build.query<ListSessionsApiResponse, ListSessionsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions` }),
    }),
    createSession: build.mutation<CreateSessionApiResponse, CreateSessionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions`,
        method: "POST",
        body: queryArg.createSessionRequest,
      }),
    }),
    getSession: build.query<GetSessionApiResponse, GetSessionApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}` }),
    }),
    deleteSession: build.mutation<DeleteSessionApiResponse, DeleteSessionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}`,
        method: "DELETE",
      }),
    }),
    updateSession: build.mutation<UpdateSessionApiResponse, UpdateSessionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}`,
        method: "PATCH",
        body: queryArg.updateSessionRequest,
      }),
    }),
    getMyPreferences: build.query<GetMyPreferencesApiResponse, GetMyPreferencesApiArg>({
      query: () => ({ url: `/control-plane/v1/users/me/preferences` }),
    }),
    patchMyPreferences: build.mutation<PatchMyPreferencesApiResponse, PatchMyPreferencesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/users/me/preferences`,
        method: "PATCH",
        body: queryArg.patchUserPreferences,
      }),
    }),
    listPlatformRoles: build.query<ListPlatformRolesApiResponse, ListPlatformRolesApiArg>({
      query: () => ({ url: `/control-plane/v1/users/platform-roles` }),
    }),
    grantPlatformRole: build.mutation<GrantPlatformRoleApiResponse, GrantPlatformRoleApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/users/${queryArg.user}/platform-roles/${queryArg.role}`,
        method: "PUT",
      }),
    }),
    revokePlatformRole: build.mutation<RevokePlatformRoleApiResponse, RevokePlatformRoleApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/users/${queryArg.user}/platform-roles/${queryArg.role}`,
        method: "DELETE",
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as controlPlaneApi };
export type OrganizationRegistryApiResponse = /** status 200 undefined */ OrganizationPage;
export type OrganizationRegistryApiArg = {
  /** Exclusive UUID cursor; at most 100 active organizations. */
  after?: string;
};
export type CreateOrganizationApiResponse = /** status 201 undefined */ Space;
export type CreateOrganizationApiArg = {
  createOrganization: CreateOrganization;
};
export type SearchOrganizationCandidatesApiResponse = /** status 200 undefined */ UserSummary[];
export type SearchOrganizationCandidatesApiArg = {
  query: string;
};
export type GetOrganizationApiResponse = /** status 200 undefined */ OrganizationDetail;
export type GetOrganizationApiArg = {
  id: string;
};
export type UpdateOrganizationApiResponse = /** status 200 undefined */ OrganizationDetail;
export type UpdateOrganizationApiArg = {
  id: string;
  updateOrganization: UpdateOrganization;
};
export type TeamRegistryApiResponse = /** status 200 Success */ Space[];
export type TeamRegistryApiArg = {
  /** Exclusive UUID cursor; at most 100 non-personal teams, ordered by ID. */
  after?: string;
};
export type ExecuteStreamApiResponse =
  /** status 200 SSE data frames containing RuntimeEvent JSON; final closes the stream without a sentinel */ RuntimeEvent;
export type ExecuteStreamApiArg = {
  executeRequest: ExecuteRequest;
};
export type AuthorizeDocumentApiResponse = /** status 200 Success */ Allowed;
export type AuthorizeDocumentApiArg = {
  authorizeDocument: AuthorizeDocument;
};
export type AuthorizePlatformApiResponse = /** status 200 Success */ Allowed;
export type AuthorizePlatformApiArg = {
  platformCheck: PlatformCheck;
};
export type AuthorizeScopeApiResponse = /** status 200 Success */ Scope;
export type AuthorizeScopeApiArg = {
  authorizeScope: AuthorizeScope;
};
export type AuthorizeSpaceApiResponse = /** status 200 Success */ Allowed;
export type AuthorizeSpaceApiArg = {
  spaceCheck: SpaceCheck;
};
export type BootstrapPlatformAdminApiResponse = /** status 200 Success */ BootstrapResponse;
export type BootstrapPlatformAdminApiArg = {
  bootstrapRequest: BootstrapRequest;
};
export type DeletionStatusApiResponse = /** status 200 undefined */ Receipt;
export type DeletionStatusApiArg = {
  operationId: string;
};
export type CleanupApiResponse = /** status 200 undefined */ Cleanup[];
export type CleanupApiArg = void;
export type CleanedApiResponse = unknown;
export type CleanedApiArg = {
  cleaned: Cleaned;
};
export type RetrievalWorkApiResponse = /** status 200 undefined */ RetrievalWork;
export type RetrievalWorkApiArg = {
  id: string;
  operationId: string;
};
export type ConfirmRetrievableApiResponse = unknown;
export type ConfirmRetrievableApiArg = {
  id: string;
  retrievalConfirmation: RetrievalConfirmation;
};
export type AbandonApiResponse = /** status 200 undefined */ Summary;
export type AbandonApiArg = {
  id: string;
  failure: Failure;
};
export type ClaimApiResponse = /** status 200 undefined */ Descriptor;
export type ClaimApiArg = {
  id: string;
  claim: Claim;
};
export type CommitApiResponse = /** status 200 undefined */ Summary;
export type CommitApiArg = {
  id: string;
  commit: Commit;
};
export type OriginalApiResponse = /** status 200 undefined */ string;
export type OriginalApiArg = {
  id: string;
  generation: string;
};
export type VectorsApiResponse = unknown;
export type VectorsApiArg = {
  id: string;
  vectorPlan: VectorPlan;
};
export type WorkApiResponse = /** status 200 undefined */ Work;
export type WorkApiArg = {
  id: string;
};
export type ReceiptApiResponse = /** status 200 undefined */ UploadReceipt;
export type ReceiptApiArg = {
  /** The upload's `Idempotency-Key` */
  id: string;
};
export type AcknowledgeApiResponse = unknown;
export type AcknowledgeApiArg = {
  /** The upload's `Idempotency-Key` */
  id: string;
};
export type DeleteDocumentApiResponse = /** status 200 undefined */ Receipt | /** status 202 undefined */ Receipt;
export type DeleteDocumentApiArg = {
  id: string;
};
export type ContentApiResponse = /** status 200 undefined */ string;
export type ContentApiArg = {
  id: string;
};
export type PreviewApiResponse = /** status 200 undefined */ string | /** status 206 undefined */ string;
export type PreviewApiArg = {
  id: string;
  /** native, raw, metadata, or a relative path from the published manifest. */
  artifact?: string;
};
export type HistoryApiResponse = /** status 200 undefined */ Summary[];
export type HistoryApiArg = {
  id: string;
  /** Cursor: `id` of the last attempt read. */
  before?: string | null;
};
export type StartApiResponse = /** status 200 undefined */ Summary;
export type StartApiArg = {
  /** Stored document */
  id: string;
  /** Caller-chosen request UUID; replaying it is safe */
  "Idempotency-Key": string;
  start: Start;
};
export type SetRetrievableApiResponse = /** status 200 undefined */ Document;
export type SetRetrievableApiArg = {
  id: string;
  setRetrievable: SetRetrievable;
};
export type CreateFolderApiResponse = /** status 201 Success */ Folder;
export type CreateFolderApiArg = {
  createFolder: CreateFolder;
};
export type DeleteFolderApiResponse = unknown;
export type DeleteFolderApiArg = {
  id: string;
};
export type RenameFolderApiResponse = unknown;
export type RenameFolderApiArg = {
  id: string;
  rename: Rename;
};
export type UploadApiResponse = /** status 200 Replay of a stored request key */
  | UploadReceipt
  | /** status 201 Stored */ UploadReceipt;
export type UploadApiArg = {
  /** Destination folder */
  id: string;
  /** Caller-chosen request UUID; replaying it is safe */
  "Idempotency-Key": string;
  /** Request key of a failed upload of the same file to the same folder */
  retryOf?: string;
  /** Processing profile; omit to store only */
  profile?: Profile;
  fileUpload: FileUpload;
};
export type PreflightApiResponse = /** status 200 undefined */ PreflightResult;
export type PreflightApiArg = {
  /** Destination folder */
  id: string;
  preflight: Preflight;
};
export type FrontendConfigApiResponse = /** status 200 undefined */ FrontendConfig;
export type FrontendConfigApiArg = void;
export type AcceptTermsApiResponse = unknown;
export type AcceptTermsApiArg = {
  termsRequest: TermsRequest;
};
export type HealthApiResponse = /** status 200 undefined */ Health;
export type HealthApiArg = void;
export type ImportBlueprintApiResponse = /** status 200 Success */ Report;
export type ImportBlueprintApiArg = {
  provisioningUpload: ProvisioningUpload;
};
export type MeApiResponse = /** status 200 Success */ Me;
export type MeApiArg = void;
export type OnboardingStatusApiResponse = /** status 200 undefined */ OnboardingStatus;
export type OnboardingStatusApiArg = void;
export type CreatePersonalSpaceApiResponse = /** status 200 Existing personal space */
  | Space
  | /** status 201 Created personal space */ Space;
export type CreatePersonalSpaceApiArg = {
  createPersonalSpace: CreatePersonalSpace;
};
export type MySpacesApiResponse = /** status 200 Success */ MySpace[];
export type MySpacesApiArg = void;
export type OrganizationAgentsApiResponse = /** status 200 undefined */ AgentEnablement[];
export type OrganizationAgentsApiArg = {
  organizationId: string;
};
export type SetOrganizationAgentDefaultApiResponse = /** status 200 undefined */ AgentDefaultOnResult;
export type SetOrganizationAgentDefaultApiArg = {
  organizationId: string;
  agentId: string;
  setDefaultOnRequest: SetDefaultOnRequest;
};
export type OrganizationCapabilitiesApiResponse = /** status 200 undefined */ PodCapabilityInventory[];
export type OrganizationCapabilitiesApiArg = {
  organizationId: string;
};
export type RefreshOrganizationCapabilitiesApiResponse = unknown;
export type RefreshOrganizationCapabilitiesApiArg = {
  organizationId: string;
  runtimeId: string;
};
export type SetOrganizationCapabilityDefaultApiResponse = unknown;
export type SetOrganizationCapabilityDefaultApiArg = {
  organizationId: string;
  runtimeId: string;
  capabilityId: string;
  setDefaultOnRequest: SetDefaultOnRequest;
};
export type OrganizationCapabilityRevokeImpactApiResponse =
  /** status 200 Instances usable now that disabling this offer would stop */ AffectedAgentInstance[];
export type OrganizationCapabilityRevokeImpactApiArg = {
  organizationId: string;
  runtimeId: string;
  capabilityId: string;
};
export type OrganizationModelPolicyApiResponse = /** status 200 undefined */ OrganizationModelPolicy;
export type OrganizationModelPolicyApiArg = {
  organizationId: string;
};
export type ReplaceOrganizationModelPolicyApiResponse = /** status 200 undefined */ OrganizationModelPolicy;
export type ReplaceOrganizationModelPolicyApiArg = {
  organizationId: string;
  replaceModelPolicy: ReplaceModelPolicy;
};
export type RefreshModelSourceApiResponse = unknown;
export type RefreshModelSourceApiArg = {
  organizationId: string;
  sourceId: string;
};
export type OrganizationModelsApiResponse = /** status 200 undefined */ OrganizationModelInventory;
export type OrganizationModelsApiArg = {
  organizationId: string;
};
export type OrganizationSupervisionApiResponse = /** status 200 undefined */ OrganizationSupervision;
export type OrganizationSupervisionApiArg = {
  organizationId: string;
  /** Exclusive team UUID cursor; does not filter organization totals */
  after?: string;
};
export type TeamSupervisionApiResponse = /** status 200 undefined */ TeamSupervisionDetail;
export type TeamSupervisionApiArg = {
  organizationId: string;
  teamId: string;
};
export type CreateSpaceApiResponse = /** status 201 Success */ Space;
export type CreateSpaceApiArg = {
  createSpace: CreateSpace;
};
export type DeleteSpaceApiResponse = /** status 200 Already completed */
  | Receipt
  | /** status 202 Durably accepted */ Receipt;
export type DeleteSpaceApiArg = {
  id: string;
};
export type ReceiptsApiResponse = /** status 200 undefined */ UploadReceipt[];
export type ReceiptsApiArg = {
  id: string;
  /** Cursor: `created_at` of the last receipt read; requires `before_key` */
  before?: string;
  /** Cursor: `request_key` of the last receipt read */
  beforeKey?: string;
  /** 1..200, default 50 */
  limit?: number;
};
export type EntriesApiResponse = /** status 200 undefined */ Directory;
export type EntriesApiArg = {
  id: string;
  parentId?: string;
  /** Literal case-insensitive substring; at most 255 characters. */
  search?: string;
  order?: EntryOrder;
  offset?: number;
  limit?: number;
};
export type GrantApiResponse = unknown;
export type GrantApiArg = {
  id: string;
  role: Role;
  user: string;
};
export type RevokeApiResponse = unknown;
export type RevokeApiArg = {
  id: string;
  role: Role;
  user: string;
};
export type SummaryApiResponse = /** status 200 undefined */ StorageSummary;
export type SummaryApiArg = {
  id: string;
};
export type ListAgentInstancesApiResponse = /** status 200 undefined */ ManagedAgentInstanceSummary[];
export type ListAgentInstancesApiArg = {
  spaceId: string;
};
export type CreateAgentInstanceApiResponse = /** status 201 undefined */ ManagedAgentInstanceSummary;
export type CreateAgentInstanceApiArg = {
  spaceId: string;
  createAgentInstanceRequest: CreateAgentInstanceRequest;
};
export type GetAgentInstanceApiResponse = /** status 200 undefined */ ManagedAgentInstanceSummary;
export type GetAgentInstanceApiArg = {
  spaceId: string;
  agentInstanceId: string;
};
export type DeleteAgentInstanceApiResponse = unknown;
export type DeleteAgentInstanceApiArg = {
  spaceId: string;
  agentInstanceId: string;
};
export type UpdateAgentInstanceApiResponse = /** status 200 undefined */ ManagedAgentInstanceSummary;
export type UpdateAgentInstanceApiArg = {
  spaceId: string;
  agentInstanceId: string;
  updateAgentInstanceRequest: UpdateAgentInstanceRequest;
};
export type PrepareExecutionApiResponse = /** status 200 undefined */ ExecutionPreparation;
export type PrepareExecutionApiArg = {
  spaceId: string;
  agentInstanceId: string;
  /** Registered conversation to verify before routing. */
  sessionId?: string;
  /** Requested model source; supply together with model_upstream_id. */
  modelSourceId?: string;
  /** Requested upstream model; never an authorization. */
  modelUpstreamId?: string;
};
export type ResolveRuntimeApiResponse = /** status 200 undefined */ RuntimeBinding;
export type ResolveRuntimeApiArg = {
  spaceId: string;
  agentInstanceId: string;
  /** Canonical person; only a trusted delegated call may supply this assertion. */
  person?: string;
  /** Run identifier; required together with person and agent. */
  run?: string;
  /** Delegated agent instance UUID; must match agent_instance_id. */
  agent?: string;
  /** Registered conversation; this resolver checks its private canonical association, then the pod checks checkpoint provenance before loading history. */
  conversation?: string;
};
export type SpaceAgentTemplatesApiResponse = /** status 200 undefined */ AgentTemplateSummary[];
export type SpaceAgentTemplatesApiArg = {
  spaceId: string;
};
export type ListSessionsApiResponse = /** status 200 undefined */ SessionDetails[];
export type ListSessionsApiArg = {
  spaceId: string;
};
export type CreateSessionApiResponse = /** status 200 undefined */
  | SessionDetails
  | /** status 201 undefined */ SessionDetails;
export type CreateSessionApiArg = {
  spaceId: string;
  createSessionRequest: CreateSessionRequest;
};
export type GetSessionApiResponse = /** status 200 undefined */ SessionDetails;
export type GetSessionApiArg = {
  spaceId: string;
  sessionId: string;
};
export type DeleteSessionApiResponse = /** status 200 undefined */ Receipt | /** status 202 undefined */ Receipt;
export type DeleteSessionApiArg = {
  spaceId: string;
  sessionId: string;
};
export type UpdateSessionApiResponse = /** status 200 undefined */ SessionDetails;
export type UpdateSessionApiArg = {
  spaceId: string;
  sessionId: string;
  updateSessionRequest: UpdateSessionRequest;
};
export type GetMyPreferencesApiResponse = /** status 200 undefined */ UserPreferences;
export type GetMyPreferencesApiArg = void;
export type PatchMyPreferencesApiResponse = /** status 200 undefined */ UserPreferences;
export type PatchMyPreferencesApiArg = {
  patchUserPreferences: PatchUserPreferences;
};
export type ListPlatformRolesApiResponse = /** status 200 Success */ Grant[];
export type ListPlatformRolesApiArg = void;
export type GrantPlatformRoleApiResponse = unknown;
export type GrantPlatformRoleApiArg = {
  user: string;
  role: PlatformRole;
};
export type RevokePlatformRoleApiResponse = unknown;
export type RevokePlatformRoleApiArg = {
  user: string;
  role: PlatformRole;
};
export type SpaceKind = "organization" | "team" | "project" | "personal";
export type Space = {
  id: string;
  kind: SpaceKind;
  name: string;
  parent_id: string | null;
  /** Ancestors then self: the search scope. A personal space's path is itself. */
  path: string[];
  personal_owner: string | null;
};
export type OrganizationPage = {
  items: Space[];
  next_cursor?: string | null;
};
export type ErrorBody = {
  code: string;
  detail: string;
};
export type CreateOrganization = {
  /** Accounts that become the organization's direct administrators; a repeated name grants once. */
  admin_usernames: string[];
  name: string;
  owner_username: string;
};
export type UserSummary = {
  avatar_image_url?: string | null;
  email?: string | null;
  first_name?: string | null;
  id: string;
  last_name?: string | null;
  username?: string | null;
};
export type OrganizationDetail = {
  admins: UserSummary[];
  organization: Space;
  owners: UserSummary[];
};
export type UpdateOrganization = {
  /** The complete set of direct administrators: missing ones are added, others revoked. */
  admin_usernames?: string[] | null;
  name?: string | null;
  owner_username?: string | null;
};
export type RuntimeEvent =
  | {
      kind: "status";
      sequence: number;
      status: string;
    }
  | {
      delta: string;
      kind: "assistant_delta";
      sequence: number;
    }
  | {
      content: string;
      finish_reason: string;
      kind: "final";
      sequence: number;
    };
export type ExecuteRequest = {
  agent_id?: string | null;
  agent_instance_id?: string | null;
  input?: string;
  runtime_context?:
    | {
        [key: string]: any;
      }
    | {
        [key: string]: any;
      };
  session_id?: string | null;
  [key: string]: any;
};
export type Allowed = {
  allowed: boolean;
};
export type Permission = "read" | "write" | "manage";
export type AuthorizeDocument = {
  document_id: string;
  permission: Permission;
};
export type PlatformPermission =
  | "list_all_teams"
  | "delete_team"
  | "delete_space"
  | "rescue_team_admin"
  | "edit_agent_class_path"
  | "observe_platform"
  | "administer_users"
  | "manage_platform"
  | "manage_capabilities"
  | "edit_platform_prompt";
export type PlatformCheck = {
  permission: PlatformPermission;
};
export type Scope = {
  /** Filter for chunks and metadata: `space_id` must be one of these. The space and its
    ancestors, never descendants: a team conversation never sees its projects' content.
    A personal space's scope is itself. */
  space_ids: string[];
};
export type AuthorizeScope = {
  /** Keep only spaces of these kinds; omitted keeps every level. Never adds a space. */
  levels?: SpaceKind[] | null;
  space_id: string;
};
export type SpacePermission =
  | "read"
  | "write"
  | "manage"
  | "run_evaluations"
  | "manage_evaluation_corpus"
  | "read_conversations_for_evaluation"
  | "own_organization"
  | "create_personal_space";
export type SpaceCheck = {
  permission: SpacePermission;
  space_id: string;
};
export type BootstrapResponse = {
  user_id: string;
  username: string;
};
export type BootstrapRequest = {
  token: string;
};
export type Status = "queued" | "running" | "retrying" | "blocked" | "completed";
export type TargetKind = "organization" | "team" | "project" | "document" | "session";
export type Receipt = {
  actor_subject: string;
  completed_at?: string | null;
  documents_deleted: number;
  due_at: string;
  error_code?: string | null;
  folders_deleted: number;
  id: string;
  organization_id: string;
  requested_at: string;
  rule_id?: string | null;
  spaces_deleted: number;
  status: Status;
  target_id: string;
  target_kind: TargetKind;
  target_parent_id?: string | null;
};
export type Profile = "fast" | "medium" | "rich";
export type Work = {
  contract_version: number;
  document_id: string;
  installation_id: string;
  original_sha256: string;
  processing_id: string;
  profile: Profile;
};
export type Cleanup = {
  batch: number;
  chunks: number;
  cursor: number;
  generation: string;
  output_prefix: string;
  preserve_objects: boolean;
  protected_ordinals: number[];
  purge_document: boolean;
  work: Work;
};
export type Cleaned = {
  cursor: number;
  generation: string;
  next_cursor: number;
  objects_empty: boolean;
  purge_document?: boolean;
  work: Work;
};
export type Artifact = {
  path: string;
  sha256: string;
  size: number;
};
export type Manifest = {
  artifacts: Artifact[];
  chunks: number;
  generation: string;
  rows?: number | null;
  vector_ordinals: number[];
  vectors: number;
};
export type ProjectionPhase = "ready" | "writing" | "applied";
export type RetrievalWork = {
  confirmed: boolean;
  document_id: string;
  manifest: Manifest;
  operation_id: string;
  phase: ProjectionPhase;
  retrievable: boolean;
};
export type RetrievalStep = "claim" | "applied" | "confirm";
export type RetrievalConfirmation = {
  operation_id: string;
  retrievable: boolean;
  step: RetrievalStep;
};
export type Stage = "queued" | "preparation" | "extraction" | "indexing" | "done";
export type ProcessingStatus = "pending" | "running" | "succeeded" | "failed";
export type Summary = {
  /** Published text chunks; set on success. */
  chunks: number;
  /** When the attempt became `succeeded` or `failed`. */
  completed_at?: string | null;
  created_at: string;
  document_id: string;
  /** Last reported `FailureCode`; final once `failed`. */
  error_code?: string | null;
  /** Attempt ID; pass it as `retry_of` to retry a failed attempt. */
  id: string;
  profile: Profile;
  /** Failed attempt this one retries. */
  retry_of?: string | null;
  /** Increases with every recorded change, so a poller can skip unchanged attempts. */
  revision: number;
  /** Table rows, for a tabular document. */
  rows?: number | null;
  stage: Stage;
  status: ProcessingStatus;
  /** Published search vectors; set on success. */
  vectors: number;
};
export type FailureCode =
  | "unsupported_input"
  | "access_changed"
  | "integrity_failure"
  | "extraction_failed"
  | "preview_failed"
  | "indexing_failed"
  | "capacity_exceeded"
  | "worker_failed"
  | "deadline_exceeded"
  | "delivery_unknown";
export type Failure = {
  code: FailureCode;
  generation?: string | null;
  stage: Stage;
  work: Work;
};
export type Predecessor = {
  manifest: Manifest;
  prefix: string;
};
export type Descriptor = {
  actor: string;
  committed?: Manifest | null;
  expires_at: string;
  file: any;
  folder_id: string;
  folder_path: string;
  generation: string;
  max_artifacts: number;
  max_chunks: number;
  max_output_bytes: number;
  mime: string;
  name: string;
  organization_id: string;
  output_prefix: string;
  predecessor?: Predecessor | null;
  profile_settings: any;
  size: number;
  space_id: string;
  stage: Stage;
  work: Work;
};
export type Claim = {
  activity_id: string;
  attempt: number;
  execution_id: string;
  stage: Stage;
  work: Work;
};
export type Commit = {
  manifest: Manifest;
  stage: Stage;
  work: Work;
};
export type VectorPlan = {
  count: number;
  generation: string;
  work: Work;
};
export type UploadStatus = "pending" | "stored" | "failed";
export type UploadReceipt = {
  /** When the receipt was dismissed or superseded. */
  acknowledged_at?: string | null;
  /** When the upload became `stored` or `failed`. */
  completed_at?: string | null;
  created_at: string;
  /** Set once `stored`. */
  document_id?: string | null;
  /** Failure code when `failed`. */
  error_code?: string | null;
  folder_id: string;
  /** MIME type reported by the client; metadata, not verified. */
  mime: string;
  /** NFC-normalized filename. */
  name: string;
  processing?: Summary | null;
  processing_profile?: Profile | null;
  /** The `Idempotency-Key` that identifies this receipt. */
  request_key: string;
  /** Hex SHA-256 of the received bytes. */
  sha256: string;
  /** Bytes received. */
  size: number;
  space_id: string;
  status: UploadStatus;
  /** Request key of the retry that replaced this failed upload. */
  successor_key?: string | null;
};
export type Start = {
  profile: Profile;
  /** Failed attempt to retry; required once the document has any attempt. */
  retry_of?: string | null;
};
export type Document = {
  created_at: string;
  created_by: string;
  folder_id: string | null;
  id: string;
  mime: string;
  name: string;
  retrievable: boolean;
  retrievable_pending: boolean;
  sha256: string;
  size: number;
  space_id: string;
};
export type SetRetrievable = {
  retrievable: boolean;
};
export type Folder = {
  created_at: string;
  id: string;
  name: string;
  parent_id: string | null;
  path: string;
  space_id: string;
};
export type CreateFolder = {
  name: string;
  parent_id?: string | null;
  space_id: string;
};
export type Rename = {
  name: string;
};
export type FileUpload = {
  /** The file; its multipart filename becomes the document name. */
  file: Blob;
};
export type TypeUsage = {
  bytes: number;
  documents: number;
  /** Reported MIME type, or `other`. */
  mime: string;
};
export type StorageSummary = {
  /** Total size of those documents. */
  bytes: number;
  /** Documents in this space alone. */
  documents: number;
  /** Largest accepted file. */
  max_file_bytes: number;
  /** Whether processing can be requested. */
  processing_enabled: boolean;
  /** Quota shared by the space and, for a team, its projects. */
  quota_bytes: number;
  /** Bytes reserved by uploads in progress, also counted against the quota. */
  reserved_bytes: number;
  /** Usage by reported MIME type: the 20 largest, then `other`. */
  types: TypeUsage[];
  uploads_enabled: boolean;
  /** Published bytes counted against that quota. */
  used_bytes: number;
};
export type PreflightResult = {
  /** Requested names already stored or being uploaded in the folder. */
  conflicts: string[];
  storage: StorageSummary;
};
export type Candidate = {
  /** Filename as it will be uploaded. */
  name: string;
  /** Size in bytes. */
  size: number;
};
export type Preflight = {
  /** 1..200 files to check. */
  files: Candidate[];
};
export type PublicAuth = {
  client_id: string;
  enabled: boolean;
  provider: string;
  realm_url: string;
  roles_claim?: string[] | null;
  uid_claim: string;
};
export type FrontendConfig = {
  gcu_version?: string | null;
  root_bootstrap_completed: boolean;
  root_bootstrap_required: boolean;
  user_auth: PublicAuth;
};
export type TermsRequest = {
  version: string;
};
export type Health = {
  status: string;
};
export type Report = {
  grants_acknowledged: number;
  identities_created: number;
  identities_resolved: number;
  spaces_reconciled: number;
};
export type ProvisioningUpload = {
  file: Blob;
};
export type PlatformRole = "platform_owner" | "platform_observer" | "feature_manager" | "prompt_editor";
export type Me = {
  platform_roles: PlatformRole[];
  user_id: string;
  username: string;
};
export type Acceptance = {
  accepted_at: string;
  version: string;
};
export type OnboardingStatus = {
  acceptance?: Acceptance | null;
  gcu_version?: string | null;
  root_bootstrap_required: boolean;
  user_id: string;
  username: string;
};
export type CreatePersonalSpace = {
  organization_id: string;
};
export type Role = "member" | "editor" | "admin" | "analyst" | "organization_owner" | "personal_space_creator";
export type MySpace = Space & {
  /** The subset of `roles` held only through an ancestor. */
  inherited_roles: Role[];
  organization_id: string;
  /** Effective roles, including those descending from an ancestor. */
  roles: Role[];
};
export type AgentCapabilityKind = "agent";
export type AgentScopePolicy = "admin_gated";
export type AgentEnablement = {
  default_capability_ids: string[];
  default_on: boolean;
  description: string;
  icon: string;
  id: string;
  kind: AgentCapabilityKind;
  name: string;
  public_version?: string | null;
  runtime_id: string;
  source_id: string;
  team_scope: AgentScopePolicy;
  version: string;
};
export type AgentDefaultOnResult = {
  capability_id: string;
  default_on: boolean;
};
export type SetDefaultOnRequest = {
  default_on: boolean;
};
export type CapabilityFieldType =
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
export type CapabilityFieldDescription = {
  description?: string | null;
  description_by_lang?: {
    [key: string]: string;
  };
  item_type?: CapabilityFieldType | null;
  key: string;
  max?: number | null;
  min?: number | null;
  required?: boolean;
  scope_private?: boolean | null;
  title: string;
  type: CapabilityFieldType;
};
export type CapabilityExecutionModel = "react" | "graph";
export type PodCapabilityKind = "tool";
export type PodCapabilityDescriptor = {
  config_fields?: CapabilityFieldDescription[];
  description: string;
  execution_models?: CapabilityExecutionModel[];
  icon: string;
  id: string;
  kind?: PodCapabilityKind;
  name: string;
  public_version?: string | null;
  runtime_id?: string | null;
  source_id?: string | null;
  team_settings_fields?: CapabilityFieldDescription[];
  version: string;
};
export type AffectedAgentInstance = {
  agent_instance_id: string;
  display_name: string;
  /** Display name of a personal space's owner; null for other spaces. */
  owner_name: string | null;
  space_id: string;
  space_kind: SpaceKind;
  space_name: string;
};
export type CapabilityInventoryOffer = {
  /** Present in the last successful snapshot; independent of observation state. */
  advertised: boolean;
  capability_id: string;
  /** Enabled for every space of this organization. */
  default_on: boolean;
  descriptor: PodCapabilityDescriptor;
  runtime_id: string;
  /** Instances that select this offer and may no longer use it. */
  unusable_instances: AffectedAgentInstance[];
  version: string;
};
export type CatalogObservationState = "not_observed" | "observed" | "unavailable";
export type PodTemplateCapability = {
  capability_id: string;
  default_selected: boolean;
  source_agent_id: string;
};
export type PodCapabilityInventory = {
  capabilities: CapabilityInventoryOffer[];
  checked_at?: string | null;
  enabled: boolean;
  observation: CatalogObservationState;
  observed_at?: string | null;
  runtime_id: string;
  /** Links from the last successful snapshot, all scoped to this runtime. */
  template_capabilities: PodTemplateCapability[];
};
export type ModelOfferKey = {
  source_id: string;
  upstream_model_id: string;
};
export type OrganizationModelPolicy = {
  created_at?: string | null;
  created_by?: string | null;
  default?: ModelOfferKey | null;
  fallback?: ModelOfferKey | null;
  organization_id: string;
  permitted: ModelOfferKey[];
  /** Organization ceiling, independent of the user's per-question choice. */
  reasoning_enabled: ModelOfferKey[];
  /** Zero means no saved policy: no permissions or implicit selections. */
  revision: number;
  updated_at?: string | null;
  updated_by?: string | null;
};
export type ReplaceModelPolicy = {
  default: ModelOfferKey | null;
  expected_revision: number;
  fallback: ModelOfferKey | null;
  permitted: ModelOfferKey[];
  /** Organization ceiling, independent of the user's per-question choice. */
  reasoning_enabled: ModelOfferKey[];
};
export type ModelObservation = {
  checked_at?: string | null;
  enabled: boolean;
  error_code?: string | null;
  last_success_at?: string | null;
  snapshot_revision: number;
  snapshot_source_revision?: number | null;
  source_id: string;
  source_revision: number;
  state: string;
};
export type ChatProvenance = "source_guarantee" | "api_metadata";
export type ModelMetadata = {
  chat?: boolean | null;
  chat_provenance?: ChatProvenance | null;
  context_window_tokens?: number | null;
  display_name?: string | null;
  max_input_tokens?: number | null;
  max_output_tokens?: number | null;
  /** Source-reported aptitude; absent means unknown, not unsupported. */
  reasoning?: boolean | null;
};
export type StoredModelOffer = {
  advertised: boolean;
  first_seen_at: string;
  last_seen_at: string;
  metadata: ModelMetadata;
  source_id: string;
  upstream_model_id: string;
  withdrawn_at?: string | null;
};
export type ModelInventory = {
  observation: ModelObservation;
  offers: StoredModelOffer[];
};
export type OrganizationModelInventory = {
  /** Only this organization's choices; none is a proof of executability. */
  policy: OrganizationModelPolicy;
  /** Shared platform observations. Presence/chat/discovery are independent of permission. */
  sources: ModelInventory[];
};
export type DocumentCounts = {
  /** Logical original bytes recorded in SQL, not physical storage usage. */
  bytes: number;
  documents: number;
};
export type RoleAssignments = {
  /** Direct (user, space, role) tuples, never effective/inherited grants. */
  assignments: number;
  role: Role;
};
export type ProcessingCount = {
  documents: number;
  stage: Stage;
  status: ProcessingStatus;
};
export type PublicationCounts = {
  /** Committed manifest counts; no OpenSearch presence check. */
  chunks: number;
  datasets_with_unknown_rows: number;
  documents: number;
  known_rows: number;
  /** Published datasets/*.parquet artifacts, not SQL tables. */
  tabular_datasets: number;
  /** Null when at least one dataset has no attributable row count. */
  total_rows: number | null;
  vectors: number;
};
export type SupervisionCounts = {
  active: DocumentCounts;
  /** Roles with no direct attribution are omitted (zero). */
  direct_roles: RoleAssignments[];
  /** Union of direct subjects; never sum role columns or child distinct counts. */
  distinct_users: number;
  failed_documents: number;
  /** Remaining SQL documents retired directly or through their owning space. */
  pending_purge: DocumentCounts;
  /** Latest attempt per active document. Missing status/stage pairs mean zero. */
  processing: ProcessingCount[];
  published: PublicationCounts;
};
export type TeamSupervision = {
  /** Includes the team's projects, without inherited organization roles. */
  counts: SupervisionCounts;
  id: string;
  name: string;
};
export type SupervisionTeamsPage = {
  items: TeamSupervision[];
  next_cursor: string | null;
};
export type OrganizationSupervision = {
  active_teams: number;
  /** Collection bounds, not an atomic SQL/OpenFGA snapshot. */
  collection_finished_at: string;
  collection_started_at: string;
  organization_direct: SupervisionCounts;
  organization_id: string;
  /** All personal spaces aggregated; no personal identity or space is exposed. */
  personal_total: SupervisionCounts;
  /** UUID ascending, at most 100 teams. Totals never depend on this page. */
  teams: SupervisionTeamsPage;
  teams_total: SupervisionCounts;
  totals: SupervisionCounts;
};
export type TeamSupervisionDetail = {
  collection_finished_at: string;
  collection_started_at: string;
  organization_id: string;
  team: TeamSupervision;
};
export type CreateSpace = {
  /** Initial administrator; creation grants the caller nothing on the new space. */
  admin: string;
  kind: SpaceKind;
  name: string;
  parent_id: string;
};
export type Entry =
  | {
      data: Folder;
      kind: "folder";
    }
  | {
      data: Document;
      kind: "document";
    };
export type Directory = {
  ancestors: Folder[];
  can_write: boolean;
  items: Entry[];
  limit: number;
  offset: number;
  processing: {
    [key: string]: Summary;
  };
  processing_enabled: boolean;
  total: number;
  /** Display names of the listed documents' `created_by`; unknown users are absent. */
  uploaders: {
    [key: string]: string;
  };
};
export type EntryOrder = "name_asc" | "name_desc" | "created_asc" | "created_desc" | "size_asc" | "size_desc";
export type ModelOptions = {
  max_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
};
export type AgentInstanceStatus = "enabled" | "disabled";
export type ManagedAgentInstanceSummary = {
  agent_instance_id: string;
  capability_config: {
    [key: string]: {
      [key: string]: any;
    };
  };
  created_at: string;
  created_by?: string | null;
  description?: string | null;
  display_name: string;
  model_options?: ModelOptions | null;
  /** Diagnostic only; requires explicit re-selection if no recommended_model is saved. */
  recommended_chat_profile_id?: string | null;
  recommended_model?: ModelOfferKey | null;
  role: string;
  selected_capability_ids?: string[] | null;
  source_agent_id: string;
  source_runtime_id: string;
  space_id: string;
  /** Operator state only, not runtime availability. */
  status: AgentInstanceStatus;
  template_id: string;
  tuning_field_values: {
    [key: string]: any;
  };
  updated_at: string;
  updated_by?: string | null;
  usage_statement: string;
};
export type TuningScalar = string | number | boolean;
export type TuningValue =
  | TuningScalar
  | TuningScalar[]
  | {
      [key: string]: TuningScalar;
    };
export type CreateAgentInstanceRequest = {
  /** Values for unselected capabilities are ignored. */
  capability_config_values?:
    | {
        [key: string]: {
          [key: string]: any;
        };
      }
    | {
        [key: string]: {
          [key: string]: any;
        };
      };
  /** Omitted/null inherits template defaults; [] selects no optional capabilities. */
  capability_ids?: string[] | null;
  description?: string | null;
  display_name: string;
  model_options?: ModelOptions | null;
  /** Legacy diagnostic reference only; non-null creation is refused. Re-select by offer key. */
  recommended_chat_profile_id?: string | null;
  recommended_model?: ModelOfferKey | null;
  role?: string | null;
  /** Canonical UUID returned by this space's template catalog. */
  template_id: string;
  /** All values must match TuningValue before unknown keys are ignored.
    Known values must also match the pod's FieldSpecs. */
  tuning_field_values?:
    | {
        [key: string]: TuningValue;
      }
    | {
        [key: string]: TuningValue;
      };
  usage_statement: string;
};
export type UpdateAgentInstanceRequest = {
  /** Omitted keeps config for an unchanged selection; null resets selected config. */
  capability_config_values?:
    | {
        [key: string]: {
          [key: string]: any;
        };
      }
    | {
        [key: string]: {
          [key: string]: any;
        };
      };
  /** Omitted keeps selection; null resolves current defaults; [] selects none. */
  capability_ids?: string[] | null;
  /** An empty string is an explicit description. */
  description?: string | null;
  /** Omitted/null metadata leaves the saved value unchanged. */
  display_name?: string | null;
  model_options?: ModelOptions | null;
  /** Omitted keeps the recommendation; null clears it; other values return 422. */
  recommended_chat_profile_id?: string | null;
  recommended_model?: ModelOfferKey | null;
  role?: string | null;
  status?: AgentInstanceStatus | null;
  /** Omitted keeps values; null/{} clears them; an object replaces known values. */
  tuning_field_values?:
    | {
        [key: string]: TuningValue;
      }
    | {
        [key: string]: TuningValue;
      };
  usage_statement?: string | null;
};
export type ChatControlDescriptor = {
  capability_id: string;
  params?:
    | {
        [key: string]: any;
      }
    | {
        [key: string]: any;
      };
  widget: string;
};
export type ExecutionTransport = "sse";
export type ModelPreparationErrorCode =
  | "selection_missing"
  | "reselection_required"
  | "offer_unknown"
  | "offer_forbidden"
  | "offer_unavailable"
  | "fallback_unavailable";
export type ModelPreparationError = {
  code: ModelPreparationErrorCode;
  message: string;
};
export type ModelDiagnostic =
  | "unknown_offer"
  | "not_permitted"
  | "source_disabled"
  | "source_revision_unobserved"
  | "discovery_unavailable"
  | "withdrawn"
  | "chat_not_established"
  | "options_exceed_known_limit";
export type PreparationModelOffer = {
  candidate: boolean;
  diagnostics: ModelDiagnostic[];
  key: ModelOfferKey;
  metadata: ModelMetadata | null;
  permitted: boolean;
  reasoning_enabled: boolean;
  selectable: boolean;
};
export type PreparationModels = {
  default: ModelOfferKey | null;
  fallback: ModelOfferKey | null;
  /** A retained diagnostic only, never a selectable profile. */
  legacy_profile_id: string | null;
  offers: PreparationModelOffer[];
  options: ModelOptions;
  recommendation: ModelOfferKey | null;
  requires_reselection: boolean;
};
export type ExecutionPreparation = {
  agent_configuration_revision: number;
  agent_instance_id: string;
  chat_controls: ChatControlDescriptor[];
  execute_stream_url: string;
  execute_url: string;
  execution_transport: ExecutionTransport;
  max_chat_input_chars: number | null;
  /** RFC 6570 Level 1 template. Substitute the registered session ID. */
  messages_url_template: string;
  model_choice: ModelOfferKey | null;
  model_error: ModelPreparationError | null;
  models: PreparationModels;
  runtime_id: string;
  space_id: string;
  /** False until the managed Weaver HITL journey is connected. */
  supports_hitl: boolean;
  supports_streaming: boolean;
  supports_ui_parts: boolean;
};
export type RuntimeAgent = {
  /** Saved tuning, excluding the legacy profile reference exposed in models for diagnostics.
    No refresh from the catalog; fields, values and capability envelopes are preserved. */
  configuration: any;
  configuration_revision: number;
  configuration_updated_at: string;
  instance_id: string;
  runtime_id: string;
  /** Organization-qualified OpenFGA identity, distinct from the registry key. */
  template_id: string;
  template_key: string;
};
export type ModelConnection = {
  api_root: string;
  /** Platform-approved reference to pod-local inference provisioning, never a secret value. */
  credential_binding: string;
  provider: string;
};
export type RuntimeModelOffer = {
  /** Necessary known facts only; local support, credentials and connectivity remain unproven. */
  candidate: boolean;
  connection?: ModelConnection | null;
  diagnostics: ModelDiagnostic[];
  key: ModelOfferKey;
  metadata?: ModelMetadata | null;
  observation?: ModelObservation | null;
  permitted: boolean;
  /** New selection writes additionally require successful current discovery (M2). */
  selectable: boolean;
};
export type RuntimeModels = {
  /** Diagnostic only. Never an alternative resolution key. */
  legacy_profile_id?: string | null;
  /** Union of permitted keys and retained recommendation/default/fallback references. */
  offers: RuntimeModelOffer[];
  options: ModelOptions;
  policy: OrganizationModelPolicy;
  recommendation?: ModelOfferKey | null;
  requires_reselection: boolean;
};
export type RuntimeSpace = {
  id: string;
  kind: SpaceKind;
  /** Canonical organization ownership, not inherited document scope for personal spaces. */
  organization_id: string | null;
  project_id: string | null;
  team_id: string | null;
};
export type RuntimeBinding = {
  agent: RuntimeAgent;
  conversation_id: string | null;
  models: RuntimeModels;
  run_id: string | null;
  space: RuntimeSpace;
  subject_id: string;
};
export type AgentTemplateStatus = "available";
export type AgentTemplateSummary = {
  /** Pod-owned descriptors, including config fields, schemas and routing metadata. */
  available_capabilities: {
    [key: string]: any;
  }[];
  capabilities: string[];
  category: string;
  default_capability_ids: string[];
  /** Pod-owned FieldSpecs, including localized defaults and UI hints, unchanged. */
  default_tuning_fields: {
    [key: string]: any;
  }[];
  description: string;
  description_by_lang?:
    | {
        [key: string]: string;
      }
    | {
        [key: string]: string;
      };
  display_name: string;
  /** Current pod input limit, absent when not advertised. */
  max_chat_input_chars?: number | null;
  public_version?: string | null;
  source_agent_id: string;
  source_runtime_id: string;
  status: AgentTemplateStatus;
  supports_capabilities: boolean;
  tags: string[];
  team_instantiable: boolean;
  template_id: string;
};
export type SessionDetails = {
  agent_configuration_changed: boolean;
  agent_configuration_revision: number;
  agent_deleted: boolean;
  agent_disabled: boolean;
  /** Current name, or the registration snapshot after instance removal. */
  agent_display_name: string;
  agent_instance_id: string;
  created_at: string;
  /** Public history destination, independent of instance/template execution state.
    Null if this runtime has no enabled, platform-approved public route. */
  messages_url: string | null;
  runtime_id: string;
  session_id: string;
  space_id: string;
  template_id: string;
  title: string | null;
  updated_at: string;
};
export type CreateSessionRequest = {
  agent_configuration_revision: number;
  agent_instance_id: string;
  /** Frontend-generated identifier, retained verbatim. */
  session_id: string;
  title?: string | null;
};
export type UpdateSessionRequest = {
  /** Omitted/null keeps the current title; an empty string explicitly clears it. */
  title?: string | null;
  /** Last observed activity. Monotonic, capped at server time; omission keeps activity. */
  updated_at?: string | null;
};
export type AgentSort = "name" | "created_at:desc" | "updated_at:desc";
export type Language = "en" | "fr";
export type TeamSortMode = "recent" | "alpha";
export type ThemeMode = "light" | "dark" | "system";
export type UserPreferences = {
  agent_sort: AgentSort;
  initialized: boolean;
  language?: Language | null;
  sidebar_collapsed: boolean;
  team_sort_mode: TeamSortMode;
  theme_mode: ThemeMode;
  ui_theme_id?: string | null;
};
export type PatchUserPreferences = {
  agent_sort?: AgentSort | null;
  language?: Language | null;
  sidebar_collapsed?: boolean | null;
  team_sort_mode?: TeamSortMode | null;
  theme_mode?: ThemeMode | null;
  ui_theme_id?: string | null;
};
export type Grant = {
  role: PlatformRole;
  user_id: string;
};
export const {
  useOrganizationRegistryQuery,
  useLazyOrganizationRegistryQuery,
  useCreateOrganizationMutation,
  useSearchOrganizationCandidatesQuery,
  useLazySearchOrganizationCandidatesQuery,
  useGetOrganizationQuery,
  useLazyGetOrganizationQuery,
  useUpdateOrganizationMutation,
  useTeamRegistryQuery,
  useLazyTeamRegistryQuery,
  useExecuteStreamMutation,
  useAuthorizeDocumentMutation,
  useAuthorizePlatformMutation,
  useAuthorizeScopeMutation,
  useAuthorizeSpaceMutation,
  useBootstrapPlatformAdminMutation,
  useDeletionStatusQuery,
  useLazyDeletionStatusQuery,
  useCleanupQuery,
  useLazyCleanupQuery,
  useCleanedMutation,
  useRetrievalWorkQuery,
  useLazyRetrievalWorkQuery,
  useConfirmRetrievableMutation,
  useAbandonMutation,
  useClaimMutation,
  useCommitMutation,
  useOriginalQuery,
  useLazyOriginalQuery,
  useVectorsMutation,
  useWorkQuery,
  useLazyWorkQuery,
  useReceiptQuery,
  useLazyReceiptQuery,
  useAcknowledgeMutation,
  useDeleteDocumentMutation,
  useContentQuery,
  useLazyContentQuery,
  usePreviewQuery,
  useLazyPreviewQuery,
  useHistoryQuery,
  useLazyHistoryQuery,
  useStartMutation,
  useSetRetrievableMutation,
  useCreateFolderMutation,
  useDeleteFolderMutation,
  useRenameFolderMutation,
  useUploadMutation,
  usePreflightMutation,
  useFrontendConfigQuery,
  useLazyFrontendConfigQuery,
  useAcceptTermsMutation,
  useHealthQuery,
  useLazyHealthQuery,
  useImportBlueprintMutation,
  useMeQuery,
  useLazyMeQuery,
  useOnboardingStatusQuery,
  useLazyOnboardingStatusQuery,
  useCreatePersonalSpaceMutation,
  useMySpacesQuery,
  useLazyMySpacesQuery,
  useOrganizationAgentsQuery,
  useLazyOrganizationAgentsQuery,
  useSetOrganizationAgentDefaultMutation,
  useOrganizationCapabilitiesQuery,
  useLazyOrganizationCapabilitiesQuery,
  useRefreshOrganizationCapabilitiesMutation,
  useSetOrganizationCapabilityDefaultMutation,
  useOrganizationCapabilityRevokeImpactQuery,
  useLazyOrganizationCapabilityRevokeImpactQuery,
  useOrganizationModelPolicyQuery,
  useLazyOrganizationModelPolicyQuery,
  useReplaceOrganizationModelPolicyMutation,
  useRefreshModelSourceMutation,
  useOrganizationModelsQuery,
  useLazyOrganizationModelsQuery,
  useOrganizationSupervisionQuery,
  useLazyOrganizationSupervisionQuery,
  useTeamSupervisionQuery,
  useLazyTeamSupervisionQuery,
  useCreateSpaceMutation,
  useDeleteSpaceMutation,
  useReceiptsQuery,
  useLazyReceiptsQuery,
  useEntriesQuery,
  useLazyEntriesQuery,
  useGrantMutation,
  useRevokeMutation,
  useSummaryQuery,
  useLazySummaryQuery,
  useListAgentInstancesQuery,
  useLazyListAgentInstancesQuery,
  useCreateAgentInstanceMutation,
  useGetAgentInstanceQuery,
  useLazyGetAgentInstanceQuery,
  useDeleteAgentInstanceMutation,
  useUpdateAgentInstanceMutation,
  usePrepareExecutionMutation,
  useResolveRuntimeQuery,
  useLazyResolveRuntimeQuery,
  useSpaceAgentTemplatesQuery,
  useLazySpaceAgentTemplatesQuery,
  useListSessionsQuery,
  useLazyListSessionsQuery,
  useCreateSessionMutation,
  useGetSessionQuery,
  useLazyGetSessionQuery,
  useDeleteSessionMutation,
  useUpdateSessionMutation,
  useGetMyPreferencesQuery,
  useLazyGetMyPreferencesQuery,
  usePatchMyPreferencesMutation,
  useListPlatformRolesQuery,
  useLazyListPlatformRolesQuery,
  useGrantPlatformRoleMutation,
  useRevokePlatformRoleMutation,
} = injectedRtkApi;
