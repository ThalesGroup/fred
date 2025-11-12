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
    listCatalogFilesKnowledgeFlowV1PullCatalogFilesGet: build.query<
      ListCatalogFilesKnowledgeFlowV1PullCatalogFilesGetApiResponse,
      ListCatalogFilesKnowledgeFlowV1PullCatalogFilesGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/pull/catalog/files`,
        params: {
          source_tag: queryArg.sourceTag,
          offset: queryArg.offset,
          limit: queryArg.limit,
        },
      }),
    }),
    rescanCatalogSourceKnowledgeFlowV1PullCatalogRescanSourceTagPost: build.mutation<
      RescanCatalogSourceKnowledgeFlowV1PullCatalogRescanSourceTagPostApiResponse,
      RescanCatalogSourceKnowledgeFlowV1PullCatalogRescanSourceTagPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/pull/catalog/rescan/${queryArg.sourceTag}`, method: "POST" }),
    }),
    listDocumentSourcesKnowledgeFlowV1DocumentsSourcesGet: build.query<
      ListDocumentSourcesKnowledgeFlowV1DocumentsSourcesGetApiResponse,
      ListDocumentSourcesKnowledgeFlowV1DocumentsSourcesGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/documents/sources` }),
    }),
    listPullDocumentsKnowledgeFlowV1PullDocumentsGet: build.query<
      ListPullDocumentsKnowledgeFlowV1PullDocumentsGetApiResponse,
      ListPullDocumentsKnowledgeFlowV1PullDocumentsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/pull/documents`,
        params: {
          source_tag: queryArg.sourceTag,
          offset: queryArg.offset,
          limit: queryArg.limit,
        },
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
    lightweightMarkdownKnowledgeFlowV1LiteMarkdownPost: build.mutation<
      LightweightMarkdownKnowledgeFlowV1LiteMarkdownPostApiResponse,
      LightweightMarkdownKnowledgeFlowV1LiteMarkdownPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/lite/markdown`,
        method: "POST",
        body: queryArg.bodyLightweightMarkdownKnowledgeFlowV1LiteMarkdownPost,
        params: {
          format: queryArg.format,
        },
      }),
    }),
    listTabularDatabases: build.query<ListTabularDatabasesApiResponse, ListTabularDatabasesApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/databases` }),
    }),
    loadTabularDatabase: build.mutation<LoadTabularDatabaseApiResponse, LoadTabularDatabaseApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/load/${queryArg.dbName}`, method: "POST" }),
    }),
    listTablesLoadedDb: build.query<ListTablesLoadedDbApiResponse, ListTablesLoadedDbApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/tables` }),
    }),
    listAllTableSchemasLoadedDb: build.query<ListAllTableSchemasLoadedDbApiResponse, ListAllTableSchemasLoadedDbApiArg>(
      {
        query: () => ({ url: `/knowledge-flow/v1/tabular/schemas` }),
      },
    ),
    getTableSchemaLoadedDb: build.query<GetTableSchemaLoadedDbApiResponse, GetTableSchemaLoadedDbApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/tables/${queryArg.tableName}/schema` }),
    }),
    tabularSqlReadLoadedDb: build.mutation<TabularSqlReadLoadedDbApiResponse, TabularSqlReadLoadedDbApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/sql/read`,
        method: "POST",
        body: queryArg.rawSqlRequest,
      }),
    }),
    tabularSqlWriteLoadedDb: build.mutation<TabularSqlWriteLoadedDbApiResponse, TabularSqlWriteLoadedDbApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/sql/write`,
        method: "POST",
        body: queryArg.rawSqlRequest,
      }),
    }),
    deleteTableLoadedDb: build.mutation<DeleteTableLoadedDbApiResponse, DeleteTableLoadedDbApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/tables/${queryArg.tableName}`, method: "DELETE" }),
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
    getTagPermissionsKnowledgeFlowV1TagsTagIdPermissionsGet: build.query<
      GetTagPermissionsKnowledgeFlowV1TagsTagIdPermissionsGetApiResponse,
      GetTagPermissionsKnowledgeFlowV1TagsTagIdPermissionsGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tags/${queryArg.tagId}/permissions` }),
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
    queryKnowledgeFlowV1KpiQueryPost: build.mutation<
      QueryKnowledgeFlowV1KpiQueryPostApiResponse,
      QueryKnowledgeFlowV1KpiQueryPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/kpi/query`, method: "POST", body: queryArg.kpiQuery }),
    }),
    osHealth: build.query<OsHealthApiResponse, OsHealthApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/os/health` }),
    }),
    osPendingTasks: build.query<OsPendingTasksApiResponse, OsPendingTasksApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/os/pending_tasks` }),
    }),
    osAllocationExplain: build.query<OsAllocationExplainApiResponse, OsAllocationExplainApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/os/allocation/explain`,
        params: {
          index: queryArg.index,
          shard: queryArg.shard,
          primary: queryArg.primary,
          include_disk_info: queryArg.includeDiskInfo,
        },
      }),
    }),
    osNodesStats: build.query<OsNodesStatsApiResponse, OsNodesStatsApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/os/nodes/stats`,
        params: {
          metric: queryArg.metric,
        },
      }),
    }),
    osIndices: build.query<OsIndicesApiResponse, OsIndicesApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/os/indices`,
        params: {
          pattern: queryArg.pattern,
          bytes: queryArg.bytes,
        },
      }),
    }),
    osIndexStats: build.query<OsIndexStatsApiResponse, OsIndexStatsApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/os/index/${queryArg.index}/stats` }),
    }),
    osIndexMapping: build.query<OsIndexMappingApiResponse, OsIndexMappingApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/os/index/${queryArg.index}/mapping` }),
    }),
    osIndexSettings: build.query<OsIndexSettingsApiResponse, OsIndexSettingsApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/os/index/${queryArg.index}/settings` }),
    }),
    osShards: build.query<OsShardsApiResponse, OsShardsApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/os/shards`,
        params: {
          pattern: queryArg.pattern,
        },
      }),
    }),
    osDiagnostics: build.query<OsDiagnosticsApiResponse, OsDiagnosticsApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/os/diagnostics` }),
    }),
    queryLogsKnowledgeFlowV1LogsQueryPost: build.mutation<
      QueryLogsKnowledgeFlowV1LogsQueryPostApiResponse,
      QueryLogsKnowledgeFlowV1LogsQueryPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/logs/query`, method: "POST", body: queryArg.logQuery }),
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
    listGroupsKnowledgeFlowV1GroupsGet: build.query<
      ListGroupsKnowledgeFlowV1GroupsGetApiResponse,
      ListGroupsKnowledgeFlowV1GroupsGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/groups` }),
    }),
    listUsersKnowledgeFlowV1UsersGet: build.query<
      ListUsersKnowledgeFlowV1UsersGetApiResponse,
      ListUsersKnowledgeFlowV1UsersGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/users` }),
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
    scheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPost: build.mutation<
      ScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostApiResponse,
      ScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/schedule-documents`,
        method: "POST",
        body: queryArg.processDocumentsRequest,
      }),
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
export type UpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutApiResponse =
  /** status 200 Successful Response */ any;
export type UpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutApiArg = {
  documentUid: string;
  retrievable: boolean;
};
export type BrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostApiResponse =
  /** status 200 Successful Response */ PullDocumentsResponse;
export type BrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostApiArg = {
  browseDocumentsRequest: BrowseDocumentsRequest;
};
export type ListCatalogFilesKnowledgeFlowV1PullCatalogFilesGetApiResponse =
  /** status 200 Successful Response */ PullFileEntry[];
export type ListCatalogFilesKnowledgeFlowV1PullCatalogFilesGetApiArg = {
  /** The source tag for the cataloged files */
  sourceTag: string;
  /** Number of entries to skip */
  offset?: number;
  /** Max number of entries to return */
  limit?: number;
};
export type RescanCatalogSourceKnowledgeFlowV1PullCatalogRescanSourceTagPostApiResponse =
  /** status 200 Successful Response */ any;
export type RescanCatalogSourceKnowledgeFlowV1PullCatalogRescanSourceTagPostApiArg = {
  sourceTag: string;
};
export type ListDocumentSourcesKnowledgeFlowV1DocumentsSourcesGetApiResponse =
  /** status 200 Successful Response */ DocumentSourceInfo[];
export type ListDocumentSourcesKnowledgeFlowV1DocumentsSourcesGetApiArg = void;
export type ListPullDocumentsKnowledgeFlowV1PullDocumentsGetApiResponse =
  /** status 200 Successful Response */ PullDocumentsResponse;
export type ListPullDocumentsKnowledgeFlowV1PullDocumentsGetApiArg = {
  /** The pull source tag to list documents from */
  sourceTag: string;
  /** Start offset for pagination */
  offset?: number;
  /** Maximum number of documents to return */
  limit?: number;
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
export type LightweightMarkdownKnowledgeFlowV1LiteMarkdownPostApiResponse = /** status 200 Successful Response */ any;
export type LightweightMarkdownKnowledgeFlowV1LiteMarkdownPostApiArg = {
  /** Response format: 'json' or 'text' */
  format?: string;
  bodyLightweightMarkdownKnowledgeFlowV1LiteMarkdownPost: BodyLightweightMarkdownKnowledgeFlowV1LiteMarkdownPost;
};
export type ListTabularDatabasesApiResponse = /** status 200 Successful Response */ string[];
export type ListTabularDatabasesApiArg = void;
export type LoadTabularDatabaseApiResponse = /** status 200 Successful Response */ any;
export type LoadTabularDatabaseApiArg = {
  /** Name of the database to load */
  dbName: string;
};
export type ListTablesLoadedDbApiResponse = /** status 200 Successful Response */ ListTableResponse;
export type ListTablesLoadedDbApiArg = void;
export type ListAllTableSchemasLoadedDbApiResponse = /** status 200 Successful Response */ TabularSchemaResponse[];
export type ListAllTableSchemasLoadedDbApiArg = void;
export type GetTableSchemaLoadedDbApiResponse = /** status 200 Successful Response */ TabularSchemaResponse;
export type GetTableSchemaLoadedDbApiArg = {
  /** Name of the table */
  tableName: string;
};
export type TabularSqlReadLoadedDbApiResponse = /** status 200 Successful Response */ TabularQueryResponse;
export type TabularSqlReadLoadedDbApiArg = {
  rawSqlRequest: RawSqlRequest;
};
export type TabularSqlWriteLoadedDbApiResponse = /** status 200 Successful Response */ TabularQueryResponse;
export type TabularSqlWriteLoadedDbApiArg = {
  rawSqlRequest: RawSqlRequest;
};
export type DeleteTableLoadedDbApiResponse = unknown;
export type DeleteTableLoadedDbApiArg = {
  /** Table name to delete */
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
export type ListAllTagsKnowledgeFlowV1TagsGetApiResponse = /** status 200 Successful Response */ TagWithItemsId[];
export type ListAllTagsKnowledgeFlowV1TagsGetApiArg = {
  /** Filter by tag type */
  type?: TagType | null;
  /** Filter by hierarchical path prefix, e.g. 'Sales' or 'Sales/HR' */
  pathPrefix?: string | null;
  /** Max items to return */
  limit?: number;
  /** Items to skip */
  offset?: number;
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
export type GetTagPermissionsKnowledgeFlowV1TagsTagIdPermissionsGetApiResponse =
  /** status 200 Successful Response */ TagPermissionsResponse;
export type GetTagPermissionsKnowledgeFlowV1TagsTagIdPermissionsGetApiArg = {
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
export type QueryKnowledgeFlowV1KpiQueryPostApiResponse = /** status 200 Successful Response */ KpiQueryResult;
export type QueryKnowledgeFlowV1KpiQueryPostApiArg = {
  kpiQuery: KpiQuery;
};
export type OsHealthApiResponse = /** status 200 Successful Response */ any;
export type OsHealthApiArg = void;
export type OsPendingTasksApiResponse = /** status 200 Successful Response */ any;
export type OsPendingTasksApiArg = void;
export type OsAllocationExplainApiResponse = /** status 200 Successful Response */ any;
export type OsAllocationExplainApiArg = {
  /** Index name (optional) */
  index?: string | null;
  /** Shard number (optional) */
  shard?: number | null;
  /** Whether primary shard (optional) */
  primary?: boolean | null;
  /** Include disk info in explanation */
  includeDiskInfo?: boolean;
};
export type OsNodesStatsApiResponse = /** status 200 Successful Response */ any;
export type OsNodesStatsApiArg = {
  metric?: string;
};
export type OsIndicesApiResponse = /** status 200 Successful Response */ any;
export type OsIndicesApiArg = {
  pattern?: string;
  bytes?: string;
};
export type OsIndexStatsApiResponse = /** status 200 Successful Response */ any;
export type OsIndexStatsApiArg = {
  index: string;
};
export type OsIndexMappingApiResponse = /** status 200 Successful Response */ any;
export type OsIndexMappingApiArg = {
  index: string;
};
export type OsIndexSettingsApiResponse = /** status 200 Successful Response */ any;
export type OsIndexSettingsApiArg = {
  index: string;
};
export type OsShardsApiResponse = /** status 200 Successful Response */ any;
export type OsShardsApiArg = {
  pattern?: string;
};
export type OsDiagnosticsApiResponse = /** status 200 Successful Response */ any;
export type OsDiagnosticsApiArg = void;
export type QueryLogsKnowledgeFlowV1LogsQueryPostApiResponse = /** status 200 Successful Response */ LogQueryResult;
export type QueryLogsKnowledgeFlowV1LogsQueryPostApiArg = {
  logQuery: LogQuery;
};
export type WriteReportKnowledgeFlowV1McpReportsWritePostApiResponse =
  /** status 200 Successful Response */ WriteReportResponse;
export type WriteReportKnowledgeFlowV1McpReportsWritePostApiArg = {
  writeReportRequest: WriteReportRequest;
};
export type ListGroupsKnowledgeFlowV1GroupsGetApiResponse = /** status 200 Successful Response */ GroupSummary[];
export type ListGroupsKnowledgeFlowV1GroupsGetApiArg = void;
export type ListUsersKnowledgeFlowV1UsersGetApiResponse = /** status 200 Successful Response */ UserSummary[];
export type ListUsersKnowledgeFlowV1UsersGetApiArg = void;
export type ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiResponse = /** status 200 Successful Response */ any;
export type ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiArg = {
  processDocumentsRequest: ProcessDocumentsRequest;
};
export type ScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostApiResponse =
  /** status 200 Successful Response */ any;
export type ScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostApiArg = {
  processDocumentsRequest: ProcessDocumentsRequest;
};
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
export type Identity = {
  /** Original file name incl. extension */
  document_name: string;
  /** Stable unique id across the system */
  document_uid: string;
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
export type PullDocumentsResponse = {
  total: number;
  documents: DocumentMetadata[];
};
export type SortOption = {
  field: string;
  direction: "asc" | "desc";
};
export type BrowseDocumentsRequest = {
  /** Tag of the document source to browse (pull or push) */
  source_tag: string;
  /** Optional metadata filters */
  filters?: {
    [key: string]: any;
  } | null;
  offset?: number;
  limit?: number;
  sort_by?: SortOption[] | null;
};
export type PullFileEntry = {
  path: string;
  size: number;
  modified_time: number;
  hash: string;
};
export type DocumentSourceInfo = {
  tag: string;
  type: "push" | "pull";
  provider?: string | null;
  description: string;
  catalog_supported?: boolean | null;
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
export type BodyUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPost = {
  files: Blob[];
  metadata_json: string;
};
export type BodyProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPost = {
  files: Blob[];
  metadata_json: string;
};
export type BodyLightweightMarkdownKnowledgeFlowV1LiteMarkdownPost = {
  file: Blob;
  /** JSON string of LiteMarkdownOptions */
  options_json?: string | null;
};
export type ListTableResponse = {
  db_name: string;
  tables: string[];
};
export type TabularColumnSchema = {
  name: string;
  dtype: "string" | "integer" | "float" | "boolean" | "datetime" | "unknown";
};
export type TabularSchemaResponse = {
  db_name: string;
  table_name: string;
  columns: TabularColumnSchema[];
  row_count?: number | null;
};
export type TabularQueryResponse = {
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
export type TagType = "document" | "prompt" | "template" | "chat-context";
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
};
export type TagUpdate = {
  name: string;
  path?: string | null;
  description?: string | null;
  type: TagType;
  item_ids?: string[];
};
export type TagPermission = "read" | "update" | "delete" | "share";
export type TagPermissionsResponse = {
  permissions: TagPermission[];
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
export type GroupSummary = {
  id: string;
  name: string;
  member_count?: number | null;
  total_member_count?: number | null;
  sub_groups?: GroupSummary[];
};
export type TagMemberGroup = {
  type?: "group";
  relation: UserTagRelation;
  group: GroupSummary;
};
export type TagMembersResponse = {
  users?: TagMemberUser[];
  groups?: TagMemberGroup[];
};
export type ShareTargetResource = "user" | "group";
export type TagShareRequest = {
  target_id: string;
  target_type: ShareTargetResource;
  relation: UserTagRelation;
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
export type SearchPolicy = {
  k_final?: number;
  fetch_k?: number;
  vector_min_cosine?: number;
  bm25_min_score?: number;
  require_phrase_hit?: boolean;
  use_mmr?: boolean;
};
export type SearchPolicyName = "hybrid" | "strict" | "semantic";
export type EchoEnvelope = {
  kind: "SearchPolicy" | "SearchPolicyName";
  /** Schema payload being echoed */
  payload: SearchPolicy | SearchPolicyName;
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
  /** Optional search policy preset. If omitted, defaults to 'hybrid'. */
  search_policy?: SearchPolicyName | null;
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
    | "dims.model";
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
  filters?: FilterTerm[];
  select: SelectMetric[];
  group_by?: (
    | "dims.file_type"
    | "dims.doc_uid"
    | "dims.doc_source"
    | "dims.user_id"
    | "dims.agent_id"
    | "dims.tool_name"
    | "dims.model"
    | "dims.http_status"
    | "dims.error_code"
    | "dims.status"
  )[];
  time_bucket?: TimeBucket | null;
  limit?: number;
  order_by?: OrderBy | null;
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
export type FileToProcessWithoutUser = {
  source_tag: string;
  tags?: string[];
  display_name?: string | null;
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
export type ProcessorDescriptor = {
  id: string;
  name: string;
  kind: "standard" | "lite";
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
  kind: "standard" | "lite";
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
export const {
  useHealthzKnowledgeFlowV1HealthzGetQuery,
  useLazyHealthzKnowledgeFlowV1HealthzGetQuery,
  useReadyKnowledgeFlowV1ReadyGetQuery,
  useLazyReadyKnowledgeFlowV1ReadyGetQuery,
  useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation,
  useGetDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGetQuery,
  useLazyGetDocumentMetadataKnowledgeFlowV1DocumentsMetadataDocumentUidGetQuery,
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation,
  useBrowseDocumentsKnowledgeFlowV1DocumentsBrowsePostMutation,
  useListCatalogFilesKnowledgeFlowV1PullCatalogFilesGetQuery,
  useLazyListCatalogFilesKnowledgeFlowV1PullCatalogFilesGetQuery,
  useRescanCatalogSourceKnowledgeFlowV1PullCatalogRescanSourceTagPostMutation,
  useListDocumentSourcesKnowledgeFlowV1DocumentsSourcesGetQuery,
  useLazyListDocumentSourcesKnowledgeFlowV1DocumentsSourcesGetQuery,
  useListPullDocumentsKnowledgeFlowV1PullDocumentsGetQuery,
  useLazyListPullDocumentsKnowledgeFlowV1PullDocumentsGetQuery,
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
  useUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPostMutation,
  useProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPostMutation,
  useLightweightMarkdownKnowledgeFlowV1LiteMarkdownPostMutation,
  useListTabularDatabasesQuery,
  useLazyListTabularDatabasesQuery,
  useLoadTabularDatabaseMutation,
  useListTablesLoadedDbQuery,
  useLazyListTablesLoadedDbQuery,
  useListAllTableSchemasLoadedDbQuery,
  useLazyListAllTableSchemasLoadedDbQuery,
  useGetTableSchemaLoadedDbQuery,
  useLazyGetTableSchemaLoadedDbQuery,
  useTabularSqlReadLoadedDbMutation,
  useTabularSqlWriteLoadedDbMutation,
  useDeleteTableLoadedDbMutation,
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
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useLazyListAllTagsKnowledgeFlowV1TagsGetQuery,
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useGetTagPermissionsKnowledgeFlowV1TagsTagIdPermissionsGetQuery,
  useLazyGetTagPermissionsKnowledgeFlowV1TagsTagIdPermissionsGetQuery,
  useListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
  useLazyListTagMembersKnowledgeFlowV1TagsTagIdMembersGetQuery,
  useShareTagKnowledgeFlowV1TagsTagIdSharePostMutation,
  useUnshareTagKnowledgeFlowV1TagsTagIdShareTargetIdDeleteMutation,
  useGetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetQuery,
  useLazyGetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetQuery,
  useCreateResourceKnowledgeFlowV1ResourcesPostMutation,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  useLazyListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  useUpdateResourceKnowledgeFlowV1ResourcesResourceIdPutMutation,
  useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
  useLazyGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
  useDeleteResourceKnowledgeFlowV1ResourcesResourceIdDeleteMutation,
  useEchoSchemaKnowledgeFlowV1SchemasEchoPostMutation,
  useSearchDocumentsUsingVectorizationMutation,
  useTestPostSuccessMutation,
  useQueryKnowledgeFlowV1KpiQueryPostMutation,
  useOsHealthQuery,
  useLazyOsHealthQuery,
  useOsPendingTasksQuery,
  useLazyOsPendingTasksQuery,
  useOsAllocationExplainQuery,
  useLazyOsAllocationExplainQuery,
  useOsNodesStatsQuery,
  useLazyOsNodesStatsQuery,
  useOsIndicesQuery,
  useLazyOsIndicesQuery,
  useOsIndexStatsQuery,
  useLazyOsIndexStatsQuery,
  useOsIndexMappingQuery,
  useLazyOsIndexMappingQuery,
  useOsIndexSettingsQuery,
  useLazyOsIndexSettingsQuery,
  useOsShardsQuery,
  useLazyOsShardsQuery,
  useOsDiagnosticsQuery,
  useLazyOsDiagnosticsQuery,
  useQueryLogsKnowledgeFlowV1LogsQueryPostMutation,
  useWriteReportKnowledgeFlowV1McpReportsWritePostMutation,
  useListGroupsKnowledgeFlowV1GroupsGetQuery,
  useLazyListGroupsKnowledgeFlowV1GroupsGetQuery,
  useListUsersKnowledgeFlowV1UsersGetQuery,
  useLazyListUsersKnowledgeFlowV1UsersGetQuery,
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
  useScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostMutation,
  useListProcessorsKnowledgeFlowV1DevBenchProcessorsGetQuery,
  useLazyListProcessorsKnowledgeFlowV1DevBenchProcessorsGetQuery,
  useRunKnowledgeFlowV1DevBenchRunPostMutation,
  useListRunsKnowledgeFlowV1DevBenchRunsGetQuery,
  useLazyListRunsKnowledgeFlowV1DevBenchRunsGetQuery,
  useGetRunKnowledgeFlowV1DevBenchRunsRunIdGetQuery,
  useLazyGetRunKnowledgeFlowV1DevBenchRunsRunIdGetQuery,
  useDeleteRunKnowledgeFlowV1DevBenchRunsRunIdDeleteMutation,
} = injectedRtkApi;
