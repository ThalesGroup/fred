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
    listTabularDatabases: build.query<ListTabularDatabasesApiResponse, ListTabularDatabasesApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/databases` }),
    }),
    listTableNames: build.query<ListTableNamesApiResponse, ListTableNamesApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/${queryArg.dbName}/tables` }),
    }),
    getAllSchemas: build.query<GetAllSchemasApiResponse, GetAllSchemasApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/${queryArg.dbName}/schemas` }),
    }),
    rawSqlQuery: build.mutation<RawSqlQueryApiResponse, RawSqlQueryApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/${queryArg.dbName}/sql`,
        method: "POST",
        body: queryArg.rawSqlRequest,
      }),
    }),
    deleteTable: build.mutation<DeleteTableApiResponse, DeleteTableApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/${queryArg.dbName}/tables/${queryArg.tableName}`,
        method: "DELETE",
      }),
    }),
    listDatasetsKnowledgeFlowV1StatListDatasetsGet: build.query<
      ListDatasetsKnowledgeFlowV1StatListDatasetsGetApiResponse,
      ListDatasetsKnowledgeFlowV1StatListDatasetsGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/stat/list_datasets` }),
    }),
    setDatasetKnowledgeFlowV1StatSetDatasetPost: build.mutation<
      SetDatasetKnowledgeFlowV1StatSetDatasetPostApiResponse,
      SetDatasetKnowledgeFlowV1StatSetDatasetPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/set_dataset`,
        method: "POST",
        body: queryArg.setDatasetRequest,
      }),
    }),
    headKnowledgeFlowV1StatHeadGet: build.query<
      HeadKnowledgeFlowV1StatHeadGetApiResponse,
      HeadKnowledgeFlowV1StatHeadGetApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/head`,
        params: {
          n: queryArg.n,
        },
      }),
    }),
    describeKnowledgeFlowV1StatDescribeGet: build.query<
      DescribeKnowledgeFlowV1StatDescribeGetApiResponse,
      DescribeKnowledgeFlowV1StatDescribeGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/stat/describe` }),
    }),
    detectOutliersKnowledgeFlowV1StatDetectOutliersPost: build.mutation<
      DetectOutliersKnowledgeFlowV1StatDetectOutliersPostApiResponse,
      DetectOutliersKnowledgeFlowV1StatDetectOutliersPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/detect_outliers`,
        method: "POST",
        body: queryArg.detectOutliersRequest,
      }),
    }),
    correlationsKnowledgeFlowV1StatCorrelationsGet: build.query<
      CorrelationsKnowledgeFlowV1StatCorrelationsGetApiResponse,
      CorrelationsKnowledgeFlowV1StatCorrelationsGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/stat/correlations`, body: queryArg.correlationsRequest }),
    }),
    plotHistogramKnowledgeFlowV1StatPlotHistogramPost: build.mutation<
      PlotHistogramKnowledgeFlowV1StatPlotHistogramPostApiResponse,
      PlotHistogramKnowledgeFlowV1StatPlotHistogramPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/plot/histogram`,
        method: "POST",
        body: queryArg.plotHistogramRequest,
      }),
    }),
    plotScatterKnowledgeFlowV1StatPlotScatterPost: build.mutation<
      PlotScatterKnowledgeFlowV1StatPlotScatterPostApiResponse,
      PlotScatterKnowledgeFlowV1StatPlotScatterPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/plot/scatter`,
        method: "POST",
        body: queryArg.plotScatterRequest,
      }),
    }),
    trainModelKnowledgeFlowV1StatTrainPost: build.mutation<
      TrainModelKnowledgeFlowV1StatTrainPostApiResponse,
      TrainModelKnowledgeFlowV1StatTrainPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/stat/train`, method: "POST", body: queryArg.trainModelRequest }),
    }),
    evaluateModelKnowledgeFlowV1StatEvaluateGet: build.query<
      EvaluateModelKnowledgeFlowV1StatEvaluateGetApiResponse,
      EvaluateModelKnowledgeFlowV1StatEvaluateGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/stat/evaluate` }),
    }),
    predictRowKnowledgeFlowV1StatPredictRowPost: build.mutation<
      PredictRowKnowledgeFlowV1StatPredictRowPostApiResponse,
      PredictRowKnowledgeFlowV1StatPredictRowPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/predict_row`,
        method: "POST",
        body: queryArg.predictRowRequest,
      }),
    }),
    saveModelKnowledgeFlowV1StatSaveModelPost: build.mutation<
      SaveModelKnowledgeFlowV1StatSaveModelPostApiResponse,
      SaveModelKnowledgeFlowV1StatSaveModelPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/save_model`,
        method: "POST",
        body: queryArg.saveModelRequest,
      }),
    }),
    listModelsKnowledgeFlowV1StatListModelsGet: build.query<
      ListModelsKnowledgeFlowV1StatListModelsGetApiResponse,
      ListModelsKnowledgeFlowV1StatListModelsGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/stat/list_models` }),
    }),
    loadModelKnowledgeFlowV1StatLoadModelPost: build.mutation<
      LoadModelKnowledgeFlowV1StatLoadModelPostApiResponse,
      LoadModelKnowledgeFlowV1StatLoadModelPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/stat/load_model`,
        method: "POST",
        body: queryArg.loadModelRequest,
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
    searchDocumentsUsingVectorization: build.mutation<
      SearchDocumentsUsingVectorizationApiResponse,
      SearchDocumentsUsingVectorizationApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/vector/search`, method: "POST", body: queryArg.searchRequest }),
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
  /** status 200 Binary file stream */ any;
export type DownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetApiArg = {
  documentUid: string;
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
export type ListTabularDatabasesApiResponse = /** status 200 Successful Response */ string[];
export type ListTabularDatabasesApiArg = void;
export type ListTableNamesApiResponse = /** status 200 Successful Response */ string[];
export type ListTableNamesApiArg = {
  /** Name of the tabular database */
  dbName: string;
};
export type GetAllSchemasApiResponse = /** status 200 Successful Response */ TabularSchemaResponse[];
export type GetAllSchemasApiArg = {
  /** Name of the tabular database */
  dbName: string;
};
export type RawSqlQueryApiResponse = /** status 200 Successful Response */ TabularQueryResponse;
export type RawSqlQueryApiArg = {
  /** Name of the tabular database */
  dbName: string;
  rawSqlRequest: RawSqlRequest;
};
export type DeleteTableApiResponse = unknown;
export type DeleteTableApiArg = {
  /** Name of the tabular database */
  dbName: string;
  /** Table name to delete */
  tableName: string;
};
export type ListDatasetsKnowledgeFlowV1StatListDatasetsGetApiResponse = /** status 200 Successful Response */ any;
export type ListDatasetsKnowledgeFlowV1StatListDatasetsGetApiArg = void;
export type SetDatasetKnowledgeFlowV1StatSetDatasetPostApiResponse = /** status 200 Successful Response */ any;
export type SetDatasetKnowledgeFlowV1StatSetDatasetPostApiArg = {
  setDatasetRequest: SetDatasetRequest;
};
export type HeadKnowledgeFlowV1StatHeadGetApiResponse = /** status 200 Successful Response */ any;
export type HeadKnowledgeFlowV1StatHeadGetApiArg = {
  n?: number;
};
export type DescribeKnowledgeFlowV1StatDescribeGetApiResponse = /** status 200 Successful Response */ any;
export type DescribeKnowledgeFlowV1StatDescribeGetApiArg = void;
export type DetectOutliersKnowledgeFlowV1StatDetectOutliersPostApiResponse = /** status 200 Successful Response */ any;
export type DetectOutliersKnowledgeFlowV1StatDetectOutliersPostApiArg = {
  detectOutliersRequest: DetectOutliersRequest;
};
export type CorrelationsKnowledgeFlowV1StatCorrelationsGetApiResponse = /** status 200 Successful Response */ any;
export type CorrelationsKnowledgeFlowV1StatCorrelationsGetApiArg = {
  correlationsRequest: CorrelationsRequest;
};
export type PlotHistogramKnowledgeFlowV1StatPlotHistogramPostApiResponse = /** status 200 Successful Response */ any;
export type PlotHistogramKnowledgeFlowV1StatPlotHistogramPostApiArg = {
  plotHistogramRequest: PlotHistogramRequest;
};
export type PlotScatterKnowledgeFlowV1StatPlotScatterPostApiResponse = /** status 200 Successful Response */ any;
export type PlotScatterKnowledgeFlowV1StatPlotScatterPostApiArg = {
  plotScatterRequest: PlotScatterRequest;
};
export type TrainModelKnowledgeFlowV1StatTrainPostApiResponse = /** status 200 Successful Response */ any;
export type TrainModelKnowledgeFlowV1StatTrainPostApiArg = {
  trainModelRequest: TrainModelRequest;
};
export type EvaluateModelKnowledgeFlowV1StatEvaluateGetApiResponse = /** status 200 Successful Response */ any;
export type EvaluateModelKnowledgeFlowV1StatEvaluateGetApiArg = void;
export type PredictRowKnowledgeFlowV1StatPredictRowPostApiResponse = /** status 200 Successful Response */ any;
export type PredictRowKnowledgeFlowV1StatPredictRowPostApiArg = {
  predictRowRequest: PredictRowRequest;
};
export type SaveModelKnowledgeFlowV1StatSaveModelPostApiResponse = /** status 200 Successful Response */ any;
export type SaveModelKnowledgeFlowV1StatSaveModelPostApiArg = {
  saveModelRequest: SaveModelRequest;
};
export type ListModelsKnowledgeFlowV1StatListModelsGetApiResponse = /** status 200 Successful Response */ any;
export type ListModelsKnowledgeFlowV1StatListModelsGetApiArg = void;
export type LoadModelKnowledgeFlowV1StatLoadModelPostApiResponse = /** status 200 Successful Response */ any;
export type LoadModelKnowledgeFlowV1StatLoadModelPostApiArg = {
  loadModelRequest: LoadModelRequest;
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
export type SearchDocumentsUsingVectorizationApiResponse = /** status 200 Successful Response */ VectorSearchHit[];
export type SearchDocumentsUsingVectorizationApiArg = {
  searchRequest: SearchRequest;
};
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
export type ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiResponse = /** status 200 Successful Response */ any;
export type ProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostApiArg = {
  processDocumentsRequest: ProcessDocumentsRequest;
};
export type ScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostApiResponse =
  /** status 200 Successful Response */ any;
export type ScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostApiArg = {
  processDocumentsRequest: ProcessDocumentsRequest;
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
export type BodyUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPost = {
  files: Blob[];
  metadata_json: string;
};
export type BodyProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPost = {
  files: Blob[];
  metadata_json: string;
};
export type TabularColumnSchema = {
  name: string;
  dtype: "string" | "integer" | "float" | "boolean" | "datetime" | "unknown";
};
export type TabularSchemaResponse = {
  document_name: string;
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
export type CorrelationsRequest = {
  top_n?: number;
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
export type TagType = "document" | "prompt" | "template";
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
  item_ids?: string[];
};
export type TagUpdate = {
  name: string;
  path?: string | null;
  description?: string | null;
  type: TagType;
  item_ids?: string[];
};
export type ResourceKind = "prompt" | "template";
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
  query: string;
  top_k?: number;
  /** Optional list of tags to filter documents. Only chunks in a document with at least one of these tags will be returned. */
  tags?: string[] | null;
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
export type FileToProcess = {
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
  files: FileToProcess[];
  pipeline_name: string;
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
  useUploadDocumentsSyncKnowledgeFlowV1UploadDocumentsPostMutation,
  useProcessDocumentsSyncKnowledgeFlowV1UploadProcessDocumentsPostMutation,
  useListTabularDatabasesQuery,
  useLazyListTabularDatabasesQuery,
  useListTableNamesQuery,
  useLazyListTableNamesQuery,
  useGetAllSchemasQuery,
  useLazyGetAllSchemasQuery,
  useRawSqlQueryMutation,
  useDeleteTableMutation,
  useListDatasetsKnowledgeFlowV1StatListDatasetsGetQuery,
  useLazyListDatasetsKnowledgeFlowV1StatListDatasetsGetQuery,
  useSetDatasetKnowledgeFlowV1StatSetDatasetPostMutation,
  useHeadKnowledgeFlowV1StatHeadGetQuery,
  useLazyHeadKnowledgeFlowV1StatHeadGetQuery,
  useDescribeKnowledgeFlowV1StatDescribeGetQuery,
  useLazyDescribeKnowledgeFlowV1StatDescribeGetQuery,
  useDetectOutliersKnowledgeFlowV1StatDetectOutliersPostMutation,
  useCorrelationsKnowledgeFlowV1StatCorrelationsGetQuery,
  useLazyCorrelationsKnowledgeFlowV1StatCorrelationsGetQuery,
  usePlotHistogramKnowledgeFlowV1StatPlotHistogramPostMutation,
  usePlotScatterKnowledgeFlowV1StatPlotScatterPostMutation,
  useTrainModelKnowledgeFlowV1StatTrainPostMutation,
  useEvaluateModelKnowledgeFlowV1StatEvaluateGetQuery,
  useLazyEvaluateModelKnowledgeFlowV1StatEvaluateGetQuery,
  usePredictRowKnowledgeFlowV1StatPredictRowPostMutation,
  useSaveModelKnowledgeFlowV1StatSaveModelPostMutation,
  useListModelsKnowledgeFlowV1StatListModelsGetQuery,
  useLazyListModelsKnowledgeFlowV1StatListModelsGetQuery,
  useLoadModelKnowledgeFlowV1StatLoadModelPostMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useLazyListAllTagsKnowledgeFlowV1TagsGetQuery,
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useGetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetQuery,
  useLazyGetCreateResSchemaKnowledgeFlowV1ResourcesSchemaGetQuery,
  useCreateResourceKnowledgeFlowV1ResourcesPostMutation,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  useLazyListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  useUpdateResourceKnowledgeFlowV1ResourcesResourceIdPutMutation,
  useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
  useLazyGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
  useDeleteResourceKnowledgeFlowV1ResourcesResourceIdDeleteMutation,
  useSearchDocumentsUsingVectorizationMutation,
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
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
  useScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostMutation,
} = injectedRtkApi;
