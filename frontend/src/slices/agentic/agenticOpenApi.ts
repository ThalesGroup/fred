import { agenticApi as api } from "./agenticApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
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
    completePromptAgenticV1PromptsCompletePost: build.mutation<
      CompletePromptAgenticV1PromptsCompletePostApiResponse,
      CompletePromptAgenticV1PromptsCompletePostApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/prompts/complete`,
        method: "POST",
        body: queryArg.promptCompleteRequest,
      }),
    }),
    createAgentAgenticV1AgentsCreatePost: build.mutation<
      CreateAgentAgenticV1AgentsCreatePostApiResponse,
      CreateAgentAgenticV1AgentsCreatePostApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/create`, method: "POST", body: queryArg.req }),
    }),
    updateAgentAgenticV1AgentsNamePut: build.mutation<
      UpdateAgentAgenticV1AgentsNamePutApiResponse,
      UpdateAgentAgenticV1AgentsNamePutApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/${queryArg.name}`, method: "PUT", body: queryArg.req }),
    }),
    deleteAgentAgenticV1AgentsNameDelete: build.mutation<
      DeleteAgentAgenticV1AgentsNameDeleteApiResponse,
      DeleteAgentAgenticV1AgentsNameDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/${queryArg.name}`, method: "DELETE" }),
    }),
    echoSchemaAgenticV1SchemasEchoPost: build.mutation<
      EchoSchemaAgenticV1SchemasEchoPostApiResponse,
      EchoSchemaAgenticV1SchemasEchoPostApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/schemas/echo`, method: "POST", body: queryArg.echoEnvelopeInput }),
    }),
    getFrontendConfigAgenticV1ConfigFrontendSettingsGet: build.query<
      GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiResponse,
      GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/config/frontend_settings` }),
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
  }),
  overrideExisting: false,
});
export { injectedRtkApi as agenticApi };
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
export type CompletePromptAgenticV1PromptsCompletePostApiResponse =
  /** status 200 Successful Response */ PromptCompleteResponse;
export type CompletePromptAgenticV1PromptsCompletePostApiArg = {
  promptCompleteRequest: PromptCompleteRequest;
};
export type CreateAgentAgenticV1AgentsCreatePostApiResponse = /** status 200 Successful Response */ any;
export type CreateAgentAgenticV1AgentsCreatePostApiArg = {
  req: {
    agent_type: "mcp";
  } & McpAgentRequest;
};
export type UpdateAgentAgenticV1AgentsNamePutApiResponse = /** status 200 Successful Response */ any;
export type UpdateAgentAgenticV1AgentsNamePutApiArg = {
  name: string;
  req: {
    agent_type: "mcp";
  } & McpAgentRequest;
};
export type DeleteAgentAgenticV1AgentsNameDeleteApiResponse = /** status 200 Successful Response */ any;
export type DeleteAgentAgenticV1AgentsNameDeleteApiArg = {
  name: string;
};
export type EchoSchemaAgenticV1SchemasEchoPostApiResponse = /** status 200 Successful Response */ EchoEnvelope;
export type EchoSchemaAgenticV1SchemasEchoPostApiArg = {
  echoEnvelopeInput: EchoEnvelope2;
};
export type GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiResponse = /** status 200 Successful Response */ any;
export type GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiArg = void;
export type GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse =
  /** status 200 Successful Response */ AgenticFlow[];
export type GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiArg = void;
export type GetSessionsAgenticV1ChatbotSessionsGetApiResponse =
  /** status 200 Successful Response */ SessionWithFiles[];
export type GetSessionsAgenticV1ChatbotSessionsGetApiArg = void;
export type GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiResponse =
  /** status 200 Successful Response */ ChatMessage[];
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
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type FeedbackPayload = {
  rating: number;
  comment?: string | null;
  messageId: string;
  sessionId: string;
  agentName: string;
};
export type PromptCompleteResponse = {
  prompt: string;
  completion: string;
};
export type PromptCompleteRequest = {
  prompt: string;
  temperature?: number | null;
  max_tokens?: number | null;
  model?: string | null;
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
export type McpAgentRequest = {
  agent_type: "mcp";
  name: string;
  base_prompt: string;
  mcp_servers: McpServerConfiguration[];
  role: string;
  nickname?: string | null;
  description: string;
  icon?: string | null;
  categories?: string[] | null;
  tag?: string | null;
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
  [key: string]: any;
};
export type ChatAskInput = {
  user_id: string;
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
export type StreamEvent2 = {
  type?: "stream";
  message: ChatMessage2;
};
export type FinalEvent2 = {
  type?: "final";
  messages: ChatMessage2[];
  session: SessionSchema;
};
export type EchoEnvelope2 = {
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
    | ChatMessage2
    | ChatAskInput
    | StreamEvent2
    | FinalEvent2
    | ErrorEvent
    | SessionSchema
    | SessionWithFiles
    | MetricsResponse
    | MetricsBucket
    | VectorSearchHit
    | RuntimeContext;
};
export type AgenticFlow = {
  /** Name of the agentic flow */
  name: string;
  /** Human-readable role of the agentic flow */
  role: string;
  /** Human-readable nickname of the agentic flow */
  nickname: string | null;
  /** Human-readable description of the agentic flow */
  description: string;
  /** Icon of the agentic flow */
  icon: string | null;
  /** List of experts in the agentic flow */
  experts: string[] | null;
  /** Human-readable tag of the agentic flow */
  tag: string | null;
};
export type BodyUploadFileAgenticV1ChatbotUploadPost = {
  user_id: string;
  session_id: string;
  agent_name: string;
  file: Blob;
};
export const {
  useGetFeedbackAgenticV1ChatbotFeedbackGetQuery,
  useLazyGetFeedbackAgenticV1ChatbotFeedbackGetQuery,
  usePostFeedbackAgenticV1ChatbotFeedbackPostMutation,
  useDeleteFeedbackAgenticV1ChatbotFeedbackFeedbackIdDeleteMutation,
  useCompletePromptAgenticV1PromptsCompletePostMutation,
  useCreateAgentAgenticV1AgentsCreatePostMutation,
  useUpdateAgentAgenticV1AgentsNamePutMutation,
  useDeleteAgentAgenticV1AgentsNameDeleteMutation,
  useEchoSchemaAgenticV1SchemasEchoPostMutation,
  useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery,
  useLazyGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery,
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
} = injectedRtkApi;
