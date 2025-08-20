import { knowledgeFlowApi as api } from "./knowledgeFlowApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
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
    listTableNames: build.query<ListTableNamesApiResponse, ListTableNamesApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/tables` }),
    }),
    getAllSchemas: build.query<GetAllSchemasApiResponse, GetAllSchemasApiArg>({
      query: () => ({ url: `/knowledge-flow/v1/tabular/schemas` }),
    }),
    rawSqlQuery: build.mutation<RawSqlQueryApiResponse, RawSqlQueryApiArg>({
      query: (queryArg) => ({ url: `/knowledge-flow/v1/tabular/sql`, method: "POST", body: queryArg.rawSqlRequest }),
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
  /** status 200 Successful Response */ any;
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
export type ListTableNamesApiResponse = /** status 200 Successful Response */ string[];
export type ListTableNamesApiArg = void;
export type GetAllSchemasApiResponse = /** status 200 Successful Response */ TabularSchemaResponse[];
export type GetAllSchemasApiArg = void;
export type RawSqlQueryApiResponse = /** status 200 Successful Response */ TabularQueryResponse;
export type RawSqlQueryApiArg = {
  rawSqlRequest: RawSqlRequest;
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
export const DOCUMENT_PROCESSING_STAGES = ["raw", "preview", "vector", "sql", "mcp"] as const;
export const {
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
  useListTableNamesQuery,
  useLazyListTableNamesQuery,
  useGetAllSchemasQuery,
  useLazyGetAllSchemasQuery,
  useRawSqlQueryMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useLazyListAllTagsKnowledgeFlowV1TagsGetQuery,
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useLazyGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useCreateResourceKnowledgeFlowV1ResourcesPostMutation,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  useLazyListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
  useUpdateResourceKnowledgeFlowV1ResourcesResourceIdPutMutation,
  useGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
  useLazyGetResourceKnowledgeFlowV1ResourcesResourceIdGetQuery,
  useDeleteResourceKnowledgeFlowV1ResourcesResourceIdDeleteMutation,
  useSearchDocumentsUsingVectorizationMutation,
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
  useScheduleDocumentsKnowledgeFlowV1ScheduleDocumentsPostMutation,
} = injectedRtkApi;
