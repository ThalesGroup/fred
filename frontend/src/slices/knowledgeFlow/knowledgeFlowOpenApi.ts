import { knowledgeFlowApi as api } from "./knowledgeFlowApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    healthzKnowledgeFlowV1HealthzGet: build.query<
      HealthzKnowledgeFlowV1HealthzGetApiResponse,
      HealthzKnowledgeFlowV1HealthzGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/healthz` }),
    }),
    readyKnowledgeFlowV1ReadyGet: build.query<
      ReadyKnowledgeFlowV1ReadyGetApiResponse,
      ReadyKnowledgeFlowV1ReadyGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/ready` }),
    }),
    searchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPost: build.mutation<
      SearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostApiResponse,
      SearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/documents/metadata/search`,
        method: "POST",
        body: queryArg.filters,
      }),
    }),
    getDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGet: build.query<
      GetDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGetApiResponse,
      GetDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/documents/metadata/${queryArg.documentUid}` }),
    }),
    getProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGet: build.query<
      GetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetApiResponse,
      GetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/documents/processing/graph` }),
    }),
    getProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGet: build.query<
      GetProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGetApiResponse,
      GetProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/documents/processing/summary` }),
    }),
    updateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPut: build.mutation<
      UpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutApiResponse,
      UpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/document/metadata/${queryArg.documentUid}`,
        method: "PUT",
        params: {
          retrievable: queryArg.retrievable,
        },
      }),
    }),
    browseDocumentsKnowledgeFlowV1DocumentsBrowsePost: build.mutation<
      BrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostApiResponse,
      BrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/documents/browse`,
        method: "POST",
        body: queryArg.browseDocumentsRequest,
      }),
    }),
    browseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePost: build.mutation<
      BrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostApiResponse,
      BrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/documents/metadata/browse`,
        method: "POST",
        body: queryArg.browseDocumentsByTagRequest,
      }),
    }),
    documentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGet: build.query<
      DocumentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGetApiResponse,
      DocumentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/documents/${queryArg.documentUid}/vectors` }),
    }),
    documentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGet: build.query<
      DocumentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGetApiResponse,
      DocumentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/documents/${queryArg.documentUid}/chunks` }),
    }),
    auditDocumentsKnowledgeFlowV1DocumentsAuditGet: build.query<
      AuditDocumentsKnowledgeFlowV1DocumentsAuditGetApiResponse,
      AuditDocumentsKnowledgeFlowV1DocumentsAuditGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/documents/audit` }),
    }),
    fixDocumentsKnowledgeFlowV1DocumentsAuditFixPost: build.mutation<
      FixDocumentsKnowledgeFlowV1DocumentsAuditFixPostApiResponse,
      FixDocumentsKnowledgeFlowV1DocumentsAuditFixPostApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/documents/audit/fix`, method: "POST" }),
    }),
    getChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdGet: build.query<
      GetChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdGetApiResponse,
      GetChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/documents/${queryArg.documentUid}/chunks/${queryArg.chunkId}` }),
    }),
    deleteChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdDelete: build.mutation<
      DeleteChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdDeleteApiResponse,
      DeleteChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/documents/${queryArg.documentUid}/chunks/${queryArg.chunkId}`,
        method: "DELETE",
      }),
    }),
    trainUmapKnowledgeFlowV1ModelsUmapTagIdTrainPost: build.mutation<
      TrainUmapKnowledgeFlowV1ModelsUmapTagIdTrainPostApiResponse,
      TrainUmapKnowledgeFlowV1ModelsUmapTagIdTrainPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/models/umap/${queryArg.tagId}/train`, method: "POST" }),
    }),
    modelStatusKnowledgeFlowV1ModelsUmapTagUidGet: build.query<
      ModelStatusKnowledgeFlowV1ModelsUmapTagUidGetApiResponse,
      ModelStatusKnowledgeFlowV1ModelsUmapTagUidGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/models/umap/${queryArg.tagUid}` }),
    }),
    projectKnowledgeFlowV1ModelsUmapRefTagUidProjectPost: build.mutation<
      ProjectKnowledgeFlowV1ModelsUmapRefTagUidProjectPostApiResponse,
      ProjectKnowledgeFlowV1ModelsUmapRefTagUidProjectPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/models/umap/${queryArg.refTagUid}/project`,
        method: "POST",
        body: queryArg.projectRequest,
      }),
    }),
    deleteModelKnowledgeFlowV1ModelsUmapRefTagUidDelete: build.mutation<
      DeleteModelKnowledgeFlowV1ModelsUmapRefTagUidDeleteApiResponse,
      DeleteModelKnowledgeFlowV1ModelsUmapRefTagUidDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/models/umap/${queryArg.refTagUid}`, method: "DELETE" }),
    }),
    projectTextKnowledgeFlowV1ModelsUmapRefTagUidProjectTextPost: build.mutation<
      ProjectTextKnowledgeFlowV1ModelsUmapRefTagUidProjectTextPostApiResponse,
      ProjectTextKnowledgeFlowV1ModelsUmapRefTagUidProjectTextPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/models/umap/${queryArg.refTagUid}/project-text`,
        method: "POST",
        body: queryArg.projectTextRequest,
      }),
    }),
    getMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGet: build.query<
      GetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetApiResponse,
      GetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/markdown/${queryArg.documentUid}` }),
    }),
    downloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGet: build.query<
      DownloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGetApiResponse,
      DownloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/markdown/${queryArg.documentUid}/media/${queryArg.mediaId}` }),
    }),
    downloadDocumentKnowledgeFlowV1RawContentDocumentUidGet: build.query<
      DownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetApiResponse,
      DownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/raw_content/${queryArg.documentUid}` }),
    }),
    streamDocumentKnowledgeFlowV1RawContentStreamDocumentUidGet: build.query<
      StreamDocumentKnowledgeFlowV1RawContentStreamDocumentUidGetApiResponse,
      StreamDocumentKnowledgeFlowV1RawContentStreamDocumentUidGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/raw_content/stream/${queryArg.documentUid}`,
        headers: {
          Range: queryArg.range,
        },
      }),
    }),
    uploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPost: build.mutation<
      UploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPostApiResponse,
      UploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/agent-assets/${queryArg.agent}/upload`,
        method: "POST",
        body: queryArg.bodyUploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPost,
      }),
    }),
    listAgentAssetsKnowledgeFlowV1AgentAssetsAgentGet: build.query<
      ListAgentAssetsKnowledgeFlowV1AgentAssetsAgentGetApiResponse,
      ListAgentAssetsKnowledgeFlowV1AgentAssetsAgentGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/agent-assets/${queryArg.agent}` }),
    }),
    getAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyGet: build.query<
      GetAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyGetApiResponse,
      GetAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/agent-assets/${queryArg.agent}/${queryArg.key}`,
        headers: {
          Range: queryArg.range,
        },
      }),
    }),
    deleteAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyDelete: build.mutation<
      DeleteAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteApiResponse,
      DeleteAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/agent-assets/${queryArg.agent}/${queryArg.key}`,
        method: "DELETE",
      }),
    }),
    uploadUserAssetKnowledgeFlowV1UserAssetsUploadPost: build.mutation<
      UploadUserAssetKnowledgeFlowV1UserAssetsUploadPostApiResponse,
      UploadUserAssetKnowledgeFlowV1UserAssetsUploadPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/user-assets/upload`,
        method: "POST",
        body: queryArg.bodyUploadUserAssetKnowledgeFlowV1UserAssetsUploadPost,
      }),
    }),
    listUserAssetsKnowledgeFlowV1UserAssetsGet: build.query<
      ListUserAssetsKnowledgeFlowV1UserAssetsGetApiResponse,
      ListUserAssetsKnowledgeFlowV1UserAssetsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/user-assets`,
        headers: {
          "X-Asset-User-ID": queryArg["X-Asset-User-ID"],
        },
      }),
    }),
    getUserAssetKnowledgeFlowV1UserAssetsKeyGet: build.query<
      GetUserAssetKnowledgeFlowV1UserAssetsKeyGetApiResponse,
      GetUserAssetKnowledgeFlowV1UserAssetsKeyGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/user-assets/${queryArg.key}`,
        headers: {
          Range: queryArg.range,
          "X-Asset-User-ID": queryArg["X-Asset-User-ID"],
        },
      }),
    }),
    deleteUserAssetKnowledgeFlowV1UserAssetsKeyDelete: build.mutation<
      DeleteUserAssetKnowledgeFlowV1UserAssetsKeyDeleteApiResponse,
      DeleteUserAssetKnowledgeFlowV1UserAssetsKeyDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/user-assets/${queryArg.key}`,
        method: "DELETE",
        headers: {
          "X-Asset-User-ID": queryArg["X-Asset-User-ID"],
        },
      }),
    }),
    uploadUserFileKnowledgeFlowV1StorageUserUploadPost: build.mutation<
      UploadUserFileKnowledgeFlowV1StorageUserUploadPostApiResponse,
      UploadUserFileKnowledgeFlowV1StorageUserUploadPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/user/upload`,
        method: "POST",
        body: queryArg.bodyUploadUserFileKnowledgeFlowV1StorageUserUploadPost,
      }),
    }),
    listUserFilesKnowledgeFlowV1StorageUserGet: build.query<
      ListUserFilesKnowledgeFlowV1StorageUserGetApiResponse,
      ListUserFilesKnowledgeFlowV1StorageUserGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/user`,
        params: {
          prefix: queryArg.prefix,
        },
      }),
    }),
    downloadUserFileKnowledgeFlowV1StorageUserKeyGet: build.query<
      DownloadUserFileKnowledgeFlowV1StorageUserKeyGetApiResponse,
      DownloadUserFileKnowledgeFlowV1StorageUserKeyGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/storage/user/${queryArg.key}` }),
    }),
    deleteUserFileKnowledgeFlowV1StorageUserKeyDelete: build.mutation<
      DeleteUserFileKnowledgeFlowV1StorageUserKeyDeleteApiResponse,
      DeleteUserFileKnowledgeFlowV1StorageUserKeyDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/storage/user/${queryArg.key}`, method: "DELETE" }),
    }),
    uploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPost: build.mutation<
      UploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPostApiResponse,
      UploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/agent-config/${queryArg.agentId}/upload`,
        method: "POST",
        body: queryArg.bodyUploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPost,
      }),
    }),
    listAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGet: build.query<
      ListAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGetApiResponse,
      ListAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/agent-config/${queryArg.agentId}`,
        params: {
          prefix: queryArg.prefix,
        },
      }),
    }),
    downloadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyGet: build.query<
      DownloadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyGetApiResponse,
      DownloadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/storage/agent-config/${queryArg.agentId}/${queryArg.key}` }),
    }),
    deleteAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyDelete: build.mutation<
      DeleteAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyDeleteApiResponse,
      DeleteAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/agent-config/${queryArg.agentId}/${queryArg.key}`,
        method: "DELETE",
      }),
    }),
    uploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPost: build.mutation<
      UploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPostApiResponse,
      UploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/agent-user/${queryArg.agentId}/${queryArg.targetUserId}/upload`,
        method: "POST",
        body: queryArg.bodyUploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPost,
      }),
    }),
    listAgentUserFilesKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdGet: build.query<
      ListAgentUserFilesKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdGetApiResponse,
      ListAgentUserFilesKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/agent-user/${queryArg.agentId}/${queryArg.targetUserId}`,
        params: {
          prefix: queryArg.prefix,
        },
      }),
    }),
    downloadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyGet: build.query<
      DownloadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyGetApiResponse,
      DownloadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/agent-user/${queryArg.agentId}/${queryArg.targetUserId}/${queryArg.key}`,
      }),
    }),
    deleteAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyDelete: build.mutation<
      DeleteAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyDeleteApiResponse,
      DeleteAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/storage/agent-user/${queryArg.agentId}/${queryArg.targetUserId}/${queryArg.key}`,
        method: "DELETE",
      }),
    }),
    listAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGet: build.query<
      ListAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGetApiResponse,
      ListAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/processing/pipelines/available-processors` }),
    }),
    registerProcessingPipelineKnowledgeFlowV1ProcessingPipelinesPost: build.mutation<
      RegisterProcessingPipelineKnowledgeFlowV1ProcessingPipelinesPostApiResponse,
      RegisterProcessingPipelineKnowledgeFlowV1ProcessingPipelinesPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/processing/pipelines`,
        method: "POST",
        body: queryArg.processingPipelineDefinition,
      }),
    }),
    assignPipelineToLibraryKnowledgeFlowV1ProcessingPipelinesAssignLibraryPost: build.mutation<
      AssignPipelineToLibraryKnowledgeFlowV1ProcessingPipelinesAssignLibraryPostApiResponse,
      AssignPipelineToLibraryKnowledgeFlowV1ProcessingPipelinesAssignLibraryPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/processing/pipelines/assign-library`,
        method: "POST",
        body: queryArg.pipelineAssignment,
      }),
    }),
    getLibraryPipelineKnowledgeFlowV1ProcessingPipelinesLibraryLibraryTagIdGet: build.query<
      GetLibraryPipelineKnowledgeFlowV1ProcessingPipelinesLibraryLibraryTagIdGetApiResponse,
      GetLibraryPipelineKnowledgeFlowV1ProcessingPipelinesLibraryLibraryTagIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/processing/pipelines/library/${queryArg.libraryTagId}` }),
    }),
    uploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPost: build.mutation<
      UploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPostApiResponse,
      UploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/upload-documents`,
        method: "POST",
        body: queryArg.bodyUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPost,
      }),
    }),
    processDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPost: build.mutation<
      ProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPostApiResponse,
      ProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/upload-process-documents`,
        method: "POST",
        body: queryArg.bodyProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPost,
      }),
    }),
    getUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGet: build.query<
      GetUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGetApiResponse,
      GetUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/upload-process-documents/progress`,
        params: {
          workflow_id: queryArg.workflowId,
        },
      }),
    }),
    fastMarkdownKnowledgeFlowV1FastTextPost: build.mutation<
      FastMarkdownKnowledgeFlowV1FastTextPostApiResponse,
      FastMarkdownKnowledgeFlowV1FastTextPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/fast/text`,
        method: "POST",
        body: queryArg.bodyFastMarkdownKnowledgeFlowV1FastTextPost,
        params: {
          format: queryArg.format,
        },
      }),
    }),
    fastIngestKnowledgeFlowV1FastIngestPost: build.mutation<
      FastIngestKnowledgeFlowV1FastIngestPostApiResponse,
      FastIngestKnowledgeFlowV1FastIngestPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/fast/ingest`,
        method: "POST",
        body: queryArg.bodyFastIngestKnowledgeFlowV1FastIngestPost,
      }),
    }),
    deleteFastIngestKnowledgeFlowV1FastIngestDocumentUidDelete: build.mutation<
      DeleteFastIngestKnowledgeFlowV1FastIngestDocumentUidDeleteApiResponse,
      DeleteFastIngestKnowledgeFlowV1FastIngestDocumentUidDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/fast/ingest/${queryArg.documentUid}`,
        method: "DELETE",
        params: {
          session_id: queryArg.sessionId,
        },
      }),
    }),
    listAllTagsKnowledgeFlowV1TagsGet: build.query<
      ListAllTagsKnowledgeFlowV1TagsGetApiResponse,
      ListAllTagsKnowledgeFlowV1TagsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tags`,
        params: {
          type: queryArg["type"],
          path_prefix: queryArg.pathPrefix,
          limit: queryArg.limit,
          offset: queryArg.offset,
          owner_filter: queryArg.ownerFilter,
          team_id: queryArg.teamId,
        },
      }),
    }),
    createTagKnowledgeFlowV1TagsPost: build.mutation<
      CreateTagKnowledgeFlowV1TagsPostApiResponse,
      CreateTagKnowledgeFlowV1TagsPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tags`, method: "POST", body: queryArg.tagCreate }),
    }),
    getTagKnowledgeFlowV1TagsTagIdGet: build.query<
      GetTagKnowledgeFlowV1TagsTagIdGetApiResponse,
      GetTagKnowledgeFlowV1TagsTagIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tags/${queryArg.tagId}` }),
    }),
    updateTagKnowledgeFlowV1TagsTagIdPut: build.mutation<
      UpdateTagKnowledgeFlowV1TagsTagIdPutApiResponse,
      UpdateTagKnowledgeFlowV1TagsTagIdPutApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tags/${queryArg.tagId}`,
        method: "PUT",
        body: queryArg.tagUpdate,
      }),
    }),
    deleteTagKnowledgeFlowV1TagsTagIdDelete: build.mutation<
      DeleteTagKnowledgeFlowV1TagsTagIdDeleteApiResponse,
      DeleteTagKnowledgeFlowV1TagsTagIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tags/${queryArg.tagId}`, method: "DELETE" }),
    }),
    listTagMembersKnowledgeFlowV1TagsTagIdMembersGet: build.query<
      ListTagMembersKnowledgeFlowV1TagsTagIdMembersGetApiResponse,
      ListTagMembersKnowledgeFlowV1TagsTagIdMembersGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tags/${queryArg.tagId}/members` }),
    }),
    shareTagKnowledgeFlowV1TagsTagIdSharePost: build.mutation<
      ShareTagKnowledgeFlowV1TagsTagIdSharePostApiResponse,
      ShareTagKnowledgeFlowV1TagsTagIdSharePostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tags/${queryArg.tagId}/share`,
        method: "POST",
        body: queryArg.tagShareRequest,
      }),
    }),
    unshareTagKnowledgeFlowV1TagsTagIdShareTargetIdDelete: build.mutation<
      UnshareTagKnowledgeFlowV1TagsTagIdShareTargetIdDeleteApiResponse,
      UnshareTagKnowledgeFlowV1TagsTagIdShareTargetIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tags/${queryArg.tagId}/share/${queryArg.targetId}`,
        method: "DELETE",
        params: {
          target_type: queryArg.targetType,
        },
      }),
    }),
    backfillRebacRelationsKnowledgeFlowV1TagsRebacBackfillPost: build.mutation<
      BackfillRebacRelationsKnowledgeFlowV1TagsRebacBackfillPostApiResponse,
      BackfillRebacRelationsKnowledgeFlowV1TagsRebacBackfillPostApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/tags/rebac/backfill`, method: "POST" }),
    }),
    echoSchemaKnowledgeFlowV1SchemasEchoPost: build.mutation<
      EchoSchemaKnowledgeFlowV1SchemasEchoPostApiResponse,
      EchoSchemaKnowledgeFlowV1SchemasEchoPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/schemas/echo`, method: "POST", body: queryArg.echoEnvelope }),
    }),
    searchDocumentsUsingVectorization: build.mutation<
      SearchDocumentsUsingVectorizationApiResponse,
      SearchDocumentsUsingVectorizationApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/vector/search`, method: "POST", body: queryArg.searchRequest }),
    }),
    testPostSuccess: build.mutation<TestPostSuccessApiResponse, TestPostSuccessApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/vector/test`, method: "POST" }),
    }),
    rerankDocuments: build.mutation<RerankDocumentsApiResponse, RerankDocumentsApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/vector/rerank`, method: "POST", body: queryArg.rerankRequest }),
    }),
    queryKnowledgeFlowV1KpiQueryPost: build.mutation<
      QueryKnowledgeFlowV1KpiQueryPostApiResponse,
      QueryKnowledgeFlowV1KpiQueryPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/kpi/query`, method: "POST", body: queryArg.kpiQuery }),
    }),
    getCreateResSchemaKnowledgeFlowV1ResourcesSchemaGet: build.query<
      GetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetApiResponse,
      GetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/resources/schema` }),
    }),
    createResourceKnowledgeFlowV1ResourcesPost: build.mutation<
      CreateResourceKnowledgeFlowV1ResourcesPostApiResponse,
      CreateResourceKnowledgeFlowV1ResourcesPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/resources`,
        method: "POST",
        body: queryArg.resourceCreate,
        params: {
          library_tag_id: queryArg.libraryTagId,
        },
      }),
    }),
    listResourcesByKindKnowledgeFlowV1ResourcesGet: build.query<
      ListResourcesByKindKnowledgeFlowV1ResourcesGetApiResponse,
      ListResourcesByKindKnowledgeFlowV1ResourcesGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/resources`,
        params: {
          kind: queryArg.kind,
        },
      }),
    }),
    updateResourceKnowledgeFlowV1ResourcesResourceIdPut: build.mutation<
      UpdateResourceKnowledgeFlowV1ResourcesResourceIdPutApiResponse,
      UpdateResourceKnowledgeFlowV1ResourcesResourceIdPutApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/resources/${queryArg.resourceId}`,
        method: "PUT",
        body: queryArg.resourceUpdate,
      }),
    }),
    getResourceKnowledgeFlowV1ResourcesResourceIdGet: build.query<
      GetResourceKnowledgeFlowV1ResourcesResourceIdGetApiResponse,
      GetResourceKnowledgeFlowV1ResourcesResourceIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/resources/${queryArg.resourceId}` }),
    }),
    deleteResourceKnowledgeFlowV1ResourcesResourceIdDelete: build.mutation<
      DeleteResourceKnowledgeFlowV1ResourcesResourceIdDeleteApiResponse,
      DeleteResourceKnowledgeFlowV1ResourcesResourceIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/resources/${queryArg.resourceId}`, method: "DELETE" }),
    }),
    listFiles: build.query<ListFilesApiResponse, ListFilesApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/fs/list`,
        params: {
          prefix: queryArg.prefix,
        },
      }),
    }),
    statFileOrDirectory: build.query<StatFileOrDirectoryApiResponse, StatFileOrDirectoryApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/fs/stat/${queryArg.path}` }),
    }),
    catFile: build.query<CatFileApiResponse, CatFileApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/fs/cat/${queryArg.path}` }),
    }),
    writeFile: build.mutation<WriteFileApiResponse, WriteFileApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/fs/write/${queryArg.path}`,
        method: "POST",
        body: queryArg.bodyWriteFile,
      }),
    }),
    deleteFile: build.mutation<DeleteFileApiResponse, DeleteFileApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/fs/delete/${queryArg.path}`, method: "DELETE" }),
    }),
    grepFileRegex: build.query<GrepFileRegexApiResponse, GrepFileRegexApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/fs/grep`,
        params: {
          pattern: queryArg.pattern,
          prefix: queryArg.prefix,
        },
      }),
    }),
    printRootDirectory: build.query<PrintRootDirectoryApiResponse, PrintRootDirectoryApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/fs/print_root_dir` }),
    }),
    createDirectory: build.mutation<CreateDirectoryApiResponse, CreateDirectoryApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/fs/mkdir/${queryArg.path}`, method: "POST" }),
    }),
    corpusCapabilities: build.query<CorpusCapabilitiesApiResponse, CorpusCapabilitiesApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/corpus/capabilities` }),
    }),
    corpusBuildToc: build.mutation<CorpusBuildTocApiResponse, CorpusBuildTocApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/corpus/build-toc`,
        method: "POST",
        body: queryArg.buildCorpusTocRequestV1,
      }),
    }),
    corpusRevectorize: build.mutation<CorpusRevectorizeApiResponse, CorpusRevectorizeApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/corpus/revectorize`,
        method: "POST",
        body: queryArg.revectorizeCorpusRequestV1,
      }),
    }),
    corpusPurgeVectors: build.mutation<CorpusPurgeVectorsApiResponse, CorpusPurgeVectorsApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/corpus/purge-vectors`,
        method: "POST",
        body: queryArg.purgeVectorsRequestV1,
      }),
    }),
    corpusTasksGet: build.mutation<CorpusTasksGetApiResponse, CorpusTasksGetApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/corpus/tasks/get`,
        method: "POST",
        body: queryArg.taskGetRequestV1,
      }),
    }),
    corpusTasksResult: build.mutation<CorpusTasksResultApiResponse, CorpusTasksResultApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/corpus/tasks/result`,
        method: "POST",
        body: queryArg.taskResultRequestV1,
      }),
    }),
    corpusTasksList: build.mutation<CorpusTasksListApiResponse, CorpusTasksListApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/corpus/tasks/list`,
        method: "POST",
        body: queryArg.taskListRequestV1,
      }),
    }),
    queryLogsKnowledgeFlowV1LogsQueryPost: build.mutation<
      QueryLogsKnowledgeFlowV1LogsQueryPostApiResponse,
      QueryLogsKnowledgeFlowV1LogsQueryPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/logs/query`, method: "POST", body: queryArg.logQuery }),
    }),
    listTeamsKnowledgeFlowV1TeamsGet: build.query<
      ListTeamsKnowledgeFlowV1TeamsGetApiResponse,
      ListTeamsKnowledgeFlowV1TeamsGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/teams` }),
    }),
    getTeamKnowledgeFlowV1TeamsTeamIdGet: build.query<
      GetTeamKnowledgeFlowV1TeamsTeamIdGetApiResponse,
      GetTeamKnowledgeFlowV1TeamsTeamIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/teams/${queryArg.teamId}` }),
    }),
    updateTeamKnowledgeFlowV1TeamsTeamIdPatch: build.mutation<
      UpdateTeamKnowledgeFlowV1TeamsTeamIdPatchApiResponse,
      UpdateTeamKnowledgeFlowV1TeamsTeamIdPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/teams/${queryArg.teamId}`,
        method: "PATCH",
        body: queryArg.teamUpdate,
      }),
    }),
    uploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPost: build.mutation<
      UploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPostApiResponse,
      UploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/teams/${queryArg.teamId}/banner`,
        method: "POST",
        body: queryArg.bodyUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPost,
      }),
    }),
    listTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGet: build.query<
      ListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetApiResponse,
      ListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/teams/${queryArg.teamId}/members` }),
    }),
    addTeamMemberKnowledgeFlowV1TeamsTeamIdMembersPost: build.mutation<
      AddTeamMemberKnowledgeFlowV1TeamsTeamIdMembersPostApiResponse,
      AddTeamMemberKnowledgeFlowV1TeamsTeamIdMembersPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/teams/${queryArg.teamId}/members`,
        method: "POST",
        body: queryArg.addTeamMemberRequest,
      }),
    }),
    removeTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDelete: build.mutation<
      RemoveTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDeleteApiResponse,
      RemoveTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/teams/${queryArg.teamId}/members/${queryArg.userId}`,
        method: "DELETE",
      }),
    }),
    updateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatch: build.mutation<
      UpdateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatchApiResponse,
      UpdateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatchApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/teams/${queryArg.teamId}/members/${queryArg.userId}`,
        method: "PATCH",
        body: queryArg.updateTeamMemberRequest,
      }),
    }),
    listUsersKnowledgeFlowV1UsersGet: build.query<
      ListUsersKnowledgeFlowV1UsersGetApiResponse,
      ListUsersKnowledgeFlowV1UsersGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/users` }),
    }),
    listProcessorsKnowledgeFlowV1DevBenchProcessorsGet: build.query<
      ListProcessorsKnowledgeFlowV1DevBenchProcessorsGetApiResponse,
      ListProcessorsKnowledgeFlowV1DevBenchProcessorsGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/dev/bench/processors` }),
    }),
    runKnowledgeFlowV1DevBenchRunPost: build.mutation<
      RunKnowledgeFlowV1DevBenchRunPostApiResponse,
      RunKnowledgeFlowV1DevBenchRunPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/dev/bench/run`,
        method: "POST",
        body: queryArg.bodyRunKnowledgeFlowV1DevBenchRunPost,
      }),
    }),
    listRunsKnowledgeFlowV1DevBenchRunsGet: build.query<
      ListRunsKnowledgeFlowV1DevBenchRunsGetApiResponse,
      ListRunsKnowledgeFlowV1DevBenchRunsGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/dev/bench/runs` }),
    }),
    getRunKnowledgeFlowV1DevBenchRunsRunIdGet: build.query<
      GetRunKnowledgeFlowV1DevBenchRunsRunIdGetApiResponse,
      GetRunKnowledgeFlowV1DevBenchRunsRunIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/dev/bench/runs/${queryArg.runId}` }),
    }),
    deleteRunKnowledgeFlowV1DevBenchRunsRunIdDelete: build.mutation<
      DeleteRunKnowledgeFlowV1DevBenchRunsRunIdDeleteApiResponse,
      DeleteRunKnowledgeFlowV1DevBenchRunsRunIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/dev/bench/runs/${queryArg.runId}`, method: "DELETE" }),
    }),
    listDatabases: build.query<ListDatabasesApiResponse, ListDatabasesApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/databases` }),
    }),
    listTables: build.query<ListTablesApiResponse, ListTablesApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/databases/${queryArg.dbName}/tables` }),
    }),
    getDatabaseSchemas: build.query<GetDatabaseSchemasApiResponse, GetDatabaseSchemasApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/databases/${queryArg.dbName}/schemas` }),
    }),
    describeTable: build.query<DescribeTableApiResponse, DescribeTableApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/databases/${queryArg.dbName}/tables/${queryArg.tableName}/descibe_table`,
      }),
    }),
    getContext: build.query<GetContextApiResponse, GetContextApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/context` }),
    }),
    readQuery: build.mutation<ReadQueryApiResponse, ReadQueryApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/databases/${queryArg.dbName}/sql/read`,
        method: "POST",
        body: queryArg.rawSqlRequest,
      }),
    }),
    executeWriteQuery: build.mutation<ExecuteWriteQueryApiResponse, ExecuteWriteQueryApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/databases/${queryArg.dbName}/sql/write`,
        method: "POST",
        body: queryArg.rawSqlRequest,
      }),
    }),
    deleteTable: build.mutation<DeleteTableApiResponse, DeleteTableApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/databases/${queryArg.dbName}/tables/${queryArg.tableName}`,
        method: "DELETE",
      }),
    }),
    listDatasets: build.query<ListDatasetsApiResponse, ListDatasetsApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/stat/list_datasets` }),
    }),
    setDataset: build.mutation<SetDatasetApiResponse, SetDatasetApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/set_dataset`,
        method: "POST",
        body: queryArg.setDatasetRequest,
      }),
    }),
    head: build.query<HeadApiResponse, HeadApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/head`,
        params: {
          n: queryArg.n,
        },
      }),
    }),
    describe: build.query<DescribeApiResponse, DescribeApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/stat/describe` }),
    }),
    detectOutliers: build.mutation<DetectOutliersApiResponse, DetectOutliersApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/detect_outliers`,
        method: "POST",
        body: queryArg.detectOutliersRequest,
      }),
    }),
    correlations: build.query<CorrelationsApiResponse, CorrelationsApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/stat/correlations` }),
    }),
    plotHistogram: build.mutation<PlotHistogramApiResponse, PlotHistogramApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/plot/histogram`,
        method: "POST",
        body: queryArg.plotHistogramRequest,
      }),
    }),
    plotScatter: build.mutation<PlotScatterApiResponse, PlotScatterApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/plot/scatter`,
        method: "POST",
        body: queryArg.plotScatterRequest,
      }),
    }),
    trainModel: build.mutation<TrainModelApiResponse, TrainModelApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/stat/train`, method: "POST", body: queryArg.trainModelRequest }),
    }),
    evaluateModel: build.query<EvaluateModelApiResponse, EvaluateModelApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/stat/evaluate` }),
    }),
    predictRow: build.mutation<PredictRowApiResponse, PredictRowApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/predict_row`,
        method: "POST",
        body: queryArg.predictRowRequest,
      }),
    }),
    saveModel: build.mutation<SaveModelApiResponse, SaveModelApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/save_model`,
        method: "POST",
        body: queryArg.saveModelRequest,
      }),
    }),
    listModels: build.query<ListModelsApiResponse, ListModelsApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/stat/list_models` }),
    }),
    loadModel: build.mutation<LoadModelApiResponse, LoadModelApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/load_model`,
        method: "POST",
        body: queryArg.loadModelRequest,
      }),
    }),
    testDistribution: build.query<TestDistributionApiResponse, TestDistributionApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/test_distribution`,
        params: {
          column: queryArg.column,
        },
      }),
    }),
    detectOutliersMl: build.mutation<DetectOutliersMlApiResponse, DetectOutliersMlApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/detect_outliers_ml`,
        method: "POST",
        body: queryArg.detectOutliersMlRequest,
      }),
    }),
    runPca: build.mutation<RunPcaApiResponse, RunPcaApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/stat/pca`, method: "POST", body: queryArg.pcaRequest }),
    }),
    writeReportKnowledgeFlowV1McpReportsWritePost: build.mutation<
      WriteReportKnowledgeFlowV1McpReportsWritePostApiResponse,
      WriteReportKnowledgeFlowV1McpReportsWritePostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/mcp/reports/write`,
        method: "POST",
        body: queryArg.writeReportRequest,
      }),
    }),
    processDocumentsKnowledgeFlowV1ProcessDocumentsPost: build.mutation<
      ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiResponse,
      ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/process-documents`,
        method: "POST",
        body: queryArg.processDocumentsRequest,
      }),
    }),
    processLibraryKnowledgeFlowV1ProcessLibraryPost: build.mutation<
      ProcessLibraryKnowledgeFlowV1ProcessLibraryPostApiResponse,
      ProcessLibraryKnowledgeFlowV1ProcessLibraryPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/process-library`,
        method: "POST",
        body: queryArg.processLibraryRequest,
      }),
    }),
    processDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPost: build.mutation<
      ProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostApiResponse,
      ProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/process-documents/progress`,
        method: "POST",
        body: queryArg.processDocumentsProgressRequest,
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as knowledgeFlowApi };
export type HealthzKnowledgeFlowV1HealthzGetApiResponse = /** status 200 Successful Response */ any;
export type HealthzKnowledgeFlowV1HealthzGetApiArg = void;
export type ReadyKnowledgeFlowV1ReadyGetApiResponse = /** status 200 Successful Response */ any;
export type ReadyKnowledgeFlowV1ReadyGetApiArg = void;
export type SearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostApiResponse =
  /** status 200 Successful Response */ DocumentMetadata[];
export type SearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostApiArg = {
  filters: {
    [key: string]: any;
  };
};
export type GetDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGetApiResponse =
  /** status 200 Successful Response */ DocumentMetadata;
export type GetDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGetApiArg = {
  documentUid: string;
};
export type GetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetApiResponse =
  /** status 200 Successful Response */ ProcessingGraph;
export type GetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetApiArg = void;
export type GetProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGetApiResponse =
  /** status 200 Successful Response */ ProcessingSummary;
export type GetProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGetApiArg = void;
export type UpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutApiResponse =
  /** status 200 Successful Response */ any;
export type UpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutApiArg = {
  documentUid: string;
  retrievable: boolean;
};
export type BrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostApiResponse =
  /** status 200 Successful Response */ BrowseDocumentsResponse;
export type BrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostApiArg = {
  browseDocumentsRequest: BrowseDocumentsRequest;
};
export type BrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostApiResponse =
  /** status 200 Successful Response */ BrowseDocumentsResponse;
export type BrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostApiArg = {
  browseDocumentsByTagRequest: BrowseDocumentsByTagRequest;
};
export type DocumentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGetApiResponse =
  /** status 200 Successful Response */ VectorChunk[];
export type DocumentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGetApiArg = {
  documentUid: string;
};
export type DocumentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGetApiResponse =
  /** status 200 Successful Response */ {
    [key: string]: any;
  }[];
export type DocumentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGetApiArg = {
  documentUid: string;
};
export type AuditDocumentsKnowledgeFlowV1DocumentsAuditGetApiResponse =
  /** status 200 Successful Response */ StoreAuditReport;
export type AuditDocumentsKnowledgeFlowV1DocumentsAuditGetApiArg = void;
export type FixDocumentsKnowledgeFlowV1DocumentsAuditFixPostApiResponse =
  /** status 200 Successful Response */ StoreAuditFixResponse;
export type FixDocumentsKnowledgeFlowV1DocumentsAuditFixPostApiArg = void;
export type GetChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdGetApiResponse =
  /** status 200 Successful Response */ {
    [key: string]: any;
  };
export type GetChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdGetApiArg = {
  documentUid: string;
  chunkId: string;
};
export type DeleteChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdDeleteApiResponse =
  /** status 200 Successful Response */ any;
export type DeleteChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdDeleteApiArg = {
  documentUid: string;
  chunkId: string;
};
export type TrainUmapKnowledgeFlowV1ModelsUmapTagIdTrainPostApiResponse =
  /** status 200 Successful Response */ TrainResponse;
export type TrainUmapKnowledgeFlowV1ModelsUmapTagIdTrainPostApiArg = {
  tagId: string;
};
export type ModelStatusKnowledgeFlowV1ModelsUmapTagUidGetApiResponse =
  /** status 200 Successful Response */ StatusResponse;
export type ModelStatusKnowledgeFlowV1ModelsUmapTagUidGetApiArg = {
  tagUid: string;
};
export type ProjectKnowledgeFlowV1ModelsUmapRefTagUidProjectPostApiResponse =
  /** status 200 Successful Response */ ProjectResponse;
export type ProjectKnowledgeFlowV1ModelsUmapRefTagUidProjectPostApiArg = {
  refTagUid: string;
  projectRequest: ProjectRequest;
};
export type DeleteModelKnowledgeFlowV1ModelsUmapRefTagUidDeleteApiResponse = /** status 200 Successful Response */ {
  [key: string]: any;
};
export type DeleteModelKnowledgeFlowV1ModelsUmapRefTagUidDeleteApiArg = {
  refTagUid: string;
};
export type ProjectTextKnowledgeFlowV1ModelsUmapRefTagUidProjectTextPostApiResponse =
  /** status 200 Successful Response */ ProjectTextResponse;
export type ProjectTextKnowledgeFlowV1ModelsUmapRefTagUidProjectTextPostApiArg = {
  refTagUid: string;
  projectTextRequest: ProjectTextRequest;
};
export type GetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetApiResponse =
  /** status 200 Successful Response */ MarkdownContentResponse;
export type GetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetApiArg = {
  documentUid: string;
};
export type DownloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGetApiResponse =
  /** status 200 Successful Response */ any;
export type DownloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGetApiArg = {
  documentUid: string;
  mediaId: string;
};
export type DownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetApiResponse =
  /** status 200 Binary file stream */ Blob;
export type DownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetApiArg = {
  documentUid: string;
};
export type StreamDocumentKnowledgeFlowV1RawContentStreamDocumentUidGetApiResponse = unknown;
export type StreamDocumentKnowledgeFlowV1RawContentStreamDocumentUidGetApiArg = {
  documentUid: string;
  range?: string | null;
};
export type UploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPostApiResponse =
  /** status 200 Successful Response */ AssetMeta;
export type UploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPostApiArg = {
  agent: string;
  bodyUploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPost: BodyUploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPost;
};
export type ListAgentAssetsKnowledgeFlowV1AgentAssetsAgentGetApiResponse =
  /** status 200 Successful Response */ AssetListResponse;
export type ListAgentAssetsKnowledgeFlowV1AgentAssetsAgentGetApiArg = {
  agent: string;
};
export type GetAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyGetApiResponse = /** status 200 Successful Response */ any;
export type GetAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyGetApiArg = {
  agent: string;
  key: string;
  range?: string | null;
};
export type DeleteAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteApiResponse =
  /** status 200 Successful Response */ {
    [key: string]: any;
  };
export type DeleteAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteApiArg = {
  agent: string;
  key: string;
};
export type UploadUserAssetKnowledgeFlowV1UserAssetsUploadPostApiResponse =
  /** status 200 Successful Response */ AssetMeta;
export type UploadUserAssetKnowledgeFlowV1UserAssetsUploadPostApiArg = {
  bodyUploadUserAssetKnowledgeFlowV1UserAssetsUploadPost: BodyUploadUserAssetKnowledgeFlowV1UserAssetsUploadPost;
};
export type ListUserAssetsKnowledgeFlowV1UserAssetsGetApiResponse =
  /** status 200 Successful Response */ AssetListResponse;
export type ListUserAssetsKnowledgeFlowV1UserAssetsGetApiArg = {
  /** [AGENT USE ONLY] Explicit user ID of the asset owner (Header) */
  "X-Asset-User-ID"?: string | null;
};
export type GetUserAssetKnowledgeFlowV1UserAssetsKeyGetApiResponse = /** status 200 Successful Response */ any;
export type GetUserAssetKnowledgeFlowV1UserAssetsKeyGetApiArg = {
  key: string;
  range?: string | null;
  /** [AGENT USE ONLY] Explicit user ID of the asset owner (Header) */
  "X-Asset-User-ID"?: string | null;
};
export type DeleteUserAssetKnowledgeFlowV1UserAssetsKeyDeleteApiResponse = /** status 200 Successful Response */ {
  [key: string]: any;
};
export type DeleteUserAssetKnowledgeFlowV1UserAssetsKeyDeleteApiArg = {
  key: string;
  /** [AGENT USE ONLY] Explicit user ID of the asset owner (Header) */
  "X-Asset-User-ID"?: string | null;
};
export type UploadUserFileKnowledgeFlowV1StorageUserUploadPostApiResponse = /** status 200 Successful Response */ any;
export type UploadUserFileKnowledgeFlowV1StorageUserUploadPostApiArg = {
  bodyUploadUserFileKnowledgeFlowV1StorageUserUploadPost: BodyUploadUserFileKnowledgeFlowV1StorageUserUploadPost;
};
export type ListUserFilesKnowledgeFlowV1StorageUserGetApiResponse = /** status 200 Successful Response */ any;
export type ListUserFilesKnowledgeFlowV1StorageUserGetApiArg = {
  prefix?: string;
};
export type DownloadUserFileKnowledgeFlowV1StorageUserKeyGetApiResponse = /** status 200 Successful Response */ any;
export type DownloadUserFileKnowledgeFlowV1StorageUserKeyGetApiArg = {
  key: string;
};
export type DeleteUserFileKnowledgeFlowV1StorageUserKeyDeleteApiResponse = /** status 200 Successful Response */ any;
export type DeleteUserFileKnowledgeFlowV1StorageUserKeyDeleteApiArg = {
  key: string;
};
export type UploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPostApiResponse =
  /** status 200 Successful Response */ any;
export type UploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPostApiArg = {
  agentId: string;
  bodyUploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPost: BodyUploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPost;
};
export type ListAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGetApiResponse =
  /** status 200 Successful Response */ any;
export type ListAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGetApiArg = {
  agentId: string;
  prefix?: string;
};
export type DownloadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyGetApiResponse =
  /** status 200 Successful Response */ any;
export type DownloadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyGetApiArg = {
  agentId: string;
  key: string;
};
export type DeleteAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyDeleteApiResponse =
  /** status 200 Successful Response */ any;
export type DeleteAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyDeleteApiArg = {
  agentId: string;
  key: string;
};
export type UploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPostApiResponse =
  /** status 200 Successful Response */ any;
export type UploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPostApiArg = {
  agentId: string;
  targetUserId: string;
  bodyUploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPost: BodyUploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPost;
};
export type ListAgentUserFilesKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdGetApiResponse =
  /** status 200 Successful Response */ any;
export type ListAgentUserFilesKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdGetApiArg = {
  agentId: string;
  targetUserId: string;
  prefix?: string;
};
export type DownloadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyGetApiResponse =
  /** status 200 Successful Response */ any;
export type DownloadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyGetApiArg = {
  agentId: string;
  targetUserId: string;
  key: string;
};
export type DeleteAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyDeleteApiResponse =
  /** status 200 Successful Response */ any;
export type DeleteAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyDeleteApiArg = {
  agentId: string;
  targetUserId: string;
  key: string;
};
export type ListAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGetApiResponse =
  /** status 200 Successful Response */ AvailableProcessorsResponse;
export type ListAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGetApiArg = void;
export type RegisterProcessingPipelineKnowledgeFlowV1ProcessingPipelinesPostApiResponse =
  /** status 200 Successful Response */ any;
export type RegisterProcessingPipelineKnowledgeFlowV1ProcessingPipelinesPostApiArg = {
  processingPipelineDefinition: ProcessingPipelineDefinition;
};
export type AssignPipelineToLibraryKnowledgeFlowV1ProcessingPipelinesAssignLibraryPostApiResponse =
  /** status 200 Successful Response */ any;
export type AssignPipelineToLibraryKnowledgeFlowV1ProcessingPipelinesAssignLibraryPostApiArg = {
  pipelineAssignment: PipelineAssignment;
};
export type GetLibraryPipelineKnowledgeFlowV1ProcessingPipelinesLibraryLibraryTagIdGetApiResponse =
  /** status 200 Successful Response */ ProcessingPipelineInfo;
export type GetLibraryPipelineKnowledgeFlowV1ProcessingPipelinesLibraryLibraryTagIdGetApiArg = {
  libraryTagId: string;
};
export type UploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPostApiResponse =
  /** status 200 Successful Response */ any;
export type UploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPostApiArg = {
  bodyUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPost: BodyUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPost;
};
export type ProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPostApiResponse =
  /** status 200 Successful Response */ any;
export type ProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPostApiArg = {
  bodyProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPost: BodyProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPost;
};
export type GetUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGetApiResponse =
  /** status 200 Successful Response */ ProcessDocumentsProgressResponse;
export type GetUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGetApiArg = {
  /** Workflow id returned by /upload-process-documents */
  workflowId: string;
};
export type FastMarkdownKnowledgeFlowV1FastTextPostApiResponse = /** status 200 Successful Response */ any;
export type FastMarkdownKnowledgeFlowV1FastTextPostApiArg = {
  /** Response format: 'json' or 'text' */
  format?: string;
  bodyFastMarkdownKnowledgeFlowV1FastTextPost: BodyFastMarkdownKnowledgeFlowV1FastTextPost;
};
export type FastIngestKnowledgeFlowV1FastIngestPostApiResponse = /** status 200 Successful Response */ any;
export type FastIngestKnowledgeFlowV1FastIngestPostApiArg = {
  bodyFastIngestKnowledgeFlowV1FastIngestPost: BodyFastIngestKnowledgeFlowV1FastIngestPost;
};
export type DeleteFastIngestKnowledgeFlowV1FastIngestDocumentUidDeleteApiResponse =
  /** status 200 Successful Response */ any;
export type DeleteFastIngestKnowledgeFlowV1FastIngestDocumentUidDeleteApiArg = {
  documentUid: string;
  /** Optional session_id for scoped cleanup */
  sessionId?: string | null;
};
export type ListAllTagsKnowledgeFlowV1TagsGetApiResponse = /** status 200 Successful Response */ TagWithPermissions[];
export type ListAllTagsKnowledgeFlowV1TagsGetApiArg = {
  /** Filter by tag type */
  type?: TagType | null;
  /** Filter by hierarchical path prefix, e.g. 'Sales' or 'Sales/HR' */
  pathPrefix?: string | null;
  /** Max items to return */
  limit?: number;
  /** Items to skip */
  offset?: number;
  /** Filter by ownership: 'personal' for user-owned tags, 'team' for team-owned tags */
  ownerFilter?: OwnerFilter | null;
  /** Team ID, required when owner_filter is 'team' */
  teamId?: string | null;
};
export type CreateTagKnowledgeFlowV1TagsPostApiResponse = /** status 201 Successful Response */ TagWithItemsId;
export type CreateTagKnowledgeFlowV1TagsPostApiArg = {
  tagCreate: TagCreate;
};
export type GetTagKnowledgeFlowV1TagsTagIdGetApiResponse = /** status 200 Successful Response */ TagWithItemsId;
export type GetTagKnowledgeFlowV1TagsTagIdGetApiArg = {
  tagId: string;
};
export type UpdateTagKnowledgeFlowV1TagsTagIdPutApiResponse = /** status 200 Successful Response */ TagWithItemsId;
export type UpdateTagKnowledgeFlowV1TagsTagIdPutApiArg = {
  tagId: string;
  tagUpdate: TagUpdate;
};
export type DeleteTagKnowledgeFlowV1TagsTagIdDeleteApiResponse = unknown;
export type DeleteTagKnowledgeFlowV1TagsTagIdDeleteApiArg = {
  tagId: string;
};
export type ListTagMembersKnowledgeFlowV1TagsTagIdMembersGetApiResponse =
  /** status 200 Successful Response */ TagMembersResponse;
export type ListTagMembersKnowledgeFlowV1TagsTagIdMembersGetApiArg = {
  tagId: string;
};
export type ShareTagKnowledgeFlowV1TagsTagIdSharePostApiResponse = unknown;
export type ShareTagKnowledgeFlowV1TagsTagIdSharePostApiArg = {
  tagId: string;
  tagShareRequest: TagShareRequest;
};
export type UnshareTagKnowledgeFlowV1TagsTagIdShareTargetIdDeleteApiResponse = unknown;
export type UnshareTagKnowledgeFlowV1TagsTagIdShareTargetIdDeleteApiArg = {
  tagId: string;
  targetId: string;
  targetType: ShareTargetResource;
};
export type BackfillRebacRelationsKnowledgeFlowV1TagsRebacBackfillPostApiResponse =
  /** status 200 Successful Response */ RebacBackfillResponse;
export type BackfillRebacRelationsKnowledgeFlowV1TagsRebacBackfillPostApiArg = void;
export type EchoSchemaKnowledgeFlowV1SchemasEchoPostApiResponse = /** status 200 Successful Response */ any;
export type EchoSchemaKnowledgeFlowV1SchemasEchoPostApiArg = {
  echoEnvelope: EchoEnvelope;
};
export type SearchDocumentsUsingVectorizationApiResponse = /** status 200 Successful Response */ VectorSearchHit[];
export type SearchDocumentsUsingVectorizationApiArg = {
  searchRequest: SearchRequest;
};
export type TestPostSuccessApiResponse = /** status 200 Successful Response */ VectorSearchHit[];
export type TestPostSuccessApiArg = void;
export type RerankDocumentsApiResponse = /** status 200 Successful Response */ VectorSearchHit[];
export type RerankDocumentsApiArg = {
  rerankRequest: RerankRequest;
};
export type QueryKnowledgeFlowV1KpiQueryPostApiResponse = /** status 200 Successful Response */ KpiQueryResult;
export type QueryKnowledgeFlowV1KpiQueryPostApiArg = {
  kpiQuery: KpiQuery;
};
export type GetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetApiResponse = /** status 200 Successful Response */ {
  [key: string]: any;
};
export type GetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetApiArg = void;
export type CreateResourceKnowledgeFlowV1ResourcesPostApiResponse = /** status 201 Successful Response */ Resource;
export type CreateResourceKnowledgeFlowV1ResourcesPostApiArg = {
  /** Library tag id to attach this resource to */
  libraryTagId: string;
  resourceCreate: ResourceCreate;
};
export type ListResourcesByKindKnowledgeFlowV1ResourcesGetApiResponse =
  /** status 200 Successful Response */ Resource[];
export type ListResourcesByKindKnowledgeFlowV1ResourcesGetApiArg = {
  /** prompt | template */
  kind: ResourceKind;
};
export type UpdateResourceKnowledgeFlowV1ResourcesResourceIdPutApiResponse =
  /** status 200 Successful Response */ Resource;
export type UpdateResourceKnowledgeFlowV1ResourcesResourceIdPutApiArg = {
  resourceId: string;
  resourceUpdate: ResourceUpdate;
};
export type GetResourceKnowledgeFlowV1ResourcesResourceIdGetApiResponse =
  /** status 200 Successful Response */ Resource;
export type GetResourceKnowledgeFlowV1ResourcesResourceIdGetApiArg = {
  resourceId: string;
};
export type DeleteResourceKnowledgeFlowV1ResourcesResourceIdDeleteApiResponse =
  /** status 200 Successful Response */ any;
export type DeleteResourceKnowledgeFlowV1ResourcesResourceIdDeleteApiArg = {
  resourceId: string;
};
export type ListFilesApiResponse = /** status 200 Successful Response */ any;
export type ListFilesApiArg = {
  prefix?: string;
};
export type StatFileOrDirectoryApiResponse = /** status 200 Successful Response */ any;
export type StatFileOrDirectoryApiArg = {
  path: string;
};
export type CatFileApiResponse = /** status 200 Successful Response */ any;
export type CatFileApiArg = {
  path: string;
};
export type WriteFileApiResponse = /** status 200 Successful Response */ any;
export type WriteFileApiArg = {
  path: string;
  bodyWriteFile: BodyWriteFile;
};
export type DeleteFileApiResponse = /** status 200 Successful Response */ any;
export type DeleteFileApiArg = {
  path: string;
};
export type GrepFileRegexApiResponse = /** status 200 Successful Response */ any;
export type GrepFileRegexApiArg = {
  pattern: string;
  prefix?: string;
};
export type PrintRootDirectoryApiResponse = /** status 200 Successful Response */ any;
export type PrintRootDirectoryApiArg = void;
export type CreateDirectoryApiResponse = /** status 200 Successful Response */ any;
export type CreateDirectoryApiArg = {
  path: string;
};
export type CorpusCapabilitiesApiResponse = /** status 200 Successful Response */ CorpusCapabilitiesV1;
export type CorpusCapabilitiesApiArg = void;
export type CorpusBuildTocApiResponse = /** status 200 Successful Response */ any;
export type CorpusBuildTocApiArg = {
  buildCorpusTocRequestV1: BuildCorpusTocRequestV1;
};
export type CorpusRevectorizeApiResponse = /** status 200 Successful Response */ any;
export type CorpusRevectorizeApiArg = {
  revectorizeCorpusRequestV1: RevectorizeCorpusRequestV1;
};
export type CorpusPurgeVectorsApiResponse = /** status 200 Successful Response */ any;
export type CorpusPurgeVectorsApiArg = {
  purgeVectorsRequestV1: PurgeVectorsRequestV1;
};
export type CorpusTasksGetApiResponse = /** status 200 Successful Response */ any;
export type CorpusTasksGetApiArg = {
  taskGetRequestV1: TaskGetRequestV1;
};
export type CorpusTasksResultApiResponse = /** status 200 Successful Response */ any;
export type CorpusTasksResultApiArg = {
  taskResultRequestV1: TaskResultRequestV1;
};
export type CorpusTasksListApiResponse = /** status 200 Successful Response */ any;
export type CorpusTasksListApiArg = {
  taskListRequestV1: TaskListRequestV1;
};
export type QueryLogsKnowledgeFlowV1LogsQueryPostApiResponse = /** status 200 Successful Response */ LogQueryResult;
export type QueryLogsKnowledgeFlowV1LogsQueryPostApiArg = {
  logQuery: LogQuery;
};
export type ListTeamsKnowledgeFlowV1TeamsGetApiResponse = /** status 200 Successful Response */ Team[];
export type ListTeamsKnowledgeFlowV1TeamsGetApiArg = void;
export type GetTeamKnowledgeFlowV1TeamsTeamIdGetApiResponse = /** status 200 Successful Response */ TeamWithPermissions;
export type GetTeamKnowledgeFlowV1TeamsTeamIdGetApiArg = {
  teamId: string;
};
export type UpdateTeamKnowledgeFlowV1TeamsTeamIdPatchApiResponse =
  /** status 200 Successful Response */ TeamWithPermissions;
export type UpdateTeamKnowledgeFlowV1TeamsTeamIdPatchApiArg = {
  teamId: string;
  teamUpdate: TeamUpdate;
};
export type UploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPostApiResponse = unknown;
export type UploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPostApiArg = {
  teamId: string;
  bodyUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPost: BodyUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPost;
};
export type ListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetApiResponse =
  /** status 200 Successful Response */ TeamMember[];
export type ListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetApiArg = {
  teamId: string;
};
export type AddTeamMemberKnowledgeFlowV1TeamsTeamIdMembersPostApiResponse = unknown;
export type AddTeamMemberKnowledgeFlowV1TeamsTeamIdMembersPostApiArg = {
  teamId: string;
  addTeamMemberRequest: AddTeamMemberRequest;
};
export type RemoveTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDeleteApiResponse = unknown;
export type RemoveTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDeleteApiArg = {
  teamId: string;
  userId: string;
};
export type UpdateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatchApiResponse = unknown;
export type UpdateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatchApiArg = {
  teamId: string;
  userId: string;
  updateTeamMemberRequest: UpdateTeamMemberRequest;
};
export type ListUsersKnowledgeFlowV1UsersGetApiResponse = /** status 200 Successful Response */ UserSummary[];
export type ListUsersKnowledgeFlowV1UsersGetApiArg = void;
export type ListProcessorsKnowledgeFlowV1DevBenchProcessorsGetApiResponse =
  /** status 200 Successful Response */ ProcessorDescriptor[];
export type ListProcessorsKnowledgeFlowV1DevBenchProcessorsGetApiArg = void;
export type RunKnowledgeFlowV1DevBenchRunPostApiResponse = /** status 200 Successful Response */ BenchmarkResponse;
export type RunKnowledgeFlowV1DevBenchRunPostApiArg = {
  bodyRunKnowledgeFlowV1DevBenchRunPost: BodyRunKnowledgeFlowV1DevBenchRunPost;
};
export type ListRunsKnowledgeFlowV1DevBenchRunsGetApiResponse = /** status 200 Successful Response */ SavedRunSummary[];
export type ListRunsKnowledgeFlowV1DevBenchRunsGetApiArg = void;
export type GetRunKnowledgeFlowV1DevBenchRunsRunIdGetApiResponse =
  /** status 200 Successful Response */ BenchmarkResponse;
export type GetRunKnowledgeFlowV1DevBenchRunsRunIdGetApiArg = {
  runId: string;
};
export type DeleteRunKnowledgeFlowV1DevBenchRunsRunIdDeleteApiResponse = /** status 200 Successful Response */ {
  [key: string]: any;
};
export type DeleteRunKnowledgeFlowV1DevBenchRunsRunIdDeleteApiArg = {
  runId: string;
};
export type ListDatabasesApiResponse = /** status 200 Successful Response */ string[];
export type ListDatabasesApiArg = void;
export type ListTablesApiResponse = /** status 200 Successful Response */ ListTablesResponse;
export type ListTablesApiArg = {
  /** Database name */
  dbName: string;
};
export type GetDatabaseSchemasApiResponse = /** status 200 Successful Response */ GetSchemaResponse[];
export type GetDatabaseSchemasApiArg = {
  /** Database name */
  dbName: string;
};
export type DescribeTableApiResponse = /** status 200 Successful Response */ GetSchemaResponse;
export type DescribeTableApiArg = {
  /** Database name */
  dbName: string;
  /** Table name */
  tableName: string;
};
export type GetContextApiResponse = /** status 200 Successful Response */ {
  [key: string]: {
    [key: string]: any;
  }[];
};
export type GetContextApiArg = void;
export type ReadQueryApiResponse = /** status 200 Successful Response */ RawSqlResponse;
export type ReadQueryApiArg = {
  /** Database name */
  dbName: string;
  rawSqlRequest: RawSqlRequest;
};
export type ExecuteWriteQueryApiResponse = /** status 200 Successful Response */ RawSqlResponse;
export type ExecuteWriteQueryApiArg = {
  /** Database name */
  dbName: string;
  rawSqlRequest: RawSqlRequest;
};
export type DeleteTableApiResponse = unknown;
export type DeleteTableApiArg = {
  /** Database name */
  dbName: string;
  /** Table name */
  tableName: string;
};
export type ListDatasetsApiResponse = /** status 200 Successful Response */ any;
export type ListDatasetsApiArg = void;
export type SetDatasetApiResponse = /** status 200 Successful Response */ any;
export type SetDatasetApiArg = {
  setDatasetRequest: SetDatasetRequest;
};
export type HeadApiResponse = /** status 200 Successful Response */ any;
export type HeadApiArg = {
  n?: number;
};
export type DescribeApiResponse = /** status 200 Successful Response */ any;
export type DescribeApiArg = void;
export type DetectOutliersApiResponse = /** status 200 Successful Response */ any;
export type DetectOutliersApiArg = {
  detectOutliersRequest: DetectOutliersRequest;
};
export type CorrelationsApiResponse = /** status 200 Successful Response */ any;
export type CorrelationsApiArg = void;
export type PlotHistogramApiResponse = /** status 200 Successful Response */ any;
export type PlotHistogramApiArg = {
  plotHistogramRequest: PlotHistogramRequest;
};
export type PlotScatterApiResponse = /** status 200 Successful Response */ any;
export type PlotScatterApiArg = {
  plotScatterRequest: PlotScatterRequest;
};
export type TrainModelApiResponse = /** status 200 Successful Response */ any;
export type TrainModelApiArg = {
  trainModelRequest: TrainModelRequest;
};
export type EvaluateModelApiResponse = /** status 200 Successful Response */ any;
export type EvaluateModelApiArg = void;
export type PredictRowApiResponse = /** status 200 Successful Response */ any;
export type PredictRowApiArg = {
  predictRowRequest: PredictRowRequest;
};
export type SaveModelApiResponse = /** status 200 Successful Response */ any;
export type SaveModelApiArg = {
  saveModelRequest: SaveModelRequest;
};
export type ListModelsApiResponse = /** status 200 Successful Response */ any;
export type ListModelsApiArg = void;
export type LoadModelApiResponse = /** status 200 Successful Response */ any;
export type LoadModelApiArg = {
  loadModelRequest: LoadModelRequest;
};
export type TestDistributionApiResponse = /** status 200 Successful Response */ any;
export type TestDistributionApiArg = {
  column: string;
};
export type DetectOutliersMlApiResponse = /** status 200 Successful Response */ any;
export type DetectOutliersMlApiArg = {
  detectOutliersMlRequest: DetectOutliersMlRequest;
};
export type RunPcaApiResponse = /** status 200 Successful Response */ any;
export type RunPcaApiArg = {
  pcaRequest: PcaRequest;
};
export type WriteReportKnowledgeFlowV1McpReportsWritePostApiResponse =
  /** status 200 Successful Response */ WriteReportResponse;
export type WriteReportKnowledgeFlowV1McpReportsWritePostApiArg = {
  writeReportRequest: WriteReportRequest;
};
export type ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiResponse =
  /** status 200 Successful Response */ ProcessDocumentsResponse;
export type ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiArg = {
  processDocumentsRequest: ProcessDocumentsRequest;
};
export type ProcessLibraryKnowledgeFlowV1ProcessLibraryPostApiResponse =
  /** status 200 Successful Response */ ProcessLibraryResponse;
export type ProcessLibraryKnowledgeFlowV1ProcessLibraryPostApiArg = {
  processLibraryRequest: ProcessLibraryRequest;
};
export type ProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostApiResponse =
  /** status 200 Successful Response */ ProcessDocumentsProgressResponse;
export type ProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostApiArg = {
  processDocumentsProgressRequest: ProcessDocumentsProgressRequest;
};
export type Identity = {
  /** Original file name incl. extension (display name) */
  document_name: string;
  /** Stable unique id across the system */
  document_uid: string;
  /** Base file name without transient version suffix (e.g., 'report.docx' for 'report.docx (1)') */
  canonical_name?: string | null;
  /** Version number within a folder/tag. 0 means canonical/original name, 1 -> 'name (1)', etc. */
  version?: number;
  /** Human-friendly title for UI */
  title?: string | null;
  author?: string | null;
  created?: string | null;
  modified?: string | null;
  last_modified_by?: string | null;
};
export type SourceType = "push" | "pull";
export type SourceInfo = {
  source_type: SourceType;
  /** Repository/connector id, e.g. 'uploads', 'github' */
  source_tag?: string | null;
  /** Path or URI to the original pull file */
  pull_location?: string | null;
  /** True if raw file can be re-fetched */
  retrievable?: boolean;
  /** When the document was added to the system */
  date_added_to_kb?: string;
  /** Web base of the repository, e.g. https://git/org/repo */
  repository_web?: string | null;
  /** Commit SHA or branch used when pulling */
  repo_ref?: string | null;
  /** Path within the repository (POSIX style) */
  file_path?: string | null;
};
export type FileType = "pdf" | "docx" | "pptx" | "xlsx" | "csv" | "md" | "html" | "txt" | "other";
export type FileInfo = {
  file_type?: FileType;
  mime_type?: string | null;
  file_size_bytes?: number | null;
  page_count?: number | null;
  row_count?: number | null;
  sha256?: string | null;
  md5?: string | null;
  language?: string | null;
};
export type DocSummary = {
  /** Concise doc abstract for humans (UI). */
  abstract?: string | null;
  /** Top key terms for navigation and filters. */
  keywords?: string[] | null;
  /** LLM/flow used to produce this summary. */
  model_name?: string | null;
  /** Algorithm/flow id (e.g., 'SmartDocSummarizer@v1'). */
  method?: string | null;
  /** UTC when this summary was computed. */
  created_at?: string | null;
};
export type Tagging = {
  /** Stable tag IDs (UUIDs) */
  tag_ids?: string[];
  /** Display names for chips */
  tag_names?: string[];
};
export type AccessInfo = {
  license?: string | null;
  confidential?: boolean;
  acl?: string[];
};
export type ProcessingStatus = "not_started" | "in_progress" | "done" | "failed";
export type Processing = {
  stages?: {
    [key: string]: ProcessingStatus;
  };
  errors?: {
    [key: string]: string;
  };
};
export type DocumentMetadata = {
  identity: Identity;
  source: SourceInfo;
  file?: FileInfo;
  summary?: DocSummary | null;
  tags?: Tagging;
  access?: AccessInfo;
  processing?: Processing;
  preview_url?: string | null;
  viewer_url?: string | null;
  /** Processor-specific additional attributes (namespaced keys). */
  extensions?: {
    [key: string]: any;
  } | null;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type ProcessingGraphNode = {
  id: string;
  kind: string;
  label: string;
  document_uid?: string | null;
  table_name?: string | null;
  vector_count?: number | null;
  row_count?: number | null;
  file_type?: FileType | null;
  source_tag?: string | null;
  /** Document version (0=base, 1=draft). Set only for document nodes. */
  version?: number | null;
  backend?: string | null;
  backend_detail?: string | null;
  embedding_model?: string | null;
  embedding_dimension?: number | null;
};
export type ProcessingGraphEdge = {
  source: string;
  target: string;
  kind: string;
};
export type ProcessingGraph = {
  nodes: ProcessingGraphNode[];
  edges: ProcessingGraphEdge[];
};
export type ProcessingSummary = {
  total_documents: number;
  fully_processed: number;
  in_progress: number;
  failed: number;
  not_started: number;
};
export type BrowseDocumentsResponse = {
  total: number;
  documents: DocumentMetadata[];
};
export type SortOption = {
  field: string;
  direction: "asc" | "desc";
};
export type BrowseDocumentsRequest = {
  /** Optional metadata filters */
  filters?: {
    [key: string]: any;
  } | null;
  offset?: number;
  limit?: number;
  sort_by?: SortOption[] | null;
};
export type BrowseDocumentsByTagRequest = {
  /** Library tag identifier */
  tag_id: string;
  offset?: number;
  limit?: number;
};
export type VectorChunk = {
  /** Unique identifier of the chunk */
  chunk_uid: string;
  /** Chunk embedding */
  vector: number[];
};
export type StoreAuditFinding = {
  document_uid: string;
  document_name?: string | null;
  source_tag?: string | null;
  present_in_metadata: boolean;
  present_in_vector_store: boolean;
  present_in_content_store: boolean;
  /** Number of chunks in vector store (when available) */
  vector_chunks?: number | null;
  issues?: string[];
};
export type StoreAuditReport = {
  has_anomalies: boolean;
  total_seen: number;
  metadata_count: number;
  vector_count: number;
  content_count: number;
  anomalies?: StoreAuditFinding[];
};
export type StoreAuditFixResponse = {
  before: StoreAuditReport;
  after: StoreAuditReport;
  deleted_metadata?: string[];
  deleted_vectors?: string[];
  deleted_content?: string[];
};
export type TrainResponse = {
  tag_id: string;
  trained_at: string;
  n_chunks: number;
  n_documents: number;
  model_kind: string;
  embedding_model?: string | null;
};
export type StatusResponse = {
  tag_uid: string;
  exists: boolean;
  trained_at?: string | null;
  n_chunks?: number | null;
  n_documents?: number | null;
  model_kind?: string | null;
  embedding_model?: string | null;
};
export type Point3D = {
  x: number;
  y: number;
  z: number;
};
export type Point2D = {
  x: number;
  y: number;
};
export type Clusters = {
  d3?: number | null;
  d2?: number | null;
  vector?: number | null;
  distance?: number | null;
};
export type PointMetadata = {
  chunk_order?: number | null;
  chunk_uid?: string | null;
  document_uid?: string | null;
  text?: string | null;
};
export type GraphPoint = {
  point_3d?: Point3D | null;
  point_2d?: Point2D | null;
  clusters?: Clusters | null;
  metadata?: PointMetadata | null;
};
export type ProjectResponse = {
  graph_points: GraphPoint[];
};
export type ProjectRequest = {
  /** Documents UIDs list to project. If None, all chunks will be projected. */
  document_uids?: string[] | null;
  /** Library UIDs list to filter documents before projection. */
  tag_uids?: string[] | null;
  /** Whether to include clustering information in the projection. */
  with_clustering?: boolean | null;
  /** Whether to include documents text in the projection. */
  with_documents?: boolean | null;
};
export type ProjectTextResponse = {
  graph_point: GraphPoint;
};
export type ProjectTextRequest = {
  /** The text to vectorize and project in 3D space. */
  text: string;
};
export type MarkdownContentResponse = {
  content: string;
};
export type AssetMeta = {
  scope: "agents" | "users";
  entity_id: string;
  owner_user_id: string;
  key: string;
  file_name: string;
  content_type: string;
  size: number;
  etag?: string | null;
  modified?: string | null;
  document_uid?: string | null;
  extra?: {
    [key: string]: any;
  };
};
export type BodyUploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPost = {
  /** Binary payload (e.g., .pptx) */
  file: Blob;
  /** Logical asset key (defaults to uploaded filename) */
  key?: string | null;
  /** Force a content-type if needed */
  content_type_override?: string | null;
};
export type AssetListResponse = {
  items: AssetMeta[];
};
export type BodyUploadUserAssetKnowledgeFlowV1UserAssetsUploadPost = {
  /** Binary payload (e.g., .pptx, .pdf) */
  file: Blob;
  /** Logical asset key (defaults to uploaded filename) */
  key?: string | null;
  /** Force a content-type if needed */
  content_type_override?: string | null;
  /** [AGENT USE ONLY] Explicit user ID of the asset owner */
  user_id_override?: string | null;
};
export type BodyUploadUserFileKnowledgeFlowV1StorageUserUploadPost = {
  /** Binary payload */
  file: Blob;
  /** Logical path inside the user's space */
  key?: string | null;
};
export type BodyUploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPost = {
  /** Binary payload */
  file: Blob;
  /** Logical path inside the agent's config space */
  key?: string | null;
};
export type BodyUploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPost = {
  /** Binary payload */
  file: Blob;
  /** Logical path inside the agent-user space */
  key?: string | null;
};
export type ProcessorConfig = {
  /** The file extension this processor handles (e.g., '.pdf') */
  prefix: string;
  /** Dotted import path of the processor class */
  class_path: string;
  /** Human-readable description of the processor purpose shown in the UI. */
  description?: string | null;
};
export type LibraryProcessorConfig = {
  /** Dotted import path of the library output processor class */
  class_path: string;
  /** Human-readable description of the library output processor purpose shown in the UI. */
  description?: string | null;
};
export type AvailableProcessorsResponse = {
  input_processors: ProcessorConfig[];
  output_processors: ProcessorConfig[];
  library_output_processors: LibraryProcessorConfig[];
};
export type ProcessingPipelineDefinition = {
  name: string;
  input_processors?: ProcessorConfig[] | null;
  output_processors: ProcessorConfig[];
  library_output_processors?: LibraryProcessorConfig[] | null;
};
export type PipelineAssignment = {
  library_tag_id: string;
  pipeline_name: string;
};
export type ProcessingPipelineInfo = {
  name: string;
  is_default_for_library: boolean;
  input_processors: ProcessorConfig[];
  output_processors: ProcessorConfig[];
  library_output_processors: LibraryProcessorConfig[];
};
export type BodyUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPost = {
  files: Blob[];
  metadata_json: string;
};
export type BodyProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPost = {
  files: Blob[];
  metadata_json: string;
};
export type DocumentProgress = {
  document_uid: string;
  stages: {
    [key: string]: ProcessingStatus;
  };
  fully_processed?: boolean;
  has_failed?: boolean;
};
export type ProcessDocumentsProgressResponse = {
  total_documents: number;
  documents_found: number;
  documents_missing: number;
  documents_with_preview: number;
  documents_vectorized: number;
  documents_sql_indexed: number;
  documents_fully_processed: number;
  documents_failed: number;
  documents: DocumentProgress[];
};
export type BodyFastMarkdownKnowledgeFlowV1FastTextPost = {
  file: Blob;
  /** JSON string of FastTextOptions */
  options_json?: string | null;
};
export type BodyFastIngestKnowledgeFlowV1FastIngestPost = {
  file: Blob;
  /** JSON string of FastTextOptions */
  options_json?: string | null;
  /** Optional chat session id for scoping */
  session_id?: string | null;
  /** Logical scope label, default 'session' */
  scope?: string;
};
export type TagType = "document" | "prompt" | "template" | "chat-context";
export type TagPermission = "read" | "update" | "delete" | "share" | "owner" | "editor" | "viewer";
export type TagWithPermissions = {
  id: string;
  created_at: string;
  updated_at: string;
  owner_id: string;
  name: string;
  path?: string | null;
  description?: string | null;
  type: TagType;
  item_ids: string[];
  permissions?: TagPermission[];
};
export type OwnerFilter = "personal" | "team";
export type TagWithItemsId = {
  id: string;
  created_at: string;
  updated_at: string;
  owner_id: string;
  name: string;
  path?: string | null;
  description?: string | null;
  type: TagType;
  item_ids: string[];
};
export type TagCreate = {
  name: string;
  path?: string | null;
  description?: string | null;
  type: TagType;
  team_id?: string | null;
};
export type TagUpdate = {
  name: string;
  path?: string | null;
  description?: string | null;
  type: TagType;
  item_ids?: string[];
};
export type UserTagRelation = "owner" | "editor" | "viewer";
export type UserSummary = {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
  username?: string | null;
};
export type TagMemberUser = {
  type?: "user";
  relation: UserTagRelation;
  user: UserSummary;
};
export type TagMembersResponse = {
  users?: TagMemberUser[];
};
export type ShareTargetResource = "user";
export type TagShareRequest = {
  target_id: string;
  target_type: ShareTargetResource;
  relation: UserTagRelation;
};
export type RebacBackfillResponse = {
  rebac_enabled: boolean;
  tags_seen: number;
  documents_seen: number;
  tag_owner_relations_created: number;
  tag_parent_relations_created: number;
};
export type SearchPolicyName = "hybrid" | "strict" | "semantic";
export type EchoEnvelope = {
  kind: "SearchPolicyName";
  /** Schema payload being echoed */
  payload: SearchPolicyName;
};
export type VectorSearchHit = {
  content: string;
  page?: number | null;
  section?: string | null;
  viewer_fragment?: string | null;
  /** Document UID */
  uid: string;
  title: string;
  author?: string | null;
  created?: string | null;
  modified?: string | null;
  file_name?: string | null;
  file_path?: string | null;
  repository?: string | null;
  pull_location?: string | null;
  language?: string | null;
  mime_type?: string | null;
  /** File type/category */
  type?: string | null;
  tag_ids?: string[];
  tag_names?: string[];
  tag_full_paths?: string[];
  preview_url?: string | null;
  preview_at_url?: string | null;
  repo_url?: string | null;
  citation_url?: string | null;
  license?: string | null;
  confidential?: boolean | null;
  /** Similarity score from vector search */
  score: number;
  rank?: number | null;
  embedding_model?: string | null;
  vector_index?: string | null;
  token_count?: number | null;
  retrieved_at?: string | null;
  retrieval_session_id?: string | null;
};
export type SearchRequest = {
  question: string;
  /** Number of results to return. */
  top_k?: number;
  /** Optional list of tag names to filter documents. Only chunks in a document with at least one of these tags will be returned. */
  document_library_tags_ids?: string[] | null;
  /** Optional list of document UIDs to restrict results to specific documents. */
  document_uids?: string[] | null;
  /** Optional search policy preset. If omitted, defaults to 'hybrid'. */
  search_policy?: SearchPolicyName | null;
  /** Optional chat session id to include session-scoped attachments (user/session filtered). */
  session_id?: string | null;
  /** If true and session_id is provided, also search session-scoped attachment vectors (filtered by user/session). */
  include_session_scope?: boolean;
  /** If true, also search corpus/library vectors (non-session scope). */
  include_corpus_scope?: boolean;
};
export type RerankRequest = {
  question: string;
  documents: VectorSearchHit[];
  /** Number of top-reranked chunks to consider */
  top_r?: number;
};
export type KpiQueryResultRow = {
  group: {
    [key: string]: any;
  };
  metrics: {
    [key: string]: number;
  };
  doc_count: number;
};
export type KpiQueryResult = {
  rows?: KpiQueryResultRow[];
};
export type FilterTerm = {
  field:
    | "metric.name"
    | "metric.type"
    | "dims.status"
    | "dims.user_id"
    | "dims.agent_id"
    | "dims.doc_uid"
    | "dims.file_type"
    | "dims.http_status"
    | "dims.error_code"
    | "dims.model"
    | "dims.step"
    | "dims.agent_step"
    | "dims.service";
  value: string;
};
export type SelectMetric = {
  /** name in response, e.g. 'p95' or 'cost_usd' */
  alias: string;
  op: "sum" | "avg" | "min" | "max" | "count" | "value_count" | "percentile";
  /** Required except for count/percentile */
  field?: ("metric.value" | "cost.tokens_total" | "cost.usd" | "cost.tokens_prompt" | "cost.tokens_completion") | null;
  /** Percentile, e.g. 95 */
  p?: number | null;
};
export type TimeBucket = {
  /** e.g. '1h', '1d', '15m' */
  interval: string;
  /** IANA TZ, e.g. 'Europe/Paris' */
  timezone?: string | null;
};
export type OrderBy = {
  by?: "doc_count" | "metric";
  metric_alias?: string | null;
  direction?: "asc" | "desc";
};
export type KpiQuery = {
  /** ISO or 'now-24h' */
  since: string;
  until?: string | null;
  view_global?: boolean;
  filters?: FilterTerm[];
  select: SelectMetric[];
  group_by?: (
    | "dims.file_type"
    | "dims.doc_uid"
    | "dims.doc_source"
    | "dims.user_id"
    | "dims.agent_id"
    | "dims.step"
    | "dims.agent_step"
    | "dims.tool_name"
    | "dims.model"
    | "dims.http_status"
    | "dims.error_code"
    | "dims.status"
    | "dims.service"
  )[];
  time_bucket?: TimeBucket | null;
  limit?: number;
  order_by?: OrderBy | null;
};
export type ResourceKind = "prompt" | "template" | "chat-context";
export type Resource = {
  id: string;
  kind: ResourceKind;
  version: string;
  name?: string | null;
  description?: string | null;
  labels?: string[] | null;
  author: string;
  created_at: string;
  updated_at: string;
  /** Raw YAML text or other content */
  content: string;
  /** List of tags associated with the resource */
  library_tags: string[];
};
export type ResourceCreate = {
  kind: ResourceKind;
  content: string;
  name?: string | null;
  description?: string | null;
  labels?: string[] | null;
};
export type ResourceUpdate = {
  content?: string | null;
  name?: string | null;
  description?: string | null;
  labels?: string[] | null;
};
export type BodyWriteFile = {
  data: string;
};
export type ToolSpecV1 = {
  name: string;
  summary: string;
  request_schema: {
    [key: string]: any;
  };
  async_task?: boolean;
};
export type CorpusCapabilitiesV1 = {
  version?: "v1";
  tools: ToolSpecV1[];
};
export type CorpusScopeV1 = {
  library_id?: string | null;
  project_id?: string | null;
  tag_ids?: string[];
  document_uids?: string[];
  source_tag?: string | null;
};
export type TocBuildOptionsV1 = {
  max_depth?: number;
  max_sections?: number;
  include_gaps?: boolean;
  gap_sensitivity?: "low" | "medium" | "high";
  output_format?: "markdown" | "json" | "both";
  /** e.g. 'fr', 'en' */
  language?: string | null;
};
export type BuildCorpusTocRequestV1 = {
  version?: "v1";
  scope: CorpusScopeV1;
  options?: TocBuildOptionsV1;
  title?: string | null;
  thread_id?: string | null;
  exchange_id?: string | null;
};
export type RevectorizeOptionsV1 = {
  mode?: "full" | "incremental";
  force?: boolean;
  embedding_model?: string | null;
};
export type RevectorizeCorpusRequestV1 = {
  version?: "v1";
  scope: CorpusScopeV1;
  options?: RevectorizeOptionsV1;
  thread_id?: string | null;
  exchange_id?: string | null;
};
export type PurgeVectorsOptionsV1 = {
  purge_scope?: "vectors_only" | "vectors_and_chunks";
  dry_run?: boolean;
};
export type PurgeVectorsRequestV1 = {
  version?: "v1";
  scope: CorpusScopeV1;
  options?: PurgeVectorsOptionsV1;
  thread_id?: string | null;
  exchange_id?: string | null;
};
export type TaskGetRequestV1 = {
  task_id: string;
};
export type TaskResultRequestV1 = {
  task_id: string;
};
export type TaskListRequestV1 = {
  thread_id?: string | null;
  exchange_id?: string | null;
  operation?: string | null;
  status?: ("queued" | "running" | "succeeded" | "failed" | "canceled") | null;
  limit?: number;
};
export type LogEventDto = {
  ts: number;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  logger: string;
  file: string;
  line: number;
  msg: string;
  service?: string | null;
  extra?: {
    [key: string]: any;
  } | null;
};
export type LogQueryResult = {
  events?: LogEventDto[];
};
export type LogFilter = {
  level_at_least?: ("DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL") | null;
  logger_like?: string | null;
  service?: string | null;
  text_like?: string | null;
};
export type LogQuery = {
  /** ISO or 'now-10m' */
  since: string;
  until?: string | null;
  filters?: LogFilter;
  limit?: number;
  order?: "asc" | "desc";
};
export type Team = {
  description?: string | null;
  is_private?: boolean;
  id: string;
  name: string;
  member_count?: number | null;
  owners?: UserSummary[];
  is_member?: boolean;
  banner_image_url?: string | null;
};
export type TeamPermission =
  | "can_read"
  | "can_update_info"
  | "can_update_resources"
  | "can_update_agents"
  | "can_read_members"
  | "can_administer_members"
  | "can_administer_managers"
  | "can_administer_owners";
export type TeamWithPermissions = {
  description?: string | null;
  is_private?: boolean;
  id: string;
  name: string;
  member_count?: number | null;
  owners?: UserSummary[];
  is_member?: boolean;
  banner_image_url?: string | null;
  permissions?: TeamPermission[];
};
export type TeamUpdate = {
  description?: string | null;
  banner_object_storage_key?: string | null;
  is_private?: boolean | null;
};
export type BodyUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPost = {
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
export type UpdateTeamMemberRequest = {
  relation: UserTeamRelation;
};
export type ProcessorDescriptor = {
  id: string;
  name: string;
  kind: "standard" | "fast";
  file_types?: string[];
};
export type ProcessorRunMetrics = {
  chars: number;
  words: number;
  headings: number;
  h1: number;
  h2: number;
  h3: number;
  images: number;
  links: number;
  code_blocks: number;
  table_like_lines: number;
  tokens_est: number;
};
export type ProcessorRunResult = {
  processor_id: string;
  display_name: string;
  kind: "standard" | "fast";
  status: "ok" | "error";
  duration_ms: number;
  markdown?: string | null;
  metrics?: ProcessorRunMetrics | null;
  page_count?: number | null;
  error_message?: string | null;
};
export type BenchmarkResponse = {
  input_filename: string;
  file_type: string;
  results: ProcessorRunResult[];
};
export type BodyRunKnowledgeFlowV1DevBenchRunPost = {
  /** Input document (pdf, docx, …) */
  file: Blob;
  /** Comma-separated processor ids; default by file type */
  processors?: string | null;
  /** Persist the run under the user's benchmark folder */
  persist?: boolean | null;
};
export type SavedRunSummary = {
  id: string;
  input_filename: string;
  file_type: string;
  processors_count: number;
  size?: number | null;
  modified?: string | null;
};
export type ListTablesResponse = {
  db_name: string;
  tables: string[];
};
export type TabularColumnSchema = {
  name: string;
  dtype: "string" | "integer" | "float" | "boolean" | "datetime" | "unknown";
};
export type GetSchemaResponse = {
  db_name: string;
  table_name: string;
  columns: TabularColumnSchema[];
  row_count?: number | null;
};
export type RawSqlResponse = {
  db_name: string;
  sql_query: string;
  rows?:
    | {
        [key: string]: any;
      }[]
    | null;
  error?: string | null;
};
export type RawSqlRequest = {
  query: string;
};
export type SetDatasetRequest = {
  dataset_name: string;
};
export type DetectOutliersRequest = {
  method?: "zscore" | "iqr";
  threshold?: number;
};
export type PlotHistogramRequest = {
  column: string;
  bins?: number;
};
export type PlotScatterRequest = {
  x_col: string;
  y_col: string;
};
export type TrainModelRequest = {
  target: string;
  features: string[];
  model_type?: "linear" | "random_forest";
};
export type PredictRowRequest = {
  row: {
    [key: string]: any;
  };
};
export type SaveModelRequest = {
  name: string;
};
export type LoadModelRequest = {
  name: string;
};
export type DetectOutliersMlRequest = {
  features: string[];
  method?: "isolation_forest" | "lof";
};
export type PcaRequest = {
  features: string[];
  n_components?: number;
};
export type WriteReportResponse = {
  document_uid: string;
  md_url: string;
  html_url?: string | null;
  pdf_url?: string | null;
};
export type WriteReportRequest = {
  /** Report title shown in UI */
  title: string;
  /** Canonical Markdown content (stored as-is) */
  markdown: string;
  /** Optional template identifier for traceability */
  template_id?: string | null;
  /** UI tags (chips) */
  tags?: string[];
  render_formats?: string[];
};
export type ProcessDocumentsResponse = {
  status: string;
  pipeline_name: string;
  total_files: number;
  workflow_id: string;
  run_id?: string | null;
};
export type IngestionProcessingProfile = "fast" | "medium" | "rich";
export type FileToProcessWithoutUser = {
  source_tag: string;
  tags?: string[];
  display_name?: string | null;
  profile?: IngestionProcessingProfile;
  document_uid?: string | null;
  external_path?: string | null;
  size?: number | null;
  modified_time?: number | null;
  hash?: string | null;
};
export type ProcessDocumentsRequest = {
  files: FileToProcessWithoutUser[];
  pipeline_name: string;
};
export type ProcessLibraryResponse = {
  status: string;
  library_tag: string;
  workflow_id: string;
  run_id?: string | null;
  document_count?: number | null;
};
export type ProcessLibraryRequest = {
  library_tag: string;
  processor: string;
  document_uids?: string[] | null;
};
export type ProcessDocumentsProgressRequest = {
  workflow_id?: string | null;
};
export const {
  useHealthzKnowledgeFlowV1HealthzGetQuery,
  useLazyHealthzKnowledgeFlowV1HealthzGetQuery,
  useReadyKnowledgeFlowV1ReadyGetQuery,
  useLazyReadyKnowledgeFlowV1ReadyGetQuery,
  useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation,
  useGetDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGetQuery,
  useLazyGetDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGetQuery,
  useGetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetQuery,
  useLazyGetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetQuery,
  useGetProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGetQuery,
  useLazyGetProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGetQuery,
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation,
  useBrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostMutation,
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
  useDocumentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGetQuery,
  useLazyDocumentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGetQuery,
  useDocumentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGetQuery,
  useLazyDocumentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGetQuery,
  useAuditDocumentsKnowledgeFlowV1DocumentsAuditGetQuery,
  useLazyAuditDocumentsKnowledgeFlowV1DocumentsAuditGetQuery,
  useFixDocumentsKnowledgeFlowV1DocumentsAuditFixPostMutation,
  useGetChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdGetQuery,
  useLazyGetChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdGetQuery,
  useDeleteChunkKnowledgeFlowV1DocumentsDocumentUidChunksChunkIdDeleteMutation,
  useTrainUmapKnowledgeFlowV1ModelsUmapTagIdTrainPostMutation,
  useModelStatusKnowledgeFlowV1ModelsUmapTagUidGetQuery,
  useLazyModelStatusKnowledgeFlowV1ModelsUmapTagUidGetQuery,
  useProjectKnowledgeFlowV1ModelsUmapRefTagUidProjectPostMutation,
  useDeleteModelKnowledgeFlowV1ModelsUmapRefTagUidDeleteMutation,
  useProjectTextKnowledgeFlowV1ModelsUmapRefTagUidProjectTextPostMutation,
  useGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery,
  useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery,
  useDownloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGetQuery,
  useLazyDownloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGetQuery,
  useDownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetQuery,
  useLazyDownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetQuery,
  useStreamDocumentKnowledgeFlowV1RawContentStreamDocumentUidGetQuery,
  useLazyStreamDocumentKnowledgeFlowV1RawContentStreamDocumentUidGetQuery,
  useUploadAgentAssetKnowledgeFlowV1AgentAssetsAgentUploadPostMutation,
  useListAgentAssetsKnowledgeFlowV1AgentAssetsAgentGetQuery,
  useLazyListAgentAssetsKnowledgeFlowV1AgentAssetsAgentGetQuery,
  useGetAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyGetQuery,
  useLazyGetAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyGetQuery,
  useDeleteAgentAssetKnowledgeFlowV1AgentAssetsAgentKeyDeleteMutation,
  useUploadUserAssetKnowledgeFlowV1UserAssetsUploadPostMutation,
  useListUserAssetsKnowledgeFlowV1UserAssetsGetQuery,
  useLazyListUserAssetsKnowledgeFlowV1UserAssetsGetQuery,
  useGetUserAssetKnowledgeFlowV1UserAssetsKeyGetQuery,
  useLazyGetUserAssetKnowledgeFlowV1UserAssetsKeyGetQuery,
  useDeleteUserAssetKnowledgeFlowV1UserAssetsKeyDeleteMutation,
  useUploadUserFileKnowledgeFlowV1StorageUserUploadPostMutation,
  useListUserFilesKnowledgeFlowV1StorageUserGetQuery,
  useLazyListUserFilesKnowledgeFlowV1StorageUserGetQuery,
  useDownloadUserFileKnowledgeFlowV1StorageUserKeyGetQuery,
  useLazyDownloadUserFileKnowledgeFlowV1StorageUserKeyGetQuery,
  useDeleteUserFileKnowledgeFlowV1StorageUserKeyDeleteMutation,
  useUploadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdUploadPostMutation,
  useListAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGetQuery,
  useLazyListAgentConfigFilesKnowledgeFlowV1StorageAgentConfigAgentIdGetQuery,
  useDownloadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyGetQuery,
  useLazyDownloadAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyGetQuery,
  useDeleteAgentConfigFileKnowledgeFlowV1StorageAgentConfigAgentIdKeyDeleteMutation,
  useUploadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdUploadPostMutation,
  useListAgentUserFilesKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdGetQuery,
  useLazyListAgentUserFilesKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdGetQuery,
  useDownloadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyGetQuery,
  useLazyDownloadAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyGetQuery,
  useDeleteAgentUserFileKnowledgeFlowV1StorageAgentUserAgentIdTargetUserIdKeyDeleteMutation,
  useListAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGetQuery,
  useLazyListAvailableProcessorsKnowledgeFlowV1ProcessingPipelinesAvailableProcessorsGetQuery,
  useRegisterProcessingPipelineKnowledgeFlowV1ProcessingPipelinesPostMutation,
  useAssignPipelineToLibraryKnowledgeFlowV1ProcessingPipelinesAssignLibraryPostMutation,
  useGetLibraryPipelineKnowledgeFlowV1ProcessingPipelinesLibraryLibraryTagIdGetQuery,
  useLazyGetLibraryPipelineKnowledgeFlowV1ProcessingPipelinesLibraryLibraryTagIdGetQuery,
  useUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPostMutation,
  useProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPostMutation,
  useGetUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGetQuery,
  useLazyGetUploadProcessDocumentsProgressKnowledgeFlowV1UploadProcessDocumentsProgressGetQuery,
  useFastMarkdownKnowledgeFlowV1FastTextPostMutation,
  useFastIngestKnowledgeFlowV1FastIngestPostMutation,
  useDeleteFastIngestKnowledgeFlowV1FastIngestDocumentUidDeleteMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useLazyListAllTagsKnowledgeFlowV1TagsGetQuery,
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
  useLazyListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
  useShareTagKnowledgeFlowV1TagsTagIdSharePostMutation,
  useUnshareTagKnowledgeFlowV1TagsTagIdShareTargetIdDeleteMutation,
  useBackfillRebacRelationsKnowledgeFlowV1TagsRebacBackfillPostMutation,
  useEchoSchemaKnowledgeFlowV1SchemasEchoPostMutation,
  useSearchDocumentsUsingVectorizationMutation,
  useTestPostSuccessMutation,
  useRerankDocumentsMutation,
  useQueryKnowledgeFlowV1KpiQueryPostMutation,
  useGetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetQuery,
  useLazyGetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetQuery,
  useCreateResourceKnowledgeFlowV1ResourcesPostMutation,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  useLazyListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  useUpdateResourceKnowledgeFlowV1ResourcesResourceIdPutMutation,
  useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
  useLazyGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
  useDeleteResourceKnowledgeFlowV1ResourcesResourceIdDeleteMutation,
  useListFilesQuery,
  useLazyListFilesQuery,
  useStatFileOrDirectoryQuery,
  useLazyStatFileOrDirectoryQuery,
  useCatFileQuery,
  useLazyCatFileQuery,
  useWriteFileMutation,
  useDeleteFileMutation,
  useGrepFileRegexQuery,
  useLazyGrepFileRegexQuery,
  usePrintRootDirectoryQuery,
  useLazyPrintRootDirectoryQuery,
  useCreateDirectoryMutation,
  useCorpusCapabilitiesQuery,
  useLazyCorpusCapabilitiesQuery,
  useCorpusBuildTocMutation,
  useCorpusRevectorizeMutation,
  useCorpusPurgeVectorsMutation,
  useCorpusTasksGetMutation,
  useCorpusTasksResultMutation,
  useCorpusTasksListMutation,
  useQueryLogsKnowledgeFlowV1LogsQueryPostMutation,
  useListTeamsKnowledgeFlowV1TeamsGetQuery,
  useLazyListTeamsKnowledgeFlowV1TeamsGetQuery,
  useGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery,
  useLazyGetTeamKnowledgeFlowV1TeamsTeamIdGetQuery,
  useUpdateTeamKnowledgeFlowV1TeamsTeamIdPatchMutation,
  useUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPostMutation,
  useListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetQuery,
  useLazyListTeamMembersKnowledgeFlowV1TeamsTeamIdMembersGetQuery,
  useAddTeamMemberKnowledgeFlowV1TeamsTeamIdMembersPostMutation,
  useRemoveTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdDeleteMutation,
  useUpdateTeamMemberKnowledgeFlowV1TeamsTeamIdMembersUserIdPatchMutation,
  useListUsersKnowledgeFlowV1UsersGetQuery,
  useLazyListUsersKnowledgeFlowV1UsersGetQuery,
  useListProcessorsKnowledgeFlowV1DevBenchProcessorsGetQuery,
  useLazyListProcessorsKnowledgeFlowV1DevBenchProcessorsGetQuery,
  useRunKnowledgeFlowV1DevBenchRunPostMutation,
  useListRunsKnowledgeFlowV1DevBenchRunsGetQuery,
  useLazyListRunsKnowledgeFlowV1DevBenchRunsGetQuery,
  useGetRunKnowledgeFlowV1DevBenchRunsRunIdGetQuery,
  useLazyGetRunKnowledgeFlowV1DevBenchRunsRunIdGetQuery,
  useDeleteRunKnowledgeFlowV1DevBenchRunsRunIdDeleteMutation,
  useListDatabasesQuery,
  useLazyListDatabasesQuery,
  useListTablesQuery,
  useLazyListTablesQuery,
  useGetDatabaseSchemasQuery,
  useLazyGetDatabaseSchemasQuery,
  useDescribeTableQuery,
  useLazyDescribeTableQuery,
  useGetContextQuery,
  useLazyGetContextQuery,
  useReadQueryMutation,
  useExecuteWriteQueryMutation,
  useDeleteTableMutation,
  useListDatasetsQuery,
  useLazyListDatasetsQuery,
  useSetDatasetMutation,
  useHeadQuery,
  useLazyHeadQuery,
  useDescribeQuery,
  useLazyDescribeQuery,
  useDetectOutliersMutation,
  useCorrelationsQuery,
  useLazyCorrelationsQuery,
  usePlotHistogramMutation,
  usePlotScatterMutation,
  useTrainModelMutation,
  useEvaluateModelQuery,
  useLazyEvaluateModelQuery,
  usePredictRowMutation,
  useSaveModelMutation,
  useListModelsQuery,
  useLazyListModelsQuery,
  useLoadModelMutation,
  useTestDistributionQuery,
  useLazyTestDistributionQuery,
  useDetectOutliersMlMutation,
  useRunPcaMutation,
  useWriteReportKnowledgeFlowV1McpReportsWritePostMutation,
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
  useProcessLibraryKnowledgeFlowV1ProcessLibraryPostMutation,
  useProcessDocumentsProgressKnowledgeFlowV1ProcessDocumentsProgressPostMutation,
} = injectedRtkApi;
