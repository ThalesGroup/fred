import { knowledgeFlowApi as api } from "./knowledgeFlowApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    getDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPost: build.mutation<
      GetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostApiResponse,
      GetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/documents/metadata`, method: "POST", body: queryArg.filters }),
    }),
    getDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGet: build.query<
      GetDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGetApiResponse,
      GetDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGetApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/document/${queryArg.documentUid}` }),
    }),
    updateDocumentRetrievableKnowledgeFlowV1DocumentDocumentUidPut: build.mutation<
      UpdateDocumentRetrievableKnowledgeFlowV1DocumentDocumentUidPutApiResponse,
      UpdateDocumentRetrievableKnowledgeFlowV1DocumentDocumentUidPutApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/document/${queryArg.documentUid}`,
        method: "PUT",
        body: queryArg.updateRetrievableRequest,
      }),
    }),
    deleteDocumentMetadataKnowledgeFlowV1DocumentDocumentUidDelete: build.mutation<
      DeleteDocumentMetadataKnowledgeFlowV1DocumentDocumentUidDeleteApiResponse,
      DeleteDocumentMetadataKnowledgeFlowV1DocumentDocumentUidDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/document/${queryArg.documentUid}`, method: "DELETE" }),
    }),
    updateDocumentMetadataKnowledgeFlowV1DocumentDocumentUidUpdateMetadataPost: build.mutation<
      UpdateDocumentMetadataKnowledgeFlowV1DocumentDocumentUidUpdateMetadataPostApiResponse,
      UpdateDocumentMetadataKnowledgeFlowV1DocumentDocumentUidUpdateMetadataPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/document/${queryArg.documentUid}/update_metadata`,
        method: "POST",
        body: queryArg.updateDocumentMetadataRequest,
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
    streamProcessKnowledgeFlowV1ProcessFilesPost: build.mutation<
      StreamProcessKnowledgeFlowV1ProcessFilesPostApiResponse,
      StreamProcessKnowledgeFlowV1ProcessFilesPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/process-files`,
        method: "POST",
        body: queryArg.bodyStreamProcessKnowledgeFlowV1ProcessFilesPost,
      }),
    }),
    streamLoadKnowledgeFlowV1UploadFilesPost: build.mutation<
      StreamLoadKnowledgeFlowV1UploadFilesPostApiResponse,
      StreamLoadKnowledgeFlowV1UploadFilesPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/upload-files`,
        method: "POST",
        body: queryArg.bodyStreamLoadKnowledgeFlowV1UploadFilesPost,
      }),
    }),
    listTableNames: build.query<ListTableNamesApiResponse, ListTableNamesApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/tables` }),
    }),
    getAllSchemas: build.query<GetAllSchemasApiResponse, GetAllSchemasApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/schemas` }),
    }),
    rawSqlQuery: build.mutation<RawSqlQueryApiResponse, RawSqlQueryApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/sql`, method: "POST", body: queryArg.rawSqlRequest }),
    }),
    listTagsKnowledgeFlowV1TagsGet: build.query<
      ListTagsKnowledgeFlowV1TagsGetApiResponse,
      ListTagsKnowledgeFlowV1TagsGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v1/tags` }),
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
    searchDocumentsUsingVectorization: build.mutation<
      SearchDocumentsUsingVectorizationApiResponse,
      SearchDocumentsUsingVectorizationApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/vector/search`, method: "POST", body: queryArg.searchRequest }),
    }),
    submitPipelineKnowledgeFlowV1PipelinesSubmitPost: build.mutation<
      SubmitPipelineKnowledgeFlowV1PipelinesSubmitPostApiResponse,
      SubmitPipelineKnowledgeFlowV1PipelinesSubmitPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/pipelines/submit`,
        method: "POST",
        body: queryArg.pipelineDefinition,
      }),
    }),
    processDocumentsKnowledgeFlowV1PipelinesProcessDocumentsPost: build.mutation<
      ProcessDocumentsKnowledgeFlowV1PipelinesProcessDocumentsPostApiResponse,
      ProcessDocumentsKnowledgeFlowV1PipelinesProcessDocumentsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/pipelines/process-documents`,
        method: "POST",
        body: queryArg.processDocumentsRequest,
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as knowledgeFlowApi };
export type GetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostApiResponse =
  /** status 200 Successful Response */ GetDocumentsMetadataResponse;
export type GetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostApiArg = {
  filters: {
    [key: string]: any;
  };
};
export type GetDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGetApiResponse =
  /** status 200 Successful Response */ GetDocumentMetadataResponse;
export type GetDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGetApiArg = {
  documentUid: string;
};
export type UpdateDocumentRetrievableKnowledgeFlowV1DocumentDocumentUidPutApiResponse =
  /** status 200 Successful Response */ UpdateDocumentMetadataResponse;
export type UpdateDocumentRetrievableKnowledgeFlowV1DocumentDocumentUidPutApiArg = {
  documentUid: string;
  updateRetrievableRequest: UpdateRetrievableRequest;
};
export type DeleteDocumentMetadataKnowledgeFlowV1DocumentDocumentUidDeleteApiResponse =
  /** status 200 Successful Response */ DeleteDocumentMetadataResponse;
export type DeleteDocumentMetadataKnowledgeFlowV1DocumentDocumentUidDeleteApiArg = {
  documentUid: string;
};
export type UpdateDocumentMetadataKnowledgeFlowV1DocumentDocumentUidUpdateMetadataPostApiResponse =
  /** status 200 Successful Response */ UpdateDocumentMetadataResponse;
export type UpdateDocumentMetadataKnowledgeFlowV1DocumentDocumentUidUpdateMetadataPostApiArg = {
  documentUid: string;
  updateDocumentMetadataRequest: UpdateDocumentMetadataRequest;
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
  /** status 200 Successful Response */ any;
export type DownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetApiArg = {
  documentUid: string;
};
export type StreamProcessKnowledgeFlowV1ProcessFilesPostApiResponse = /** status 200 Successful Response */ any;
export type StreamProcessKnowledgeFlowV1ProcessFilesPostApiArg = {
  bodyStreamProcessKnowledgeFlowV1ProcessFilesPost: BodyStreamProcessKnowledgeFlowV1ProcessFilesPost;
};
export type StreamLoadKnowledgeFlowV1UploadFilesPostApiResponse = /** status 200 Successful Response */ any;
export type StreamLoadKnowledgeFlowV1UploadFilesPostApiArg = {
  bodyStreamLoadKnowledgeFlowV1UploadFilesPost: BodyStreamLoadKnowledgeFlowV1UploadFilesPost;
};
export type ListTableNamesApiResponse = /** status 200 Successful Response */ string[];
export type ListTableNamesApiArg = void;
export type GetAllSchemasApiResponse = /** status 200 Successful Response */ TabularSchemaResponse[];
export type GetAllSchemasApiArg = void;
export type RawSqlQueryApiResponse = /** status 200 Successful Response */ TabularQueryResponse;
export type RawSqlQueryApiArg = {
  rawSqlRequest: RawSqlRequest;
};
export type ListTagsKnowledgeFlowV1TagsGetApiResponse = /** status 200 Successful Response */ TagWithDocumentsId[];
export type ListTagsKnowledgeFlowV1TagsGetApiArg = void;
export type CreateTagKnowledgeFlowV1TagsPostApiResponse = /** status 200 Successful Response */ TagWithDocumentsId;
export type CreateTagKnowledgeFlowV1TagsPostApiArg = {
  tagCreate: TagCreate;
};
export type GetTagKnowledgeFlowV1TagsTagIdGetApiResponse = /** status 200 Successful Response */ TagWithDocumentsId;
export type GetTagKnowledgeFlowV1TagsTagIdGetApiArg = {
  tagId: string;
};
export type UpdateTagKnowledgeFlowV1TagsTagIdPutApiResponse = /** status 200 Successful Response */ TagWithDocumentsId;
export type UpdateTagKnowledgeFlowV1TagsTagIdPutApiArg = {
  tagId: string;
  tagUpdate: TagUpdate;
};
export type DeleteTagKnowledgeFlowV1TagsTagIdDeleteApiResponse = unknown;
export type DeleteTagKnowledgeFlowV1TagsTagIdDeleteApiArg = {
  tagId: string;
};
export type SearchDocumentsUsingVectorizationApiResponse = /** status 200 Successful Response */ DocumentSource[];
export type SearchDocumentsUsingVectorizationApiArg = {
  searchRequest: SearchRequest;
};
export type SubmitPipelineKnowledgeFlowV1PipelinesSubmitPostApiResponse =
  /** status 200 Temporal workflow ID and run ID */ any;
export type SubmitPipelineKnowledgeFlowV1PipelinesSubmitPostApiArg = {
  pipelineDefinition: PipelineDefinition;
};
export type ProcessDocumentsKnowledgeFlowV1PipelinesProcessDocumentsPostApiResponse =
  /** status 200 Successful Response */ any;
export type ProcessDocumentsKnowledgeFlowV1PipelinesProcessDocumentsPostApiArg = {
  processDocumentsRequest: ProcessDocumentsRequest;
};
export type SourceType = "push" | "pull";
export type DocumentMetadata = {
  document_name: string;
  document_uid: string;
  /** When the document was added to the system */
  date_added_to_kb?: string;
  /** True if the system can download or access the original file again */
  retrievable?: boolean;
  /** Tag identifying the pull source (e.g., 'local-docs', 'contracts-git') */
  source_tag?: string | null;
  /** Path or URI to the original pull file */
  pull_location?: string | null;
  source_type: SourceType;
  /** User-assigned tags */
  tags?: string[] | null;
  title?: string | null;
  author?: string | null;
  created?: string | null;
  modified?: string | null;
  last_modified_by?: string | null;
  category?: string | null;
  subject?: string | null;
  keywords?: string | null;
  /** Status of each well-defined processing stage */
  processing_stages?: {
    [key: string]: "not_started" | "in_progress" | "done" | "failed";
  };
};
export type GetDocumentsMetadataResponse = {
  status: string;
  documents: DocumentMetadata[];
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type GetDocumentMetadataResponse = {
  status: string;
  metadata: DocumentMetadata;
};
export type UpdateDocumentMetadataResponse = {
  status: string;
  metadata: DocumentMetadata;
};
export type UpdateRetrievableRequest = {
  retrievable: boolean;
};
export type DeleteDocumentMetadataResponse = {
  status: string;
  message: string;
};
export type UpdateDocumentMetadataRequest = {
  description?: string | null;
  title?: string | null;
  domain?: string | null;
  tags?: string[] | null;
};
export type PullDocumentsResponse = {
  total: number;
  documents: DocumentMetadata[];
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
export type BodyStreamProcessKnowledgeFlowV1ProcessFilesPost = {
  files: Blob[];
  metadata_json: string;
};
export type BodyStreamLoadKnowledgeFlowV1UploadFilesPost = {
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
  document_name: string;
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
export type TagType = "library";
export type TagWithDocumentsId = {
  id: string;
  created_at: string;
  updated_at: string;
  owner_id: string;
  name: string;
  description?: string | null;
  type: TagType;
  document_ids: string[];
};
export type TagCreate = {
  name: string;
  description?: string | null;
  type: TagType;
  document_ids?: string[];
};
export type TagUpdate = {
  name: string;
  description?: string | null;
  type: TagType;
  document_ids?: string[];
};
export type DocumentSource = {
  content: string;
  file_path: string;
  file_name: string;
  page: number | null;
  uid: string;
  modified?: string | null;
  title: string;
  author: string;
  created: string;
  type: string;
  /** Similarity score returned by the vector store (e.g., cosine distance). */
  score: number;
  /** Rank of the document among the retrieved results. */
  rank?: number | null;
  /** Identifier of the embedding model used. */
  embedding_model?: string | null;
  /** Name of the vector index used for retrieval. */
  vector_index?: string | null;
  /** Approximate token count of the content. */
  token_count?: number | null;
  /** Timestamp when the document was retrieved. */
  retrieved_at?: string | null;
  /** Session or trace ID for auditability. */
  retrieval_session_id?: string | null;
};
export type SearchRequest = {
  query: string;
  top_k?: number;
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
export type PipelineDefinition = {
  name: string;
  files: FileToProcess[];
};
export type ProcessDocumentsRequest = {
  files: FileToProcess[];
  pipeline_name?: string | null;
};
export const {
  useGetDocumentsMetadataKnowledgeFlowV1DocumentsMetadataPostMutation,
  useGetDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGetQuery,
  useLazyGetDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGetQuery,
  useUpdateDocumentRetrievableKnowledgeFlowV1DocumentDocumentUidPutMutation,
  useDeleteDocumentMetadataKnowledgeFlowV1DocumentDocumentUidDeleteMutation,
  useUpdateDocumentMetadataKnowledgeFlowV1DocumentDocumentUidUpdateMetadataPostMutation,
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
  useStreamProcessKnowledgeFlowV1ProcessFilesPostMutation,
  useStreamLoadKnowledgeFlowV1UploadFilesPostMutation,
  useListTableNamesQuery,
  useLazyListTableNamesQuery,
  useGetAllSchemasQuery,
  useLazyGetAllSchemasQuery,
  useRawSqlQueryMutation,
  useListTagsKnowledgeFlowV1TagsGetQuery,
  useLazyListTagsKnowledgeFlowV1TagsGetQuery,
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useSearchDocumentsUsingVectorizationMutation,
  useSubmitPipelineKnowledgeFlowV1PipelinesSubmitPostMutation,
  useProcessDocumentsKnowledgeFlowV1PipelinesProcessDocumentsPostMutation,
} = injectedRtkApi;
