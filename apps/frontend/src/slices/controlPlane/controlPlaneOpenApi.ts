import { controlPlaneApi as api } from "./controlPlaneApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    getConversationTraceHistoryAccess: build.query<
      GetConversationTraceHistoryAccessApiResponse,
      GetConversationTraceHistoryAccessApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/conversation-traces/${queryArg.sessionId}/history-access`,
        params: {
          runtime_id: queryArg.runtimeId,
          exchange_id: queryArg.exchangeId,
          after_rank: queryArg.afterRank,
          limit: queryArg.limit,
        },
      }),
    }),
    getConversationTraceHttpAccess: build.query<
      GetConversationTraceHttpAccessApiResponse,
      GetConversationTraceHttpAccessApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/conversation-traces/${queryArg.sessionId}/http-access`,
        params: {
          runtime_id: queryArg.runtimeId,
          exchange_id: queryArg.exchangeId,
          ref: queryArg.ref,
          index: queryArg.index,
        },
      }),
    }),
    getConversationTraceModelAccess: build.query<
      GetConversationTraceModelAccessApiResponse,
      GetConversationTraceModelAccessApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/conversation-traces/${queryArg.sessionId}/model-access`,
        params: {
          runtime_id: queryArg.runtimeId,
          exchange_id: queryArg.exchangeId,
          ref: queryArg.ref,
          index: queryArg.index,
        },
      }),
    }),
    getConversationTraceSseAccess: build.query<
      GetConversationTraceSseAccessApiResponse,
      GetConversationTraceSseAccessApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/conversation-traces/${queryArg.sessionId}/sse-access`,
        params: {
          runtime_id: queryArg.runtimeId,
          exchange_id: queryArg.exchangeId,
          ref: queryArg.ref,
          index: queryArg.index,
        },
      }),
    }),
    getConversationTraceSseHeaderAccess: build.query<
      GetConversationTraceSseHeaderAccessApiResponse,
      GetConversationTraceSseHeaderAccessApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/conversation-traces/${queryArg.sessionId}/sse-header-access`,
        params: {
          runtime_id: queryArg.runtimeId,
          exchange_id: queryArg.exchangeId,
          ref: queryArg.ref,
          index: queryArg.index,
        },
      }),
    }),
    getConversationTraceToolAccess: build.query<
      GetConversationTraceToolAccessApiResponse,
      GetConversationTraceToolAccessApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/admin/conversation-traces/${queryArg.sessionId}/tool-access`,
        params: {
          runtime_id: queryArg.runtimeId,
          exchange_id: queryArg.exchangeId,
          ref: queryArg.ref,
          index: queryArg.index,
        },
      }),
    }),
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
    queryAnalytics: build.query<QueryAnalyticsApiResponse, QueryAnalyticsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/analytics/query`,
        method: "POST",
        body: queryArg.analyticsRequest,
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
    capabilityPreparationTextAdmission: build.query<
      CapabilityPreparationTextAdmissionApiResponse,
      CapabilityPreparationTextAdmissionApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/capability-preparations/${queryArg.id}/text-admission` }),
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
    retiredCorpora: build.query<RetiredCorporaApiResponse, RetiredCorporaApiArg>({
      query: () => ({ url: `/control-plane/v1/document-processing/vector-reindex/retired` }),
    }),
    retiredCorpusProgress: build.mutation<RetiredCorpusProgressApiResponse, RetiredCorpusProgressApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/vector-reindex/retired`,
        method: "POST",
        body: queryArg.retiredCorpusProgress,
      }),
    }),
    vectorReindexProgress: build.mutation<VectorReindexProgressApiResponse, VectorReindexProgressApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/vector-reindex/${queryArg.id}`,
        method: "POST",
        body: queryArg.reindexProgress,
      }),
    }),
    vectorReindexWork: build.mutation<VectorReindexWorkApiResponse, VectorReindexWorkApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/document-processing/vector-reindex/${queryArg.id}/claim`,
        method: "POST",
        body: queryArg.claimVectorReindex,
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
    admitTraceTurn: build.mutation<AdmitTraceTurnApiResponse, AdmitTraceTurnApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/internal/runtimes/${queryArg.runtimeId}/conversation-traces/admit`,
        method: "POST",
        body: queryArg.traceAdmissionRequest,
      }),
    }),
    claimTraceStorageCleanup: build.mutation<ClaimTraceStorageCleanupApiResponse, ClaimTraceStorageCleanupApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/internal/runtimes/${queryArg.runtimeId}/conversation-traces/cleanup`,
        method: "POST",
      }),
    }),
    acknowledgeTraceStorageCleanup: build.mutation<
      AcknowledgeTraceStorageCleanupApiResponse,
      AcknowledgeTraceStorageCleanupApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/internal/runtimes/${queryArg.runtimeId}/conversation-traces/cleanup/${queryArg.workId}`,
        method: "PUT",
        body: queryArg.traceStorageCleanupResult,
      }),
    }),
    getTraceOwnerHiddenSessions: build.mutation<
      GetTraceOwnerHiddenSessionsApiResponse,
      GetTraceOwnerHiddenSessionsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/internal/runtimes/${queryArg.runtimeId}/conversation-traces/owner-hidden`,
        method: "POST",
        body: queryArg.traceOwnerVisibilityRequest,
      }),
    }),
    reconcileTraceAdmission: build.mutation<ReconcileTraceAdmissionApiResponse, ReconcileTraceAdmissionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/internal/runtimes/${queryArg.runtimeId}/conversation-traces/reconcile/${queryArg.segmentId}`,
        method: "PUT",
        body: queryArg.traceAdmissionReconciliation,
      }),
    }),
    finalizeTraceTurn: build.mutation<FinalizeTraceTurnApiResponse, FinalizeTraceTurnApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/internal/runtimes/${queryArg.runtimeId}/conversation-traces/${queryArg.captureId}`,
        method: "PUT",
        body: queryArg.traceFinalization,
      }),
    }),
    settleIncrementalTraceStorage: build.mutation<
      SettleIncrementalTraceStorageApiResponse,
      SettleIncrementalTraceStorageApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/internal/runtimes/${queryArg.runtimeId}/conversation-traces/${queryArg.captureId}/publications/${queryArg.publicationId}`,
        method: "PUT",
        body: queryArg.traceStoragePublication,
      }),
    }),
    reserveTraceStorage: build.mutation<ReserveTraceStorageApiResponse, ReserveTraceStorageApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/internal/runtimes/${queryArg.runtimeId}/conversation-traces/${queryArg.captureId}/reserve`,
        method: "POST",
        body: queryArg.traceStorageReservation,
      }),
    }),
    publish: build.mutation<PublishApiResponse, PublishApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-base-definitions/publish`,
        method: "POST",
        body: queryArg.publishDefinitions,
      }),
    }),
    context: build.query<ContextApiResponse, ContextApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/knowledge-base-runs/${queryArg.id}` }),
    }),
    claimKnowledgeBaseRun: build.mutation<ClaimKnowledgeBaseRunApiResponse, ClaimKnowledgeBaseRunApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/knowledge-base-runs/${queryArg.id}/claim`, method: "POST" }),
    }),
    complete: build.mutation<CompleteApiResponse, CompleteApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-base-runs/${queryArg.id}/complete`,
        method: "POST",
        body: queryArg.completeRun,
      }),
    }),
    catalogue: build.query<CatalogueApiResponse, CatalogueApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-base-runs/${queryArg.id}/documents`,
        params: {
          cursor: queryArg.cursor,
          limit: queryArg.limit,
        },
      }),
    }),
    uploadKnowledgeBaseDocument: build.mutation<
      UploadKnowledgeBaseDocumentApiResponse,
      UploadKnowledgeBaseDocumentApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-base-runs/${queryArg.id}/documents`,
        method: "POST",
        body: queryArg.fileUpload,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
        params: {
          source_key: queryArg.sourceKey,
          source_version: queryArg.sourceVersion,
        },
      }),
    }),
    retract: build.mutation<RetractApiResponse, RetractApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-base-runs/${queryArg.id}/documents`,
        method: "DELETE",
        params: {
          source_key: queryArg.sourceKey,
        },
      }),
    }),
    outcome: build.query<OutcomeApiResponse, OutcomeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-base-runs/${queryArg.id}/documents/tasks/${queryArg.task}`,
      }),
    }),
    binding: build.query<BindingApiResponse, BindingApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-bases/worker`,
        params: {
          runtime_id: queryArg.runtimeId,
          definition_id: queryArg.definitionId,
        },
      }),
    }),
    updateKnowledgeBase: build.mutation<UpdateKnowledgeBaseApiResponse, UpdateKnowledgeBaseApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-bases/${queryArg.id}`,
        method: "PATCH",
        body: queryArg.updateInstance,
      }),
    }),
    knowledgeBaseRuns: build.query<KnowledgeBaseRunsApiResponse, KnowledgeBaseRunsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/knowledge-bases/${queryArg.id}/runs` }),
    }),
    startKnowledgeBaseRun: build.mutation<StartKnowledgeBaseRunApiResponse, StartKnowledgeBaseRunApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/knowledge-bases/${queryArg.id}/runs`,
        method: "POST",
        body: queryArg.startRun,
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
    organizationApplications: build.query<OrganizationApplicationsApiResponse, OrganizationApplicationsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/organizations/${queryArg.organizationId}/applications` }),
    }),
    createApplication: build.mutation<CreateApplicationApiResponse, CreateApplicationApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/applications`,
        method: "POST",
        body: queryArg.createApplication,
      }),
    }),
    updateApplication: build.mutation<UpdateApplicationApiResponse, UpdateApplicationApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/applications/${queryArg.applicationId}`,
        method: "PUT",
        body: queryArg.updateApplication,
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
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/capabilities/${queryArg.sourceId}/refresh`,
        method: "POST",
      }),
    }),
    setOrganizationCapabilityDefault: build.mutation<
      SetOrganizationCapabilityDefaultApiResponse,
      SetOrganizationCapabilityDefaultApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/capabilities/${queryArg.sourceId}/${queryArg.capabilityId}/default-on`,
        method: "PUT",
        body: queryArg.setDefaultOnRequest,
      }),
    }),
    organizationCapabilityRevokeImpact: build.query<
      OrganizationCapabilityRevokeImpactApiResponse,
      OrganizationCapabilityRevokeImpactApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/capabilities/${queryArg.sourceId}/${queryArg.capabilityId}/revoke-impact`,
      }),
    }),
    listConversationTraces: build.query<ListConversationTracesApiResponse, ListConversationTracesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces`,
        params: {
          failed_only: queryArg.failedOnly,
          outcomes: queryArg.outcomes,
          team_ids: queryArg.teamIds,
          user_id: queryArg.userId,
          consent: queryArg.consent,
          query: queryArg.query,
          query_outcomes: queryArg.queryOutcomes,
          since: queryArg.since,
          until: queryArg.until,
          sort: queryArg.sort,
          direction: queryArg.direction,
          limit: queryArg.limit,
          cursor: queryArg.cursor,
        },
      }),
    }),
    flushConversationTraceCaptures: build.mutation<
      FlushConversationTraceCapturesApiResponse,
      FlushConversationTraceCapturesApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/captures`,
        method: "DELETE",
      }),
    }),
    deleteConversationTraces: build.mutation<DeleteConversationTracesApiResponse, DeleteConversationTracesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/delete`,
        method: "POST",
        body: queryArg.deleteConversationTracesRequest,
      }),
    }),
    exportConversationTraces: build.mutation<ExportConversationTracesApiResponse, ExportConversationTracesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/export`,
        method: "POST",
        body: queryArg.exportConversationTracesRequest,
      }),
    }),
    getConversationTraceSettings: build.query<
      GetConversationTraceSettingsApiResponse,
      GetConversationTraceSettingsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/settings`,
      }),
    }),
    setConversationTraceSettings: build.mutation<
      SetConversationTraceSettingsApiResponse,
      SetConversationTraceSettingsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/settings`,
        method: "PUT",
        body: queryArg.conversationTraceSettingsUpdate,
      }),
    }),
    listConversationTraceTeams: build.query<ListConversationTraceTeamsApiResponse, ListConversationTraceTeamsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/teams`,
      }),
    }),
    getConversationTrace: build.query<GetConversationTraceApiResponse, GetConversationTraceApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}`,
        params: {
          limit: queryArg.limit,
          cursor: queryArg.cursor,
        },
      }),
    }),
    getConversationTraceHistory: build.query<GetConversationTraceHistoryApiResponse, GetConversationTraceHistoryApiArg>(
      {
        query: (queryArg) => ({
          url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/history/${queryArg.exchangeId}`,
          params: {
            after_rank: queryArg.afterRank,
            limit: queryArg.limit,
          },
        }),
      },
    ),
    listConversationTraceHttpAttempts: build.query<
      ListConversationTraceHttpAttemptsApiResponse,
      ListConversationTraceHttpAttemptsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/http/${queryArg.exchangeId}`,
      }),
    }),
    getConversationTraceHttpEvidence: build.query<
      GetConversationTraceHttpEvidenceApiResponse,
      GetConversationTraceHttpEvidenceApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/http/${queryArg.exchangeId}/${queryArg.ref}`,
        params: {
          request_offset: queryArg.requestOffset,
          response_offset: queryArg.responseOffset,
        },
      }),
    }),
    listConversationTraceModelCalls: build.query<
      ListConversationTraceModelCallsApiResponse,
      ListConversationTraceModelCallsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/model/${queryArg.exchangeId}`,
      }),
    }),
    getConversationTraceModelEvidence: build.query<
      GetConversationTraceModelEvidenceApiResponse,
      GetConversationTraceModelEvidenceApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/model/${queryArg.exchangeId}/${queryArg.ref}`,
      }),
    }),
    listConversationTraceSpans: build.query<ListConversationTraceSpansApiResponse, ListConversationTraceSpansApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/spans/${queryArg.exchangeId}`,
      }),
    }),
    getConversationTraceSseFramePage: build.query<
      GetConversationTraceSseFramePageApiResponse,
      GetConversationTraceSseFramePageApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/sse-frames/${queryArg.exchangeId}/${queryArg.ref}/${queryArg.page}`,
      }),
    }),
    getConversationTraceSseHeaders: build.query<
      GetConversationTraceSseHeadersApiResponse,
      GetConversationTraceSseHeadersApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/sse-headers/${queryArg.exchangeId}/${queryArg.ref}`,
      }),
    }),
    listConversationTraceSseSegments: build.query<
      ListConversationTraceSseSegmentsApiResponse,
      ListConversationTraceSseSegmentsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/sse/${queryArg.exchangeId}`,
      }),
    }),
    getConversationTraceSseFrame: build.query<
      GetConversationTraceSseFrameApiResponse,
      GetConversationTraceSseFrameApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/sse/${queryArg.exchangeId}/${queryArg.ref}/${queryArg.index}`,
      }),
    }),
    listConversationTraceToolCalls: build.query<
      ListConversationTraceToolCallsApiResponse,
      ListConversationTraceToolCallsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/tool/${queryArg.exchangeId}`,
      }),
    }),
    getConversationTraceToolEvidence: build.query<
      GetConversationTraceToolEvidenceApiResponse,
      GetConversationTraceToolEvidenceApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/conversation-traces/${queryArg.sessionId}/tool/${queryArg.exchangeId}/${queryArg.ref}`,
      }),
    }),
    organizationKnowledgeBaseServices: build.query<
      OrganizationKnowledgeBaseServicesApiResponse,
      OrganizationKnowledgeBaseServicesApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/knowledge-base-services`,
      }),
    }),
    registerKnowledgeBaseService: build.mutation<
      RegisterKnowledgeBaseServiceApiResponse,
      RegisterKnowledgeBaseServiceApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/knowledge-base-services`,
        method: "POST",
        body: queryArg.registerKnowledgeBaseService,
      }),
    }),
    updateKnowledgeBaseService: build.mutation<UpdateKnowledgeBaseServiceApiResponse, UpdateKnowledgeBaseServiceApiArg>(
      {
        query: (queryArg) => ({
          url: `/control-plane/v1/organizations/${queryArg.organizationId}/knowledge-base-services/${queryArg.runtimeId}`,
          method: "PUT",
          body: queryArg.updateKnowledgeBaseService,
        }),
      },
    ),
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
    createModelCatalog: build.mutation<CreateModelCatalogApiResponse, CreateModelCatalogApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-sources`,
        method: "POST",
        body: queryArg.createModelCatalog,
      }),
    }),
    updateModelCatalog: build.mutation<UpdateModelCatalogApiResponse, UpdateModelCatalogApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-sources/${queryArg.sourceId}`,
        method: "PUT",
        body: queryArg.updateModelCatalog,
      }),
    }),
    deleteModelCatalog: build.mutation<DeleteModelCatalogApiResponse, DeleteModelCatalogApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-sources/${queryArg.sourceId}`,
        method: "DELETE",
      }),
    }),
    modelAccessMatrix: build.query<ModelAccessMatrixApiResponse, ModelAccessMatrixApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-sources/${queryArg.sourceId}/access`,
        params: {
          upstream_model_id: queryArg.upstreamModelId,
          after: queryArg.after,
          name: queryArg.name,
        },
      }),
    }),
    setModelAccess: build.mutation<SetModelAccessApiResponse, SetModelAccessApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-sources/${queryArg.sourceId}/access`,
        method: "PUT",
        body: queryArg.setModelAccess,
      }),
    }),
    replaceModelComplements: build.mutation<ReplaceModelComplementsApiResponse, ReplaceModelComplementsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/model-sources/${queryArg.sourceId}/metadata`,
        method: "PUT",
        body: queryArg.replaceModelComplements,
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
    organizationResources: build.query<OrganizationResourcesApiResponse, OrganizationResourcesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/resources`,
        params: {
          search: queryArg.search,
          page: queryArg.page,
          kind: queryArg.kind,
        },
      }),
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
    organizationTeams: build.query<OrganizationTeamsApiResponse, OrganizationTeamsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/teams`,
        params: {
          search: queryArg.search,
          page: queryArg.page,
        },
      }),
    }),
    vectorReindexStatus: build.query<VectorReindexStatusApiResponse, VectorReindexStatusApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/organizations/${queryArg.organizationId}/vector-reindex` }),
    }),
    startVectorReindex: build.mutation<StartVectorReindexApiResponse, StartVectorReindexApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/organizations/${queryArg.organizationId}/vector-reindex`,
        method: "POST",
        body: queryArg.startVectorReindex,
      }),
    }),
    powerpointUploadReceipt: build.query<PowerpointUploadReceiptApiResponse, PowerpointUploadReceiptApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/powerpoint-uploads/${queryArg.requestKey}` }),
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
    updateTeamParameters: build.mutation<UpdateTeamParametersApiResponse, UpdateTeamParametersApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}`,
        method: "PATCH",
        body: queryArg.teamParameters,
      }),
    }),
    getTeamAvatar: build.query<GetTeamAvatarApiResponse, GetTeamAvatarApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/avatar` }),
    }),
    putTeamAvatar: build.mutation<PutTeamAvatarApiResponse, PutTeamAvatarApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/avatar`,
        method: "PUT",
        body: queryArg.fileUpload,
      }),
    }),
    deleteTeamAvatar: build.mutation<DeleteTeamAvatarApiResponse, DeleteTeamAvatarApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/avatar`, method: "DELETE" }),
    }),
    teamConversationRetention: build.query<TeamConversationRetentionApiResponse, TeamConversationRetentionApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/conversation-retention` }),
    }),
    replaceTeamConversationRetention: build.mutation<
      ReplaceTeamConversationRetentionApiResponse,
      ReplaceTeamConversationRetentionApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/conversation-retention`,
        method: "PUT",
        body: queryArg.replaceConversationRetention,
      }),
    }),
    projectDeletionStatus: build.query<ProjectDeletionStatusApiResponse, ProjectDeletionStatusApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/deletion` }),
    }),
    teamMetadata: build.query<TeamMetadataApiResponse, TeamMetadataApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/discovery` }),
    }),
    teamDocumentActivity: build.query<TeamDocumentActivityApiResponse, TeamDocumentActivityApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/document-activity`,
        params: {
          kind: queryArg.kind,
          status: queryArg.status,
          before: queryArg.before,
          until: queryArg.until,
        },
      }),
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
    joinTeam: build.mutation<JoinTeamApiResponse, JoinTeamApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/join`, method: "POST" }),
    }),
    teamJoinLink: build.query<TeamJoinLinkApiResponse, TeamJoinLinkApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/join-link` }),
    }),
    createTeamJoinLink: build.mutation<CreateTeamJoinLinkApiResponse, CreateTeamJoinLinkApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/join-link`, method: "POST" }),
    }),
    revokeTeamJoinLink: build.mutation<RevokeTeamJoinLinkApiResponse, RevokeTeamJoinLinkApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/join-link`, method: "DELETE" }),
    }),
    spaceMemberCandidates: build.query<SpaceMemberCandidatesApiResponse, SpaceMemberCandidatesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/member-candidates`,
        params: {
          after: queryArg.after,
          search: queryArg.search,
        },
      }),
    }),
    spaceMembers: build.query<SpaceMembersApiResponse, SpaceMembersApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/members`,
        params: {
          after: queryArg.after,
          search: queryArg.search,
        },
      }),
    }),
    removeSpaceMember: build.mutation<RemoveSpaceMemberApiResponse, RemoveSpaceMemberApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.id}/members/${queryArg.user}`,
        method: "DELETE",
      }),
    }),
    teamProjects: build.query<TeamProjectsApiResponse, TeamProjectsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.id}/projects` }),
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
    organizationHome: build.query<OrganizationHomeApiResponse, OrganizationHomeApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.organizationId}/home` }),
    }),
    organizationHomeCandidates: build.query<OrganizationHomeCandidatesApiResponse, OrganizationHomeCandidatesApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.organizationId}/home-candidates`,
        params: {
          after: queryArg.after,
        },
      }),
    }),
    organizationHomeSettings: build.query<OrganizationHomeSettingsApiResponse, OrganizationHomeSettingsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.organizationId}/home-settings` }),
    }),
    setOrganizationHome: build.mutation<SetOrganizationHomeApiResponse, SetOrganizationHomeApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.organizationId}/home-settings`,
        method: "PUT",
        body: queryArg.setOrganizationHomeRequest,
      }),
    }),
    getCommonPromptSettings: build.query<GetCommonPromptSettingsApiResponse, GetCommonPromptSettingsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.organizationId}/prompt-settings/common` }),
    }),
    putCommonPromptSettings: build.mutation<PutCommonPromptSettingsApiResponse, PutCommonPromptSettingsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.organizationId}/prompt-settings/common`,
        method: "PUT",
        body: queryArg.setCommonPrompt,
      }),
    }),
    getCreationAssistantSettings: build.query<
      GetCreationAssistantSettingsApiResponse,
      GetCreationAssistantSettingsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.organizationId}/prompt-settings/creation-assistant`,
      }),
    }),
    resetCreationAssistantPrompt: build.mutation<
      ResetCreationAssistantPromptApiResponse,
      ResetCreationAssistantPromptApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.organizationId}/prompt-settings/creation-assistant`,
        method: "DELETE",
      }),
    }),
    patchCreationAssistantSettings: build.mutation<
      PatchCreationAssistantSettingsApiResponse,
      PatchCreationAssistantSettingsApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.organizationId}/prompt-settings/creation-assistant`,
        method: "PATCH",
        body: queryArg.patchCreationAssistant,
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
    transcribeAgentAudio: build.mutation<TranscribeAgentAudioApiResponse, TranscribeAgentAudioApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-instances/${queryArg.agentInstanceId}/transcriptions`,
        method: "POST",
        body: queryArg.dictationUpload,
      }),
    }),
    spaceAgentTemplates: build.query<SpaceAgentTemplatesApiResponse, SpaceAgentTemplatesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-templates` }),
    }),
    draftAgent: build.mutation<DraftAgentApiResponse, DraftAgentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-templates/${queryArg.templateId}/creation-assistant/draft`,
        method: "POST",
        body: queryArg.agentDraftRequest,
      }),
    }),
    admitAgentDraft: build.mutation<AdmitAgentDraftApiResponse, AdmitAgentDraftApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/agent-templates/${queryArg.templateId}/creation-assistant/runtime`,
        method: "POST",
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    spaceApplications: build.query<SpaceApplicationsApiResponse, SpaceApplicationsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/applications` }),
    }),
    spaceCapabilityPolicies: build.query<SpaceCapabilityPoliciesApiResponse, SpaceCapabilityPoliciesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/capability-policies` }),
    }),
    replaceSpaceCapabilityPolicy: build.mutation<
      ReplaceSpaceCapabilityPolicyApiResponse,
      ReplaceSpaceCapabilityPolicyApiArg
    >({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/capability-policies/${queryArg.sourceId}`,
        method: "PUT",
        body: queryArg.replaceSpaceCapabilityPolicy,
      }),
    }),
    availableKnowledgeBaseDefinitions: build.query<
      AvailableKnowledgeBaseDefinitionsApiResponse,
      AvailableKnowledgeBaseDefinitionsApiArg
    >({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/knowledge-base-definitions` }),
    }),
    spaceKnowledgeBases: build.query<SpaceKnowledgeBasesApiResponse, SpaceKnowledgeBasesApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/knowledge-bases` }),
    }),
    createKnowledgeBase: build.mutation<CreateKnowledgeBaseApiResponse, CreateKnowledgeBaseApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/knowledge-bases`,
        method: "POST",
        body: queryArg.createInstance,
      }),
    }),
    marketplaceInstallation: build.query<MarketplaceInstallationApiResponse, MarketplaceInstallationApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/marketplace-installations/${queryArg.installationId}`,
      }),
    }),
    mcpConnections: build.query<McpConnectionsApiResponse, McpConnectionsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/mcp-connections` }),
    }),
    createMcpConnection: build.mutation<CreateMcpConnectionApiResponse, CreateMcpConnectionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/mcp-connections`,
        method: "POST",
        body: queryArg.createMcpConnection,
      }),
    }),
    updateMcpConnection: build.mutation<UpdateMcpConnectionApiResponse, UpdateMcpConnectionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/mcp-connections/${queryArg.id}`,
        method: "PUT",
        body: queryArg.updateMcpConnection,
      }),
    }),
    publishMcpConnection: build.mutation<PublishMcpConnectionApiResponse, PublishMcpConnectionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/mcp-connections/${queryArg.id}/publish`,
        method: "POST",
        body: queryArg.mcpPublication,
      }),
    }),
    testMcpConnection: build.mutation<TestMcpConnectionApiResponse, TestMcpConnectionApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/mcp-connections/${queryArg.id}/test`,
        method: "POST",
        body: queryArg.mcpRevision,
      }),
    }),
    mcpCredentials: build.query<McpCredentialsApiResponse, McpCredentialsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/mcp-credentials` }),
    }),
    replaceSpaceModelPolicy: build.mutation<ReplaceSpaceModelPolicyApiResponse, ReplaceSpaceModelPolicyApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/model-policy`,
        method: "PUT",
        body: queryArg.replaceSpaceModelPolicy,
      }),
    }),
    spaceModels: build.query<SpaceModelsApiResponse, SpaceModelsApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/models` }),
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
    getTraceConsent: build.query<GetTraceConsentApiResponse, GetTraceConsentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/trace-consent`,
      }),
    }),
    setTraceConsent: build.mutation<SetTraceConsentApiResponse, SetTraceConsentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/trace-consent`,
        method: "PUT",
        body: queryArg.traceConsentRequest,
      }),
    }),
    revokeTraceConsent: build.mutation<RevokeTraceConsentApiResponse, RevokeTraceConsentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/trace-consent`,
        method: "DELETE",
      }),
    }),
    getTraceIncidentOffer: build.query<GetTraceIncidentOfferApiResponse, GetTraceIncidentOfferApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/trace-incident/${queryArg.errorRef}`,
      }),
    }),
    shareTraceIncident: build.mutation<ShareTraceIncidentApiResponse, ShareTraceIncidentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/sessions/${queryArg.sessionId}/trace-incident/${queryArg.errorRef}`,
        method: "PUT",
        body: queryArg.traceConsentRequest,
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
    getUserAvatar: build.query<GetUserAvatarApiResponse, GetUserAvatarApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/spaces/${queryArg.spaceId}/users/${queryArg.userId}/avatar` }),
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
    prepareWikiDocument: build.mutation<PrepareWikiDocumentApiResponse, PrepareWikiDocumentApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/format`,
        method: "POST",
        body: queryArg.prepareWikiDocumentRequest,
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
    wikiProposals: build.query<WikiProposalsApiResponse, WikiProposalsApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals`,
        params: {
          cursor: queryArg.cursor,
        },
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
    proposeWikiFile: build.mutation<ProposeWikiFileApiResponse, ProposeWikiFileApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals/file`,
        method: "POST",
        body: queryArg.proposeWikiFileRequest,
        headers: {
          "Idempotency-Key": queryArg["Idempotency-Key"],
        },
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
    withdrawWikiProposal: build.mutation<WithdrawWikiProposalApiResponse, WithdrawWikiProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals/${queryArg.proposalId}`,
        method: "DELETE",
      }),
    }),
    acceptWikiProposal: build.mutation<AcceptWikiProposalApiResponse, AcceptWikiProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals/${queryArg.proposalId}/accept`,
        method: "POST",
      }),
    }),
    submitWikiProposal: build.mutation<SubmitWikiProposalApiResponse, SubmitWikiProposalApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/proposals/${queryArg.proposalId}/submit`,
        method: "POST",
      }),
    }),
    wikiRevisionFile: build.query<WikiRevisionFileApiResponse, WikiRevisionFileApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/revisions/${queryArg.revisionId}/${queryArg.part}`,
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
    wikiSearch: build.query<WikiSearchApiResponse, WikiSearchApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/wiki/search`,
        params: {
          q: queryArg.q,
          type: queryArg["type"],
          tag: queryArg.tag,
          limit: queryArg.limit,
          offset: queryArg.offset,
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
          session_id: queryArg.sessionId,
        },
      }),
    }),
    resolveWordTemplateLibrary: build.query<ResolveWordTemplateLibraryApiResponse, ResolveWordTemplateLibraryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/word-template-library`,
        params: {
          agent_instance_id: queryArg.agentInstanceId,
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    saveWordTemplateLibrary: build.mutation<SaveWordTemplateLibraryApiResponse, SaveWordTemplateLibraryApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/word-template-library`,
        method: "PUT",
        body: queryArg.libraryChange,
        params: {
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    uploadWordTemplate: build.mutation<UploadWordTemplateApiResponse, UploadWordTemplateApiArg>({
      query: (queryArg) => ({
        url: `/control-plane/v1/spaces/${queryArg.spaceId}/word-template-library/uploads`,
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
          slot: queryArg.slot,
        },
      }),
    }),
    previewTeamJoinLink: build.query<PreviewTeamJoinLinkApiResponse, PreviewTeamJoinLinkApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/team-join-links/${queryArg.token}` }),
    }),
    redeemTeamJoinLink: build.mutation<RedeemTeamJoinLinkApiResponse, RedeemTeamJoinLinkApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/team-join-links/${queryArg.token}`, method: "POST" }),
    }),
    getMyAvatar: build.query<GetMyAvatarApiResponse, GetMyAvatarApiArg>({
      query: () => ({ url: `/control-plane/v1/users/me/avatar` }),
    }),
    putMyAvatar: build.mutation<PutMyAvatarApiResponse, PutMyAvatarApiArg>({
      query: (queryArg) => ({ url: `/control-plane/v1/users/me/avatar`, method: "PUT", body: queryArg.fileUpload }),
    }),
    deleteMyAvatar: build.mutation<DeleteMyAvatarApiResponse, DeleteMyAvatarApiArg>({
      query: () => ({ url: `/control-plane/v1/users/me/avatar`, method: "DELETE" }),
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
export type GetConversationTraceHistoryAccessApiResponse = /** status 200 undefined */ TraceHistoryAccess;
export type GetConversationTraceHistoryAccessApiArg = {
  sessionId: string;
  runtimeId?: string;
  exchangeId?: string;
  afterRank?: number;
  limit?: number;
};
export type GetConversationTraceHttpAccessApiResponse = /** status 200 undefined */ TraceHttpArtifactAccess;
export type GetConversationTraceHttpAccessApiArg = {
  sessionId: string;
  runtimeId: string;
  exchangeId: string;
  ref: string;
  index?: number;
};
export type GetConversationTraceModelAccessApiResponse = /** status 200 undefined */ TraceModelArtifactAccess;
export type GetConversationTraceModelAccessApiArg = {
  sessionId: string;
  runtimeId: string;
  exchangeId: string;
  ref: string;
  index?: number;
};
export type GetConversationTraceSseAccessApiResponse = /** status 200 undefined */ TraceSseArtifactAccess;
export type GetConversationTraceSseAccessApiArg = {
  sessionId: string;
  runtimeId: string;
  exchangeId: string;
  ref: string;
  index?: number;
};
export type GetConversationTraceSseHeaderAccessApiResponse = /** status 200 undefined */ TraceSseHeaderAccess;
export type GetConversationTraceSseHeaderAccessApiArg = {
  sessionId: string;
  runtimeId: string;
  exchangeId: string;
  ref: string;
  index?: number;
};
export type GetConversationTraceToolAccessApiResponse = /** status 200 undefined */ TraceToolArtifactAccess;
export type GetConversationTraceToolAccessApiArg = {
  sessionId: string;
  runtimeId: string;
  exchangeId: string;
  ref: string;
  index?: number;
};
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
export type QueryAnalyticsApiResponse = /** status 200 undefined */ AnalyticsResponse;
export type QueryAnalyticsApiArg = {
  analyticsRequest: AnalyticsRequest;
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
export type CapabilityPreparationTextAdmissionApiResponse = /** status 200 undefined */ InferenceAdmission;
export type CapabilityPreparationTextAdmissionApiArg = {
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
export type RetiredCorporaApiResponse = /** status 200 undefined */ RetiredCorpus[];
export type RetiredCorporaApiArg = void;
export type RetiredCorpusProgressApiResponse = unknown;
export type RetiredCorpusProgressApiArg = {
  retiredCorpusProgress: RetiredCorpusProgress;
};
export type VectorReindexProgressApiResponse = /** status 200 undefined */ boolean;
export type VectorReindexProgressApiArg = {
  id: string;
  reindexProgress: ReindexProgress;
};
export type VectorReindexWorkApiResponse = /** status 200 undefined */ VectorReindexWork | null;
export type VectorReindexWorkApiArg = {
  id: string;
  claimVectorReindex: ClaimVectorReindex;
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
export type DeleteFolderApiResponse = /** status 200 Already purged */
  | Receipt
  | /** status 202 Retired; physical cleanup is asynchronous */ Receipt;
export type DeleteFolderApiArg = {
  id: string;
  /** Refuse retirement if any live child folder remains; live documents and pending uploads always prevent retirement */
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
export type AdmitTraceTurnApiResponse = /** status 200 undefined */ TraceAdmission | null;
export type AdmitTraceTurnApiArg = {
  runtimeId: string;
  traceAdmissionRequest: TraceAdmissionRequest;
};
export type ClaimTraceStorageCleanupApiResponse = /** status 200 undefined */ TraceStorageCleanup | null;
export type ClaimTraceStorageCleanupApiArg = {
  runtimeId: string;
};
export type AcknowledgeTraceStorageCleanupApiResponse = unknown;
export type AcknowledgeTraceStorageCleanupApiArg = {
  runtimeId: string;
  workId: string;
  traceStorageCleanupResult: TraceStorageCleanupResult;
};
export type GetTraceOwnerHiddenSessionsApiResponse = /** status 200 undefined */ string[];
export type GetTraceOwnerHiddenSessionsApiArg = {
  runtimeId: string;
  traceOwnerVisibilityRequest: TraceOwnerVisibilityRequest;
};
export type ReconcileTraceAdmissionApiResponse = unknown;
export type ReconcileTraceAdmissionApiArg = {
  runtimeId: string;
  segmentId: string;
  traceAdmissionReconciliation: TraceAdmissionReconciliation;
};
export type FinalizeTraceTurnApiResponse = unknown;
export type FinalizeTraceTurnApiArg = {
  runtimeId: string;
  captureId: string;
  traceFinalization: TraceFinalization;
};
export type SettleIncrementalTraceStorageApiResponse = unknown;
export type SettleIncrementalTraceStorageApiArg = {
  runtimeId: string;
  captureId: string;
  publicationId: string;
  traceStoragePublication: TraceStoragePublication;
};
export type ReserveTraceStorageApiResponse = /** status 200 undefined */ TraceStorageReservationState;
export type ReserveTraceStorageApiArg = {
  runtimeId: string;
  captureId: string;
  traceStorageReservation: TraceStorageReservation;
};
export type PublishApiResponse = unknown;
export type PublishApiArg = {
  publishDefinitions: PublishDefinitions;
};
export type ContextApiResponse = /** status 200 undefined */ KnowledgeBaseRun;
export type ContextApiArg = {
  id: string;
};
export type ClaimKnowledgeBaseRunApiResponse = /** status 200 undefined */ KnowledgeBaseRun;
export type ClaimKnowledgeBaseRunApiArg = {
  id: string;
};
export type CompleteApiResponse = unknown;
export type CompleteApiArg = {
  id: string;
  completeRun: CompleteRun;
};
export type CatalogueApiResponse = /** status 200 undefined */ Catalogue;
export type CatalogueApiArg = {
  id: string;
  cursor?: string;
  limit?: number;
};
export type UploadKnowledgeBaseDocumentApiResponse = /** status 200 undefined */
  | KnowledgeBaseDocumentReceipt
  | /** status 202 undefined */ KnowledgeBaseDocumentReceipt;
export type UploadKnowledgeBaseDocumentApiArg = {
  id: string;
  "Idempotency-Key": string;
  sourceKey: string;
  sourceVersion: string;
  fileUpload: FileUpload;
};
export type RetractApiResponse = unknown;
export type RetractApiArg = {
  id: string;
  sourceKey: string;
};
export type OutcomeApiResponse = /** status 200 undefined */ KnowledgeBaseDocumentReceipt;
export type OutcomeApiArg = {
  id: string;
  task: string;
};
export type BindingApiResponse = /** status 200 undefined */ KnowledgeBaseWorkerBinding;
export type BindingApiArg = {
  runtimeId: string;
  definitionId: string;
};
export type UpdateKnowledgeBaseApiResponse = /** status 200 undefined */ KnowledgeBaseInstance;
export type UpdateKnowledgeBaseApiArg = {
  id: string;
  updateInstance: UpdateInstance;
};
export type KnowledgeBaseRunsApiResponse = /** status 200 undefined */ KnowledgeBaseRun[];
export type KnowledgeBaseRunsApiArg = {
  id: string;
};
export type StartKnowledgeBaseRunApiResponse = /** status 202 undefined */ KnowledgeBaseRun;
export type StartKnowledgeBaseRunApiArg = {
  id: string;
  startRun: StartRun;
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
export type OrganizationApplicationsApiResponse = /** status 200 undefined */ Application[];
export type OrganizationApplicationsApiArg = {
  organizationId: string;
};
export type CreateApplicationApiResponse = /** status 201 undefined */ Application;
export type CreateApplicationApiArg = {
  organizationId: string;
  createApplication: CreateApplication;
};
export type UpdateApplicationApiResponse = /** status 200 undefined */ Application;
export type UpdateApplicationApiArg = {
  organizationId: string;
  applicationId: string;
  updateApplication: UpdateApplication;
};
export type OrganizationCapabilitiesApiResponse = /** status 200 undefined */ CapabilityInventory[];
export type OrganizationCapabilitiesApiArg = {
  organizationId: string;
};
export type RefreshOrganizationCapabilitiesApiResponse = unknown;
export type RefreshOrganizationCapabilitiesApiArg = {
  organizationId: string;
  sourceId: string;
};
export type SetOrganizationCapabilityDefaultApiResponse = unknown;
export type SetOrganizationCapabilityDefaultApiArg = {
  organizationId: string;
  sourceId: string;
  capabilityId: string;
  setDefaultOnRequest: SetDefaultOnRequest;
};
export type OrganizationCapabilityRevokeImpactApiResponse =
  /** status 200 Instances usable now that disabling this offer would stop */ AffectedAgentInstance[];
export type OrganizationCapabilityRevokeImpactApiArg = {
  organizationId: string;
  sourceId: string;
  capabilityId: string;
};
export type ListConversationTracesApiResponse = /** status 200 undefined */ ConversationTraceCatalog;
export type ListConversationTracesApiArg = {
  organizationId: string;
  failedOnly?: boolean;
  outcomes?: string[];
  teamIds?: string[];
  userId?: string;
  consent?: TraceConsentFilter;
  query?: string;
  queryOutcomes?: string[];
  since?: string;
  until?: string;
  sort?: TraceCatalogSort;
  direction?: string;
  limit?: number;
  cursor?: string;
};
export type FlushConversationTraceCapturesApiResponse = /** status 200 undefined */ DeleteConversationTracesResult;
export type FlushConversationTraceCapturesApiArg = {
  organizationId: string;
};
export type DeleteConversationTracesApiResponse = /** status 200 undefined */ DeleteConversationTracesResult;
export type DeleteConversationTracesApiArg = {
  organizationId: string;
  deleteConversationTracesRequest: DeleteConversationTracesRequest;
};
export type ExportConversationTracesApiResponse = /** status 200 undefined */ string;
export type ExportConversationTracesApiArg = {
  organizationId: string;
  exportConversationTracesRequest: ExportConversationTracesRequest;
};
export type GetConversationTraceSettingsApiResponse = /** status 200 undefined */ ConversationTraceSettings;
export type GetConversationTraceSettingsApiArg = {
  organizationId: string;
};
export type SetConversationTraceSettingsApiResponse = /** status 200 undefined */ ConversationTraceSettings;
export type SetConversationTraceSettingsApiArg = {
  organizationId: string;
  conversationTraceSettingsUpdate: ConversationTraceSettingsUpdate;
};
export type ListConversationTraceTeamsApiResponse = /** status 200 undefined */ TraceTeamOption[];
export type ListConversationTraceTeamsApiArg = {
  organizationId: string;
};
export type GetConversationTraceApiResponse = /** status 200 undefined */ ConversationTraceDetail;
export type GetConversationTraceApiArg = {
  organizationId: string;
  sessionId: string;
  limit?: number;
  cursor?: string;
};
export type GetConversationTraceHistoryApiResponse = /** status 200 undefined */ TraceHistoryTranscript;
export type GetConversationTraceHistoryApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
  afterRank?: number;
  limit?: number;
};
export type ListConversationTraceHttpAttemptsApiResponse = /** status 200 undefined */ TraceHttpAttempt[];
export type ListConversationTraceHttpAttemptsApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
};
export type GetConversationTraceHttpEvidenceApiResponse = /** status 200 undefined */ TraceHttpEvidence;
export type GetConversationTraceHttpEvidenceApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
  ref: string;
  requestOffset?: number;
  responseOffset?: number;
};
export type ListConversationTraceModelCallsApiResponse = /** status 200 undefined */ TraceModelCall[];
export type ListConversationTraceModelCallsApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
};
export type GetConversationTraceModelEvidenceApiResponse = /** status 200 undefined */ TraceModelEvidence;
export type GetConversationTraceModelEvidenceApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
  ref: string;
};
export type ListConversationTraceSpansApiResponse = /** status 200 undefined */ OtlpTraceSpan[];
export type ListConversationTraceSpansApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
};
export type GetConversationTraceSseFramePageApiResponse = /** status 200 undefined */ TraceSseFramePage;
export type GetConversationTraceSseFramePageApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
  ref: string;
  page: number;
};
export type GetConversationTraceSseHeadersApiResponse = /** status 200 undefined */ TraceSseHeaders;
export type GetConversationTraceSseHeadersApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
  ref: string;
};
export type ListConversationTraceSseSegmentsApiResponse = /** status 200 undefined */ TraceSseSegment[];
export type ListConversationTraceSseSegmentsApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
};
export type GetConversationTraceSseFrameApiResponse = /** status 200 undefined */ TraceSseFrame;
export type GetConversationTraceSseFrameApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
  ref: string;
  index: number;
};
export type ListConversationTraceToolCallsApiResponse = /** status 200 undefined */ TraceToolCall[];
export type ListConversationTraceToolCallsApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
};
export type GetConversationTraceToolEvidenceApiResponse = /** status 200 undefined */ TraceToolEvidence;
export type GetConversationTraceToolEvidenceApiArg = {
  organizationId: string;
  sessionId: string;
  exchangeId: string;
  ref: string;
};
export type OrganizationKnowledgeBaseServicesApiResponse = /** status 200 undefined */ KnowledgeBaseService[];
export type OrganizationKnowledgeBaseServicesApiArg = {
  organizationId: string;
};
export type RegisterKnowledgeBaseServiceApiResponse = /** status 201 undefined */ KnowledgeBaseService;
export type RegisterKnowledgeBaseServiceApiArg = {
  organizationId: string;
  registerKnowledgeBaseService: RegisterKnowledgeBaseService;
};
export type UpdateKnowledgeBaseServiceApiResponse = /** status 200 undefined */ KnowledgeBaseService;
export type UpdateKnowledgeBaseServiceApiArg = {
  organizationId: string;
  runtimeId: string;
  updateKnowledgeBaseService: UpdateKnowledgeBaseService;
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
export type CreateModelCatalogApiResponse = /** status 201 undefined */ string;
export type CreateModelCatalogApiArg = {
  organizationId: string;
  createModelCatalog: CreateModelCatalogWrite;
};
export type UpdateModelCatalogApiResponse = unknown;
export type UpdateModelCatalogApiArg = {
  organizationId: string;
  sourceId: string;
  updateModelCatalog: UpdateModelCatalogWrite;
};
export type DeleteModelCatalogApiResponse = unknown;
export type DeleteModelCatalogApiArg = {
  organizationId: string;
  sourceId: string;
};
export type ModelAccessMatrixApiResponse = /** status 200 undefined */ ModelAccessMatrix;
export type ModelAccessMatrixApiArg = {
  organizationId: string;
  sourceId: string;
  upstreamModelId: string;
  after?: string;
  name?: string;
};
export type SetModelAccessApiResponse = unknown;
export type SetModelAccessApiArg = {
  organizationId: string;
  sourceId: string;
  setModelAccess: SetModelAccess;
};
export type ReplaceModelComplementsApiResponse = /** status 200 undefined */ ModelMetadata;
export type ReplaceModelComplementsApiArg = {
  organizationId: string;
  sourceId: string;
  replaceModelComplements: ReplaceModelComplements;
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
export type OrganizationResourcesApiResponse = /** status 200 undefined */ ResourceDirectoryPage;
export type OrganizationResourcesApiArg = {
  organizationId: string;
  search?: string;
  page?: number;
  kind?: DiscoverableResourceKind;
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
export type OrganizationTeamsApiResponse = /** status 200 undefined */ TeamDirectoryPage;
export type OrganizationTeamsApiArg = {
  organizationId: string;
  search?: string;
  page?: number;
};
export type VectorReindexStatusApiResponse = /** status 200 undefined */ VectorReindex | null;
export type VectorReindexStatusApiArg = {
  organizationId: string;
};
export type StartVectorReindexApiResponse = /** status 200 undefined */ VectorReindex;
export type StartVectorReindexApiArg = {
  organizationId: string;
  startVectorReindex: StartVectorReindex;
};
export type PowerpointUploadReceiptApiResponse = /** status 200 undefined */ PowerPointFile;
export type PowerpointUploadReceiptApiArg = {
  requestKey: string;
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
  /** Request immediate purge for an eligible resource as a platform administrator. */
  immediate?: boolean;
};
export type UpdateTeamParametersApiResponse = /** status 200 undefined */ Space;
export type UpdateTeamParametersApiArg = {
  id: string;
  teamParameters: TeamParameters;
};
export type GetTeamAvatarApiResponse = /** status 200 undefined */ string;
export type GetTeamAvatarApiArg = {
  id: string;
};
export type PutTeamAvatarApiResponse = unknown;
export type PutTeamAvatarApiArg = {
  id: string;
  fileUpload: FileUpload;
};
export type DeleteTeamAvatarApiResponse = unknown;
export type DeleteTeamAvatarApiArg = {
  id: string;
};
export type TeamConversationRetentionApiResponse = /** status 200 undefined */ ConversationRetention;
export type TeamConversationRetentionApiArg = {
  id: string;
};
export type ReplaceTeamConversationRetentionApiResponse = /** status 200 undefined */ ConversationRetention;
export type ReplaceTeamConversationRetentionApiArg = {
  id: string;
  replaceConversationRetention: ReplaceConversationRetention;
};
export type ProjectDeletionStatusApiResponse = /** status 200 undefined */ Receipt;
export type ProjectDeletionStatusApiArg = {
  id: string;
};
export type TeamMetadataApiResponse = /** status 200 undefined */ DiscoverableTeam;
export type TeamMetadataApiArg = {
  id: string;
};
export type TeamDocumentActivityApiResponse = /** status 200 undefined */ DocumentActivityPage;
export type TeamDocumentActivityApiArg = {
  id: string;
  kind?: ActivityKind;
  status?: ActivityStatus;
  /** Opaque keyset cursor, never an offset. Keep `until` and filters when paging. */
  before?: string;
  /** Fixed upper creation bound. Polling updates outcomes without new rows pushing
    a terminal outcome off the page. Omit to start a new view including newer work. */
  until?: string;
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
export type JoinTeamApiResponse = unknown;
export type JoinTeamApiArg = {
  id: string;
};
export type TeamJoinLinkApiResponse = /** status 200 undefined */ TeamJoinLink | null;
export type TeamJoinLinkApiArg = {
  id: string;
};
export type CreateTeamJoinLinkApiResponse = /** status 200 undefined */ TeamJoinLink;
export type CreateTeamJoinLinkApiArg = {
  id: string;
};
export type RevokeTeamJoinLinkApiResponse = unknown;
export type RevokeTeamJoinLinkApiArg = {
  id: string;
};
export type SpaceMemberCandidatesApiResponse = /** status 200 undefined */ SpaceMembers;
export type SpaceMemberCandidatesApiArg = {
  id: string;
  after?: string;
  search?: string;
};
export type SpaceMembersApiResponse = /** status 200 undefined */ SpaceMembers;
export type SpaceMembersApiArg = {
  id: string;
  after?: string;
  search?: string;
};
export type RemoveSpaceMemberApiResponse = unknown;
export type RemoveSpaceMemberApiArg = {
  id: string;
  user: string;
};
export type TeamProjectsApiResponse = /** status 200 undefined */ DiscoverableTeam[];
export type TeamProjectsApiArg = {
  id: string;
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
export type OrganizationHomeApiResponse = /** status 200 undefined */ HomeShowcase;
export type OrganizationHomeApiArg = {
  organizationId: string;
};
export type OrganizationHomeCandidatesApiResponse = /** status 200 undefined */ HomeAgentPage;
export type OrganizationHomeCandidatesApiArg = {
  organizationId: string;
  after?: string;
};
export type OrganizationHomeSettingsApiResponse = /** status 200 undefined */ OrganizationHomeSettings;
export type OrganizationHomeSettingsApiArg = {
  organizationId: string;
};
export type SetOrganizationHomeApiResponse = unknown;
export type SetOrganizationHomeApiArg = {
  organizationId: string;
  setOrganizationHomeRequest: SetOrganizationHomeRequest;
};
export type GetCommonPromptSettingsApiResponse = /** status 200 undefined */ CommonPromptSettings;
export type GetCommonPromptSettingsApiArg = {
  organizationId: string;
};
export type PutCommonPromptSettingsApiResponse = unknown;
export type PutCommonPromptSettingsApiArg = {
  organizationId: string;
  setCommonPrompt: SetCommonPrompt;
};
export type GetCreationAssistantSettingsApiResponse = /** status 200 undefined */ CreationAssistantSettings;
export type GetCreationAssistantSettingsApiArg = {
  organizationId: string;
};
export type ResetCreationAssistantPromptApiResponse = unknown;
export type ResetCreationAssistantPromptApiArg = {
  organizationId: string;
};
export type PatchCreationAssistantSettingsApiResponse = unknown;
export type PatchCreationAssistantSettingsApiArg = {
  organizationId: string;
  patchCreationAssistant: PatchCreationAssistant;
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
export type TranscribeAgentAudioApiResponse = /** status 200 undefined */ DictationTranscript;
export type TranscribeAgentAudioApiArg = {
  spaceId: string;
  agentInstanceId: string;
  dictationUpload: DictationUpload;
};
export type SpaceAgentTemplatesApiResponse = /** status 200 undefined */ AgentTemplateSummary[];
export type SpaceAgentTemplatesApiArg = {
  spaceId: string;
};
export type DraftAgentApiResponse = /** status 200 undefined */ AgentDraftResult;
export type DraftAgentApiArg = {
  spaceId: string;
  templateId: string;
  agentDraftRequest: AgentDraftRequest;
};
export type AdmitAgentDraftApiResponse = /** status 200 undefined */ AgentDraftAdmission;
export type AdmitAgentDraftApiArg = {
  spaceId: string;
  templateId: string;
  person: string;
  run: string;
  agent: string;
};
export type SpaceApplicationsApiResponse = /** status 200 undefined */ SpaceApplication[];
export type SpaceApplicationsApiArg = {
  spaceId: string;
};
export type SpaceCapabilityPoliciesApiResponse = /** status 200 undefined */ SpaceCapabilityPolicy[];
export type SpaceCapabilityPoliciesApiArg = {
  spaceId: string;
};
export type ReplaceSpaceCapabilityPolicyApiResponse = unknown;
export type ReplaceSpaceCapabilityPolicyApiArg = {
  spaceId: string;
  sourceId: string;
  replaceSpaceCapabilityPolicy: ReplaceSpaceCapabilityPolicy;
};
export type AvailableKnowledgeBaseDefinitionsApiResponse =
  /** status 200 undefined */ AvailableKnowledgeBaseDefinition[];
export type AvailableKnowledgeBaseDefinitionsApiArg = {
  spaceId: string;
};
export type SpaceKnowledgeBasesApiResponse = /** status 200 undefined */ KnowledgeBaseInstance[];
export type SpaceKnowledgeBasesApiArg = {
  spaceId: string;
};
export type CreateKnowledgeBaseApiResponse = /** status 201 undefined */ KnowledgeBaseInstance;
export type CreateKnowledgeBaseApiArg = {
  spaceId: string;
  createInstance: CreateInstance;
};
export type MarketplaceInstallationApiResponse = /** status 200 undefined */ InstallationReceipt;
export type MarketplaceInstallationApiArg = {
  spaceId: string;
  installationId: string;
};
export type McpConnectionsApiResponse = /** status 200 undefined */ McpConnectionView[];
export type McpConnectionsApiArg = {
  spaceId: string;
};
export type CreateMcpConnectionApiResponse = /** status 201 undefined */ McpConnectionView;
export type CreateMcpConnectionApiArg = {
  spaceId: string;
  createMcpConnection: CreateMcpConnection;
};
export type UpdateMcpConnectionApiResponse = /** status 200 undefined */ McpConnectionView;
export type UpdateMcpConnectionApiArg = {
  spaceId: string;
  id: string;
  updateMcpConnection: UpdateMcpConnection;
};
export type PublishMcpConnectionApiResponse = /** status 200 undefined */ McpConnectionView;
export type PublishMcpConnectionApiArg = {
  spaceId: string;
  id: string;
  mcpPublication: McpPublication;
};
export type TestMcpConnectionApiResponse = /** status 200 undefined */ McpConnectionView;
export type TestMcpConnectionApiArg = {
  spaceId: string;
  id: string;
  mcpRevision: McpRevision;
};
export type McpCredentialsApiResponse = /** status 200 undefined */ McpCredentialReference[];
export type McpCredentialsApiArg = {
  spaceId: string;
};
export type ReplaceSpaceModelPolicyApiResponse = unknown;
export type ReplaceSpaceModelPolicyApiArg = {
  spaceId: string;
  replaceSpaceModelPolicy: ReplaceSpaceModelPolicy;
};
export type SpaceModelsApiResponse = /** status 200 undefined */ SpaceModels;
export type SpaceModelsApiArg = {
  spaceId: string;
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
export type GetTraceConsentApiResponse = /** status 200 undefined */ TraceConsentState;
export type GetTraceConsentApiArg = {
  spaceId: string;
  sessionId: string;
};
export type SetTraceConsentApiResponse = /** status 200 undefined */ TraceConsentState;
export type SetTraceConsentApiArg = {
  spaceId: string;
  sessionId: string;
  traceConsentRequest: TraceConsentRequest;
};
export type RevokeTraceConsentApiResponse = unknown;
export type RevokeTraceConsentApiArg = {
  spaceId: string;
  sessionId: string;
};
export type GetTraceIncidentOfferApiResponse = /** status 200 undefined */ TraceIncidentOffer;
export type GetTraceIncidentOfferApiArg = {
  spaceId: string;
  sessionId: string;
  errorRef: string;
};
export type ShareTraceIncidentApiResponse = /** status 200 undefined */ TraceConsentState;
export type ShareTraceIncidentApiArg = {
  spaceId: string;
  sessionId: string;
  errorRef: string;
  traceConsentRequest: TraceConsentRequest;
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
export type GetUserAvatarApiResponse = /** status 200 undefined */ string;
export type GetUserAvatarApiArg = {
  spaceId: string;
  userId: string;
};
export type WikiAvailabilityApiResponse = /** status 200 undefined */ WikiAvailability;
export type WikiAvailabilityApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
};
export type PrepareWikiDocumentApiResponse = /** status 200 undefined */ WikiFormat;
export type PrepareWikiDocumentApiArg = {
  spaceId: string;
  prepareWikiDocumentRequest: PrepareWikiDocumentRequest;
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
export type WikiProposalsApiResponse =
  /** status 200 Pending proposals: all for an editor, otherwise the caller's */ WikiProposalList;
export type WikiProposalsApiArg = {
  spaceId: string;
  cursor?: string;
};
export type ProposeWikiEditApiResponse =
  /** status 201 Draft for a delegated call; pending, or accepted for an editor */ WikiProposal;
export type ProposeWikiEditApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  spaceId: string;
  /** The bound conversation of a delegated call */
  sessionId?: string;
  proposeWikiEditRequest: ProposeWikiEditRequest;
};
export type ProposeWikiFileApiResponse = /** status 200 Replay of a stored request key */
  | WikiProposal
  | /** status 201 Draft for a delegated call; pending, or accepted for an editor */ WikiProposal;
export type ProposeWikiFileApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  spaceId: string;
  sessionId: string;
  /** Caller-chosen request UUID; replaying it is safe */
  "Idempotency-Key": string;
  proposeWikiFileRequest: ProposeWikiFileRequest;
};
export type ProposeWikiPageApiResponse =
  /** status 201 Draft for a delegated call; pending, or accepted for an editor */ WikiProposal;
export type ProposeWikiPageApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  spaceId: string;
  /** The bound conversation of a delegated call */
  sessionId?: string;
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
export type WithdrawWikiProposalApiResponse = unknown;
export type WithdrawWikiProposalApiArg = {
  spaceId: string;
  proposalId: string;
};
export type AcceptWikiProposalApiResponse = /** status 200 undefined */ WikiProposal;
export type AcceptWikiProposalApiArg = {
  spaceId: string;
  proposalId: string;
};
export type SubmitWikiProposalApiResponse = /** status 200 `pending`, or `published` for an editor */ WikiProposal;
export type SubmitWikiProposalApiArg = {
  spaceId: string;
  proposalId: string;
};
export type WikiRevisionFileApiResponse = unknown;
export type WikiRevisionFileApiArg = {
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
  spaceId: string;
  revisionId: string;
  part: "content" | "preview";
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
export type WikiSearchApiResponse = /** status 200 undefined */ WikiSearchResult;
export type WikiSearchApiArg = {
  spaceId: string;
  q: string;
  type?: string;
  tag?: string;
  limit?: number;
  offset?: number;
  person?: string;
  run?: string;
  agent?: string;
  sessionId?: string;
};
export type ResolveWordTemplateLibraryApiResponse = /** status 200 undefined */ Library;
export type ResolveWordTemplateLibraryApiArg = {
  spaceId: string;
  agentInstanceId?: string;
  runtimeId?: string;
};
export type SaveWordTemplateLibraryApiResponse = unknown;
export type SaveWordTemplateLibraryApiArg = {
  spaceId: string;
  runtimeId?: string;
  libraryChange: LibraryChange;
};
export type UploadWordTemplateApiResponse = /** status 200 undefined */ PowerPointFile;
export type UploadWordTemplateApiArg = {
  spaceId: string;
  agentInstanceId?: string;
  runtimeId?: string;
  templateId?: string;
  expectedFileId?: string;
  slot: number;
  "Idempotency-Key": string;
  fileUpload: FileUpload;
};
export type PreviewTeamJoinLinkApiResponse = /** status 200 undefined */ TeamJoinPreview;
export type PreviewTeamJoinLinkApiArg = {
  token: string;
};
export type RedeemTeamJoinLinkApiResponse = /** status 200 undefined */ TeamJoinPreview;
export type RedeemTeamJoinLinkApiArg = {
  token: string;
};
export type GetMyAvatarApiResponse = /** status 200 undefined */ string;
export type GetMyAvatarApiArg = void;
export type PutMyAvatarApiResponse = unknown;
export type PutMyAvatarApiArg = {
  fileUpload: FileUpload;
};
export type DeleteMyAvatarApiResponse = unknown;
export type DeleteMyAvatarApiArg = void;
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
export type TraceHistoryBoundary = {
  exchange_id: string;
  first_rank: number;
  last_rank: number;
  started_at: string;
  turn_number: number;
};
export type TraceHistoryAccess = {
  captured_rank?: number | null;
  cutoff?: TraceHistoryBoundary | null;
  grant_id?: string | null;
  local_content_access?: boolean;
  owner_id: string;
};
export type ErrorBody = {
  code: string;
  detail: string;
};
export type TraceHttpCompleteness = "complete" | "partial" | "unavailable";
export type TraceHttpFailureStage = "response_headers" | "response_body" | "http_status";
export type TraceHttpAttempt = {
  attempt: number;
  call_id: string;
  completeness: TraceHttpCompleteness;
  duration_ms: number;
  failure_stage?: TraceHttpFailureStage | null;
  model?: string | null;
  observed_through_rank?: number | null;
  ref: string;
  release?: string | null;
  request_bytes: number;
  response_bytes: number;
  status?: number | null;
  tool_ref?: string | null;
  upstream_id?: string | null;
};
export type TraceHttpArtifactAccess = {
  attempt: TraceHttpAttempt;
  grant_id?: string | null;
  local_content_access?: boolean;
};
export type TraceModelArtifactAccess = {
  grant_id?: string | null;
  local_content_access?: boolean;
  observed_through_rank?: number | null;
  owner_id: string;
};
export type TraceSseArtifactAccess = {
  grant_id?: string | null;
  index: number;
  local_content_access?: boolean;
};
export type TraceSseHeaderAccess = {
  grant_id?: string | null;
  local_content_access?: boolean;
};
export type TraceToolArtifactAccess = {
  grant_id?: string | null;
  local_content_access?: boolean;
  observed_through_rank?: number | null;
};
export type SpaceKind = "organization" | "team" | "project" | "personal";
export type Space = {
  /** Team or project purpose, absent until its owner describes it. */
  description: string | null;
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
export type ToolFailureCode = "unexpected";
export type ToolFailure = {
  code: ToolFailureCode;
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
      failure?: ToolFailure | null;
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
      failure?: ToolFailure | null;
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
export type CalculationPrecision = "exact" | "rounded" | "estimated" | "mixed";
export type CollectionCompleteness = "unknown";
export type AnalyticsInterval = "hour" | "day" | "week";
export type AnalyticsCalendar = {
  exclude_holidays?: boolean;
  exclude_weekends?: boolean;
};
export type ConsumptionMeasure =
  | "activity.median_usage_days"
  | "activity.median_days_per_week"
  | "activity.mean_daily_active"
  | "activity.daily_usage_share"
  | "activity.median_turns_per_conversation"
  | "activity.failure_rate"
  | "activity.single_turn_rate"
  | "activity.retained_conversations_per_creator_median"
  | "activity.retained_conversations_top_decile_share"
  | "activity.creators_1"
  | "activity.creators_2_3"
  | "activity.creators_4_10"
  | "activity.creators_11_30"
  | "activity.creators_31_plus"
  | "inventory.enabled_agents"
  | "inventory.retained_agents_created"
  | "inventory.agents_published"
  | "inventory.documents_added"
  | "tools.attempts"
  | "tools.successes"
  | "tools.failures"
  | "tools.cancelled"
  | "tools.awaiting_human"
  | "tools.failure_rate"
  | "usage.input_tokens"
  | "usage.output_tokens"
  | "usage.cache_read_tokens"
  | "usage.cache_creation_tokens"
  | "usage.total_tokens"
  | "usage.recorded_exchanges"
  | "usage.cost_eur"
  | "usage.co2e_grams"
  | "usage.energy_kwh"
  | "skills.user_loads"
  | "skills.agent_loads"
  | "skills.total_loads"
  | "activity.retained_conversations"
  | "activity.completed_turns"
  | "activity.agents_used"
  | "activity.active_users"
  | "activity.observed_conversations"
  | "activity.failed_turns"
  | "activity.single_turn_conversations";
export type AnalyticsUnit =
  | "day"
  | "ratio"
  | "document"
  | "attempt"
  | "token"
  | "exchange"
  | "eur"
  | "gramco2e"
  | "kwh"
  | "load"
  | "conversation"
  | "turn"
  | "agent"
  | "user";
export type AnalyticsValueType = "integer" | "decimal";
export type AnalyticsMeasure = {
  calculation: CalculationPrecision;
  id: ConsumptionMeasure;
  unit: AnalyticsUnit;
  value_type: AnalyticsValueType;
};
export type AnalyticsDimensions =
  | {
      kind: "total";
    }
  | {
      kind: "tool";
      name: string;
    }
  | {
      kind: "skill";
      name: string;
    }
  | {
      kind: "time";
      /** UTC bucket start; the first bucket may precede since, but counts are clipped to the period. */
      start: string;
    }
  | {
      agent_instance_id: string;
      /** Current/retained session name (consumption), latest observed name (turns), or null. Never an identity key. */
      display_name: string | null;
      kind: "agent";
      space_id: string;
    }
  | {
      kind: "space";
      space_id: string;
    }
  | {
      kind: "model";
      model_source_id: string;
      upstream_model_id: string;
    };
export type EstimateCoverage = "complete" | "partial" | "unavailable";
export type AnalyticsEstimate = {
  coverage: EstimateCoverage;
  /** At least one model used the catalog's explicitly configured default factors. */
  fallback: boolean;
  value: string | null;
};
export type AnalyticsRow = {
  dimensions: AnalyticsDimensions;
  /** Estimated decimal values are separate from exact counters. Null is never zero. */
  estimates?: {
    [key: string]: AnalyticsEstimate;
  };
  /** Decimal strings for matching facts; per-measure metadata distinguishes exact integers/medians
    from ratios truncated to six fractional digits. Collection completeness is separate.
    A requested attribution counter is absent when erased/missing identities or outcomes prevent an exact count.
    Absence is unavailable, never zero. No user or conversation identities are returned. */
  values: {
    [key: string]: string;
  };
};
export type AnalyticsTimezone = "UTC";
export type AnalyticsResult = {
  bucket?: AnalyticsInterval | null;
  /** UTC dates, French national holidays (metropole, excluding local additions). */
  calendar?: AnalyticsCalendar;
  measures: AnalyticsMeasure[];
  rows: AnalyticsRow[];
  since: string;
  timezone: AnalyticsTimezone;
  /** Rankings may be truncated; SQL totals and estimates cover all recorded facts. */
  truncated: boolean;
  until: string;
};
export type AnalyticsResponse = {
  /** Batch summary; precision is also declared per measure. */
  calculation: CalculationPrecision;
  collection_completeness: CollectionCompleteness;
  /** SQL results share one read-only snapshot. Historical batches are separate; mixed sources are refused. */
  results: {
    [key: string]: AnalyticsResult;
  };
};
export type AnalyticsGrouping = "time" | "agent" | "model" | "skill" | "space" | "tool";
export type AnalyticsScope =
  | {
      kind: "self";
      organization_id: string;
    }
  | {
      id: string;
      kind: "space";
    };
export type AnalyticsPeriod = {
  bucket?: AnalyticsInterval | null;
  /** UTC dates, French national holidays (metropole, excluding local additions). */
  calendar?: AnalyticsCalendar;
  /** Inclusive instant with offset. Maximum duration: 366 days. */
  since: string;
  timezone: AnalyticsTimezone;
  /** Exclusive instant with offset. */
  until: string;
};
export type AnalyticsQuery = {
  /** Consumption: total/time/agent/model; catalogues: total; turns: total/time/agent (self also space); skills: skill; tools: total/tool. */
  group_by?: AnalyticsGrouping[];
  /** Rankings only, default 100. Descending tokens, loads or turns, then stable identity. */
  limit?: number | null;
  measures: ConsumptionMeasure[];
  name: string;
  scope: AnalyticsScope;
  time: AnalyticsPeriod;
};
export type AnalyticsRequest = {
  queries: AnalyticsQuery[];
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
  | "observe_organization"
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
export type ModelWire = "openai_chat" | "openai_responses" | "rerank";
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
  /** Physical corpus namespace, only for document embedding admissions. */
  corpus_generation?: string | null;
  /** AES-GCM envelope bound to this source and destination, never a clear token.
    Trusted workloads open it using their deployment's catalogue key. It is
    not an execution grant and does not replace the admission above. */
  encrypted_credential?: string | null;
  selection: InferenceSelection;
};
export type Status = "queued" | "running" | "retrying" | "blocked" | "completed";
export type TargetKind = "organization" | "team" | "project" | "document" | "folder" | "session";
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
  corpus_generation?: string | null;
  cursor: number;
  generation: string;
  output_prefix: string;
  preserve_objects: boolean;
  protected_ordinals: number[];
  purge_document: boolean;
  rebuilding_corpus_generation?: string | null;
  work: Work;
};
export type Cleaned = {
  corpus_generation?: string | null;
  cursor: number;
  generation: string;
  next_cursor: number;
  objects_empty: boolean;
  purge_document?: boolean;
  rebuilding_corpus_generation?: string | null;
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
  corpus_generation?: string | null;
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
export type RetiredCorpus = {
  corpus_generation?: string | null;
  organization_id: string;
};
export type RetiredCorpusProgress = {
  complete: boolean;
  corpus_generation?: string | null;
  organization_id: string;
};
export type ReindexProgress = {
  document_id: string;
  execution_id: string;
  finished: boolean;
  lease: string;
  offset: number;
  succeeded: boolean;
};
export type ReindexDocument = {
  artifact: Artifact;
  document_id: string;
  folder_path?: string | null;
  generation: string;
  prefix: string;
  retrievable: boolean;
  session_id?: string | null;
  space_id: string;
};
export type VectorReindexWork = {
  admission: InferenceAdmission;
  document: ReindexDocument;
  execution_id: string;
  id: string;
  lease: string;
  offset: number;
  organization_id: string;
};
export type ClaimVectorReindex = {
  execution_id: string;
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
  /** Models admitted for this stage under the organization's policy; empty when the
    descriptor replays a committed stage, which runs no inference. */
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
  /** Declared prompts absent by logical name, created with their category. */
  prompts_created: number;
  /** Existing prompts left unchanged, including their category and text. */
  prompts_kept: number;
  /** Declared skills absent from their space, created by this import. */
  skills_created: number;
  /** Declared skills already present by name; never replaced, even if edited. */
  skills_kept: number;
  spaces_reconciled: number;
};
export type ProvisioningUpload = {
  file: Blob;
};
export type TraceAdmission = {
  capture_id: string;
  segment_id?: string | null;
  stream_offset_ms?: number;
  streaming_blocks?: boolean;
};
export type TraceAdmissionRequest = {
  agent_instance_id: string;
  exchange_id: string;
  history_rank: number;
  session_id: string;
  user_id: string;
};
export type TraceStorageCleanup = {
  id: string;
  lease: string;
  measure?: boolean;
  refs: string[];
  session_id: string;
};
export type TraceStorageCleanupResult = {
  lease: string;
  measured?:
    | {
        [key: string]: number;
      }
    | {
        [key: string]: number;
      };
  success?: boolean;
};
export type TraceOwnerVisibilityRequest = {
  session_ids: string[];
  user_id: string;
};
export type TraceCheckpointStatus = "persisted" | "not_observed" | "unconfigured" | "unknown";
export type TraceFailureCategory =
  | "http_5xx"
  | "http_429"
  | "http_400"
  | "http_other_4xx"
  | "stream_interrupted"
  | "timeout_or_connection"
  | "context_limit"
  | "tool_or_capability"
  | "internal_or_unknown";
export type TraceOutcome = "completed" | "failed" | "paused" | "unknown";
export type TraceFinalizationFacts = {
  call_ids?: string[];
  checkpoint_status: TraceCheckpointStatus;
  discarded?: boolean;
  duration_ms: number;
  failure_category?: TraceFailureCategory | null;
  outcome: TraceOutcome;
  span_id?: string | null;
  support_error_ref?: string | null;
  trace_id?: string | null;
  turn_number?: number | null;
};
export type TraceAdmissionReconciliation = {
  admission: TraceAdmissionRequest;
  facts: TraceFinalizationFacts;
};
export type TraceDegradation = "capacity" | "queue" | "storage";
export type TraceModelIndex = {
  call_id: string;
  completeness: TraceHttpCompleteness;
  model?: string | null;
  observed_invalid_tools?: string[];
  observed_through_rank?: number | null;
  ref: string;
  related_tools?: string[];
};
export type OtlpTraceStringValue = {
  stringValue: string;
};
export type OtlpTraceAttribute = {
  key: string;
  value: OtlpTraceStringValue;
};
export type OtlpTraceSpan = {
  attributes?: OtlpTraceAttribute[];
  endTimeUnixNano: string;
  name: string;
  parentSpanId: string;
  spanId: string;
  startTimeUnixNano: string;
  traceId: string;
};
export type TraceSseAvailability = "captured" | "empty" | "partial" | "unavailable";
export type TraceSseEnding =
  | "completed"
  | "failed"
  | "paused"
  | "closed"
  | "timeout"
  | "watchdog_timeout"
  | "truncated"
  | "transport_error"
  | "http_rejected"
  | "not_sse";
export type TraceSseLane = {
  availability: TraceSseAvailability;
  end_ms: number;
  ending: TraceSseEnding;
  frame_count: number;
  headers_available?: boolean;
  headers_ms?: number | null;
  last_event_ms?: number | null;
  longest_gap?: number[] | null;
  page_starts_ms?: number[];
  ref: string;
  started_ms: number;
};
export type TraceSseSegment = {
  observed_through_rank?: number | null;
  outgoing?: TraceSseLane | null;
  provider: TraceSseLane[];
};
export type TraceStoragePublication = {
  publication_id: string;
  stored: {
    [key: string]: number;
  };
  uncertain: string[];
};
export type TraceToolModelLink = {
  call_id: string;
  relation: string;
};
export type TraceToolOutcome = "success" | "error" | "paused" | "cancelled";
export type TraceToolSource = "native" | "mcp" | "knowledge_flow";
export type TraceToolCall = {
  attempt: number;
  call_id?: string | null;
  completeness: TraceHttpCompleteness;
  duration_ms: number;
  http_attempts?: TraceHttpAttempt[];
  model_calls?: TraceToolModelLink[];
  observed_through_rank?: number | null;
  outcome: TraceToolOutcome;
  ref: string;
  source: TraceToolSource;
  tool_name?: string | null;
};
export type TraceFinalization = {
  call_ids?: string[];
  checkpoint_status: TraceCheckpointStatus;
  degradation?: TraceDegradation | null;
  discarded?: boolean;
  duration_ms: number;
  evidence_pending?: boolean;
  failure_category?: TraceFailureCategory | null;
  http_attempts?: TraceHttpAttempt[];
  http_incomplete?: boolean;
  model_calls?: TraceModelIndex[];
  otel_spans?: OtlpTraceSpan[];
  outcome: TraceOutcome;
  recording_complete?: boolean | null;
  segment_id?: string | null;
  span_id?: string | null;
  sse?: TraceSseSegment | null;
  storage?: TraceStoragePublication | null;
  support_error_ref?: string | null;
  tool_calls?: TraceToolCall[];
  trace_id?: string | null;
  turn_number?: number | null;
};
export type TraceStorageReservationState = "reserved" | "capacity" | "unavailable" | "fenced";
export type TraceStorageReservation = {
  incremental?: boolean;
  objects: {
    [key: string]: number;
  };
  publication_id: string;
  segment_id?: string | null;
};
export type FieldUiHints = {
  advanced?: boolean;
  group?: string | null;
  hide?: boolean;
  markdown?: boolean;
  max_lines?: number | null;
  multiline?: boolean;
  placeholder?: string | null;
  textarea?: boolean;
  visible_when?: string | null;
  widget?: string | null;
};
export type FieldSpec = {
  default?: any;
  default_by_lang?:
    | {
        [key: string]: string;
      }
    | {
        [key: string]: string;
      };
  description?: string | null;
  description_by_lang?:
    | {
        [key: string]: string;
      }
    | {
        [key: string]: string;
      };
  enum?: string[] | null;
  item_type?: string | null;
  key: string;
  max?: number | null;
  min?: number | null;
  pattern?: string | null;
  required?: boolean;
  title?: string;
  type: string;
  ui?: FieldUiHints;
};
export type KnowledgeBaseConfiguration = {
  fields: FieldSpec[];
};
export type Definition = {
  config_schema: KnowledgeBaseConfiguration;
  description: string;
  icon?: string;
  id: string;
  name: string;
  version: string;
};
export type PublishDefinitions = {
  definitions: Definition[];
  runtime_id: string;
};
export type KnowledgeBaseRun = {
  config: object;
  credential_refs: object;
  deadline_at: string;
  definition_id: string;
  error_code?: string | null;
  folder_id: string;
  id: string;
  instance_id: string;
  profile: string;
  result?: object | null;
  runtime_id: string;
  space_id: string;
  state: string;
};
export type CompleteRun = {
  error_code?: string | null;
  result: any;
};
export type SourceDocument = {
  current_version?: string | null;
  document_id?: string | null;
  error_code?: string | null;
  pending_version?: string | null;
  processing?: Summary | null;
  source_key: string;
};
export type Catalogue = {
  items: SourceDocument[];
  next_cursor?: string | null;
};
export type KnowledgeBaseDocumentReceipt = {
  document_id: string;
  error_code?: string | null;
  state: ProcessingStatus;
  task_id: string;
};
export type KnowledgeBaseWorkerBinding = {
  installation_id: string;
  task_queue: string;
};
export type KnowledgeBaseInstance = {
  config: object;
  config_schema: KnowledgeBaseConfiguration;
  created_at: string;
  credential_refs: object;
  definition_description: string;
  definition_id: string;
  definition_name: string;
  folder_id: string;
  id: string;
  interval_seconds?: number | null;
  name: string;
  paused: boolean;
  profile: string;
  space_id: string;
};
export type UpdateInstance = {
  interval_seconds?: number | null;
  paused: boolean;
};
export type StartRun = {
  request_key: string;
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
export type Role = "member" | "editor" | "owner" | "analyst" | "organization_admin" | "organization_observer";
export type MySpace = Space & {
  organization_id: string;
  /** Roles held directly on this space. */
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
export type ApplicationMetadata = {
  description: string;
  description_by_lang?: {
    [key: string]: string;
  };
  display_name: string;
  display_name_by_lang?: {
    [key: string]: string;
  };
  icon: string;
  version?: string;
};
export type Application = ApplicationMetadata & {
  api_base_url?: string | null;
  capability_id: string;
  enabled: boolean;
  entry_permission: SpacePermission;
  id: string;
  logical_name: string;
  organization_id: string;
  revision: number;
  source_id: string;
  ui_base_url: string;
};
export type CreateApplication = ApplicationMetadata & {
  api_base_url?: string | null;
  entry_permission?: SpacePermission;
  logical_name: string;
  ui_base_url: string;
};
export type UpdateApplication = ApplicationMetadata & {
  api_base_url?: string | null;
  enabled: boolean;
  entry_permission: SpacePermission;
  expected_revision: number;
  ui_base_url: string;
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
export type PodCapabilityKind = "tool" | "application" | "knowledge_base";
export type PodCapabilityDescriptor = {
  config_fields?: CapabilityFieldDescription[];
  description: string;
  description_by_lang?: {
    [key: string]: string;
  };
  execution_models?: CapabilityExecutionModel[];
  icon: string;
  id: string;
  kind?: PodCapabilityKind;
  name: string;
  name_by_lang?: {
    [key: string]: string;
  };
  public_version?: string | null;
  runtime_id?: string | null;
  source_id?: string | null;
  team_settings_fields?: CapabilityFieldDescription[];
  version: string;
};
export type OfferOrigin = "pod" | "managed_mcp" | "application" | "knowledge_base";
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
  /** Native offer present in its snapshot, or managed connection ready for execution. */
  advertised: boolean;
  /** Immutable application key from the registry; absent for other origins. */
  application_logical_name?: string | null;
  capability_id: string;
  /** Enabled for every space of this organization. */
  default_on: boolean;
  descriptor: PodCapabilityDescriptor;
  origin: OfferOrigin;
  /** Browser route derived from the platform-approved pod ingress. */
  route_base_url?: string | null;
  runtime_id?: string | null;
  source_id: string;
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
export type CapabilityInventory = {
  capabilities: CapabilityInventoryOffer[];
  checked_at?: string | null;
  enabled: boolean;
  observation: CatalogObservationState;
  observed_at?: string | null;
  origin: OfferOrigin;
  runtime_id?: string | null;
  source_id: string;
  /** Links from the last successful snapshot, all scoped to this runtime. */
  template_capabilities: PodTemplateCapability[];
};
export type TraceContentAccess = "masked" | "shared" | "local";
export type TraceAvailability = "metadata_only" | "captured" | "partial" | "history_only";
export type ConversationTraceSummary = {
  access: TraceContentAccess;
  agent_display_name: string;
  availability: TraceAvailability;
  failure_category?: TraceFailureCategory | null;
  latest_started_at: string;
  outcome: TraceOutcome;
  session_id: string;
  support_error_ref?: string | null;
  team_id: string;
  team_name: string;
  title?: string | null;
  user_display_name?: string | null;
  user_id?: string | null;
  username?: string | null;
};
export type ConversationTraceCatalog = {
  conversations: ConversationTraceSummary[];
  next_cursor?: string | null;
};
export type TraceConsentFilter = "all" | "shared" | "masked";
export type TraceCatalogSort = "latest" | "title" | "user" | "team" | "outcome" | "consent";
export type DeleteConversationTracesResult = {
  removed: number;
};
export type DeleteConversationTracesRequest = {
  session_ids: string[];
};
export type TraceExportMode = "metadata_only" | "shared_content";
export type ExportConversationTracesRequest = {
  mode: TraceExportMode;
  session_ids: string[];
};
export type ConversationTraceSettings = {
  degradation_reason?: TraceDegradation | null;
  degraded: boolean;
  enabled: boolean;
  reserved_bytes: number;
  retention_days: number;
  sampling_percent: number;
  storage_cap_bytes: number;
  used_bytes: number;
};
export type ConversationTraceSettingsUpdate = {
  enabled?: boolean | null;
  retention_days?: number | null;
  sampling_percent?: number | null;
  storage_cap_bytes?: number | null;
};
export type TraceTeamOption = {
  name: string;
  team_id: string;
};
export type TraceReportedFailure = {
  failure_category?: TraceFailureCategory | null;
  support_error_ref: string;
};
export type ConversationTraceTurn = {
  access: TraceContentAccess;
  availability: TraceAvailability;
  call_ids: string[];
  capture_status?: string | null;
  checkpoint_status: TraceCheckpointStatus;
  degradation_reason?: TraceDegradation | null;
  duration_ms?: number | null;
  exchange_id: string;
  failure_category?: TraceFailureCategory | null;
  outcome: TraceOutcome;
  reported_failures?: TraceReportedFailure[];
  retained_cutoff?: TraceHistoryBoundary | null;
  span_id?: string | null;
  started_at: string;
  support_error_ref?: string | null;
  trace_id?: string | null;
  turn_number?: number | null;
};
export type ConversationTraceDetail = {
  agent_display_name: string;
  can_renew_title_consent?: boolean;
  consent_cutoff?: TraceHistoryBoundary | null;
  consent_version?: string | null;
  local_content_access?: boolean;
  next_cursor?: string | null;
  retained_after_delete?: boolean;
  session_id: string;
  team_id: string;
  title?: string | null;
  turns: ConversationTraceTurn[];
};
export type TraceHistoryPart = {
  text?: string | null;
  type: string;
  [key: string]: any;
};
export type TraceHistoryMessage = {
  channel: string;
  exchange_id: string;
  metadata: any;
  parts: TraceHistoryPart[];
  rank: number;
  role: string;
  session_id: string;
  timestamp: string;
};
export type TraceHistoryTranscript = {
  available: boolean;
  messages: TraceHistoryMessage[];
  next_rank?: number | null;
};
export type TraceHttpBody = {
  complete: boolean;
  data: string;
  decoded?: boolean;
  encoding: string;
  next_offset?: number | null;
  offset?: number | null;
  total_bytes?: number | null;
};
export type TraceHttpEvidence = {
  bearer_replay?: boolean | null;
  method: string;
  request_body?: TraceHttpBody | null;
  request_headers: {
    [key: string]: string;
  };
  response_body?: TraceHttpBody | null;
  response_headers: {
    [key: string]: string;
  };
  target: string;
  version: number;
};
export type TraceModelCall = {
  call_id: string;
  completeness: TraceHttpCompleteness;
  model?: string | null;
  observed_through_rank?: number | null;
  ref: string;
};
export type TraceModelSnapshot = {
  messages: {
    [key: string]: any;
  }[];
  partial?: boolean;
  tools?: {
    [key: string]: any;
  }[];
};
export type TraceNormalizationRewrite = {
  choice_index: number;
  frame_index?: number | null;
  original_id: string;
  replacement_id?: any;
  tool_call_id?: string | null;
  tool_index: number;
};
export type TraceNormalizationStatus = "skipped" | "unchanged" | "corrected" | "unavailable";
export type TraceNormalization = {
  attempt_ref: string;
  partial?: boolean;
  rewrites: TraceNormalizationRewrite[];
  status: TraceNormalizationStatus;
};
export type TraceModelOrigin = {
  call_id: string;
  exchange_id: string;
  history_rank: number;
  turn_number?: number | null;
};
export type TraceModelOutputState = "complete" | "partial" | "absent" | "unavailable";
export type TraceModelEvidence = {
  input?: TraceModelSnapshot | null;
  matched_results?: {
    [key: string]: any;
  }[];
  normalization?: TraceNormalization[];
  origins?: TraceModelOrigin[];
  output?: TraceModelSnapshot | null;
  output_state: TraceModelOutputState;
  version: number;
};
export type TraceSseKind = "text" | "reasoning" | "tool" | "status" | "done" | "error" | "other";
export type TraceSseEvent = {
  at_ms: number;
  kind: TraceSseKind;
  offset?: number | null;
  size: number;
};
export type TraceSseFramePage = {
  frames: TraceSseEvent[];
  raw_data?: string | null;
  start_index: number;
};
export type TraceSseHeaders = {
  headers: {
    [key: string]: string;
  };
};
export type TraceSseFrame = {
  data: string;
  encoding: string;
};
export type TraceToolEvidence = {
  input?: any;
  model_result?:
    | {
        [key: string]: any;
      }
    | {
        [key: string]: any;
      };
  output?: any;
  partial?: boolean;
  version: number;
};
export type KnowledgeBaseService = {
  audience: string;
  client_id: string;
  credential_bindings: string[];
  issuer: string;
  organization_id: string;
  revision: number;
  runtime_id: string;
};
export type RegisterKnowledgeBaseService = {
  audience: string;
  client_id: string;
  credential_bindings?: string[];
  issuer: string;
  runtime_id: string;
};
export type UpdateKnowledgeBaseService = {
  credential_bindings: string[];
  expected_revision: number;
};
export type OrganizationModelPolicy = {
  created_at?: string | null;
  created_by?: string | null;
  creation_assistant?: ModelOfferKey | null;
  default?: ModelOfferKey | null;
  embedding?: ModelOfferKey | null;
  /** Set by the first indexing: the corpus keeps this embedding model. */
  embedding_locked: boolean;
  fallback?: ModelOfferKey | null;
  organization_id: string;
  permitted: ModelOfferKey[];
  reranker?: ModelOfferKey | null;
  /** Zero means no saved policy: no permissions or implicit selections. */
  revision: number;
  title?: ModelOfferKey | null;
  transcription?: ModelOfferKey | null;
  updated_at?: string | null;
  updated_by?: string | null;
  vision?: ModelOfferKey | null;
};
export type ReplaceModelPolicy = {
  creation_assistant: ModelOfferKey | null;
  default: ModelOfferKey | null;
  embedding: ModelOfferKey | null;
  expected_revision: number;
  fallback: ModelOfferKey | null;
  permitted: ModelOfferKey[];
  reranker: ModelOfferKey | null;
  title: ModelOfferKey | null;
  transcription?: ModelOfferKey | null;
  vision: ModelOfferKey | null;
};
export type SingleModelUse = "chat" | "embedding" | "audio_transcription";
export type SingleModel = {
  id: string;
  usage: SingleModelUse;
};
export type CreateModelCatalog = {
  /** Explicitly approved inference root, independent of the catalogue URL. */
  api_root: string;
  dialect: ModelDialect;
  /** Optional models.dev provider ID. Omit to derive it from the source hostname. */
  metadata_provider?: string | null;
  model?: SingleModel | null;
  /** Defaults to true when omitted. */
  models_dev_enabled?: boolean | null;
  name: string;
  platform_terms_url?: string | null;
  /** Catalogue discovery URL. Supply either this or one declared model. */
  url?: string | null;
  wire: ModelWire;
};
export type CreateModelCatalogWrite = {
  /** Explicitly approved inference root, independent of the catalogue URL. */
  api_root: string;
  dialect: ModelDialect;
  /** Optional models.dev provider ID. Omit to derive it from the source hostname. */
  metadata_provider?: string | null;
  model?: SingleModel | null;
  /** Defaults to true when omitted. */
  models_dev_enabled?: boolean | null;
  name: string;
  platform_terms_url?: string | null;
  /** Write-only: the public inventory never returns this value. */
  token: string;
  /** Catalogue discovery URL. Supply either this or one declared model. */
  url?: string | null;
  wire: ModelWire;
};
export type UpdateModelCatalog = {
  expected_revision: number;
  /** Omit to keep the value; null restores hostname-based detection. */
  metadata_provider?: string | null;
  /** Omit to keep the synchronization setting. */
  models_dev_enabled?: boolean | null;
  name: string;
  /** Omit to keep the configured link. Null removes it. */
  platform_terms_url?: string | null;
};
export type UpdateModelCatalogWrite = {
  expected_revision: number;
  /** Omit to keep the value; null restores hostname-based detection. */
  metadata_provider?: string | null;
  /** Omit to keep the synchronization setting. */
  models_dev_enabled?: boolean | null;
  name: string;
  /** Omit to keep the configured link. Null removes it. */
  platform_terms_url?: string | null;
  /** Omit to keep the existing token. A rotation retains the same provider
    account/namespace; another account must be registered as another catalogue. */
  token?: string | null;
};
export type ModelScopeChoice = "disabled" | "default" | "enabled";
export type ModelTeamAccess = {
  choice: ModelScopeChoice;
  /** Organization permission and the team's own restriction, not provider readiness. */
  effective: boolean;
  locally_disabled: boolean;
  name: string;
  team_id: string;
};
export type ModelAccessMatrix = {
  next_cursor?: string | null;
  organization_permitted: boolean;
  personal: ModelScopeChoice;
  personal_effective: boolean;
  /** Shared organization policy revision; all administrative writes serialize there. */
  revision: number;
  teams: ModelTeamAccess[];
};
export type SetModelAccess = {
  choice: ModelScopeChoice;
  expected_revision: number;
  /** Null explicitly addresses all personal spaces; no individual-user overrides. */
  team_id: string | null;
  upstream_model_id: string;
};
export type ChatProvenance = "source_guarantee" | "api_metadata";
export type ModelLicense = {
  name?: string | null;
  url?: string | null;
};
export type ModelMetadata = {
  /** Accepts a recorded audio file for transcription. Realtime alone is insufficient. */
  audio_transcription?: boolean | null;
  chat?: boolean | null;
  chat_provenance?: ChatProvenance | null;
  context_window_tokens?: number | null;
  display_name?: string | null;
  /** Explicit embedding aptitude from provider, source attestation or a complement; never chat. */
  embedding?: boolean | null;
  license?: ModelLicense | null;
  max_input_tokens?: number | null;
  max_output_tokens?: number | null;
  /** Each known property's origin: provider, models_dev or manual. */
  provenance?: {
    [key: string]: string;
  };
  /** Bounded, provider-reported capabilities for catalogue descriptions only.
    They never grant eligibility for an inference endpoint. */
  provider_capabilities?: {
    [key: string]: boolean;
  };
  /** Source-reported aptitude; absent means unknown, not unsupported. */
  reasoning?: boolean | null;
  reasoning_default?: string | null;
  reasoning_efforts?: string[] | null;
  reasoning_replay?: string | null;
  reasoning_required?: boolean | null;
  reasoning_transport?: string | null;
  rerank?: boolean | null;
  structured_output?: boolean | null;
  tool_calling?: boolean | null;
  /** Source-reported image input; absent means unknown, not unsupported. */
  vision?: boolean | null;
};
export type ReplaceModelComplements = {
  expected_revision: number;
  upstream_model_id: string;
  /** An omitted field follows detection. Null explicitly records an unknown value.
    Provider-confirmed technical fields are locked. The display name can
    always be customized. An empty object resets all. */
  values: {
    [key: string]: any;
  };
};
export type ModelObservation = {
  checked_at?: string | null;
  enabled: boolean;
  /** `models_dev_unavailable` may accompany an otherwise successful provider observation. */
  error_code?: string | null;
  last_success_at?: string | null;
  snapshot_revision: number;
  snapshot_source_revision?: number | null;
  source_id: string;
  source_revision: number;
  state: string;
};
export type ModelUseOptions = {
  chat: boolean;
  embedding: boolean;
  rerank: boolean;
  transcription: boolean;
  unverified: boolean;
  vision: boolean;
};
export type StoredModelOffer = {
  advertised: boolean;
  detected_metadata: ModelMetadata;
  first_seen_at: string;
  last_seen_at: string;
  metadata: ModelMetadata;
  metadata_complements: any;
  metadata_revision: number;
  /** Server-calculated eligibility to authorize an advertised provider offer. */
  selectable: boolean;
  source_id: string;
  upstream_model_id: string;
  uses?: ModelUseOptions;
  withdrawn_at?: string | null;
};
export type ModelInventory = {
  /** Public connection settings only; credentials and bindings stay private. */
  api_root: string;
  dialect: ModelDialect;
  managed: boolean;
  metadata_provider?: string | null;
  models_dev_enabled: boolean;
  name: string;
  observation: ModelObservation;
  offers: StoredModelOffer[];
  platform_terms_url?: string | null;
  url?: string | null;
  wire: ModelWire;
};
export type OrganizationModelInventory = {
  /** Only this organization's choices; none is a proof of executability. */
  policy: OrganizationModelPolicy;
  /** Assigned source observations. Presence/chat/discovery are independent of permission. */
  sources: ModelInventory[];
};
export type DiscoverableResourceKind = "prompt" | "skill" | "agent";
export type DiscoverableResource = {
  can_read: boolean;
  description?: string | null;
  display_name: string;
  kind: DiscoverableResourceKind;
  resource_id: string;
  space_id: string;
  space_kind: SpaceKind;
  space_name: string;
};
export type ResourceDirectoryPage = {
  items: DiscoverableResource[];
  total: number;
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
export type TeamJoiningMode = "invite_only" | "open";
export type SpaceOwner = {
  display_name: string;
  id: string;
};
export type TeamVisibility = "hidden" | "visible";
export type DiscoverableTeam = {
  can_join: boolean;
  description?: string | null;
  id: string;
  /** Any direct role: every role holder is a member. */
  is_member: boolean;
  joining_mode: TeamJoiningMode;
  /** Distinct subjects holding any direct role. */
  member_count: number;
  name: string;
  /** Direct owners in total; `owners` describes at most four of them. */
  owner_count: number;
  /** Resolved after SQL; an owner the directory cannot describe is omitted. The id
    is the subject the space-scoped user avatar route expects. */
  owners: SpaceOwner[];
  visibility: TeamVisibility;
};
export type TeamDirectoryPage = {
  items: DiscoverableTeam[];
  total: number;
};
export type VectorReindex = {
  cleanup_pending: boolean;
  completed: number;
  completed_at?: string | null;
  created_at: string;
  embedding: ModelOfferKey;
  error_code?: string | null;
  id: string;
  status: string;
  total: number;
};
export type StartVectorReindex = {
  embedding: ModelOfferKey;
  expected_policy_revision: number;
  /** Stable request identity; resubmit the failed operation's ID to resume. */
  id: string;
};
export type PowerPointFileStatus = "pending" | "stored" | "retired";
export type PowerPointFile = {
  agent_instance_id: string | null;
  capability_id: string;
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
  slot: number;
  space_id: string;
  /** Stored means attached in CP, not prepared or activated in the pod. */
  status: PowerPointFileStatus;
};
export type CreateSpaceMember = {
  /** Owner, editor, analyst or member. */
  roles: Role[];
  user: string;
};
export type CreateSpace = {
  /** Absent follows the inherited value; zero is immediate purge eligibility. */
  conversation_retention_seconds?: number | null;
  /** Required for a project. */
  description?: string | null;
  joining_mode?: TeamJoiningMode | null;
  kind: SpaceKind;
  /** Initial members, at least one owner, each a member of the parent.
    Creation grants the caller nothing unless listed. */
  members: CreateSpaceMember[];
  name: string;
  parent_id: string;
  visibility?: TeamVisibility | null;
};
export type TeamParameters = {
  description?: string | null;
  joining_mode?: TeamJoiningMode | null;
  name?: string | null;
  visibility?: TeamVisibility | null;
};
export type ConversationRetention = {
  /** NULL inherits; zero is immediate purge eligibility. */
  configured_seconds: number | null;
  effective_seconds: number;
  /** True when `inherited_seconds` is the parent team's configured value. */
  inherited_from_team: boolean;
  /** The parent team's configured value for a project, otherwise the policy. */
  inherited_seconds: number;
  organization_ceiling_seconds: number | null;
};
export type ReplaceConversationRetention = {
  /** NULL restores inheritance; zero requests immediate eligibility. */
  configured_seconds: number | null;
};
export type ActivityKind = "upload" | "processing" | "document_deletion" | "folder_deletion";
export type ActivityStatus = "pending" | "running" | "succeeded" | "failed" | "retrying" | "blocked";
export type DocumentActivity = {
  completed_at?: string | null;
  created_at: string;
  due_at?: string | null;
  error_code?: string | null;
  id: string;
  kind: ActivityKind;
  /** Current name where retained; deletion receipts deliberately retain only identity. */
  name?: string | null;
  profile?: string | null;
  retry_of?: string | null;
  stage?: string | null;
  status: ActivityStatus;
  target_id?: string | null;
};
export type DocumentActivityPage = {
  items: DocumentActivity[];
  next_cursor?: string | null;
  until: string;
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
export type TeamJoinLink = {
  expires_at: string;
  token: string;
};
export type RemovalBlocked = "forbidden" | "last_owner" | "child_roles";
export type SpaceMember = {
  removal_blocked?: RemovalBlocked | null;
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
export type FileMetadata = {
  mime: string;
  name: string;
  sha256: string;
  size: number;
};
export type MarketplaceFile = FileMetadata & {
  document_id: string;
};
export type ExportedCapability = {
  config: {
    [key: string]: any;
  };
  /** Frozen configuration files owned by the marketplace, indexed by the pod's asset key. */
  files: {
    [key: string]: MarketplaceFile;
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
export type HomeAgent = {
  agent_instance_id: string;
  description?: string | null;
  display_name: string;
  role: string;
  space_id: string;
  space_name: string;
  template_id: string;
};
export type FeaturedHomeAgent = {
  agent: HomeAgent;
  badge?: string | null;
  highlights: string[];
};
export type HomeLayout = "classic" | "advanced";
export type HomeShowcase = {
  ask_agent?: HomeAgent | null;
  featured: FeaturedHomeAgent[];
  layout: HomeLayout;
  recent_agents: HomeAgent[];
};
export type HomeAgentPage = {
  items: HomeAgent[];
  next_cursor: string | null;
};
export type AdminHomeAgent = {
  agent?: HomeAgent | null;
  agent_instance_id: string;
  badge?: string | null;
  highlights: string[];
};
export type OrganizationHomeSettings = {
  ask_agent?: AdminHomeAgent | null;
  featured: AdminHomeAgent[];
  layout: HomeLayout;
  updated_at?: string | null;
  updated_by?: string | null;
};
export type FeaturedAgentEntry = {
  agent_instance_id: string;
  badge?: string | null;
  highlights: string[];
};
export type SetOrganizationHomeRequest = {
  ask_agent_instance_id?: string | null;
  featured: FeaturedAgentEntry[];
  layout: HomeLayout;
};
export type RuntimePromptDefaults = {
  creation_assistant_prompt?: string | null;
  creation_assistant_prompt_revised_at?: string | null;
  platform_instructions?: string | null;
  platform_prompt?: string | null;
  runtime_id: string;
  source_unavailable: boolean;
};
export type CommonPromptSettings = {
  defaults: RuntimePromptDefaults[];
  text: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
};
export type SetCommonPrompt = {
  text: string;
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
  uses?: ModelUseOptions | null;
};
export type RuntimeModels = {
  default: ModelOfferKey | null;
  /** Union of permitted keys and retained recommendation/default/fallback references. */
  offers: RuntimeModelOffer[];
  options: ModelOptions;
  policy: OrganizationModelPolicy;
  /** Local preference for models that support reasoning. */
  reasoning_default_on: ModelOfferKey[];
  recommendation?: ModelOfferKey | null;
};
export type CreationAssistantSettings = {
  defaults: RuntimePromptDefaults[];
  missing_language_placeholder: boolean;
  model: ModelOfferKey | null;
  models: RuntimeModels;
  reasoning: boolean;
  text: string | null;
  text_updated_at?: string | null;
  text_updated_by?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
};
export type PatchCreationAssistant = {
  model?: ModelOfferKey | null;
  reasoning?: boolean | null;
  /** Omitted: preserve; null: runtime default; string: save verbatim and date the text. */
  text?: string | null;
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
  created_by_name?: string | null;
  description?: string | null;
  discoverable: boolean;
  display_name: string;
  logical_name: string;
  model_options?: ModelOptions | null;
  preparation_error: string | null;
  preparation_state: string;
  recommended_model?: ModelOfferKey | null;
  role: string;
  selected_capability_ids?: string[] | null;
  /** Canonical names of selected managed MCP offers, including withdrawn offers. */
  selected_capability_names?: {
    [key: string]: string;
  };
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
  updated_by_name?: string | null;
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
export type LibraryEntry = {
  file_id: string;
  label: string;
};
export type LibraryChange = {
  expected_file_ids: string[];
  files: LibraryEntry[];
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
  word_template?: LibraryChange | null;
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
  /** Omitted/null preserves the choice. Personal instances stay private. */
  discoverable?: boolean | null;
  /** Omitted/null metadata leaves the saved value unchanged.
    A new display name must remain unique within the space, ignoring case. */
  display_name?: string | null;
  model_options?: ModelOptions | null;
  powerpoint?: FileChange | null;
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
  word_template?: LibraryChange | null;
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
  | "offer_unknown"
  | "offer_forbidden"
  | "offer_unavailable"
  | "fallback_unavailable";
export type ModelPreparationError = {
  code: ModelPreparationErrorCode;
  message: string;
};
export type PreparationModelOffer = {
  candidate: boolean;
  diagnostics: ModelDiagnostic[];
  key: ModelOfferKey;
  metadata: ModelMetadata | null;
  permitted: boolean;
  reasoning_default_on: boolean;
  /** The available offer supports the reasoning control. */
  reasoning_enabled: boolean;
  selectable: boolean;
  /** Display name of the catalogue supplying this model. */
  source_name?: string | null;
  /** This selectable offer has no reported usage. Choosing it attempts the requested use. */
  unverified_usage?: boolean;
};
export type PreparationModels = {
  default: ModelOfferKey | null;
  fallback: ModelOfferKey | null;
  offers: PreparationModelOffer[];
  options: ModelOptions;
  recommendation: ModelOfferKey | null;
};
export type SkillAvailability = "available" | "disabled" | "unavailable";
export type PackageSummary = {
  argument_hint?: string | null;
  builtin: boolean;
  description: string;
  disable_model_invocation: boolean;
  name: string;
  user_invocable: boolean;
};
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
  /** Dictation routes to the organization's permitted transcription model for this space. */
  dictation_available: boolean;
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
  /** Saved tuning, including model offer selection and invocation options.
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
export type McpAuthentication =
  | {
      kind: "none";
    }
  | {
      credential_binding: string;
      kind: "bearer";
    }
  | {
      credential_binding: string;
      header: string;
      kind: "api_key";
    };
export type McpConfiguration = {
  allow_insecure_http?: boolean;
  authentication: McpAuthentication;
  url: string;
};
export type McpTool = {
  annotations?: any;
  description?: string | null;
  input_schema: any;
  name: string;
  output_schema?: any;
};
export type McpBinding =
  | {
      capability_id: string;
      configuration: McpConfiguration;
      connection_id: string;
      display_name: string;
      kind: "connection";
      revision: number;
      tools: McpTool[];
    }
  | {
      kind: "knowledge_flow_tabular";
      url: string;
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
  /** Readable corpus fixed at admission; document publication/lifecycle stays live. */
  authorized_space_ids: string[];
  conversation_id: string | null;
  inference?: InferenceAdmission | null;
  mcp_bindings: McpBinding[];
  models: RuntimeModels;
  /** Organization common text fixed at admission. Null uses the runtime default. */
  platform_prompt: string | null;
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
export type DictationTranscript = {
  text: string;
};
export type DictationUpload = {
  file: Blob;
};
export type AgentTemplateStatus = "available" | "dependency_unavailable";
export type AgentTemplateSummary = {
  /** Native and compatible managed offers, including configuration descriptors. */
  available_capabilities: {
    [key: string]: any;
  }[];
  capabilities: string[];
  category: string;
  /** Editable destination for a creation draft; absent when the template is ineligible. */
  creation_assistant_prompt_key?: string | null;
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
  supports_managed_mcp: boolean;
  tags: string[];
  team_instantiable: boolean;
  template_id: string;
};
export type AgentDraftResult = {
  capability_ids: string[];
  description?: string | null;
  name?: string | null;
  role?: string | null;
  system_prompt: string;
};
export type AgentDraftCapabilityCandidate = {
  description?: string;
  id: string;
  name: string;
};
export type AgentDraftRequest = {
  agent_name?: string | null;
  agent_role?: string | null;
  capabilities?: AgentDraftCapabilityCandidate[];
  description: string;
  language?: string;
};
export type AgentDraftAdmission = {
  capability_ids: string[];
  creation_prompt?: string | null;
  inference: InferenceAdmission;
  prompt_key: string;
  run_id: string;
  runtime_id: string;
  space: RuntimeSpace;
  subject_id: string;
  template_id: string;
  template_key: string;
};
export type SpaceApplication = ApplicationMetadata & {
  api_path?: string | null;
  capability_id: string;
  entry_permission: SpacePermission;
  id: string;
  logical_name: string;
  source_id: string;
  ui_path: string;
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
  origin: OfferOrigin;
  permitted_ids: string[];
  reachable: boolean;
  restricted: boolean;
  revision: number;
  runtime_id?: string | null;
  source_enabled: boolean;
  source_id: string;
};
export type ReplaceSpaceCapabilityPolicy = {
  expected_revision: number;
  permitted_ids: string[];
  restricted: boolean;
};
export type AvailableKnowledgeBaseDefinition = {
  credential_bindings: string[];
  definition: Definition;
  runtime_id: string;
};
export type CreateInstance = {
  config: any;
  credential_refs?: {
    [key: string]: string;
  };
  definition_id: string;
  interval_seconds?: number | null;
  name: string;
  paused?: boolean;
  profile: string;
};
export type McpToolChanges = {
  added: string[];
  modified: string[];
  removed: string[];
};
export type McpConnectionView = {
  /** Instances in the owning organization that select this connection. */
  affected_instance_count: number;
  available: boolean;
  capability_id: string;
  checked_at?: string | null;
  configuration: McpConfiguration;
  description: string;
  display_name: string;
  enabled: boolean;
  error_code?: string | null;
  id: string;
  last_success_at?: string | null;
  logical_name: string;
  observation_revision?: number | null;
  observation_state: string;
  observed_tools: McpTool[];
  published_revision?: number | null;
  published_tools: McpTool[];
  revision: number;
  space_id: string;
  tool_changes?: McpToolChanges | null;
};
export type CreateMcpConnection = {
  configuration: McpConfiguration;
  description: string;
  display_name: string;
  logical_name: string;
};
export type UpdateMcpConnection = {
  configuration: McpConfiguration;
  description: string;
  display_name: string;
  enabled: boolean;
  expected_revision: number;
};
export type McpPublication = {
  expected_checked_at: string;
  expected_revision: number;
};
export type McpRevision = {
  expected_revision: number;
};
export type McpCredentialReference = {
  available: boolean;
  credential_binding: string;
  url: string;
};
export type ReplaceSpaceModelPolicy = {
  default: ModelOfferKey | null;
  disabled: ModelOfferKey[];
  expected_revision: number;
  reasoning_default_on: ModelOfferKey[];
};
export type SpaceModelPolicy = {
  default: ModelOfferKey | null;
  disabled: ModelOfferKey[];
  /** Preference only; organization permission and reported aptitude still apply. */
  reasoning_default_on: ModelOfferKey[];
  revision: number;
};
export type SpaceModels = {
  inherited_default: ModelOfferKey | null;
  /** Public catalogue projection: no connection, credential or ancestor role. */
  models: RuntimeModels;
  parent_permitted: ModelOfferKey[];
  policy: SpaceModelPolicy;
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
  discoverable: boolean;
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
  /** Omitted/null keeps the choice. Personal resources cannot be discoverable. */
  discoverable?: boolean | null;
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
export type TraceConsentGrant = {
  cutoff: TraceHistoryBoundary;
  grant_id: string;
};
export type TraceConsentState = {
  available_cutoff?: TraceHistoryBoundary | null;
  consent?: TraceConsentGrant | null;
  consent_version?: string | null;
  history_unavailable?: boolean;
};
export type TraceConsentRequest = {
  exchange_id: string;
  expected_version?: string | null;
  last_rank: number;
};
export type TraceIncidentOffer = {
  capture_available: boolean;
  consent_cutoff?: TraceHistoryBoundary | null;
  consent_version?: string | null;
  cutoff: TraceHistoryBoundary;
  reported: boolean;
};
export type SpaceSkill = {
  discoverable: boolean;
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
  /** Omitted/null preserves the saved choice. Personal packages stay private. */
  discoverable?: boolean | null;
  expected_revision?: string | null;
  files: BTreeMap;
};
export type WikiAvailability = {
  /** Human publication authority, independent of the agent writing mode. */
  can_publish: boolean;
  enabled: boolean;
};
export type WikiFreshness = "unspecified" | "fresh" | "stale" | "malformed";
export type WikiSource = {
  author?: string | null;
  id?: string | null;
  last_modified?: string | null;
  resource: string;
  title?: string | null;
};
export type WikiTrust = "unverified";
export type WikiVerification = {
  at: string;
  by: string;
};
export type WikiFormat = {
  aliases: string[];
  body_md: string;
  description?: string | null;
  freshness: WikiFreshness;
  /** Exact source prefix, including delimiters and line endings. Never rebuild YAML from fields. */
  frontmatter_prefix: string;
  page_type: string;
  read_when?: string | null;
  sources: WikiSource[];
  stale_after?: string | null;
  tags: string[];
  trust: WikiTrust;
  /** Publication is not content confirmation. Empty until confirmations exist. */
  verified: WikiVerification[];
};
export type WikiPropertiesPatch = {
  description?: string | null;
  page_type?: string | null;
  tags?: string[] | null;
};
export type PrepareWikiDocumentRequest = {
  content_md: string;
  properties?: WikiPropertiesPatch | null;
};
export type WikiPageSummary = {
  agent_instance_id?: string | null;
  /** The current revision's agent name, as seen in the source conversation. */
  agent_name?: string | null;
  /** Display name of author_user_id, resolved after releasing the transaction. */
  author_name?: string | null;
  /** Author of the current revision, distinct from its publisher or last metadata editor. */
  author_user_id?: string | null;
  kind: string;
  /** A file entry's media type and size; null for pages. */
  mime?: string | null;
  page_id: string;
  parent_page_id?: string | null;
  position: number;
  size?: number | null;
  slug: string;
  title: string;
  updated_at?: string | null;
  updated_by: string;
  updated_by_name?: string | null;
};
export type WikiPageTree = {
  pages: WikiPageSummary[];
};
export type WikiPageDetail = {
  content_md: string;
  format?: WikiFormat | null;
  /** Why stored ordinary text has no format view (`path: message`); `content_md`
    stays the readable source and the next write must conform. */
  format_error?: string | null;
  /** A file entry's bytes are read through `/wiki/revisions/{revision_id}/content`,
    its PDF preview, when one was copied with it, through `/preview`. */
  has_preview: boolean;
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
  current_format?: WikiFormat | null;
  current_revision_id?: string | null;
  detail: string;
};
export type UpdateWikiContentRequest = {
  base_revision_id?: string | null;
  content_md: string;
};
export type WikiRevisionSummary = {
  agent_instance_id?: string | null;
  agent_name?: string | null;
  author_user_id: string;
  created_at: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  revision_id: string;
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
  agent_name?: string | null;
  author_user_id: string;
  base_revision_id?: string | null;
  content_md: string;
  created_at: string;
  current_content_md: string;
  has_preview: boolean;
  /** `page` (new page), `edit` (page text) or `file` (a new file, or a new version
    of the file named by `slug`). */
  kind: string;
  /** The frozen copy of a file proposal; null for pages. */
  mime?: string | null;
  /** The entry changed, or a sibling took the name, since the proposal: not acceptable. */
  outdated: boolean;
  parent_slug?: string | null;
  proposal_id: string;
  size?: number | null;
  slug?: string | null;
  /** `draft` (awaits its author in the conversation), `pending` (awaits an editor)
    or `published`. A refused or withdrawn proposal no longer exists. */
  status: string;
  title: string;
};
export type WikiProposalList = {
  authors: {
    [key: string]: string;
  };
  next_cursor?: string | null;
  proposals: WikiProposal[];
};
export type ProposeWikiEditRequest = {
  base_revision_id: string;
  content_md: string;
  slug: string;
};
export type WorkspaceWikiSource = {
  path: string;
  /** SHA-256 of the selected bytes, checked against the authenticated source. */
  sha256: string;
};
export type WritableWikiFormat = "md" | "docx";
export type WritableWikiSource = {
  document_id: string;
  format?: WritableWikiFormat | null;
  /** SHA-256 of the saved Markdown at preparation (UTF-8), before export. */
  sha256: string;
};
export type ProposeWikiFileRequest = {
  base_revision_id?: string | null;
  /** Create or use a page with this name under parent_slug, on confirmation.
    Editors only. The page and the first successful file appear together. */
  destination_title?: string | null;
  /** Exactly one source: catalogue document, editable document, or workspace file. */
  document_id?: string | null;
  /** The content the person read; without it, the content current at the request. */
  expected_content_id?: string | null;
  parent_slug?: string | null;
  slug?: string | null;
  title?: string | null;
  workspace_file?: WorkspaceWikiSource | null;
  writable_document?: WritableWikiSource | null;
};
export type ProposeWikiPageRequest = {
  content_md: string;
  parent_slug?: string | null;
  title: string;
};
export type WikiSearchHit = {
  description?: string | null;
  /** Contextual excerpt, at most 300 characters; PostgreSQL may strip source HTML tags.
    Display as text, never HTML or Markdown. */
  excerpt: string;
  page_id: string;
  page_type: string;
  slug: string;
  title: string;
};
export type WikiSearchResult = {
  hits: WikiSearchHit[];
  /** Candidate position; continue only with this value. No snapshot across writes. */
  next_offset?: number | null;
  /** The 200 candidate ceiling was reached; refine the query. */
  truncated: boolean;
};
export type LibraryFile = {
  file: PowerPointFile;
  label: string;
  preparation_error?: string | null;
  preparation_state: string;
};
export type Library = {
  activation_ready: boolean;
  files: LibraryFile[];
  own_file_ids: string[];
  source: PowerPointSource;
};
export type TeamJoinPreview = {
  team_id: string;
  team_name: string;
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
  useGetConversationTraceHistoryAccessQuery,
  useLazyGetConversationTraceHistoryAccessQuery,
  useGetConversationTraceHttpAccessQuery,
  useLazyGetConversationTraceHttpAccessQuery,
  useGetConversationTraceModelAccessQuery,
  useLazyGetConversationTraceModelAccessQuery,
  useGetConversationTraceSseAccessQuery,
  useLazyGetConversationTraceSseAccessQuery,
  useGetConversationTraceSseHeaderAccessQuery,
  useLazyGetConversationTraceSseHeaderAccessQuery,
  useGetConversationTraceToolAccessQuery,
  useLazyGetConversationTraceToolAccessQuery,
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
  useQueryAnalyticsQuery,
  useLazyQueryAnalyticsQuery,
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
  useCapabilityPreparationTextAdmissionQuery,
  useLazyCapabilityPreparationTextAdmissionQuery,
  useDeletionStatusQuery,
  useLazyDeletionStatusQuery,
  useCleanupQuery,
  useLazyCleanupQuery,
  useCleanedMutation,
  useRetrievalWorkQuery,
  useLazyRetrievalWorkQuery,
  useConfirmRetrievableMutation,
  useRetiredCorporaQuery,
  useLazyRetiredCorporaQuery,
  useRetiredCorpusProgressMutation,
  useVectorReindexProgressMutation,
  useVectorReindexWorkMutation,
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
  useAdmitTraceTurnMutation,
  useClaimTraceStorageCleanupMutation,
  useAcknowledgeTraceStorageCleanupMutation,
  useGetTraceOwnerHiddenSessionsMutation,
  useReconcileTraceAdmissionMutation,
  useFinalizeTraceTurnMutation,
  useSettleIncrementalTraceStorageMutation,
  useReserveTraceStorageMutation,
  usePublishMutation,
  useContextQuery,
  useLazyContextQuery,
  useClaimKnowledgeBaseRunMutation,
  useCompleteMutation,
  useCatalogueQuery,
  useLazyCatalogueQuery,
  useUploadKnowledgeBaseDocumentMutation,
  useRetractMutation,
  useOutcomeQuery,
  useLazyOutcomeQuery,
  useBindingQuery,
  useLazyBindingQuery,
  useUpdateKnowledgeBaseMutation,
  useKnowledgeBaseRunsQuery,
  useLazyKnowledgeBaseRunsQuery,
  useStartKnowledgeBaseRunMutation,
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
  useOrganizationAgentsQuery,
  useLazyOrganizationAgentsQuery,
  useSetOrganizationAgentDefaultMutation,
  useOrganizationApplicationsQuery,
  useLazyOrganizationApplicationsQuery,
  useCreateApplicationMutation,
  useUpdateApplicationMutation,
  useOrganizationCapabilitiesQuery,
  useLazyOrganizationCapabilitiesQuery,
  useRefreshOrganizationCapabilitiesMutation,
  useSetOrganizationCapabilityDefaultMutation,
  useOrganizationCapabilityRevokeImpactQuery,
  useLazyOrganizationCapabilityRevokeImpactQuery,
  useListConversationTracesQuery,
  useLazyListConversationTracesQuery,
  useFlushConversationTraceCapturesMutation,
  useDeleteConversationTracesMutation,
  useExportConversationTracesMutation,
  useGetConversationTraceSettingsQuery,
  useLazyGetConversationTraceSettingsQuery,
  useSetConversationTraceSettingsMutation,
  useListConversationTraceTeamsQuery,
  useLazyListConversationTraceTeamsQuery,
  useGetConversationTraceQuery,
  useLazyGetConversationTraceQuery,
  useGetConversationTraceHistoryQuery,
  useLazyGetConversationTraceHistoryQuery,
  useListConversationTraceHttpAttemptsQuery,
  useLazyListConversationTraceHttpAttemptsQuery,
  useGetConversationTraceHttpEvidenceQuery,
  useLazyGetConversationTraceHttpEvidenceQuery,
  useListConversationTraceModelCallsQuery,
  useLazyListConversationTraceModelCallsQuery,
  useGetConversationTraceModelEvidenceQuery,
  useLazyGetConversationTraceModelEvidenceQuery,
  useListConversationTraceSpansQuery,
  useLazyListConversationTraceSpansQuery,
  useGetConversationTraceSseFramePageQuery,
  useLazyGetConversationTraceSseFramePageQuery,
  useGetConversationTraceSseHeadersQuery,
  useLazyGetConversationTraceSseHeadersQuery,
  useListConversationTraceSseSegmentsQuery,
  useLazyListConversationTraceSseSegmentsQuery,
  useGetConversationTraceSseFrameQuery,
  useLazyGetConversationTraceSseFrameQuery,
  useListConversationTraceToolCallsQuery,
  useLazyListConversationTraceToolCallsQuery,
  useGetConversationTraceToolEvidenceQuery,
  useLazyGetConversationTraceToolEvidenceQuery,
  useOrganizationKnowledgeBaseServicesQuery,
  useLazyOrganizationKnowledgeBaseServicesQuery,
  useRegisterKnowledgeBaseServiceMutation,
  useUpdateKnowledgeBaseServiceMutation,
  useOrganizationModelPolicyQuery,
  useLazyOrganizationModelPolicyQuery,
  useReplaceOrganizationModelPolicyMutation,
  useCreateModelCatalogMutation,
  useUpdateModelCatalogMutation,
  useDeleteModelCatalogMutation,
  useModelAccessMatrixQuery,
  useLazyModelAccessMatrixQuery,
  useSetModelAccessMutation,
  useReplaceModelComplementsMutation,
  useRefreshModelSourceMutation,
  useOrganizationModelsQuery,
  useLazyOrganizationModelsQuery,
  useOrganizationResourcesQuery,
  useLazyOrganizationResourcesQuery,
  useOrganizationSupervisionQuery,
  useLazyOrganizationSupervisionQuery,
  useTeamSupervisionQuery,
  useLazyTeamSupervisionQuery,
  useOrganizationTeamsQuery,
  useLazyOrganizationTeamsQuery,
  useVectorReindexStatusQuery,
  useLazyVectorReindexStatusQuery,
  useStartVectorReindexMutation,
  usePowerpointUploadReceiptQuery,
  useLazyPowerpointUploadReceiptQuery,
  useCreateSpaceMutation,
  useDeleteSpaceMutation,
  useUpdateTeamParametersMutation,
  useGetTeamAvatarQuery,
  useLazyGetTeamAvatarQuery,
  usePutTeamAvatarMutation,
  useDeleteTeamAvatarMutation,
  useTeamConversationRetentionQuery,
  useLazyTeamConversationRetentionQuery,
  useReplaceTeamConversationRetentionMutation,
  useProjectDeletionStatusQuery,
  useLazyProjectDeletionStatusQuery,
  useTeamMetadataQuery,
  useLazyTeamMetadataQuery,
  useTeamDocumentActivityQuery,
  useLazyTeamDocumentActivityQuery,
  useReceiptsQuery,
  useLazyReceiptsQuery,
  useEntriesQuery,
  useLazyEntriesQuery,
  useJoinTeamMutation,
  useTeamJoinLinkQuery,
  useLazyTeamJoinLinkQuery,
  useCreateTeamJoinLinkMutation,
  useRevokeTeamJoinLinkMutation,
  useSpaceMemberCandidatesQuery,
  useLazySpaceMemberCandidatesQuery,
  useSpaceMembersQuery,
  useLazySpaceMembersQuery,
  useRemoveSpaceMemberMutation,
  useTeamProjectsQuery,
  useLazyTeamProjectsQuery,
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
  useOrganizationHomeQuery,
  useLazyOrganizationHomeQuery,
  useOrganizationHomeCandidatesQuery,
  useLazyOrganizationHomeCandidatesQuery,
  useOrganizationHomeSettingsQuery,
  useLazyOrganizationHomeSettingsQuery,
  useSetOrganizationHomeMutation,
  useGetCommonPromptSettingsQuery,
  useLazyGetCommonPromptSettingsQuery,
  usePutCommonPromptSettingsMutation,
  useGetCreationAssistantSettingsQuery,
  useLazyGetCreationAssistantSettingsQuery,
  useResetCreationAssistantPromptMutation,
  usePatchCreationAssistantSettingsMutation,
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
  useTranscribeAgentAudioMutation,
  useSpaceAgentTemplatesQuery,
  useLazySpaceAgentTemplatesQuery,
  useDraftAgentMutation,
  useAdmitAgentDraftMutation,
  useSpaceApplicationsQuery,
  useLazySpaceApplicationsQuery,
  useSpaceCapabilityPoliciesQuery,
  useLazySpaceCapabilityPoliciesQuery,
  useReplaceSpaceCapabilityPolicyMutation,
  useAvailableKnowledgeBaseDefinitionsQuery,
  useLazyAvailableKnowledgeBaseDefinitionsQuery,
  useSpaceKnowledgeBasesQuery,
  useLazySpaceKnowledgeBasesQuery,
  useCreateKnowledgeBaseMutation,
  useMarketplaceInstallationQuery,
  useLazyMarketplaceInstallationQuery,
  useMcpConnectionsQuery,
  useLazyMcpConnectionsQuery,
  useCreateMcpConnectionMutation,
  useUpdateMcpConnectionMutation,
  usePublishMcpConnectionMutation,
  useTestMcpConnectionMutation,
  useMcpCredentialsQuery,
  useLazyMcpCredentialsQuery,
  useReplaceSpaceModelPolicyMutation,
  useSpaceModelsQuery,
  useLazySpaceModelsQuery,
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
  useGetTraceConsentQuery,
  useLazyGetTraceConsentQuery,
  useSetTraceConsentMutation,
  useRevokeTraceConsentMutation,
  useGetTraceIncidentOfferQuery,
  useLazyGetTraceIncidentOfferQuery,
  useShareTraceIncidentMutation,
  useListSkillsQuery,
  useLazyListSkillsQuery,
  useCreateSkillMutation,
  useSkillScopeQuery,
  useLazySkillScopeQuery,
  usePreviewSkillQuery,
  useLazyPreviewSkillQuery,
  useGetSkillQuery,
  useLazyGetSkillQuery,
  usePutSkillMutation,
  useDeleteSkillMutation,
  useGetUserAvatarQuery,
  useLazyGetUserAvatarQuery,
  useWikiAvailabilityQuery,
  useLazyWikiAvailabilityQuery,
  usePrepareWikiDocumentMutation,
  useWikiPagesQuery,
  useLazyWikiPagesQuery,
  useCreateWikiPageMutation,
  useWikiPageQuery,
  useLazyWikiPageQuery,
  useDeleteWikiPageMutation,
  usePatchWikiPageMutation,
  useWriteWikiPageMutation,
  useWikiRevisionsQuery,
  useLazyWikiRevisionsQuery,
  useRestoreWikiRevisionMutation,
  useWikiProposalsQuery,
  useLazyWikiProposalsQuery,
  useProposeWikiEditMutation,
  useProposeWikiFileMutation,
  useProposeWikiPageMutation,
  useWikiProposalQuery,
  useLazyWikiProposalQuery,
  useWithdrawWikiProposalMutation,
  useAcceptWikiProposalMutation,
  useSubmitWikiProposalMutation,
  useWikiRevisionFileQuery,
  useLazyWikiRevisionFileQuery,
  useWikiRulesQuery,
  useLazyWikiRulesQuery,
  useWriteWikiRulesMutation,
  useWikiSearchQuery,
  useLazyWikiSearchQuery,
  useResolveWordTemplateLibraryQuery,
  useLazyResolveWordTemplateLibraryQuery,
  useSaveWordTemplateLibraryMutation,
  useUploadWordTemplateMutation,
  usePreviewTeamJoinLinkQuery,
  useLazyPreviewTeamJoinLinkQuery,
  useRedeemTeamJoinLinkMutation,
  useGetMyAvatarQuery,
  useLazyGetMyAvatarQuery,
  usePutMyAvatarMutation,
  useDeleteMyAvatarMutation,
  useGetMyPreferencesQuery,
  useLazyGetMyPreferencesQuery,
  usePatchMyPreferencesMutation,
  useListPlatformRolesQuery,
  useLazyListPlatformRolesQuery,
  useGrantPlatformRoleMutation,
  useRevokePlatformRoleMutation,
} = injectedRtkApi;
