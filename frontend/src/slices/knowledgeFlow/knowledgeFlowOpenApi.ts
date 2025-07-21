import { knowledgeFlowApi as api } from "./knowledgeFlowApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
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
    searchDocumentsUsingVectorization: build.mutation<
      SearchDocumentsUsingVectorizationApiResponse,
      SearchDocumentsUsingVectorizationApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/vector/search`, method: "POST", body: queryArg.searchRequest }),
    }),
    getDocumentMetadataKnowledgeFlowV1DocumentsMetadataPost: build.mutation<
      GetDocumentMetadataKnowledgeFlowV1DocumentsMetadataPostApiResponse,
      GetDocumentMetadataKnowledgeFlowV1DocumentsMetadataPostApiArg
    >({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/documents/metadata`,
        method: "POST",
        params: {
          document_uid: queryArg.documentUid,
        },
      }),
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
    getSchema: build.query<GetSchemaApiResponse, GetSchemaApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/${queryArg.documentUid}/schema` }),
    }),
    makeQuery: build.mutation<MakeQueryApiResponse, MakeQueryApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/tabular/${queryArg.documentUid}/query`,
        method: "POST",
        body: queryArg.tabularQueryRequest,
      }),
    }),
    listTables: build.query<ListTablesApiResponse, ListTablesApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/list` }),
    }),
    searchCodebase: build.mutation<SearchCodebaseApiResponse, SearchCodebaseApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v1/code/search`,
        method: "POST",
        body: queryArg.codeSearchRequest,
      }),
    }),
    indexCodebaseKnowledgeFlowV1CodeIndexPost: build.mutation<
      IndexCodebaseKnowledgeFlowV1CodeIndexPostApiResponse,
      IndexCodebaseKnowledgeFlowV1CodeIndexPostApiArg
    >({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/code/index`, method: "POST", body: queryArg.codeIndexRequest }),
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
  }),
  overrideExisting: false,
});
export { injectedRtkApi as knowledgeFlowApi };
export type StreamProcessKnowledgeFlowV1ProcessFilesPostApiResponse = /** status 200 Successful Response */ any;
export type StreamProcessKnowledgeFlowV1ProcessFilesPostApiArg = {
  bodyStreamProcessKnowledgeFlowV1ProcessFilesPost: BodyStreamProcessKnowledgeFlowV1ProcessFilesPost;
};
export type StreamLoadKnowledgeFlowV1UploadFilesPostApiResponse = /** status 200 Successful Response */ any;
export type StreamLoadKnowledgeFlowV1UploadFilesPostApiArg = {
  bodyStreamLoadKnowledgeFlowV1UploadFilesPost: BodyStreamLoadKnowledgeFlowV1UploadFilesPost;
};
export type SearchDocumentsUsingVectorizationApiResponse = /** status 200 Successful Response */ DocumentSource[];
export type SearchDocumentsUsingVectorizationApiArg = {
  searchRequest: SearchRequest;
};
export type GetDocumentMetadataKnowledgeFlowV1DocumentsMetadataPostApiResponse =
  /** status 200 Successful Response */ GetDocumentsMetadataResponse;
export type GetDocumentMetadataKnowledgeFlowV1DocumentsMetadataPostApiArg = {
  documentUid: string;
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
export type GetSchemaApiResponse = /** status 200 Successful Response */ TabularSchemaResponse;
export type GetSchemaApiArg = {
  documentUid: string;
};
export type MakeQueryApiResponse = /** status 200 Successful Response */ TabularQueryResponse;
export type MakeQueryApiArg = {
  documentUid: string;
  tabularQueryRequest: TabularQueryRequest;
};
export type ListTablesApiResponse = /** status 200 Successful Response */ TabularDatasetMetadata[];
export type ListTablesApiArg = void;
export type SearchCodebaseApiResponse = /** status 200 Successful Response */ CodeDocumentSource[];
export type SearchCodebaseApiArg = {
  codeSearchRequest: CodeSearchRequest;
};
export type IndexCodebaseKnowledgeFlowV1CodeIndexPostApiResponse = /** status 200 Successful Response */ any;
export type IndexCodebaseKnowledgeFlowV1CodeIndexPostApiArg = {
  codeIndexRequest: CodeIndexRequest;
};
export type ListTagsKnowledgeFlowV1TagsGetApiResponse = /** status 200 Successful Response */ Tag[];
export type ListTagsKnowledgeFlowV1TagsGetApiArg = void;
export type CreateTagKnowledgeFlowV1TagsPostApiResponse = /** status 200 Successful Response */ Tag;
export type CreateTagKnowledgeFlowV1TagsPostApiArg = {
  tagCreate: TagCreate;
};
export type GetTagKnowledgeFlowV1TagsTagIdGetApiResponse = /** status 200 Successful Response */ Tag;
export type GetTagKnowledgeFlowV1TagsTagIdGetApiArg = {
  tagId: string;
};
export type UpdateTagKnowledgeFlowV1TagsTagIdPutApiResponse = /** status 200 Successful Response */ Tag;
export type UpdateTagKnowledgeFlowV1TagsTagIdPutApiArg = {
  tagId: string;
  tagUpdate: TagUpdate;
};
export type DeleteTagKnowledgeFlowV1TagsTagIdDeleteApiResponse = /** status 200 Successful Response */ any;
export type DeleteTagKnowledgeFlowV1TagsTagIdDeleteApiArg = {
  tagId: string;
};
export type SubmitPipelineKnowledgeFlowV1PipelinesSubmitPostApiResponse =
  /** status 200 Temporal workflow ID and run ID */ any;
export type SubmitPipelineKnowledgeFlowV1PipelinesSubmitPostApiArg = {
  pipelineDefinition: PipelineDefinition;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type BodyStreamProcessKnowledgeFlowV1ProcessFilesPost = {
  files: Blob[];
  metadata_json: string;
};
export type BodyStreamLoadKnowledgeFlowV1UploadFilesPost = {
  files: Blob[];
  metadata_json: string;
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
export type DocumentProcessingStatus = "uploaded" | "input_processed" | "vectorized" | "completed" | "failed";
export type DocumentMetadata = {
  document_name: string;
  document_uid: string;
  date_added_to_kb?: string;
  retrievable?: boolean;
  processing_status?: DocumentProcessingStatus;
  /** User-provided tags from the frontend */
  tags?: string[] | null;
  title?: string | null;
  author?: string | null;
  created?: string | null;
  modified?: string | null;
  last_modified_by?: string | null;
  category?: string | null;
  subject?: string | null;
  keywords?: string | null;
};
export type GetDocumentsMetadataResponse = {
  status: string;
  documents: DocumentMetadata[];
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
export type MarkdownContentResponse = {
  content: string;
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
  rows: {
    [key: string]: any;
  }[];
};
export type FilterCondition = {
  column: string;
  op?: string;
  value: any;
};
export type OrderBySpec = {
  column: string;
  direction?: string | null;
};
export type JoinSpec = {
  table: string;
  on: string;
  type?: string | null;
};
export type AggregationSpec = {
  function: string;
  column: string;
  alias?: string | null;
  distinct?: boolean;
  filter?: {
    [key: string]: any;
  } | null;
};
export type SqlQueryPlan = {
  table: string;
  columns?: string[] | null;
  filters?: FilterCondition[] | null;
  group_by?: string[] | null;
  order_by?: OrderBySpec[] | null;
  limit?: number | null;
  joins?: JoinSpec[] | null;
  aggregations?: AggregationSpec[] | null;
};
export type TabularQueryRequest = {
  query?: string | SqlQueryPlan | null;
};
export type TabularDatasetMetadata = {
  document_name: string;
  title: string;
  description?: string | null;
  tags?: string[];
  domain?: string | null;
  row_count?: number | null;
};
export type CodeDocumentSource = {
  content: string;
  file_path: string;
  file_name: string;
  language: string;
  symbol?: string | null;
  uid: string;
  score: number;
  rank?: number | null;
  embedding_model?: string | null;
  vector_index?: string | null;
};
export type CodeSearchRequest = {
  query: string;
  top_k?: number;
};
export type CodeIndexRequest = {
  path: string;
};
export type TagType = "library";
export type Tag = {
  id: string;
  created_at: string;
  updated_at: string;
  owner_id: string;
  name: string;
  description?: string | null;
  type: TagType;
  document_ids?: string[];
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
export type PipelineFile = {
  path: string;
  original_filename?: string | null;
};
export type PipelineDefinition = {
  name: string;
  files: PipelineFile[];
  metadata: {
    [key: string]: any;
  };
};
export const {
  useStreamProcessKnowledgeFlowV1ProcessFilesPostMutation,
  useStreamLoadKnowledgeFlowV1UploadFilesPostMutation,
  useSearchDocumentsUsingVectorizationMutation,
  useGetDocumentMetadataKnowledgeFlowV1DocumentsMetadataPostMutation,
  useGetDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGetQuery,
  useLazyGetDocumentMetadataKnowledgeFlowV1DocumentDocumentUidGetQuery,
  useUpdateDocumentRetrievableKnowledgeFlowV1DocumentDocumentUidPutMutation,
  useDeleteDocumentMetadataKnowledgeFlowV1DocumentDocumentUidDeleteMutation,
  useUpdateDocumentMetadataKnowledgeFlowV1DocumentDocumentUidUpdateMetadataPostMutation,
  useGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery,
  useLazyGetMarkdownPreviewKnowledgeFlowV1MarkdownDocumentUidGetQuery,
  useDownloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGetQuery,
  useLazyDownloadDocumentMediaKnowledgeFlowV1MarkdownDocumentUidMediaMediaIdGetQuery,
  useDownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetQuery,
  useLazyDownloadDocumentKnowledgeFlowV1RawContentDocumentUidGetQuery,
  useGetSchemaQuery,
  useLazyGetSchemaQuery,
  useMakeQueryMutation,
  useListTablesQuery,
  useLazyListTablesQuery,
  useSearchCodebaseMutation,
  useIndexCodebaseKnowledgeFlowV1CodeIndexPostMutation,
  useListTagsKnowledgeFlowV1TagsGetQuery,
  useLazyListTagsKnowledgeFlowV1TagsGetQuery,
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useSubmitPipelineKnowledgeFlowV1PipelinesSubmitPostMutation,
} = injectedRtkApi;
