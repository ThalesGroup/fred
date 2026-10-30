import { knowledgeFlowApi as api } from "./knowledgeFlowApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    healthzKnowledgeFlowV2HealthzGet: build.query<
      HealthzKnowledgeFlowV2HealthzGetApiResponse,
      HealthzKnowledgeFlowV2HealthzGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v2/healthz` }),
    }),
    readyKnowledgeFlowV2ReadyGet: build.query<
      ReadyKnowledgeFlowV2ReadyGetApiResponse,
      ReadyKnowledgeFlowV2ReadyGetApiArg
    >({
      query: () => ({ url: `/knowledge-flow/v2/ready` }),
    }),
    searchDocuments: build.mutation<SearchDocumentsApiResponse, SearchDocumentsApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/documents/search`,
        method: "POST",
        body: queryArg.searchRequest,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    getDocumentChunks: build.query<GetDocumentChunksApiResponse, GetDocumentChunksApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/documents/${queryArg.documentUid}/chunks`,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          limit: queryArg.limit,
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    getDocumentMarkdown: build.query<GetDocumentMarkdownApiResponse, GetDocumentMarkdownApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/documents/${queryArg.documentUid}/markdown`,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    summarizeDocument: build.mutation<SummarizeDocumentApiResponse, SummarizeDocumentApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/documents/${queryArg.documentUid}/summarize`,
        method: "POST",
        body: queryArg.summarizeDocumentRequest,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    extractDocument: build.mutation<ExtractDocumentApiResponse, ExtractDocumentApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/documents/${queryArg.documentUid}/extract`,
        method: "POST",
        body: queryArg.extractDocumentRequest,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    listTabularDocuments: build.query<ListTabularDocumentsApiResponse, ListTabularDocumentsApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/tabular/documents`,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    describeTabularDocuments: build.query<DescribeTabularDocumentsApiResponse, DescribeTabularDocumentsApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/tabular/documents/schemas`,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          document_uids: queryArg.documentUids,
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    queryTabularDocuments: build.mutation<QueryTabularDocumentsApiResponse, QueryTabularDocumentsApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/tabular/query`,
        method: "POST",
        body: queryArg.tabularQueryRequest,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
    searchTabularValues: build.mutation<SearchTabularValuesApiResponse, SearchTabularValuesApiArg>({
      query: (queryArg) => ({
        url: `/knowledge-flow/v2/tabular/search`,
        method: "POST",
        body: queryArg.tabularSearchRequest,
        headers: {
          "x-fred-document-context": queryArg["x-fred-document-context"],
        },
        params: {
          person: queryArg.person,
          run: queryArg.run,
          agent: queryArg.agent,
        },
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as knowledgeFlowApi };
export type HealthzKnowledgeFlowV2HealthzGetApiResponse = /** status 200 Successful Response */ any;
export type HealthzKnowledgeFlowV2HealthzGetApiArg = void;
export type ReadyKnowledgeFlowV2ReadyGetApiResponse = /** status 200 Successful Response */ any;
export type ReadyKnowledgeFlowV2ReadyGetApiArg = void;
export type SearchDocumentsApiResponse = /** status 200 Successful Response */ VectorSearchHit[];
export type SearchDocumentsApiArg = {
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
  searchRequest: SearchRequest;
};
export type GetDocumentChunksApiResponse = /** status 200 Successful Response */ VectorSearchHit[];
export type GetDocumentChunksApiArg = {
  documentUid: string;
  limit?: number;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
};
export type GetDocumentMarkdownApiResponse = /** status 200 Successful Response */ MarkdownResponse;
export type GetDocumentMarkdownApiArg = {
  documentUid: string;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
};
export type SummarizeDocumentApiResponse = /** status 200 Successful Response */ SummarizeDocumentResponse;
export type SummarizeDocumentApiArg = {
  documentUid: string;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
  summarizeDocumentRequest: SummarizeDocumentRequest;
};
export type ExtractDocumentApiResponse = /** status 200 Successful Response */ ExtractDocumentResponse;
export type ExtractDocumentApiArg = {
  documentUid: string;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
  extractDocumentRequest: ExtractDocumentRequest;
};
export type ListTabularDocumentsApiResponse = /** status 200 Successful Response */ TabularDocumentListResponse[];
export type ListTabularDocumentsApiArg = {
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
};
export type DescribeTabularDocumentsApiResponse =
  /** status 200 Successful Response */ TabularDocumentDescriptionResponse[];
export type DescribeTabularDocumentsApiArg = {
  /** Document UUIDs from listing, encoded as repeated document_uids query parameters. All requested documents must be in scope; 1 to 1000 identifiers. */
  documentUids: string[];
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
};
export type QueryTabularDocumentsApiResponse = /** status 200 Successful Response */ RawSqlResponse;
export type QueryTabularDocumentsApiArg = {
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
  tabularQueryRequest: TabularQueryRequest;
};
export type SearchTabularValuesApiResponse = /** status 200 Successful Response */ TabularSearchResponse;
export type SearchTabularValuesApiArg = {
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  person?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  run?: string | null;
  /** Existing delegation grant identifier. Supply person, run and agent together for an admitted call. Optional only at the authentication dependency boundary; missing or invalid grants cannot authorize these operations. */
  agent?: string | null;
  /** One JSON object encoded directly as the header value (no base64 or URL encoding). Required after delegated authentication: absent -> 403; invalid -> 400. An explicit document_scope with no selections adds no filter to authorized published documents; one empty selection admits no corpus documents. Attachments require conversation_id and an explicit nonempty attachment_ids list; neither alone grants access. SQL verifies conversation owner, exact space, live state and each published retrievable document. Body and query cannot supply this context. No Fred-specific byte cap; server/proxy limits can reject the request before these handlers. */
  "x-fred-document-context": any;
  tabularSearchRequest: TabularSearchRequest;
};
export type VectorSearchHit = {
  content: string;
  page?: number | null;
  section?: string | null;
  viewer_fragment?: string | null;
  slide_id?: number | null;
  has_visual_evidence?: boolean | null;
  slide_image_uri?: string | null;
  /** content (default, real ingested prose/data) or 'dataset_pointer' (a discovery pointer to a structured dataset, never citable as a source) or 'markdown_table' (a Markdown table kept whole or split on row boundaries). */
  chunk_kind?: string | null;
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
  /** Position of the chunk inside its source document, used to restore document order */
  chunk_index?: number | null;
  embedding_model?: string | null;
  vector_index?: string | null;
  token_count?: number | null;
  retrieved_at?: string | null;
  retrieval_session_id?: string | null;
};
export type KnowledgeFlowError = {
  /** Error code or message. Do not assume all messages are stable machine-readable codes. */
  detail: string;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: any;
  ctx?: object;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type SearchPolicyName = "hybrid" | "strict" | "semantic";
export type SearchRequest = {
  /** Natural-language search query. This operation returns chunks, not a generated answer. */
  question: string;
  /** Number of results to return. */
  top_k?: number;
  /** Optional search policy preset. If omitted, defaults to 'hybrid'. */
  search_policy?: SearchPolicyName | null;
};
export type MarkdownResponse = {
  /** Full UTF-8 text of the authorized published output.md artifact; no pagination or response-size limit is imposed here. */
  content: string;
};
export type SummarizeDocumentResponse = {
  document_uid: string;
  summary: string;
  /** True when a corrective rewriting pass completed. This does not guarantee that the result is within max_chars. */
  shrunk_for_budget: boolean;
  keywords?: string[];
};
export type SummarizeDocumentRequest = {
  /** Free-text instruction steering the summary: focus area, audience, what to look for, desired length/tone. */
  instruction?: string | null;
  /** Target summary length in characters, not a guaranteed ceiling. One corrective pass is attempted if exceeded. */
  max_chars?: number;
};
export type ExtractDocumentResponse = {
  document_uid: string;
  /** Consolidated, de-duplicated list of every extracted item (markdown bullets), in document order. */
  extraction: string;
  item_count: number;
  /** Number of map windows attempted, not the number of successful model calls or source chunks. */
  chunks_processed: number;
  /** True only when input exceeded the 2,000,000-character cap and was head/tail-windowed. Does not report individual model-call failures. */
  truncated: boolean;
};
export type ExtractDocumentRequest = {
  /** What to extract exhaustively, e.g. 'every functional requirement', 'all deadlines and their context'. */
  instruction: string;
};
export type TabularDocumentListTableResponse = {
  query_alias: string;
  sheet?: string | null;
  title?: string | null;
};
export type TabularDocumentListResponse = {
  document_uid: string;
  document_name: string;
  tables?: TabularDocumentListTableResponse[] | null;
  source_kind?: "corpus" | "conversation_attachment";
  tag_names?: string[] | null;
};
export type TabularColumnSchema = {
  name: string;
  dtype: "string" | "integer" | "float" | "boolean" | "datetime" | "unknown";
  /** For string columns, whether the count of distinct non-null values is between 1 and max_categories(row_count), with null rows included in row_count. None for non-string or older columns without this analysis. */
  is_categorical?: boolean | null;
  /** For string columns, whether exactly two distinct non-null values were observed. This does not assign true/false meaning to those values. */
  has_two_values?: boolean | null;
  /** Every distinct non-null string value when is_categorical is true, preserving exact casing for SQL filters. None otherwise. */
  sample_values?: string[] | null;
  /** Smallest finite non-null value of an integer or float column. None when unavailable. */
  min_value?: number | number | null;
  /** Largest finite non-null value of an integer or float column. None when unavailable. */
  max_value?: number | number | null;
};
export type TabularTableSchema = {
  query_alias: string;
  sheet?: string | null;
  title?: string | null;
  row_count?: number | null;
  generated_at?: string | null;
  columns?: TabularColumnSchema[];
};
export type TabularDocumentDescriptionResponse = {
  document_uid: string;
  document_name: string;
  kind: "csv" | "spreadsheet";
  markdown: string | null;
  tables?: TabularTableSchema[];
  source_tag?: string | null;
};
export type RawSqlResponse = {
  /** Validated SQL before the server adds its outer result-row LIMIT. */
  sql_query: string;
  /** JSON objects keyed by selected SQL columns; values depend on the query. Bounded preview, without a completeness flag. */
  rows?: {
    [key: string]: any;
  }[];
  /** Null on this mounted success path; failures use HTTP error statuses, not a success response containing an error. */
  error?: string | null;
  /** Document UUIDs of the mounted tables. A workbook UUID may appear more than once. */
  dataset_uids?: string[];
  /** Exact aliases of the mounted tables used by the query. */
  query_aliases?: string[];
};
export type TabularQueryRequest = {
  /** One read-only SELECT/WITH using exact aliases returned by schema discovery. Must reference an authorized dataset; SELECT 1, writes and external reads are refused. */
  sql: string;
  /** Optional document UUID subset, not table aliases. Omitted/null uses the authorized scope; [] selects nothing and query/search returns 400. Every requested UUID must be in scope; a workbook includes its tables. */
  dataset_uids?: string[] | null;
  /** Requested result-row limit; omitted/null uses configured default_max_rows. Clamped to configured max_rows, not rejected when larger. No pagination or truncation flag. */
  max_rows?: number | null;
};
export type TabularTableMatch = {
  document_uid: string;
  document_name: string;
  query_alias: string;
  sheet?: string | null;
  title?: string | null;
  matched_columns?: string[];
  rows?: {
    [key: string]: any;
  }[];
  /** True when more matching rows existed than were returned (max_rows_per_table reached): other occurrences remain in this table. */
  row_truncated?: boolean;
};
export type TabularSearchResponse = {
  keyword: string;
  normalized_keyword: string;
  matches?: TabularTableMatch[];
  /** True when the result is partial: either the max_matching_tables cap was reached, or the scope exceeded the number of datasets one search may scan. Other tables may also contain the value. */
  tables_truncated?: boolean;
  /** Documents that were in scope for this search. A document dropped by the dataset limit is omitted entirely. Note this is not proof a listed document was read exhaustively: when tables_truncated is true the scan stopped early, so a listed document may still hold the keyword in a table that was never opened. */
  searched_dataset_uids?: string[];
};
export type TabularSearchRequest = {
  /** Precise value to locate. Schema minimum is 1 character; the service additionally requires at least 2 stripped characters (400) and a nonempty normalized keyword. Case/accent/whitespace-insensitive substring matching, including numeric columns. */
  keyword: string;
  /** Optional document UUID subset, not table aliases. Omitted/null uses the authorized scope; [] selects nothing and query/search returns 400. Every requested UUID must be in scope; a workbook includes its tables. */
  dataset_uids?: string[] | null;
  /** Maximum matching rows returned per table (ceiling). */
  max_rows_per_table?: number;
  /** Maximum tables with a match returned before the search stops (ceiling). */
  max_matching_tables?: number;
};
export const {
  useHealthzKnowledgeFlowV2HealthzGetQuery,
  useLazyHealthzKnowledgeFlowV2HealthzGetQuery,
  useReadyKnowledgeFlowV2ReadyGetQuery,
  useLazyReadyKnowledgeFlowV2ReadyGetQuery,
  useSearchDocumentsMutation,
  useGetDocumentChunksQuery,
  useLazyGetDocumentChunksQuery,
  useGetDocumentMarkdownQuery,
  useLazyGetDocumentMarkdownQuery,
  useSummarizeDocumentMutation,
  useExtractDocumentMutation,
  useListTabularDocumentsQuery,
  useLazyListTabularDocumentsQuery,
  useDescribeTabularDocumentsQuery,
  useLazyDescribeTabularDocumentsQuery,
  useQueryTabularDocumentsMutation,
  useSearchTabularValuesMutation,
} = injectedRtkApi;
