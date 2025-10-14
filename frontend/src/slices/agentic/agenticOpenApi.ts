import { agenticApi as api } from "./agenticApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    createAgentAgenticV1AgentsCreatePost: build.mutation<
      CreateAgentAgenticV1AgentsCreatePostApiResponse,
      CreateAgentAgenticV1AgentsCreatePostApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/create`, method: "POST", body: queryArg.createMcpAgentRequest }),
    }),
    updateAgentAgenticV1AgentsUpdatePut: build.mutation<
      UpdateAgentAgenticV1AgentsUpdatePutApiResponse,
      UpdateAgentAgenticV1AgentsUpdatePutApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/update`, method: "PUT", body: queryArg.agentSettings }),
    }),
    deleteAgentAgenticV1AgentsNameDelete: build.mutation<
      DeleteAgentAgenticV1AgentsNameDeleteApiResponse,
      DeleteAgentAgenticV1AgentsNameDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/${queryArg.name}`, method: "DELETE" }),
    }),
    listRuntimeSourceKeysAgenticV1AgentsSourceKeysGet: build.query<
      ListRuntimeSourceKeysAgenticV1AgentsSourceKeysGetApiResponse,
      ListRuntimeSourceKeysAgenticV1AgentsSourceKeysGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/agents/source/keys` }),
    }),
    runtimeSourceByObjectAgenticV1AgentsSourceByObjectGet: build.query<
      RuntimeSourceByObjectAgenticV1AgentsSourceByObjectGetApiResponse,
      RuntimeSourceByObjectAgenticV1AgentsSourceByObjectGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/agents/source/by-object`,
        params: {
          key: queryArg.key,
        },
      }),
    }),
    runtimeSourceByModuleAgenticV1AgentsSourceByModuleGet: build.query<
      RuntimeSourceByModuleAgenticV1AgentsSourceByModuleGetApiResponse,
      RuntimeSourceByModuleAgenticV1AgentsSourceByModuleGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/agents/source/by-module`,
        params: {
          module: queryArg["module"],
          qualname: queryArg.qualname,
        },
      }),
    }),
    echoSchemaAgenticV1SchemasEchoPost: build.mutation<
      EchoSchemaAgenticV1SchemasEchoPostApiResponse,
      EchoSchemaAgenticV1SchemasEchoPostApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/schemas/echo`, method: "POST", body: queryArg.echoEnvelope }),
    }),
    getFrontendConfigAgenticV1ConfigFrontendSettingsGet: build.query<
      GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiResponse,
      GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/config/frontend_settings` }),
    }),
    getUserPermissionsAgenticV1ConfigPermissionsGet: build.query<
      GetUserPermissionsAgenticV1ConfigPermissionsGetApiResponse,
      GetUserPermissionsAgenticV1ConfigPermissionsGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/config/permissions` }),
    }),
    getAgenticFlowsAgenticV1ChatbotAgenticflowsGet: build.query<
      GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse,
      GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/chatbot/agenticflows` }),
    }),
    getSessionsAgenticV1ChatbotSessionsGet: build.query<
      GetSessionsAgenticV1ChatbotSessionsGetApiResponse,
      GetSessionsAgenticV1ChatbotSessionsGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/chatbot/sessions` }),
    }),
    getSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGet: build.query<
      GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiResponse,
      GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/chatbot/session/${queryArg.sessionId}/history` }),
    }),
    deleteSessionAgenticV1ChatbotSessionSessionIdDelete: build.mutation<
      DeleteSessionAgenticV1ChatbotSessionSessionIdDeleteApiResponse,
      DeleteSessionAgenticV1ChatbotSessionSessionIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/chatbot/session/${queryArg.sessionId}`, method: "DELETE" }),
    }),
    uploadFileAgenticV1ChatbotUploadPost: build.mutation<
      UploadFileAgenticV1ChatbotUploadPostApiResponse,
      UploadFileAgenticV1ChatbotUploadPostApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/chatbot/upload`,
        method: "POST",
        body: queryArg.bodyUploadFileAgenticV1ChatbotUploadPost,
      }),
    }),
    healthzAgenticV1HealthzGet: build.query<HealthzAgenticV1HealthzGetApiResponse, HealthzAgenticV1HealthzGetApiArg>({
      query: () => ({ url: `/agentic/v1/healthz` }),
    }),
    readyAgenticV1ReadyGet: build.query<ReadyAgenticV1ReadyGetApiResponse, ReadyAgenticV1ReadyGetApiArg>({
      query: () => ({ url: `/agentic/v1/ready` }),
    }),
    getNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGet: build.query<
      GetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetApiResponse,
      GetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/metrics/chatbot/numerical`,
        params: {
          start: queryArg.start,
          end: queryArg.end,
          precision: queryArg.precision,
          agg: queryArg.agg,
          groupby: queryArg.groupby,
        },
      }),
    }),
    getFeedbackAgenticV1ChatbotFeedbackGet: build.query<
      GetFeedbackAgenticV1ChatbotFeedbackGetApiResponse,
      GetFeedbackAgenticV1ChatbotFeedbackGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/chatbot/feedback` }),
    }),
    postFeedbackAgenticV1ChatbotFeedbackPost: build.mutation<
      PostFeedbackAgenticV1ChatbotFeedbackPostApiResponse,
      PostFeedbackAgenticV1ChatbotFeedbackPostApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/chatbot/feedback`, method: "POST", body: queryArg.feedbackPayload }),
    }),
    deleteFeedbackAgenticV1ChatbotFeedbackFeedbackIdDelete: build.mutation<
      DeleteFeedbackAgenticV1ChatbotFeedbackFeedbackIdDeleteApiResponse,
      DeleteFeedbackAgenticV1ChatbotFeedbackFeedbackIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/chatbot/feedback/${queryArg.feedbackId}`, method: "DELETE" }),
    }),
    queryLogsAgenticV1LogsQueryPost: build.mutation<
      QueryLogsAgenticV1LogsQueryPostApiResponse,
      QueryLogsAgenticV1LogsQueryPostApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/logs/query`, method: "POST", body: queryArg.logQuery }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as agenticApi };
export type CreateAgentAgenticV1AgentsCreatePostApiResponse = /** status 200 Successful Response */ any;
export type CreateAgentAgenticV1AgentsCreatePostApiArg = {
  createMcpAgentRequest: CreateMcpAgentRequest;
};
export type UpdateAgentAgenticV1AgentsUpdatePutApiResponse = /** status 200 Successful Response */ any;
export type UpdateAgentAgenticV1AgentsUpdatePutApiArg = {
  agentSettings:
    | ({
        type: "agent";
      } & Agent)
    | ({
        type: "leader";
      } & Leader);
};
export type DeleteAgentAgenticV1AgentsNameDeleteApiResponse = /** status 200 Successful Response */ any;
export type DeleteAgentAgenticV1AgentsNameDeleteApiArg = {
  name: string;
};
export type ListRuntimeSourceKeysAgenticV1AgentsSourceKeysGetApiResponse = /** status 200 Successful Response */ any;
export type ListRuntimeSourceKeysAgenticV1AgentsSourceKeysGetApiArg = void;
export type RuntimeSourceByObjectAgenticV1AgentsSourceByObjectGetApiResponse =
  /** status 200 Successful Response */ string;
export type RuntimeSourceByObjectAgenticV1AgentsSourceByObjectGetApiArg = {
  key: string;
};
export type RuntimeSourceByModuleAgenticV1AgentsSourceByModuleGetApiResponse =
  /** status 200 Successful Response */ string;
export type RuntimeSourceByModuleAgenticV1AgentsSourceByModuleGetApiArg = {
  module: string;
  qualname?: string | null;
};
export type EchoSchemaAgenticV1SchemasEchoPostApiResponse = /** status 200 Successful Response */ null;
export type EchoSchemaAgenticV1SchemasEchoPostApiArg = {
  echoEnvelope: EchoEnvelope;
};
export type GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiResponse =
  /** status 200 Successful Response */ FrontendConfigDto;
export type GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiArg = void;
export type GetUserPermissionsAgenticV1ConfigPermissionsGetApiResponse = /** status 200 Successful Response */ string[];
export type GetUserPermissionsAgenticV1ConfigPermissionsGetApiArg = void;
export type GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse = /** status 200 Successful Response */ (
  | ({
      type: "agent";
    } & Agent2)
  | ({
      type: "leader";
    } & Leader2)
)[];
export type GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiArg = void;
export type GetSessionsAgenticV1ChatbotSessionsGetApiResponse =
  /** status 200 Successful Response */ SessionWithFiles[];
export type GetSessionsAgenticV1ChatbotSessionsGetApiArg = void;
export type GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiResponse =
  /** status 200 Successful Response */ ChatMessage2[];
export type GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiArg = {
  sessionId: string;
};
export type DeleteSessionAgenticV1ChatbotSessionSessionIdDeleteApiResponse =
  /** status 200 Successful Response */ boolean;
export type DeleteSessionAgenticV1ChatbotSessionSessionIdDeleteApiArg = {
  sessionId: string;
};
export type UploadFileAgenticV1ChatbotUploadPostApiResponse = /** status 200 Successful Response */ {
  [key: string]: any;
};
export type UploadFileAgenticV1ChatbotUploadPostApiArg = {
  bodyUploadFileAgenticV1ChatbotUploadPost: BodyUploadFileAgenticV1ChatbotUploadPost;
};
export type HealthzAgenticV1HealthzGetApiResponse = /** status 200 Successful Response */ any;
export type HealthzAgenticV1HealthzGetApiArg = void;
export type ReadyAgenticV1ReadyGetApiResponse = /** status 200 Successful Response */ any;
export type ReadyAgenticV1ReadyGetApiArg = void;
export type GetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetApiResponse =
  /** status 200 Successful Response */ MetricsResponse;
export type GetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetApiArg = {
  start: string;
  end: string;
  precision?: string;
  agg?: string[];
  groupby?: string[];
};
export type GetFeedbackAgenticV1ChatbotFeedbackGetApiResponse = /** status 200 Successful Response */ FeedbackRecord[];
export type GetFeedbackAgenticV1ChatbotFeedbackGetApiArg = void;
export type PostFeedbackAgenticV1ChatbotFeedbackPostApiResponse = unknown;
export type PostFeedbackAgenticV1ChatbotFeedbackPostApiArg = {
  feedbackPayload: FeedbackPayload;
};
export type DeleteFeedbackAgenticV1ChatbotFeedbackFeedbackIdDeleteApiResponse = unknown;
export type DeleteFeedbackAgenticV1ChatbotFeedbackFeedbackIdDeleteApiArg = {
  feedbackId: string;
};
export type QueryLogsAgenticV1LogsQueryPostApiResponse = /** status 200 Successful Response */ LogQueryResult;
export type QueryLogsAgenticV1LogsQueryPostApiArg = {
  logQuery: LogQuery;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type McpServerConfiguration = {
  name: string;
  /** MCP server transport. Can be sse, stdio, websocket or streamable_http */
  transport?: string | null;
  /** URL and endpoint of the MCP server */
  url?: string | null;
  /** How long (in seconds) the client will wait for a new event before disconnecting */
  sse_read_timeout?: number | null;
  /** Command to run for stdio transport. Can be uv, uvx, npx and so on. */
  command?: string | null;
  /** Args to give the command as a list. ex:  ['--directory', '/directory/to/mcp', 'run', 'server.py'] */
  args?: string[] | null;
  /** Environment variables to give the MCP server */
  env?: {
    [key: string]: string;
  } | null;
};
export type CreateMcpAgentRequest = {
  name: string;
  mcp_servers: McpServerConfiguration[];
  role: string;
  description: string;
  tags?: string[] | null;
};
export type ModelConfiguration = {
  /** Provider of the AI model, e.g., openai, ollama, azure. */
  provider?: string | null;
  /** Model name, e.g., gpt-4o, llama2. */
  name?: string | null;
  /** Additional provider-specific settings, e.g., Azure deployment name. */
  settings?: {
    [key: string]: any;
  } | null;
};
export type UiHints = {
  multiline?: boolean;
  max_lines?: number;
  placeholder?: string | null;
  markdown?: boolean;
  textarea?: boolean;
  group?: string | null;
};
export type FieldSpec = {
  key: string;
  type:
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
  title: string;
  description?: string | null;
  required?: boolean;
  default?: any | null;
  enum?: string[] | null;
  min?: number | null;
  max?: number | null;
  pattern?: string | null;
  item_type?:
    | (
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
        | "url"
      )
    | null;
  ui?: UiHints;
};
export type McpServerSpec = {
  allow_user_add?: boolean;
  allowed_transports?: string[];
  required_fields?: string[];
};
export type AgentTuning = {
  fields?: FieldSpec[];
  mcp_servers?: McpServerSpec | null;
};
export type AgentChatOptions = {
  search_policy_selection?: boolean;
  libraries_selection?: boolean;
  record_audio_files?: boolean;
  attach_files?: boolean;
};
export type Agent = {
  name: string;
  enabled?: boolean;
  class_path?: string | null;
  model?: ModelConfiguration | null;
  tags?: string[];
  role: string;
  description: string;
  tuning?: AgentTuning | null;
  /** List of active MCP server configurations for this agent. */
  mcp_servers?: McpServerConfiguration[];
  chat_options?: AgentChatOptions;
  type?: "agent";
};
export type Leader = {
  name: string;
  enabled?: boolean;
  class_path?: string | null;
  model?: ModelConfiguration | null;
  tags?: string[];
  role: string;
  description: string;
  tuning?: AgentTuning | null;
  /** List of active MCP server configurations for this agent. */
  mcp_servers?: McpServerConfiguration[];
  chat_options?: AgentChatOptions;
  type?: "leader";
  /** Names of agents in this leader's crew (if any). */
  crew?: string[];
};
export type Role = "user" | "assistant" | "tool" | "system";
export type Channel =
  | "final"
  | "plan"
  | "thought"
  | "observation"
  | "tool_call"
  | "tool_result"
  | "error"
  | "system_note";
export type CodePart = {
  type?: "code";
  language?: string | null;
  code: string;
};
export type GeoPart = {
  type?: "geo";
  geojson: {
    [key: string]: any;
  };
  popup_property?: string | null;
  fit_bounds?: boolean;
  style?: {
    [key: string]: any;
  } | null;
};
export type ImageUrlPart = {
  type?: "image_url";
  url: string;
  alt?: string | null;
};
export type LinkKind = "citation" | "download" | "external" | "dashboard" | "related";
export type LinkPart = {
  type?: "link";
  href: string;
  title?: string | null;
  kind?: LinkKind;
  rel?: string | null;
  mime?: string | null;
  source_id?: string | null;
};
export type TextPart = {
  type?: "text";
  text: string;
};
export type ToolCallPart = {
  type?: "tool_call";
  call_id: string;
  name: string;
  args: {
    [key: string]: any;
  };
};
export type ToolResultPart = {
  type?: "tool_result";
  call_id: string;
  ok?: boolean | null;
  latency_ms?: number | null;
  content: string;
};
export type ChatTokenUsage = {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
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
export type FinishReason = "stop" | "length" | "content_filter" | "tool_calls" | "cancelled" | "other";
export type ChatMetadata = {
  model?: string | null;
  token_usage?: ChatTokenUsage | null;
  sources?: VectorSearchHit[];
  agent_name?: string | null;
  latency_ms?: number | null;
  finish_reason?: FinishReason | null;
  extras?: {
    [key: string]: any;
  };
};
export type ChatMessage = {
  session_id: string;
  exchange_id: string;
  rank: number;
  timestamp: string;
  role: Role;
  channel: Channel;
  parts: (
    | ({
        type: "code";
      } & CodePart)
    | ({
        type: "geo";
      } & GeoPart)
    | ({
        type: "image_url";
      } & ImageUrlPart)
    | ({
        type: "link";
      } & LinkPart)
    | ({
        type: "text";
      } & TextPart)
    | ({
        type: "tool_call";
      } & ToolCallPart)
    | ({
        type: "tool_result";
      } & ToolResultPart)
  )[];
  metadata?: ChatMetadata;
};
export type RuntimeContext = {
  selected_document_libraries_ids?: string[] | null;
  selected_prompt_ids?: string[] | null;
  selected_template_ids?: string[] | null;
  selected_chat_context_ids?: string[] | null;
  search_policy?: string | null;
  [key: string]: any;
};
export type ChatAskInput = {
  session_id?: string | null;
  message: string;
  agent_name: string;
  runtime_context?: RuntimeContext | null;
  client_exchange_id?: string | null;
};
export type StreamEvent = {
  type?: "stream";
  message: ChatMessage;
};
export type SessionSchema = {
  id: string;
  user_id: string;
  title: string;
  updated_at: string;
};
export type FinalEvent = {
  type?: "final";
  messages: ChatMessage[];
  session: SessionSchema;
};
export type ErrorEvent = {
  type?: "error";
  content: string;
  session_id?: string | null;
};
export type SessionWithFiles = {
  id: string;
  user_id: string;
  title: string;
  updated_at: string;
  file_names?: string[];
};
export type MetricsBucket = {
  timestamp: string;
  group: {
    [key: string]: any;
  };
  aggregations: {
    [key: string]: number | number[];
  };
};
export type MetricsResponse = {
  precision: string;
  buckets: MetricsBucket[];
};
export type EchoEnvelope = {
  kind:
    | "ChatMessage"
    | "StreamEvent"
    | "FinalEvent"
    | "ErrorEvent"
    | "SessionSchema"
    | "SessionWithFiles"
    | "MetricsResponse"
    | "MetricsBucket"
    | "VectorSearchHit"
    | "RuntimeContext";
  /** Schema payload being echoed */
  payload:
    | ChatMessage
    | ChatAskInput
    | StreamEvent
    | FinalEvent
    | ErrorEvent
    | SessionSchema
    | SessionWithFiles
    | MetricsResponse
    | MetricsBucket
    | VectorSearchHit
    | RuntimeContext;
};
export type FrontendFlags = {
  enableK8Features?: boolean;
  enableElecWarfare?: boolean;
};
export type Properties = {
  logoName?: string;
  siteDisplayName?: string;
};
export type FrontendSettings = {
  feature_flags: FrontendFlags;
  properties: Properties;
};
export type UserSecurity = {
  enabled?: boolean;
  realm_url: string;
  client_id: string;
};
export type FrontendConfigDto = {
  frontend_settings: FrontendSettings;
  user_auth: UserSecurity;
};
export type AgentTuning2 = {
  fields?: FieldSpec[];
  mcp_servers?: McpServerSpec | null;
};
export type Agent2 = {
  name: string;
  enabled?: boolean;
  class_path?: string | null;
  model?: ModelConfiguration | null;
  tags?: string[];
  role: string;
  description: string;
  tuning?: AgentTuning2 | null;
  /** List of active MCP server configurations for this agent. */
  mcp_servers?: McpServerConfiguration[];
  chat_options?: AgentChatOptions;
  type?: "agent";
};
export type Leader2 = {
  name: string;
  enabled?: boolean;
  class_path?: string | null;
  model?: ModelConfiguration | null;
  tags?: string[];
  role: string;
  description: string;
  tuning?: AgentTuning2 | null;
  /** List of active MCP server configurations for this agent. */
  mcp_servers?: McpServerConfiguration[];
  chat_options?: AgentChatOptions;
  type?: "leader";
  /** Names of agents in this leader's crew (if any). */
  crew?: string[];
};
export type ChatMessage2 = {
  session_id: string;
  exchange_id: string;
  rank: number;
  timestamp: string;
  role: Role;
  channel: Channel;
  parts: (
    | ({
        type: "code";
      } & CodePart)
    | ({
        type: "geo";
      } & GeoPart)
    | ({
        type: "image_url";
      } & ImageUrlPart)
    | ({
        type: "link";
      } & LinkPart)
    | ({
        type: "text";
      } & TextPart)
    | ({
        type: "tool_call";
      } & ToolCallPart)
    | ({
        type: "tool_result";
      } & ToolResultPart)
  )[];
  metadata?: ChatMetadata;
};
export type BodyUploadFileAgenticV1ChatbotUploadPost = {
  session_id: string;
  agent_name: string;
  file: Blob;
};
export type FeedbackRecord = {
  id: string;
  /** Session ID associated with the feedback */
  session_id: string;
  /** Message ID the feedback refers to */
  message_id: string;
  /** Name of the agent that generated the message */
  agent_name: string;
  /** User rating, typically 1–5 stars */
  rating: number;
  /** Optional user comment or clarification */
  comment?: string | null;
  /** Timestamp when the feedback was submitted */
  created_at: string;
  /** Optional user ID if identity is tracked */
  user_id: string;
};
export type FeedbackPayload = {
  rating: number;
  comment?: string | null;
  messageId: string;
  sessionId: string;
  agentName: string;
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
export const {
  useCreateAgentAgenticV1AgentsCreatePostMutation,
  useUpdateAgentAgenticV1AgentsUpdatePutMutation,
  useDeleteAgentAgenticV1AgentsNameDeleteMutation,
  useListRuntimeSourceKeysAgenticV1AgentsSourceKeysGetQuery,
  useLazyListRuntimeSourceKeysAgenticV1AgentsSourceKeysGetQuery,
  useRuntimeSourceByObjectAgenticV1AgentsSourceByObjectGetQuery,
  useLazyRuntimeSourceByObjectAgenticV1AgentsSourceByObjectGetQuery,
  useRuntimeSourceByModuleAgenticV1AgentsSourceByModuleGetQuery,
  useLazyRuntimeSourceByModuleAgenticV1AgentsSourceByModuleGetQuery,
  useEchoSchemaAgenticV1SchemasEchoPostMutation,
  useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery,
  useLazyGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery,
  useGetUserPermissionsAgenticV1ConfigPermissionsGetQuery,
  useLazyGetUserPermissionsAgenticV1ConfigPermissionsGetQuery,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useLazyGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useLazyGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
  useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
  useUploadFileAgenticV1ChatbotUploadPostMutation,
  useHealthzAgenticV1HealthzGetQuery,
  useLazyHealthzAgenticV1HealthzGetQuery,
  useReadyAgenticV1ReadyGetQuery,
  useLazyReadyAgenticV1ReadyGetQuery,
  useGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery,
  useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery,
  useGetFeedbackAgenticV1ChatbotFeedbackGetQuery,
  useLazyGetFeedbackAgenticV1ChatbotFeedbackGetQuery,
  usePostFeedbackAgenticV1ChatbotFeedbackPostMutation,
  useDeleteFeedbackAgenticV1ChatbotFeedbackFeedbackIdDeleteMutation,
  useQueryLogsAgenticV1LogsQueryPostMutation,
} = injectedRtkApi;
