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
    messages: build.query<MessagesApiResponse, MessagesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/agents/sessions/${queryArg.sessionId}/messages` }),
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
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    authorizeScope: build.mutation<AuthorizeScopeApiResponse, AuthorizeScopeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/authorize/scope`,
        method: "POST",
        body: queryArg.authorizeScope,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    authorizeSpace: build.mutation<AuthorizeSpaceApiResponse, AuthorizeSpaceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/authorize/space`,
        method: "POST",
        body: queryArg.spaceCheck,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    bootstrapPlatformAdmin: build.mutation<BootstrapPlatformAdminApiResponse, BootstrapPlatformAdminApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/bootstrap/platform-admin`,
        method: "POST",
        body: queryArg.bootstrapRequest,
      }),
    }),
    capabilityPreparationCleanup: build.query<
      CapabilityPreparationCleanupApiResponse,
      CapabilityPreparationCleanupApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/capability-preparations/cleanup`,
        params: {
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    capabilityPreparationWorker: build.query<CapabilityPreparationWorkerApiResponse, CapabilityPreparationWorkerApiArg>(
      {
        query: (queryArg) => ({
          url: `/control-plane/v1/capability-preparations/worker`,
          params: {
            runtime_id: queryArg.runtimeId,
          },
        }),
      },
    ),
    capabilityPreparationContext: build.query<
      CapabilityPreparationContextApiResponse,
      CapabilityPreparationContextApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/capability-preparations/${queryArg.id}` }),
    }),
    capabilityPreparationCleaned: build.mutation<
      CapabilityPreparationCleanedApiResponse,
      CapabilityPreparationCleanedApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/capability-preparations/${queryArg.id}/cleaned`,
        method: "POST",
      }),
    }),
    capabilityPreparationConfirm: build.mutation<
      CapabilityPreparationConfirmApiResponse,
      CapabilityPreparationConfirmApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/capability-preparations/${queryArg.id}/confirm`,
        method: "POST",
        body: queryArg.resultConfirmation,
      }),
    }),
    capabilityPreparationContent: build.query<
      CapabilityPreparationContentApiResponse,
      CapabilityPreparationContentApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/capability-preparations/${queryArg.id}/content` }),
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
    writes: build.mutation<WritesApiResponse, WritesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/${queryArg.id}/writes`,
        method: "POST",
        body: queryArg.writeReceipt,
      }),
    }),
    receipt: build.query<ReceiptApiResponse, ReceiptApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/document-uploads/${queryArg.id}` }),
    }),
    acknowledge: build.mutation<AcknowledgeApiResponse, AcknowledgeApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/document-uploads/${queryArg.id}/acknowledgment`, method: "PUT" }),
    }),
    deleteDocument: build.mutation<DeleteDocumentApiResponse, DeleteDocumentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}`,
        method: "DELETE",
        params: {
          immediate: queryArg.immediate,
        },
      }),
    }),
    content: build.query<ContentApiResponse, ContentApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/documents/${queryArg.id}/content` }),
    }),
    preview: build.query<PreviewApiResponse, PreviewApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/documents/${queryArg.id}/preview`,
        params: {
          artifact: queryArg.artifact,
          session_id: queryArg.sessionId,
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
      query: (queryArg) => ({
        url: `/control-plane/v1/folders/${queryArg.id}`,
        method: "DELETE",
        params: {
          empty_only: queryArg.emptyOnly,
        },
      }),
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
    marketplaceProposalSpaces: build.query<MarketplaceProposalSpacesApiResponse, MarketplaceProposalSpacesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/me/marketplace-proposal-spaces`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    marketplaces: build.query<MarketplacesApiResponse, MarketplacesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/me/marketplaces`,
        params: {
          after: queryArg.after,
        },
      }),
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
    myUsage: build.query<MyUsageApiResponse, MyUsageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/me/usage`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
        },
      }),
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
    powerpointUploadReceipt: build.query<PowerpointUploadReceiptApiResponse, PowerpointUploadReceiptApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/powerpoint-uploads/${queryArg.requestKey}` }),
    }),
    defaultSkills: build.query<DefaultSkillsApiResponse, DefaultSkillsApiArg>({
      query: () => ({ url: `/control-plane/v1/skills/defaults` }),
    }),
    createSpace: build.mutation<CreateSpaceApiResponse, CreateSpaceApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces`, method: "POST", body: queryArg.createSpace }),
    }),
    deleteSpace: build.mutation<DeleteSpaceApiResponse, DeleteSpaceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}`,
        method: "DELETE",
        params: {
          immediate: queryArg.immediate,
        },
      }),
    }),
    projectDeletionStatus: build.query<ProjectDeletionStatusApiResponse, ProjectDeletionStatusApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/deletion` }),
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
    spaceMemberCandidates: build.query<SpaceMemberCandidatesApiResponse, SpaceMemberCandidatesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/member-candidates`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    spaceMembers: build.query<SpaceMembersApiResponse, SpaceMembersApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/members`,
        params: {
          after: queryArg.after,
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
    marketplaceEntries: build.query<MarketplaceEntriesApiResponse, MarketplaceEntriesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/entries`,
        params: {
          after: queryArg.after,
          kind: queryArg.kind,
        },
      }),
    }),
    marketplaceEntry: build.query<MarketplaceEntryApiResponse, MarketplaceEntryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/entries/${queryArg.entryId}`,
      }),
    }),
    installMarketplaceEntry: build.mutation<InstallMarketplaceEntryApiResponse, InstallMarketplaceEntryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/entries/${queryArg.entryId}/installations`,
        method: "POST",
        body: queryArg.installRequest,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
      }),
    }),
    withdrawMarketplaceEntry: build.mutation<WithdrawMarketplaceEntryApiResponse, WithdrawMarketplaceEntryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/entries/${queryArg.entryId}/withdrawal`,
        method: "PUT",
        body: queryArg.withdrawRequest,
      }),
    }),
    marketplaceProposals: build.query<MarketplaceProposalsApiResponse, MarketplaceProposalsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/proposals`,
        params: {
          after: queryArg.after,
          kind: queryArg.kind,
          state: queryArg.state,
          proposing_space_id: queryArg.proposingSpaceId,
        },
      }),
    }),
    submitMarketplaceProposal: build.mutation<SubmitMarketplaceProposalApiResponse, SubmitMarketplaceProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/proposals`,
        method: "POST",
        body: queryArg.submitProposalRequest,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
      }),
    }),
    marketplaceProposal: build.query<MarketplaceProposalApiResponse, MarketplaceProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/proposals/${queryArg.proposalId}`,
      }),
    }),
    cancelMarketplaceProposal: build.mutation<CancelMarketplaceProposalApiResponse, CancelMarketplaceProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/proposals/${queryArg.proposalId}/cancellation`,
        method: "PUT",
      }),
    }),
    decideMarketplaceProposal: build.mutation<DecideMarketplaceProposalApiResponse, DecideMarketplaceProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.marketplaceSpaceId}/marketplace/proposals/${queryArg.proposalId}/decision`,
        method: "PUT",
        body: queryArg.proposalDecisionRequest,
      }),
    }),
    listAgentInstances: build.query<ListAgentInstancesApiResponse, ListAgentInstancesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances`,
        params: {
          after: queryArg.after,
        },
      }),
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
          reasoning: queryArg.reasoning,
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
          model_source_id: queryArg.modelSourceId,
          model_upstream_id: queryArg.modelUpstreamId,
          reasoning: queryArg.reasoning,
        },
      }),
    }),
    admitRuntime: build.mutation<AdmitRuntimeApiResponse, AdmitRuntimeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances/${queryArg.agentInstanceId}/runtime`,
        method: "POST",
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          conversation: queryArg.conversation,
          model_source_id: queryArg.modelSourceId,
          model_upstream_id: queryArg.modelUpstreamId,
          reasoning: queryArg.reasoning,
          resume: queryArg.resume,
        },
      }),
    }),
    spaceAgentTemplates: build.query<SpaceAgentTemplatesApiResponse, SpaceAgentTemplatesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-templates` }),
    }),
    spaceCapabilityPolicies: build.query<SpaceCapabilityPoliciesApiResponse, SpaceCapabilityPoliciesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/capability-policies` }),
    }),
    replaceSpaceCapabilityPolicy: build.mutation<
      ReplaceSpaceCapabilityPolicyApiResponse,
      ReplaceSpaceCapabilityPolicyApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/capability-policies/${queryArg.runtimeId}`,
        method: "PUT",
        body: queryArg.replaceSpaceCapabilityPolicy,
      }),
    }),
    marketplaceInstallation: build.query<MarketplaceInstallationApiResponse, MarketplaceInstallationApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/marketplace-installations/${queryArg.installationId}`,
      }),
    }),
    resolvePowerpointTemplate: build.query<ResolvePowerpointTemplateApiResponse, ResolvePowerpointTemplateApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/powerpoint-template`,
        params: {
          agent_instance_id: queryArg.agentInstanceId,
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    uploadPowerpointTemplate: build.mutation<UploadPowerpointTemplateApiResponse, UploadPowerpointTemplateApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/powerpoint-template`,
        method: "PUT",
        body: queryArg.fileUpload,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
        params: {
          agent_instance_id: queryArg.agentInstanceId,
          runtime_id: queryArg.runtimeId,
          template_id: queryArg.templateId,
          expected_file_id: queryArg.expectedFileId,
        },
      }),
    }),
    removePowerpointTemplate: build.mutation<RemovePowerpointTemplateApiResponse, RemovePowerpointTemplateApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/powerpoint-template`,
        method: "DELETE",
        params: {
          agent_instance_id: queryArg.agentInstanceId,
          runtime_id: queryArg.runtimeId,
          expected_file_id: queryArg.expectedFileId,
        },
      }),
    }),
    rerunPowerpointTemplate: build.mutation<RerunPowerpointTemplateApiResponse, RerunPowerpointTemplateApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/powerpoint-template/prepare`,
        method: "POST",
        body: queryArg.powerPointChange,
        params: {
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    getPowerpointSettings: build.query<GetPowerpointSettingsApiResponse, GetPowerpointSettingsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/powerpoint-template/settings`,
        params: {
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    putPowerpointSettings: build.mutation<PutPowerpointSettingsApiResponse, PutPowerpointSettingsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/powerpoint-template/settings`,
        method: "PUT",
        body: queryArg.powerPointSettingsChange,
        params: {
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    downloadPowerpointTemplate: build.query<DownloadPowerpointTemplateApiResponse, DownloadPowerpointTemplateApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/powerpoint-template/${queryArg.fileId}/content`,
        params: {
          agent_instance_id: queryArg.agentInstanceId,
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    listPromptCategories: build.query<ListPromptCategoriesApiResponse, ListPromptCategoriesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompt-categories`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    createPromptCategory: build.mutation<CreatePromptCategoryApiResponse, CreatePromptCategoryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompt-categories`,
        method: "POST",
        body: queryArg.promptCategoryRequest,
      }),
    }),
    deletePromptCategory: build.mutation<DeletePromptCategoryApiResponse, DeletePromptCategoryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompt-categories/${queryArg.categoryId}`,
        method: "DELETE",
      }),
    }),
    renamePromptCategory: build.mutation<RenamePromptCategoryApiResponse, RenamePromptCategoryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompt-categories/${queryArg.categoryId}`,
        method: "PATCH",
        body: queryArg.promptCategoryRequest,
      }),
    }),
    listPrompts: build.query<ListPromptsApiResponse, ListPromptsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompts`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    createPrompt: build.mutation<CreatePromptApiResponse, CreatePromptApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompts`,
        method: "POST",
        body: queryArg.createPromptRequest,
      }),
    }),
    getPrompt: build.query<GetPromptApiResponse, GetPromptApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompts/${queryArg.promptId}` }),
    }),
    deletePrompt: build.mutation<DeletePromptApiResponse, DeletePromptApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompts/${queryArg.promptId}`,
        method: "DELETE",
      }),
    }),
    updatePrompt: build.mutation<UpdatePromptApiResponse, UpdatePromptApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompts/${queryArg.promptId}`,
        method: "PATCH",
        body: queryArg.updatePromptRequest,
      }),
    }),
    addPromptFavorite: build.mutation<AddPromptFavoriteApiResponse, AddPromptFavoriteApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompts/${queryArg.promptId}/favorite`,
        method: "PUT",
      }),
    }),
    removePromptFavorite: build.mutation<RemovePromptFavoriteApiResponse, RemovePromptFavoriteApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/prompts/${queryArg.promptId}/favorite`,
        method: "DELETE",
      }),
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
        params: {
          immediate: queryArg.immediate,
        },
      }),
    }),
    updateSession: build.mutation<UpdateSessionApiResponse, UpdateSessionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}`,
        method: "PATCH",
        body: queryArg.updateSessionRequest,
      }),
    }),
    listAttachments: build.query<ListAttachmentsApiResponse, ListAttachmentsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/attachments`,
      }),
    }),
    uploadAttachment: build.mutation<UploadAttachmentApiResponse, UploadAttachmentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/attachments`,
        method: "POST",
        body: queryArg.fileUpload,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
        params: {
          retry_of: queryArg.retryOf,
        },
      }),
    }),
    deleteAttachment: build.mutation<DeleteAttachmentApiResponse, DeleteAttachmentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/attachments/${queryArg.documentId}`,
        method: "DELETE",
      }),
    }),
    downloadAttachment: build.query<DownloadAttachmentApiResponse, DownloadAttachmentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/attachments/${queryArg.documentId}/content`,
      }),
    }),
    recordUsage: build.mutation<RecordUsageApiResponse, RecordUsageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/exchanges/${queryArg.exchangeId}/usage`,
        method: "POST",
        body: queryArg.usageReport,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
      }),
    }),
    listConversationFiles: build.query<ListConversationFilesApiResponse, ListConversationFilesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/files`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          limit: queryArg.limit,
          offset: queryArg.offset,
        },
      }),
    }),
    writeConversationFile: build.mutation<WriteConversationFileApiResponse, WriteConversationFileApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/files`,
        method: "POST",
        body: queryArg.fileUpload,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
        params: {
          path: queryArg.path,
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          expected_content_id: queryArg.expectedContentId,
          source_content_id: queryArg.sourceContentId,
        },
      }),
    }),
    fileWriteTarget: build.query<FileWriteTargetApiResponse, FileWriteTargetApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/files/write-target`,
        params: {
          path: queryArg.path,
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    downloadConversationFile: build.query<DownloadConversationFileApiResponse, DownloadConversationFileApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/files/${queryArg.documentId}/content`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    previewConversationFile: build.query<PreviewConversationFileApiResponse, PreviewConversationFileApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/files/${queryArg.documentId}/preview`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    recordTitle: build.mutation<RecordTitleApiResponse, RecordTitleApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/generated-title`,
        method: "POST",
        body: queryArg.generatedTitle,
      }),
    }),
    listSkills: build.query<ListSkillsApiResponse, ListSkillsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/skills` }),
    }),
    createSkill: build.mutation<CreateSkillApiResponse, CreateSkillApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/skills`,
        method: "POST",
        body: queryArg.createSkill,
      }),
    }),
    installSkill: build.mutation<InstallSkillApiResponse, InstallSkillApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/skills/packages/${queryArg.name}/install`,
        method: "POST",
      }),
    }),
    skillScope: build.query<SkillScopeApiResponse, SkillScopeApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/skills/scope` }),
    }),
    previewSkill: build.query<PreviewSkillApiResponse, PreviewSkillApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/skills/scope/${queryArg.skillId}` }),
    }),
    getSkill: build.query<GetSkillApiResponse, GetSkillApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/skills/${queryArg.skillId}` }),
    }),
    putSkill: build.mutation<PutSkillApiResponse, PutSkillApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/skills/${queryArg.skillId}`,
        method: "PUT",
        body: queryArg.putSkill,
      }),
    }),
    deleteSkill: build.mutation<DeleteSkillApiResponse, DeleteSkillApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/skills/${queryArg.skillId}`,
        method: "DELETE",
      }),
    }),
    spaceUsage: build.query<SpaceUsageApiResponse, SpaceUsageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/usage`,
        params: {
          since: queryArg.since,
          until: queryArg.until,
        },
      }),
    }),
    wikiAvailability: build.query<WikiAvailabilityApiResponse, WikiAvailabilityApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/availability`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    wikiPages: build.query<WikiPagesApiResponse, WikiPagesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    createWikiPage: build.mutation<CreateWikiPageApiResponse, CreateWikiPageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages`,
        method: "POST",
        body: queryArg.createWikiPageRequest,
      }),
    }),
    wikiPage: build.query<WikiPageApiResponse, WikiPageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages/${queryArg.pageId}`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    deleteWikiPage: build.mutation<DeleteWikiPageApiResponse, DeleteWikiPageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages/${queryArg.pageId}`,
        method: "DELETE",
      }),
    }),
    patchWikiPage: build.mutation<PatchWikiPageApiResponse, PatchWikiPageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages/${queryArg.pageId}`,
        method: "PATCH",
        body: queryArg.updateWikiMetadataRequest,
      }),
    }),
    writeWikiPage: build.mutation<WriteWikiPageApiResponse, WriteWikiPageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages/${queryArg.pageId}/content`,
        method: "PUT",
        body: queryArg.updateWikiContentRequest,
      }),
    }),
    setWikiReviewMark: build.mutation<SetWikiReviewMarkApiResponse, SetWikiReviewMarkApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages/${queryArg.pageId}/review`,
        method: "POST",
        body: queryArg.wikiReviewRequest,
      }),
    }),
    wikiRevisions: build.query<WikiRevisionsApiResponse, WikiRevisionsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages/${queryArg.pageId}/revisions`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
          cursor: queryArg.cursor,
        },
      }),
    }),
    restoreWikiRevision: build.mutation<RestoreWikiRevisionApiResponse, RestoreWikiRevisionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/pages/${queryArg.pageId}/revisions/${queryArg.revisionId}/restore`,
        method: "POST",
      }),
    }),
    proposeWikiEdit: build.mutation<ProposeWikiEditApiResponse, ProposeWikiEditApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals/edit`,
        method: "POST",
        body: queryArg.proposeWikiEditRequest,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    proposeWikiPage: build.mutation<ProposeWikiPageApiResponse, ProposeWikiPageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals/page`,
        method: "POST",
        body: queryArg.proposeWikiPageRequest,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    wikiProposal: build.query<WikiProposalApiResponse, WikiProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals/${queryArg.proposalId}`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    publishWikiProposal: build.mutation<PublishWikiProposalApiResponse, PublishWikiProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals/${queryArg.proposalId}/publish`,
        method: "POST",
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    wikiRules: build.query<WikiRulesApiResponse, WikiRulesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/rules`,
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    writeWikiRules: build.mutation<WriteWikiRulesApiResponse, WriteWikiRulesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/rules`,
        method: "PUT",
        body: queryArg.updateWikiContentRequest,
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
export type MessagesApiResponse = /** status 200 undefined */ ChatMessage[];
export type MessagesApiArg = {
  sessionId: string;
};
export type AuthorizeDocumentApiResponse = /** status 200 Success */ Allowed;
export type AuthorizeDocumentApiArg = {
  authorizeDocument: AuthorizeDocument;
};
export type AuthorizePlatformApiResponse = /** status 200 Success */ Allowed;
export type AuthorizePlatformApiArg = {
  /** Person asserted by a trusted workload; requires run and agent. */
  person?: string;
  /** Run identifier asserted with person and agent. */
  run?: string;
  /** Agent identifier asserted with person and run; no runtime refresh. */
  agent?: string;
  platformCheck: PlatformCheck;
};
export type AuthorizeScopeApiResponse = /** status 200 Success */ Scope;
export type AuthorizeScopeApiArg = {
  /** Person asserted by a trusted workload; requires run and agent. */
  person?: string;
  /** Run identifier asserted with person and agent. */
  run?: string;
  /** Agent identifier asserted with person and run; no runtime refresh. */
  agent?: string;
  authorizeScope: AuthorizeScope;
};
export type AuthorizeSpaceApiResponse = /** status 200 Success */ Allowed;
export type AuthorizeSpaceApiArg = {
  /** Person asserted by a trusted workload; requires run and agent. */
  person?: string;
  /** Run identifier asserted with person and agent. */
  run?: string;
  /** Agent identifier asserted with person and run; no runtime refresh. */
  agent?: string;
  spaceCheck: SpaceCheck;
};
export type BootstrapPlatformAdminApiResponse = /** status 200 Success */ BootstrapResponse;
export type BootstrapPlatformAdminApiArg = {
  bootstrapRequest: BootstrapRequest;
};
export type CapabilityPreparationCleanupApiResponse = /** status 200 undefined */ string[];
export type CapabilityPreparationCleanupApiArg = {
  runtimeId: string;
};
export type CapabilityPreparationWorkerApiResponse = /** status 200 undefined */ WorkerBinding;
export type CapabilityPreparationWorkerApiArg = {
  runtimeId: string;
};
export type CapabilityPreparationContextApiResponse = /** status 200 undefined */ Work;
export type CapabilityPreparationContextApiArg = {
  id: string;
};
export type CapabilityPreparationCleanedApiResponse = unknown;
export type CapabilityPreparationCleanedApiArg = {
  id: string;
};
export type CapabilityPreparationConfirmApiResponse = unknown;
export type CapabilityPreparationConfirmApiArg = {
  id: string;
  resultConfirmation: ResultConfirmation;
};
export type CapabilityPreparationContentApiResponse = /** status 200 undefined */ string;
export type CapabilityPreparationContentApiArg = {
  id: string;
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
export type WritesApiResponse = unknown;
export type WritesApiArg = {
  id: string;
  writeReceipt: WriteReceipt;
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
  /** Request immediate purge for an eligible resource as a platform administrator. */
  immediate?: boolean;
};
export type ContentApiResponse = /** status 200 undefined */ string;
export type ContentApiArg = {
  id: string;
};
export type PreviewApiResponse = /** status 200 undefined */ MetadataPreview | /** status 206 undefined */ string;
export type PreviewApiArg = {
  id: string;
  /** native, raw, metadata, or a relative path from the published manifest. */
  artifact?: string;
  /** Required for a conversation attachment; ownership is checked server-side. */
  sessionId?: string;
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
  /** Refuse deletion if any child folder or document remains */
  emptyOnly?: boolean;
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
export type MarketplaceProposalSpacesApiResponse = /** status 200 undefined */ ProposalSpacePage;
export type MarketplaceProposalSpacesApiArg = {
  after?: string;
};
export type MarketplacesApiResponse = /** status 200 undefined */ MarketplacePage;
export type MarketplacesApiArg = {
  after?: string;
};
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
export type MyUsageApiResponse = /** status 200 undefined */ UsageResponse;
export type MyUsageApiArg = {
  /** Inclusive ISO 8601 instant with offset; defaults to 30 days before until. */
  since?: string;
  /** Exclusive ISO 8601 instant with offset; defaults to now. Maximum range: 366 days. */
  until?: string;
};
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
export type PowerpointUploadReceiptApiResponse = /** status 200 undefined */ PowerPointFile;
export type PowerpointUploadReceiptApiArg = {
  requestKey: string;
};
export type DefaultSkillsApiResponse = /** status 200 undefined */ PackageSummary[];
export type DefaultSkillsApiArg = void;
export type CreateSpaceApiResponse = /** status 201 Success */ Space;
export type CreateSpaceApiArg = {
  createSpace: CreateSpace;
};
export type DeleteSpaceApiResponse = /** status 200 Already completed */
  | Receipt
  | /** status 202 Durably accepted */ Receipt;
export type DeleteSpaceApiArg = {
  id: string;
  /** Request immediate purge for an eligible resource as a platform administrator. */
  immediate?: boolean;
};
export type ProjectDeletionStatusApiResponse = /** status 200 undefined */ Receipt;
export type ProjectDeletionStatusApiArg = {
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
export type SpaceMemberCandidatesApiResponse = /** status 200 undefined */ SpaceMembers;
export type SpaceMemberCandidatesApiArg = {
  id: string;
  after?: string;
};
export type SpaceMembersApiResponse = /** status 200 undefined */ SpaceMembers;
export type SpaceMembersApiArg = {
  id: string;
  after?: string;
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
export type MarketplaceEntriesApiResponse = /** status 200 undefined */ MarketplaceEntryPage;
export type MarketplaceEntriesApiArg = {
  marketplaceSpaceId: string;
  after?: string;
  kind?: MarketplaceKind;
};
export type MarketplaceEntryApiResponse = /** status 200 undefined */ MarketplaceEntryDetail;
export type MarketplaceEntryApiArg = {
  marketplaceSpaceId: string;
  entryId: string;
};
export type InstallMarketplaceEntryApiResponse = /** status 200 undefined */ InstallationReceipt;
export type InstallMarketplaceEntryApiArg = {
  marketplaceSpaceId: string;
  entryId: string;
  "Idempotency-Key": string;
  installRequest: InstallRequest;
};
export type WithdrawMarketplaceEntryApiResponse = unknown;
export type WithdrawMarketplaceEntryApiArg = {
  marketplaceSpaceId: string;
  entryId: string;
  withdrawRequest: WithdrawRequest;
};
export type MarketplaceProposalsApiResponse = /** status 200 undefined */ ProposalPage;
export type MarketplaceProposalsApiArg = {
  marketplaceSpaceId: string;
  after?: string;
  kind?: MarketplaceKind;
  state?: ProposalState;
  proposingSpaceId?: string;
};
export type SubmitMarketplaceProposalApiResponse = /** status 200 undefined */ MarketplaceProposal;
export type SubmitMarketplaceProposalApiArg = {
  marketplaceSpaceId: string;
  "Idempotency-Key": string;
  submitProposalRequest: SubmitProposalRequest;
};
export type MarketplaceProposalApiResponse = /** status 200 undefined */ MarketplaceProposal;
export type MarketplaceProposalApiArg = {
  marketplaceSpaceId: string;
  proposalId: string;
};
export type CancelMarketplaceProposalApiResponse = /** status 200 undefined */ ProposalSummary;
export type CancelMarketplaceProposalApiArg = {
  marketplaceSpaceId: string;
  proposalId: string;
};
export type DecideMarketplaceProposalApiResponse = /** status 200 undefined */ ProposalSummary;
export type DecideMarketplaceProposalApiArg = {
  marketplaceSpaceId: string;
  proposalId: string;
  proposalDecisionRequest: ProposalDecisionRequest;
};
export type ListAgentInstancesApiResponse = /** status 200 undefined */ AgentInstancePage;
export type ListAgentInstancesApiArg = {
  spaceId: string;
  /** Previous page cursor */
  after?: string;
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
  /** Requested reasoning; subject to policy and known capability. */
  reasoning?: boolean;
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
  /** Registered conversation; checked before loading history. */
  conversation?: string;
  /** Requested source; never authority. */
  modelSourceId?: string;
  /** Requested model; supply with source. */
  modelUpstreamId?: string;
  /** Requested reasoning subject to policy. */
  reasoning?: boolean;
};
export type AdmitRuntimeApiResponse = /** status 200 undefined */ RuntimeBinding;
export type AdmitRuntimeApiArg = {
  spaceId: string;
  agentInstanceId: string;
  person: string;
  run: string;
  agent: string;
  conversation?: string;
  modelSourceId?: string;
  modelUpstreamId?: string;
  reasoning?: boolean;
  resume?: boolean;
};
export type SpaceAgentTemplatesApiResponse = /** status 200 undefined */ AgentTemplateSummary[];
export type SpaceAgentTemplatesApiArg = {
  spaceId: string;
};
export type SpaceCapabilityPoliciesApiResponse = /** status 200 undefined */ SpaceCapabilityPolicy[];
export type SpaceCapabilityPoliciesApiArg = {
  spaceId: string;
};
export type ReplaceSpaceCapabilityPolicyApiResponse = unknown;
export type ReplaceSpaceCapabilityPolicyApiArg = {
  spaceId: string;
  runtimeId: string;
  replaceSpaceCapabilityPolicy: ReplaceSpaceCapabilityPolicy;
};
export type MarketplaceInstallationApiResponse = /** status 200 undefined */ InstallationReceipt;
export type MarketplaceInstallationApiArg = {
  spaceId: string;
  installationId: string;
};
export type ResolvePowerpointTemplateApiResponse = /** status 200 undefined */ PowerPointResolution;
export type ResolvePowerpointTemplateApiArg = {
  spaceId: string;
  agentInstanceId?: string;
  runtimeId?: string;
};
export type UploadPowerpointTemplateApiResponse = /** status 200 undefined */ PowerPointFile;
export type UploadPowerpointTemplateApiArg = {
  spaceId: string;
  agentInstanceId?: string;
  runtimeId?: string;
  /** Only for a new draft instance */
  templateId?: string;
  /** Current own attachment; omit only if absent */
  expectedFileId?: string;
  "Idempotency-Key": string;
  fileUpload: FileUpload;
};
export type RemovePowerpointTemplateApiResponse = unknown;
export type RemovePowerpointTemplateApiArg = {
  spaceId: string;
  agentInstanceId?: string;
  runtimeId?: string;
  expectedFileId?: string;
};
export type RerunPowerpointTemplateApiResponse = unknown;
export type RerunPowerpointTemplateApiArg = {
  spaceId: string;
  runtimeId: string;
  powerPointChange: PowerPointChange;
};
export type GetPowerpointSettingsApiResponse = /** status 200 undefined */ PowerPointSettings;
export type GetPowerpointSettingsApiArg = {
  spaceId: string;
  runtimeId: string;
};
export type PutPowerpointSettingsApiResponse = unknown;
export type PutPowerpointSettingsApiArg = {
  spaceId: string;
  runtimeId: string;
  powerPointSettingsChange: PowerPointSettingsChange;
};
export type DownloadPowerpointTemplateApiResponse = /** status 200 undefined */ string;
export type DownloadPowerpointTemplateApiArg = {
  spaceId: string;
  fileId: string;
  agentInstanceId?: string;
  runtimeId?: string;
};
export type ListPromptCategoriesApiResponse = /** status 200 undefined */ PromptCategoryPage;
export type ListPromptCategoriesApiArg = {
  spaceId: string;
  after?: string;
};
export type CreatePromptCategoryApiResponse = /** status 201 undefined */ PromptCategory;
export type CreatePromptCategoryApiArg = {
  spaceId: string;
  promptCategoryRequest: PromptCategoryRequest;
};
export type DeletePromptCategoryApiResponse = unknown;
export type DeletePromptCategoryApiArg = {
  spaceId: string;
  categoryId: string;
};
export type RenamePromptCategoryApiResponse = /** status 200 undefined */ PromptCategory;
export type RenamePromptCategoryApiArg = {
  spaceId: string;
  categoryId: string;
  promptCategoryRequest: PromptCategoryRequest;
};
export type ListPromptsApiResponse = /** status 200 undefined */ PromptPage;
export type ListPromptsApiArg = {
  spaceId: string;
  /** Exclusive logical_name cursor from next_cursor. Omit for the first page; at most 100 entries per page. */
  after?: string;
};
export type CreatePromptApiResponse = /** status 201 undefined */ Prompt;
export type CreatePromptApiArg = {
  spaceId: string;
  createPromptRequest: CreatePromptRequest;
};
export type GetPromptApiResponse = /** status 200 undefined */ Prompt;
export type GetPromptApiArg = {
  spaceId: string;
  promptId: string;
};
export type DeletePromptApiResponse = unknown;
export type DeletePromptApiArg = {
  spaceId: string;
  promptId: string;
};
export type UpdatePromptApiResponse = /** status 200 undefined */ Prompt;
export type UpdatePromptApiArg = {
  spaceId: string;
  promptId: string;
  updatePromptRequest: UpdatePromptRequest;
};
export type AddPromptFavoriteApiResponse = unknown;
export type AddPromptFavoriteApiArg = {
  spaceId: string;
  promptId: string;
};
export type RemovePromptFavoriteApiResponse = unknown;
export type RemovePromptFavoriteApiArg = {
  spaceId: string;
  promptId: string;
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
  /** Request immediate purge for an eligible resource as a platform administrator. */
  immediate?: boolean;
};
export type UpdateSessionApiResponse = /** status 200 undefined */ SessionDetails;
export type UpdateSessionApiArg = {
  spaceId: string;
  sessionId: string;
  updateSessionRequest: UpdateSessionRequest;
};
export type ListAttachmentsApiResponse = /** status 200 undefined */ Attachment[];
export type ListAttachmentsApiArg = {
  spaceId: string;
  sessionId: string;
};
export type UploadAttachmentApiResponse = /** status 200 Replay of a stored request key */
  | UploadReceipt
  | /** status 201 Stored */ UploadReceipt;
export type UploadAttachmentApiArg = {
  spaceId: string;
  /** The caller's conversation */
  sessionId: string;
  /** Caller-chosen request UUID; replaying it is safe */
  "Idempotency-Key": string;
  /** Request key of a failed upload of the same file to the same conversation */
  retryOf?: string;
  fileUpload: FileUpload;
};
export type DeleteAttachmentApiResponse = /** status 200 undefined */ Receipt | /** status 202 undefined */ Receipt;
export type DeleteAttachmentApiArg = {
  spaceId: string;
  sessionId: string;
  documentId: string;
};
export type DownloadAttachmentApiResponse = /** status 200 undefined */ string;
export type DownloadAttachmentApiArg = {
  spaceId: string;
  sessionId: string;
  documentId: string;
};
export type RecordUsageApiResponse = unknown;
export type RecordUsageApiArg = {
  /** Caller-chosen consumption report UUID; required and unique per run */
  "Idempotency-Key": string;
  spaceId: string;
  sessionId: string;
  /** Turn identifier, without surrounding whitespace or control characters */
  exchangeId: string;
  usageReport: UsageReport;
};
export type ListConversationFilesApiResponse = /** status 200 undefined */ ConversationFile[];
export type ListConversationFilesApiArg = {
  spaceId: string;
  sessionId: string;
  person?: string;
  run?: string;
  agent?: string;
  limit?: number;
  offset?: number;
};
export type WriteConversationFileApiResponse = /** status 200 undefined */ FileWrite;
export type WriteConversationFileApiArg = {
  spaceId: string;
  sessionId: string;
  path: string;
  person: string;
  run: string;
  agent: string;
  expectedContentId?: string;
  sourceContentId?: string;
  "Idempotency-Key": string;
  fileUpload: FileUpload;
};
export type FileWriteTargetApiResponse = /** status 200 undefined */ FileWriteTarget;
export type FileWriteTargetApiArg = {
  spaceId: string;
  sessionId: string;
  path: string;
  person: string;
  run: string;
  agent: string;
};
export type DownloadConversationFileApiResponse = unknown;
export type DownloadConversationFileApiArg = {
  spaceId: string;
  sessionId: string;
  documentId: string;
  person?: string;
  run?: string;
  agent?: string;
};
export type PreviewConversationFileApiResponse = unknown;
export type PreviewConversationFileApiArg = {
  spaceId: string;
  sessionId: string;
  documentId: string;
  person?: string;
  run?: string;
  agent?: string;
};
export type RecordTitleApiResponse = unknown;
export type RecordTitleApiArg = {
  spaceId: string;
  sessionId: string;
  generatedTitle: GeneratedTitle;
};
export type ListSkillsApiResponse = /** status 200 undefined */ SpaceSkill[];
export type ListSkillsApiArg = {
  spaceId: string;
};
export type CreateSkillApiResponse = unknown;
export type CreateSkillApiArg = {
  spaceId: string;
  createSkill: CreateSkill;
};
export type InstallSkillApiResponse = unknown;
export type InstallSkillApiArg = {
  spaceId: string;
  name: string;
};
export type SkillScopeApiResponse = /** status 200 undefined */ SkillCatalog;
export type SkillScopeApiArg = {
  spaceId: string;
};
export type PreviewSkillApiResponse = /** status 200 undefined */ SkillDetail;
export type PreviewSkillApiArg = {
  spaceId: string;
  skillId: string;
};
export type GetSkillApiResponse = /** status 200 undefined */ PutSkill;
export type GetSkillApiArg = {
  spaceId: string;
  skillId: string;
};
export type PutSkillApiResponse = unknown;
export type PutSkillApiArg = {
  spaceId: string;
  skillId: string;
  putSkill: PutSkill;
};
export type DeleteSkillApiResponse = unknown;
export type DeleteSkillApiArg = {
  spaceId: string;
  skillId: string;
};
export type SpaceUsageApiResponse = /** status 200 undefined */ UsageResponse;
export type SpaceUsageApiArg = {
  spaceId: string;
  /** Inclusive ISO 8601 instant with offset; defaults to 30 days before until. */
  since?: string;
  /** Exclusive ISO 8601 instant with offset; defaults to now. Maximum range: 366 days. */
  until?: string;
};
export type WikiAvailabilityApiResponse = /** status 200 undefined */ WikiAvailability;
export type WikiAvailabilityApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
};
export type WikiPagesApiResponse = /** status 200 undefined */ WikiPageTree;
export type WikiPagesApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
};
export type CreateWikiPageApiResponse = /** status 201 undefined */ WikiPageDetail;
export type CreateWikiPageApiArg = {
  spaceId: string;
  createWikiPageRequest: CreateWikiPageRequest;
};
export type WikiPageApiResponse = /** status 200 undefined */ WikiPageDetail;
export type WikiPageApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
  /** Stable page slug */
  pageId: string;
};
export type DeleteWikiPageApiResponse = unknown;
export type DeleteWikiPageApiArg = {
  spaceId: string;
  pageId: string;
};
export type PatchWikiPageApiResponse = /** status 200 undefined */ WikiPageSummary;
export type PatchWikiPageApiArg = {
  spaceId: string;
  pageId: string;
  updateWikiMetadataRequest: UpdateWikiMetadataRequest;
};
export type WriteWikiPageApiResponse = /** status 200 undefined */ WikiPageDetail;
export type WriteWikiPageApiArg = {
  spaceId: string;
  pageId: string;
  updateWikiContentRequest: UpdateWikiContentRequest;
};
export type SetWikiReviewMarkApiResponse = /** status 200 undefined */ WikiPageSummary;
export type SetWikiReviewMarkApiArg = {
  spaceId: string;
  pageId: string;
  wikiReviewRequest: WikiReviewRequest;
};
export type WikiRevisionsApiResponse = /** status 200 undefined */ WikiRevisionList;
export type WikiRevisionsApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
  pageId: string;
  cursor?: string;
};
export type RestoreWikiRevisionApiResponse = /** status 200 undefined */ WikiPageDetail;
export type RestoreWikiRevisionApiArg = {
  spaceId: string;
  pageId: string;
  revisionId: string;
};
export type ProposeWikiEditApiResponse = /** status 201 undefined */ WikiProposal;
export type ProposeWikiEditApiArg = {
  person: string;
  run: string;
  agent: string;
  spaceId: string;
  sessionId: string;
  proposeWikiEditRequest: ProposeWikiEditRequest;
};
export type ProposeWikiPageApiResponse = /** status 201 undefined */ WikiProposal;
export type ProposeWikiPageApiArg = {
  person: string;
  run: string;
  agent: string;
  spaceId: string;
  sessionId: string;
  proposeWikiPageRequest: ProposeWikiPageRequest;
};
export type WikiProposalApiResponse = /** status 200 undefined */ WikiProposal;
export type WikiProposalApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
  proposalId: string;
};
export type PublishWikiProposalApiResponse = /** status 200 undefined */ WikiPageDetail;
export type PublishWikiProposalApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
  proposalId: string;
};
export type WikiRulesApiResponse = /** status 200 undefined */ WikiPageDetail;
export type WikiRulesApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
};
export type WriteWikiRulesApiResponse = /** status 200 undefined */ WikiPageDetail;
export type WriteWikiRulesApiArg = {
  spaceId: string;
  updateWikiContentRequest: UpdateWikiContentRequest;
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
  admin_username: string;
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
  admin_username?: string | null;
  name?: string | null;
  owner_username?: string | null;
};
export type SearchHit = {
  chunk_kind?: string | null;
  content: string;
  file_name?: string | null;
  page?: number | null;
  score: number;
  section?: string | null;
  title: string;
  uid: string;
  [key: string]: any;
};
export type RuntimeEvent =
  | {
      kind: "thought_start";
      phase: string;
      sequence: number;
      source: string;
      thought_id: string;
    }
  | {
      delta: string;
      kind: "thought_delta";
      sequence: number;
      thought_id: string;
    }
  | {
      kind: "thought_end";
      sequence: number;
      thought_id: string;
    }
  | {
      arguments: {
        [key: string]: any;
      };
      call_id: string;
      kind: "tool_call";
      sequence: number;
      tool_name: string;
    }
  | {
      call_id: string;
      content: string;
      is_error: boolean;
      kind: "tool_result";
      latency_ms: number;
      sequence: number;
      tool_name: string;
    }
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
      kind: "execution_error";
      message: string;
      sequence: number;
    }
  | {
      kind: "session_title";
      sequence: number;
      session_id: string;
    }
  | {
      content: string;
      finish_reason: string;
      kind: "final";
      sequence: number;
      sources: SearchHit[];
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
export type ChatMetadata = {
  sources: SearchHit[];
};
export type MessagePart =
  | {
      text: string;
      type: "text";
    }
  | {
      args: {
        [key: string]: any;
      };
      call_id: string;
      name: string;
      type: "tool_call";
    }
  | {
      call_id: string;
      content: string;
      ok: boolean;
      type: "tool_result";
    };
export type ChatMessage = {
  channel: string;
  exchange_id: string;
  metadata: ChatMetadata;
  parts: MessagePart[];
  rank: number;
  role: string;
  session_id: string;
  timestamp: string;
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
  | "rescue_team_owner"
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
  space_id: string;
  /** Filter for chunks and metadata: `space_id` must be one of these. The space and its
    ancestors, never descendants: a team conversation never sees its projects' content.
    A personal space's scope is itself. */
  space_ids: string[];
};
export type CorpusLevel = "organization" | "team" | "project";
export type AuthorizeScope = {
  /** Keep only spaces of these kinds; omitted keeps every level. Never adds a space. */
  levels?: CorpusLevel[] | null;
  space_id: string;
};
export type SpacePermission =
  | "read"
  | "write"
  | "manage"
  | "run_evaluations"
  | "manage_evaluation_corpus"
  | "read_conversations_for_evaluation"
  | "read_usage"
  | "administer_organization"
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
export type WorkerBinding = {
  installation_id: string;
  task_queue: string;
};
export type Work = {
  agent_instance_id: string | null;
  capability_id: string;
  config: object;
  configuration_revision: number | null;
  file_id: string;
  filename: string;
  installation_id: string;
  preparation_id: string;
  runtime_id: string;
  sha256: string;
  size: number;
  space_id: string;
  state: string;
};
export type ResultConfirmation = {
  error?: string | null;
  reference?: string | null;
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
  /** The document's organization, whose corpus holds its vectors. */
  organization_id: string;
  phase: ProjectionPhase;
  retrievable: boolean;
};
export type RetrievalStep = "claim" | "applied" | "confirm";
export type RetrievalConfirmation = {
  operation_id: string;
  retrievable: boolean;
  step: RetrievalStep;
};
export type Profile = "fast" | "medium" | "rich";
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
export type ModelAuthKind = "none" | "api_key" | "entra";
export type ModelAuth = {
  client_id?: string | null;
  /** Name of the header carrying a gateway key, with any kind. */
  gateway_key_header?: string | null;
  kind: ModelAuthKind;
  scope?: string | null;
  /** Required with kind `entra`, forbidden otherwise, like `client_id` and `scope`. */
  tenant_id?: string | null;
};
export type ModelDialect = "openai" | "openai_compatible" | "mistral";
export type ModelRoute = "standard" | "azure_deployment";
export type ModelWire = "openai_chat" | "openai_responses";
export type ModelConnection = {
  /** Separately approved canonical root; never derived from a discovery URL. */
  api_root: string;
  api_version?: string | null;
  auth: ModelAuth;
  /** Source-bound workload provisioning reference; never a credential value. */
  credential_binding: string;
  dialect: ModelDialect;
  route: ModelRoute;
  wire: ModelWire;
};
export type ModelOfferKey = {
  source_id: string;
  upstream_model_id: string;
};
export type ReasoningEffort = "high";
export type EffectiveModelOptions = {
  max_tokens?: number | null;
  reasoning_effort?: ReasoningEffort | null;
  temperature?: number | null;
  top_p?: number | null;
};
export type ModelSelectionSource = "user_choice" | "instance_recommendation" | "default" | "withdrawal_fallback";
export type InferenceSelection = {
  key: ModelOfferKey;
  options: EffectiveModelOptions;
  policy_revision: number;
  snapshot_revision: number;
  source: ModelSelectionSource;
  source_revision: number;
};
export type InferenceAdmission = {
  connection: ModelConnection;
  selection: InferenceSelection;
};
export type StageModels = {
  embedding: InferenceAdmission | null;
  vision: InferenceAdmission | null;
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
  folder_id: string | null;
  folder_path: string | null;
  generation: string;
  max_artifacts: number;
  max_chunks: number;
  max_output_bytes: number;
  mime: string;
  /** Models admitted for this stage under the organization's policy. */
  models: StageModels;
  name: string;
  organization_id: string;
  output_prefix: string;
  predecessor?: Predecessor | null;
  profile_settings: any;
  session_id: string | null;
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
export type WriteReceipt = {
  completed: boolean;
  generation: string;
  work: Work;
  workspace?: boolean;
  write_id: string;
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
  /** Destination folder; null for a conversation attachment. */
  folder_id: string | null;
  /** MIME type reported by the client; metadata, not verified. */
  mime: string;
  /** NFC-normalized filename. */
  name: string;
  processing?: Summary | null;
  processing_profile?: Profile | null;
  /** The `Idempotency-Key` that identifies this receipt. */
  request_key: string;
  /** Destination conversation; null for a drive upload. */
  session_id: string | null;
  /** Hex SHA-256 of the received bytes. */
  sha256: string;
  /** Bytes received. */
  size: number;
  space_id: string;
  status: UploadStatus;
  /** Request key of the retry that replaced this failed upload. */
  successor_key?: string | null;
};
export type EmailHeaders = {
  cc: string[];
  in_reply_to?: string | null;
  message_id?: string | null;
  to: string[];
};
export type PreviewExtensions = {
  email?: EmailHeaders | null;
};
export type ExtractedFacts = {
  author?: string | null;
  created?: string | null;
  title?: string | null;
};
export type MetadataPreview = {
  extensions?: PreviewExtensions | null;
  identity: ExtractedFacts;
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
export type PlatformRole = "platform_admin" | "platform_observer" | "feature_manager" | "prompt_editor";
export type Me = {
  platform_roles: PlatformRole[];
  user_id: string;
  username: string;
};
export type MarketplaceKind = "prompt" | "skill" | "agent";
export type ProposalSpace = Space & {
  marketplace_space_ids: string[];
  /** Ordinary resource placement in this writable space, for proposal and installation pickers. */
  resource_kinds: MarketplaceKind[];
};
export type ProposalSpacePage = {
  items: ProposalSpace[];
  next_cursor: string | null;
};
export type Marketplace = {
  name: string;
  space_id: string;
};
export type MarketplacePage = {
  items: Marketplace[];
  next_cursor: string | null;
};
export type Acceptance = {
  accepted_at: string;
  version: string;
};
export type OnboardingStatus = {
  acceptance?: Acceptance | null;
  admitted: boolean;
  gcu_version?: string | null;
  root_bootstrap_required: boolean;
  user_id: string;
  username: string;
};
export type CreatePersonalSpace = {
  organization_id: string;
};
export type Role = "member" | "editor" | "owner" | "analyst" | "organization_admin";
export type MySpace = Space & {
  organization_id: string;
  /** Roles held directly on this space. */
  roles: Role[];
};
export type UsageTotals = {
  cache_creation_tokens: number;
  cache_read_tokens: number;
  input_tokens: number;
  output_tokens: number;
  /** Distinct (session_id, exchange_id) whose first consumption falls in the range.
    HITL resumes add tokens, never another turn. */
  turns: number;
};
export type AgentUsage = UsageTotals & {
  agent_instance_id: string;
  /** Current instance name, latest retained session name, or null. */
  display_name: string | null;
  /** Consumption space recorded in the journal. */
  space_id: string;
};
export type ModelUsageTotals = UsageTotals & {
  model_source_id: string;
  upstream_model_id: string;
};
export type UsageInterval = "hour" | "day" | "week";
export type UsagePoint = UsageTotals & {
  /** Start of the UTC bucket; the first bucket may start before since. */
  start: string;
};
export type UsageResponse = {
  /** Sorted by input + output tokens descending. No per-user breakdown. */
  by_agent: AgentUsage[];
  /** Sorted by input + output tokens descending; a turn may use several models. */
  by_model: ModelUsageTotals[];
  interval: UsageInterval;
  series: UsagePoint[];
  since: string;
  totals: UsageTotals;
  until: string;
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
  /** Browser route derived from the platform-approved pod ingress. */
  route_base_url?: string | null;
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
export type OrganizationModelPolicy = {
  created_at?: string | null;
  created_by?: string | null;
  default?: ModelOfferKey | null;
  embedding?: ModelOfferKey | null;
  /** Set by the first indexing: the corpus keeps this embedding model. */
  embedding_locked: boolean;
  fallback?: ModelOfferKey | null;
  organization_id: string;
  permitted: ModelOfferKey[];
  /** Organization ceiling, independent of the user's per-question choice. */
  reasoning_enabled: ModelOfferKey[];
  /** Zero means no saved policy: no permissions or implicit selections. */
  revision: number;
  title?: ModelOfferKey | null;
  updated_at?: string | null;
  updated_by?: string | null;
  vision?: ModelOfferKey | null;
};
export type ReplaceModelPolicy = {
  default: ModelOfferKey | null;
  embedding: ModelOfferKey | null;
  expected_revision: number;
  fallback: ModelOfferKey | null;
  permitted: ModelOfferKey[];
  /** Organization ceiling, independent of the user's per-question choice. */
  reasoning_enabled: ModelOfferKey[];
  title: ModelOfferKey | null;
  vision: ModelOfferKey | null;
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
  /** Platform-attested embedding offer; such an offer is never chat. */
  embedding?: boolean | null;
  max_input_tokens?: number | null;
  max_output_tokens?: number | null;
  /** Source-reported aptitude; absent means unknown, not unsupported. */
  reasoning?: boolean | null;
  /** Source-reported image input; absent means unknown, not unsupported. */
  vision?: boolean | null;
};
export type StoredModelOffer = {
  advertised: boolean;
  first_seen_at: string;
  last_seen_at: string;
  metadata: ModelMetadata;
  /** Server-calculated eligibility for a new administrative selection. */
  selectable: boolean;
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
  /** Assigned source observations. Presence/chat/discovery are independent of permission. */
  sources: ModelInventory[];
};
export type DocumentCounts = {
  /** Logical original bytes recorded in SQL, not physical storage usage. */
  bytes: number;
  documents: number;
};
export type RoleAssignments = {
  /** Direct (user, space, role) tuples. */
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
  /** Includes the team's projects; organization roles are excluded. */
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
  /** Collection bounds, not an atomic snapshot of all displayed data. */
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
export type PowerPointFileStatus = "pending" | "stored" | "retired";
export type PowerPointFile = {
  agent_instance_id: string | null;
  cleaned_at: string | null;
  error_code: string | null;
  id: string;
  mime: string;
  name: string;
  published_at: string | null;
  request_key: string;
  runtime_id: string | null;
  sha256: string;
  size: number;
  space_id: string;
  /** Stored means attached in CP, not prepared or activated in the pod. */
  status: PowerPointFileStatus;
};
export type PackageSummary = {
  argument_hint?: string | null;
  builtin: boolean;
  description: string;
  disable_model_invocation: boolean;
  name: string;
  user_invocable: boolean;
};
export type CreateSpace = {
  kind: SpaceKind;
  name: string;
  /** Initial business owner; creation grants the caller nothing on the new space. */
  owner: string;
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
export type SpaceMember = {
  /** Roles on the managed space, also for candidates from its parent. */
  roles: Role[];
  user: UserSummary;
};
export type SpaceMembers = {
  items: SpaceMember[];
  next_cursor: string | null;
};
export type MarketplaceEntrySummary = {
  can_withdraw: boolean;
  description: string;
  display_name: string;
  entry_id: string;
  kind: MarketplaceKind;
  marketplace_space_id: string;
  origin_name: string;
  package_hash: string;
  proposal_id: string;
  publication_version: number;
  published_at: string;
};
export type MarketplaceEntryPage = {
  items: MarketplaceEntrySummary[];
  next_cursor: string | null;
};
export type PromptPackage = {
  description?: string | null;
  display_name: string;
  logical_name: string;
  tags: string[];
  text: string;
};
export type SkillPackage = {
  files: {
    [key: string]: string;
  };
  name: string;
};
export type ExportedCapability = {
  config: {
    [key: string]: any;
  };
  /** Exported configuration files, indexed by asset key and encoded as base64. */
  files: {
    [key: string]: string;
  };
  schema_version: string;
};
export type ModelOptions = {
  max_tokens?: number | null;
  temperature?: number | null;
  top_p?: number | null;
};
export type AgentPackage = {
  capabilities: {
    [key: string]: ExportedCapability;
  };
  description?: string | null;
  display_name: string;
  logical_name: string;
  model_options: ModelOptions;
  recommended_model?: ModelOfferKey | null;
  role: string;
  runtime_id: string;
  template_agent_id: string;
  /** Only fields certified exportable by the owning pod, never opaque saved tuning. */
  tuning_field_values: {
    [key: string]: any;
  };
  usage_statement: string;
};
export type MarketplacePackage =
  | {
      content: PromptPackage;
      kind: "prompt";
    }
  | {
      content: SkillPackage;
      kind: "skill";
    }
  | {
      content: AgentPackage;
      kind: "agent";
    };
export type MarketplaceEntryDetail = MarketplaceEntrySummary & {
  package: MarketplacePackage;
};
export type InstallationReceipt = {
  entry_id: string;
  installation_id: string;
  installed_at: string;
  kind: MarketplaceKind;
  package_hash: string;
  proposal_id: string;
  resource_exists: boolean;
  resource_id: string;
  space_id: string;
};
export type InstallOptions =
  | {
      category_id?: string | null;
      kind: "prompt";
      logical_name: string;
    }
  | {
      kind: "skill";
    }
  | {
      display_name: string;
      kind: "agent";
      logical_name?: string | null;
    };
export type InstallRequest = {
  destination_space_id: string;
  options: InstallOptions;
  proposal_id: string;
};
export type WithdrawRequest = {
  expected_publication_version: number;
};
export type ProposalActions = {
  can_cancel: boolean;
  can_decide: boolean;
};
export type ProposalState = "pending" | "approved" | "rejected" | "cancelled";
export type ProposalSummary = {
  actions: ProposalActions;
  decided_at?: string | null;
  decided_by?: string | null;
  decision_reason?: string | null;
  description: string;
  display_name: string;
  entry_id: string;
  kind: MarketplaceKind;
  marketplace_space_id: string;
  origin_name: string;
  package_hash: string;
  proposal_id: string;
  proposing_space_id?: string | null;
  /** Current catalogue version, independent of this proposal's terminal decision. */
  publication_version: number;
  published_proposal_id?: string | null;
  state: ProposalState;
  submitted_at: string;
  submitted_by: string;
};
export type ProposalPage = {
  items: ProposalSummary[];
  next_cursor: string | null;
};
export type MarketplaceProposal = ProposalSummary & {
  package: MarketplacePackage;
};
export type SubmitProposalRequest = {
  /** Absent creates an independent entry. Set explicitly for a replacement proposal. */
  entry_id?: string | null;
  /** Prompt updated_at, skill revision, or agent configuration_revision as a string. */
  expected_revision: string;
  kind: MarketplaceKind;
  source_resource_id: string;
  source_space_id: string;
};
export type ProposalDecisionRequest = {
  approve: boolean;
  expected_publication_version: number;
  reason?: string | null;
};
export type AgentInstanceStatus = "enabled" | "disabled";
export type ManagedAgentInstanceSummary = {
  agent_instance_id: string;
  capability_config: {
    [key: string]: {
      [key: string]: any;
    };
  };
  configuration_revision: number;
  created_at: string;
  created_by: string;
  description?: string | null;
  display_name: string;
  logical_name: string;
  model_options?: ModelOptions | null;
  preparation_error: string | null;
  preparation_state: string;
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
  updated_by: string;
  usage_statement: string;
};
export type AgentInstancePage = {
  /** Authorized instances in immutable logical-name order; at most 100 rows. */
  items: ManagedAgentInstanceSummary[];
  /** Follow until null. Pages are current reads, not a snapshot. */
  next_cursor: string | null;
};
export type FileChange = {
  expected_file_id?: string | null;
  /** A staged CP receipt for this exact space, logical pod and instance; null removes. */
  file_id?: string | null;
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
  /** Unique within the space, ignoring case. Surrounding whitespace is trimmed. */
  display_name: string;
  /** Immutable space-local reference, independent of the mutable display label.
    Omitted/null generates "agent-" followed by the new instance UUID's 32 hex digits.
    Explicit references are preserved; collisions return 409 agent_name_conflict. */
  logical_name?: string | null;
  model_options?: ModelOptions | null;
  powerpoint?: FileChange | null;
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
  /** Omitted/null metadata leaves the saved value unchanged.
    A new display name must remain unique within the space, ignoring case. */
  display_name?: string | null;
  model_options?: ModelOptions | null;
  powerpoint?: FileChange | null;
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
export type SkillAvailability = "available" | "disabled" | "unavailable";
export type SkillSummary = PackageSummary & {
  skill_id: string;
  space_id: string;
  space_name: string;
};
export type SkillCatalog = {
  availability: SkillAvailability;
  policy_supported: boolean;
  revision: string;
  skills: SkillSummary[];
  supported: boolean;
};
export type ExecutionPreparation = {
  agent_configuration_revision: number;
  agent_instance_id: string;
  /** Browser-reachable router of each selected capability that ships one. */
  capability_base_urls: {
    [key: string]: string;
  };
  chat_controls: ChatControlDescriptor[];
  execute_stream_url: string;
  execute_url: string | null;
  execution_transport: ExecutionTransport;
  inference: InferenceSelection | null;
  max_chat_input_chars: number | null;
  /** RFC 6570 Level 1 template; null when this runtime has no durable history. */
  messages_url_template: string | null;
  model_choice: ModelOfferKey | null;
  model_error: ModelPreparationError | null;
  models: PreparationModels;
  runtime_id: string;
  skill_detail_url_template?: string | null;
  skills?: SkillCatalog | null;
  space_id: string;
  /** Durable resume support advertised by the owning runtime; false when absent. */
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
  /** Organization-qualified template identity, distinct from the registry key. */
  template_id: string;
  template_key: string;
};
export type RuntimeAttachment = {
  document_id: string;
  mime: string;
  name: string;
};
export type RuntimeModelOffer = {
  /** Necessary known facts only; local support, credentials and connectivity remain unproven. */
  candidate: boolean;
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
  /** Canonical organization attachment, not inherited document scope for personal spaces. */
  organization_id: string | null;
  project_id: string | null;
  team_id: string | null;
};
export type TitleAdmission = {
  attempt_id: string;
  inference: InferenceAdmission;
};
export type RuntimeBinding = {
  agent: RuntimeAgent;
  attachments: RuntimeAttachment[];
  conversation_id: string | null;
  inference?: InferenceAdmission | null;
  models: RuntimeModels;
  run_id: string | null;
  skill_files?:
    | {
        [key: string]: string;
      }
    | {
        [key: string]: string;
      };
  skills?: SkillCatalog | null;
  space: RuntimeSpace;
  subject_id: string;
  title?: TitleAdmission | null;
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
  /** Owning pod advertises durable, single-use human-interrupt resume support. */
  supports_hitl: boolean;
  tags: string[];
  team_instantiable: boolean;
  template_id: string;
};
export type LocalOffer = {
  advertised: boolean;
  capability_id: string;
  descriptor: PodCapabilityDescriptor;
  parent_permitted: boolean;
  permitted: boolean;
};
export type SpaceCapabilityPolicy = {
  offers: LocalOffer[];
  permitted_ids: string[];
  reachable: boolean;
  restricted: boolean;
  revision: number;
  runtime_id: string;
  source_enabled: boolean;
};
export type ReplaceSpaceCapabilityPolicy = {
  expected_revision: number;
  permitted_ids: string[];
  restricted: boolean;
};
export type PowerPointSource = "agent" | "organization" | "builtin";
export type PowerPointResolution = {
  activation_ready: boolean;
  /** Opaque reference owned by the capability on the resolved logical pod. */
  analysis_reference: string | null;
  file: PowerPointFile | null;
  preparation_error: string | null;
  preparation_state: string;
  /** agent, organization, or builtin; no configurable platform default. */
  source: PowerPointSource;
};
export type PowerPointChange = {
  /** Compare-and-swap: omit only when no own file is currently attached. */
  expected_file_id?: string | null;
};
export type PowerPointSettings = {
  config: object;
  current: PowerPointResolution;
  replacement: PowerPointResolution | null;
};
export type PowerPointSettingsChange = {
  config: object;
  expected_file_id?: string | null;
};
export type PromptCategory = {
  id: string;
  name: string;
  space_id: string;
};
export type PromptCategoryPage = {
  items: PromptCategory[];
  /** Exclusive UUID cursor. Follow until null before displaying category filters. */
  next_cursor: string | null;
};
export type PromptCategoryRequest = {
  /** NFC-normalized, trimmed, nonblank, without control characters. */
  name: string;
};
export type PromptMetadata = {
  category_id: string | null;
  created_at: string;
  created_by: string;
  description: string | null;
  display_name: string;
  /** Immutable space-local identity. The slash command is "/" + logical_name. */
  logical_name: string;
  prompt_id: string;
  space_id: string;
  tags: string[];
  updated_at: string;
  updated_by: string;
};
export type PromptSummary = PromptMetadata & {
  is_favorite: boolean;
  /** First 240 characters, selected in PostgreSQL without fetching the full body. */
  text_preview: string;
};
export type PromptPage = {
  /** At most 100 entries, ordered by immutable logical_name in ASCII order. */
  items: PromptSummary[];
  /** Pass as `after` until null, including for search, pickers and command menus.
    Pages are not a snapshot; restart to include concurrent inserts before the cursor. */
  next_cursor: string | null;
};
export type Prompt = PromptMetadata & {
  is_favorite: boolean;
  /** Current full text, preserved verbatim. */
  text: string;
};
export type CreatePromptRequest = {
  /** Optional category belonging to this same space. */
  category_id?: string | null;
  /** Omitted/null means no description. NUL characters are rejected. */
  description?: string | null;
  /** NFC-normalized and trimmed, nonblank, without control characters. */
  display_name: string;
  /** Immutable; "skill" is reserved. Invalid names are rejected, never normalized. */
  logical_name: string;
  /** Up to 20 nonblank labels, each at most 64 characters. NFC-normalized and deduplicated. */
  tags?: string[];
  /** Nonblank text, preserved verbatim. NUL is rejected. */
  text: string;
};
export type UpdatePromptRequest = {
  /** Omitted keeps the category; null removes it. */
  category_id?: string | null;
  /** Omitted keeps the value; null clears it; a string replaces it (including ""). */
  description?: string | null;
  /** Omitted/null keeps the value. Supplied strings follow creation's label rules. */
  display_name?: string | null;
  /** Omitted/null keeps tags; [] clears them. */
  tags?: string[] | null;
  /** Omitted/null keeps the value; a nonblank string replaces it verbatim. */
  text?: string | null;
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
export type Attachment = {
  created_at: string;
  document_id: string;
  /** MIME type reported by the client; metadata, not verified. */
  mime: string;
  /** NFC-normalized filename, unique within the conversation. */
  name: string;
  processing: Summary | null;
  /** Documentary eligibility at read time, independent of capability enablement or a running turn. */
  ready: boolean;
  size: number;
};
export type ModelUsage = {
  cache_creation_tokens: number;
  cache_read_tokens: number;
  input_tokens: number;
  /** Source identifier of the Weaver catalogue offer; retained after its removal. */
  model_source_id: string;
  output_tokens: number;
  /** Upstream model identifier, 1 to 256 UTF-8 bytes, without surrounding whitespace. */
  upstream_model_id: string;
};
export type UsageReport = {
  /** Complete set of distinct offers consumed during this report (one run); order is irrelevant. */
  models: ModelUsage[];
  /** Time of consumption; at most five minutes ahead of server time. */
  occurred_at: string;
};
export type ConversationFile = {
  content_id: string;
  document_id: string;
  mime: string;
  name: string;
  path: string;
  preview_content_id?: string | null;
  sha256: string;
  size: number;
  updated_at: string;
};
export type FileWrite = {
  content_id: string;
  document_id: string;
};
export type FileWriteTarget = {
  /** Null means create; a write must submit this value unchanged after rendering. */
  current_content_id?: string | null;
};
export type GeneratedTitle = {
  agent_instance_id: string;
  attempt_id: string;
  subject_id: string;
  title: string;
};
export type SpaceSkill = {
  name: string;
  revision: string;
  skill_id: string;
  space_id: string;
  summary: PackageSummary;
};
export type BTreeMap = {
  [key: string]: string;
};
export type CreateSkill = {
  files: BTreeMap;
  name: string;
};
export type SkillDetail = {
  content: string;
  revision: string;
  skill: SkillSummary;
};
export type PutSkill = {
  expected_revision?: string | null;
  files: BTreeMap;
};
export type WikiAvailability = {
  enabled: boolean;
};
export type WikiPageSummary = {
  kind: string;
  needs_review: boolean;
  page_id: string;
  parent_page_id?: string | null;
  position: number;
  slug: string;
  title: string;
  updated_at?: string | null;
  updated_by: string;
};
export type WikiPageTree = {
  pages: WikiPageSummary[];
};
export type WikiPageDetail = {
  author_kind: string;
  author_name?: string | null;
  content_md: string;
  page: WikiPageSummary;
  revision_id?: string | null;
};
export type CreateWikiPageRequest = {
  content_md?: string;
  parent_page_id?: string | null;
  position?: number;
  title: string;
};
export type UpdateWikiMetadataRequest = {
  move_to_root?: boolean;
  parent_page_id?: string | null;
  position?: number | null;
  title?: string | null;
};
export type WikiConflict = {
  current_content_md: string;
  current_revision_id?: string | null;
  detail: string;
};
export type UpdateWikiContentRequest = {
  base_revision_id?: string | null;
  content_md: string;
};
export type WikiReviewRequest = {
  base_revision_id: string;
  needs_review: boolean;
};
export type WikiRevisionSummary = {
  agent_instance_id?: string | null;
  agent_name?: string | null;
  author_kind: string;
  author_user_id: string;
  created_at: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  revision_id: string;
  session_id?: string | null;
  status: string;
};
export type WikiRevisionList = {
  authors: {
    [key: string]: string;
  };
  contents: {
    [key: string]: string;
  };
  next_cursor?: string | null;
  revisions: WikiRevisionSummary[];
};
export type WikiProposal = {
  agent_instance_id?: string | null;
  author_user_id: string;
  content_md: string;
  created_at: string;
  current_content_md: string;
  kind: string;
  parent_slug?: string | null;
  proposal_id: string;
  slug?: string | null;
  title: string;
};
export type ProposeWikiEditRequest = {
  base_revision_id: string;
  content_md: string;
  slug: string;
};
export type ProposeWikiPageRequest = {
  content_md: string;
  parent_slug?: string | null;
  title: string;
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
  useMessagesQuery,
  useLazyMessagesQuery,
  useAuthorizeDocumentMutation,
  useAuthorizePlatformMutation,
  useAuthorizeScopeMutation,
  useAuthorizeSpaceMutation,
  useBootstrapPlatformAdminMutation,
  useCapabilityPreparationCleanupQuery,
  useLazyCapabilityPreparationCleanupQuery,
  useCapabilityPreparationWorkerQuery,
  useLazyCapabilityPreparationWorkerQuery,
  useCapabilityPreparationContextQuery,
  useLazyCapabilityPreparationContextQuery,
  useCapabilityPreparationCleanedMutation,
  useCapabilityPreparationConfirmMutation,
  useCapabilityPreparationContentQuery,
  useLazyCapabilityPreparationContentQuery,
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
  useWritesMutation,
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
  useMarketplaceProposalSpacesQuery,
  useLazyMarketplaceProposalSpacesQuery,
  useMarketplacesQuery,
  useLazyMarketplacesQuery,
  useOnboardingStatusQuery,
  useLazyOnboardingStatusQuery,
  useCreatePersonalSpaceMutation,
  useMySpacesQuery,
  useLazyMySpacesQuery,
  useMyUsageQuery,
  useLazyMyUsageQuery,
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
  usePowerpointUploadReceiptQuery,
  useLazyPowerpointUploadReceiptQuery,
  useDefaultSkillsQuery,
  useLazyDefaultSkillsQuery,
  useCreateSpaceMutation,
  useDeleteSpaceMutation,
  useProjectDeletionStatusQuery,
  useLazyProjectDeletionStatusQuery,
  useReceiptsQuery,
  useLazyReceiptsQuery,
  useEntriesQuery,
  useLazyEntriesQuery,
  useSpaceMemberCandidatesQuery,
  useLazySpaceMemberCandidatesQuery,
  useSpaceMembersQuery,
  useLazySpaceMembersQuery,
  useGrantMutation,
  useRevokeMutation,
  useSummaryQuery,
  useLazySummaryQuery,
  useMarketplaceEntriesQuery,
  useLazyMarketplaceEntriesQuery,
  useMarketplaceEntryQuery,
  useLazyMarketplaceEntryQuery,
  useInstallMarketplaceEntryMutation,
  useWithdrawMarketplaceEntryMutation,
  useMarketplaceProposalsQuery,
  useLazyMarketplaceProposalsQuery,
  useSubmitMarketplaceProposalMutation,
  useMarketplaceProposalQuery,
  useLazyMarketplaceProposalQuery,
  useCancelMarketplaceProposalMutation,
  useDecideMarketplaceProposalMutation,
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
  useAdmitRuntimeMutation,
  useSpaceAgentTemplatesQuery,
  useLazySpaceAgentTemplatesQuery,
  useSpaceCapabilityPoliciesQuery,
  useLazySpaceCapabilityPoliciesQuery,
  useReplaceSpaceCapabilityPolicyMutation,
  useMarketplaceInstallationQuery,
  useLazyMarketplaceInstallationQuery,
  useResolvePowerpointTemplateQuery,
  useLazyResolvePowerpointTemplateQuery,
  useUploadPowerpointTemplateMutation,
  useRemovePowerpointTemplateMutation,
  useRerunPowerpointTemplateMutation,
  useGetPowerpointSettingsQuery,
  useLazyGetPowerpointSettingsQuery,
  usePutPowerpointSettingsMutation,
  useDownloadPowerpointTemplateQuery,
  useLazyDownloadPowerpointTemplateQuery,
  useListPromptCategoriesQuery,
  useLazyListPromptCategoriesQuery,
  useCreatePromptCategoryMutation,
  useDeletePromptCategoryMutation,
  useRenamePromptCategoryMutation,
  useListPromptsQuery,
  useLazyListPromptsQuery,
  useCreatePromptMutation,
  useGetPromptQuery,
  useLazyGetPromptQuery,
  useDeletePromptMutation,
  useUpdatePromptMutation,
  useAddPromptFavoriteMutation,
  useRemovePromptFavoriteMutation,
  useListSessionsQuery,
  useLazyListSessionsQuery,
  useCreateSessionMutation,
  useGetSessionQuery,
  useLazyGetSessionQuery,
  useDeleteSessionMutation,
  useUpdateSessionMutation,
  useListAttachmentsQuery,
  useLazyListAttachmentsQuery,
  useUploadAttachmentMutation,
  useDeleteAttachmentMutation,
  useDownloadAttachmentQuery,
  useLazyDownloadAttachmentQuery,
  useRecordUsageMutation,
  useListConversationFilesQuery,
  useLazyListConversationFilesQuery,
  useWriteConversationFileMutation,
  useFileWriteTargetQuery,
  useLazyFileWriteTargetQuery,
  useDownloadConversationFileQuery,
  useLazyDownloadConversationFileQuery,
  usePreviewConversationFileQuery,
  useLazyPreviewConversationFileQuery,
  useRecordTitleMutation,
  useListSkillsQuery,
  useLazyListSkillsQuery,
  useCreateSkillMutation,
  useInstallSkillMutation,
  useSkillScopeQuery,
  useLazySkillScopeQuery,
  usePreviewSkillQuery,
  useLazyPreviewSkillQuery,
  useGetSkillQuery,
  useLazyGetSkillQuery,
  usePutSkillMutation,
  useDeleteSkillMutation,
  useSpaceUsageQuery,
  useLazySpaceUsageQuery,
  useWikiAvailabilityQuery,
  useLazyWikiAvailabilityQuery,
  useWikiPagesQuery,
  useLazyWikiPagesQuery,
  useCreateWikiPageMutation,
  useWikiPageQuery,
  useLazyWikiPageQuery,
  useDeleteWikiPageMutation,
  usePatchWikiPageMutation,
  useWriteWikiPageMutation,
  useSetWikiReviewMarkMutation,
  useWikiRevisionsQuery,
  useLazyWikiRevisionsQuery,
  useRestoreWikiRevisionMutation,
  useProposeWikiEditMutation,
  useProposeWikiPageMutation,
  useWikiProposalQuery,
  useLazyWikiProposalQuery,
  usePublishWikiProposalMutation,
  useWikiRulesQuery,
  useLazyWikiRulesQuery,
  useWriteWikiRulesMutation,
  useGetMyPreferencesQuery,
  useLazyGetMyPreferencesQuery,
  usePatchMyPreferencesMutation,
  useListPlatformRolesQuery,
  useLazyListPlatformRolesQuery,
  useGrantPlatformRoleMutation,
  useRevokePlatformRoleMutation,
} = injectedRtkApi;
