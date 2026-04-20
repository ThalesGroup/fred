import { runtimeApi as api } from "./runtimeApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    listAgentsPodV1AgentsGet: build.query<ListAgentsPodV1AgentsGetApiResponse, ListAgentsPodV1AgentsGetApiArg>({
      query: () => ({ url: `/pod/v1/agents` }),
    }),
    listCheckpointThreadsPodV1AgentsCheckpointsGet: build.query<
      ListCheckpointThreadsPodV1AgentsCheckpointsGetApiResponse,
      ListCheckpointThreadsPodV1AgentsCheckpointsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/pod/v1/agents/checkpoints`,
        params: {
          limit: queryArg.limit,
        },
      }),
    }),
    getCheckpointStorageStatsPodV1AgentsCheckpointsStatsGet: build.query<
      GetCheckpointStorageStatsPodV1AgentsCheckpointsStatsGetApiResponse,
      GetCheckpointStorageStatsPodV1AgentsCheckpointsStatsGetApiArg
    >({
      query: () => ({ url: `/pod/v1/agents/checkpoints/_stats` }),
    }),
    deleteCheckpointThreadPodV1AgentsCheckpointsSessionIdDelete: build.mutation<
      DeleteCheckpointThreadPodV1AgentsCheckpointsSessionIdDeleteApiResponse,
      DeleteCheckpointThreadPodV1AgentsCheckpointsSessionIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/pod/v1/agents/checkpoints/${queryArg.sessionId}`, method: "DELETE" }),
    }),
    getCheckpointThreadPodV1AgentsCheckpointsSessionIdGet: build.query<
      GetCheckpointThreadPodV1AgentsCheckpointsSessionIdGetApiResponse,
      GetCheckpointThreadPodV1AgentsCheckpointsSessionIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/pod/v1/agents/checkpoints/${queryArg.sessionId}` }),
    }),
    executePodV1AgentsExecutePost: build.mutation<
      ExecutePodV1AgentsExecutePostApiResponse,
      ExecutePodV1AgentsExecutePostApiArg
    >({
      query: (queryArg) => ({ url: `/pod/v1/agents/execute`, method: "POST", body: queryArg.runtimeExecuteRequest }),
    }),
    executeStreamPodV1AgentsExecuteStreamPost: build.mutation<
      ExecuteStreamPodV1AgentsExecuteStreamPostApiResponse,
      ExecuteStreamPodV1AgentsExecuteStreamPostApiArg
    >({
      query: (queryArg) => ({
        url: `/pod/v1/agents/execute/stream`,
        method: "POST",
        body: queryArg.runtimeExecuteRequest,
      }),
    }),
    listSessionsPodV1AgentsSessionsGet: build.query<
      ListSessionsPodV1AgentsSessionsGetApiResponse,
      ListSessionsPodV1AgentsSessionsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/pod/v1/agents/sessions`,
        params: {
          user_id: queryArg.userId,
        },
      }),
    }),
    getSessionMessagesPodV1AgentsSessionsSessionIdMessagesGet: build.query<
      GetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetApiResponse,
      GetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetApiArg
    >({
      query: (queryArg) => ({ url: `/pod/v1/agents/sessions/${queryArg.sessionId}/messages` }),
    }),
    listAgentTemplatesPodV1AgentsTemplatesGet: build.query<
      ListAgentTemplatesPodV1AgentsTemplatesGetApiResponse,
      ListAgentTemplatesPodV1AgentsTemplatesGetApiArg
    >({
      query: () => ({ url: `/pod/v1/agents/templates` }),
    }),
    chatCompletionsV1ChatCompletionsPost: build.mutation<
      ChatCompletionsV1ChatCompletionsPostApiResponse,
      ChatCompletionsV1ChatCompletionsPostApiArg
    >({
      query: (queryArg) => ({ url: `/v1/chat/completions`, method: "POST", body: queryArg.openAiChatRequest }),
    }),
    listModelsV1ModelsGet: build.query<ListModelsV1ModelsGetApiResponse, ListModelsV1ModelsGetApiArg>({
      query: () => ({ url: `/v1/models` }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as runtimeApi };
export type ListAgentsPodV1AgentsGetApiResponse = /** status 200 Successful Response */ string[];
export type ListAgentsPodV1AgentsGetApiArg = void;
export type ListCheckpointThreadsPodV1AgentsCheckpointsGetApiResponse =
  /** status 200 Successful Response */ CheckpointThreadSummary[];
export type ListCheckpointThreadsPodV1AgentsCheckpointsGetApiArg = {
  limit?: number;
};
export type GetCheckpointStorageStatsPodV1AgentsCheckpointsStatsGetApiResponse =
  /** status 200 Successful Response */ CheckpointStorageStats;
export type GetCheckpointStorageStatsPodV1AgentsCheckpointsStatsGetApiArg = void;
export type DeleteCheckpointThreadPodV1AgentsCheckpointsSessionIdDeleteApiResponse = unknown;
export type DeleteCheckpointThreadPodV1AgentsCheckpointsSessionIdDeleteApiArg = {
  sessionId: string;
};
export type GetCheckpointThreadPodV1AgentsCheckpointsSessionIdGetApiResponse =
  /** status 200 Successful Response */ CheckpointThreadDetail;
export type GetCheckpointThreadPodV1AgentsCheckpointsSessionIdGetApiArg = {
  sessionId: string;
};
export type ExecutePodV1AgentsExecutePostApiResponse = /** status 200 Successful Response */
  | (
      | ({
          kind: "assistant_delta";
        } & AssistantDeltaRuntimeEvent)
      | ({
          kind: "awaiting_human";
        } & AwaitingHumanRuntimeEvent)
      | ({
          kind: "final";
        } & FinalRuntimeEvent)
      | ({
          kind: "node_error";
        } & NodeErrorRuntimeEvent)
      | ({
          kind: "status";
        } & StatusRuntimeEvent)
      | ({
          kind: "tool_call";
        } & ToolCallRuntimeEvent)
      | ({
          kind: "tool_result";
        } & ToolResultRuntimeEvent)
      | ({
          kind: "turn_persisted";
        } & TurnPersistedEvent)
    )
  | RuntimeErrorPayload;
export type ExecutePodV1AgentsExecutePostApiArg = {
  runtimeExecuteRequest: RuntimeExecuteRequest;
};
export type ExecuteStreamPodV1AgentsExecuteStreamPostApiResponse = /** status 200 Successful Response */ any;
export type ExecuteStreamPodV1AgentsExecuteStreamPostApiArg = {
  runtimeExecuteRequest: RuntimeExecuteRequest;
};
export type ListSessionsPodV1AgentsSessionsGetApiResponse = /** status 200 Successful Response */ string[];
export type ListSessionsPodV1AgentsSessionsGetApiArg = {
  userId: string;
};
export type GetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetApiResponse =
  /** status 200 Successful Response */ ChatMessage[];
export type GetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetApiArg = {
  sessionId: string;
};
export type ListAgentTemplatesPodV1AgentsTemplatesGetApiResponse =
  /** status 200 Successful Response */ AgentTemplateSummary[];
export type ListAgentTemplatesPodV1AgentsTemplatesGetApiArg = void;
export type ChatCompletionsV1ChatCompletionsPostApiResponse = /** status 200 Successful Response */ any;
export type ChatCompletionsV1ChatCompletionsPostApiArg = {
  openAiChatRequest: OpenAiChatRequest;
};
export type ListModelsV1ModelsGetApiResponse = /** status 200 Successful Response */ OpenAiModelList;
export type ListModelsV1ModelsGetApiArg = void;
export type CheckpointThreadSummary = {
  blob_bytes_total: number;
  blob_count: number;
  checkpoint_bytes_total: number;
  checkpoint_count: number;
  first_created_at: string | null;
  latest_created_at: string | null;
  pending_write_count: number;
  session_id: string;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type CheckpointStorageStats = {
  blob_bytes_approx: number;
  blob_count: number;
  checkpoint_bytes_approx: number;
  checkpoint_count: number;
  pending_write_count: number;
  thread_count: number;
};
export type CheckpointEntry = {
  checkpoint_bytes: number;
  checkpoint_id: string;
  created_at: string | null;
  metadata: {
    [key: string]: any;
  };
  node_names: string[];
  parent_checkpoint_id: string | null;
  pending_write_count: number;
  source: string | null;
  step: number | null;
};
export type CheckpointThreadDetail = {
  checkpoints: CheckpointEntry[];
  session_id: string;
};
export type AssistantDeltaRuntimeEvent = {
  delta: string;
  kind?: "assistant_delta";
  sequence?: number;
};
export type HumanChoiceOption = {
  default?: boolean;
  description?: string | null;
  id: string;
  label: string;
};
export type HumanInputRequest = {
  checkpoint_id?: string | null;
  choices?: HumanChoiceOption[];
  free_text?: boolean;
  metadata?: {
    [key: string]: string | number | number | boolean | null;
  };
  question?: string | null;
  stage?: string | null;
  title?: string | null;
};
export type AwaitingHumanRuntimeEvent = {
  kind?: "awaiting_human";
  request: HumanInputRequest;
  sequence?: number;
};
export type VectorSearchHit = {
  author?: string | null;
  citation_url?: string | null;
  confidential?: boolean | null;
  content: string;
  created?: string | null;
  embedding_model?: string | null;
  file_name?: string | null;
  file_path?: string | null;
  has_visual_evidence?: boolean | null;
  language?: string | null;
  license?: string | null;
  mime_type?: string | null;
  modified?: string | null;
  page?: number | null;
  preview_at_url?: string | null;
  preview_url?: string | null;
  pull_location?: string | null;
  rank?: number | null;
  repo_url?: string | null;
  repository?: string | null;
  retrieval_session_id?: string | null;
  retrieved_at?: string | null;
  /** Similarity score from vector search */
  score: number;
  section?: string | null;
  slide_id?: number | null;
  slide_image_uri?: string | null;
  tag_full_paths?: string[];
  tag_ids?: string[];
  tag_names?: string[];
  title: string;
  token_count?: number | null;
  /** File type/category */
  type?: string | null;
  /** Document UID */
  uid: string;
  vector_index?: string | null;
  viewer_fragment?: string | null;
};
export type GeoPart = {
  fit_bounds?: boolean;
  geojson: {
    [key: string]: any;
  };
  popup_property?: string | null;
  style?: {
    [key: string]: any;
  } | null;
  type?: "geo";
};
export type LinkKind = "citation" | "download" | "external" | "dashboard" | "related" | "view";
export type LinkPart = {
  document_uid?: string | null;
  file_name?: string | null;
  href?: string | null;
  kind?: LinkKind;
  mime?: string | null;
  rel?: string | null;
  source_id?: string | null;
  title?: string | null;
  type?: "link";
};
export type FinalRuntimeEvent = {
  content?: string;
  finish_reason?: string | null;
  kind?: "final";
  model_name?: string | null;
  sequence?: number;
  sources?: VectorSearchHit[];
  token_usage?: {
    [key: string]: number;
  } | null;
  ui_parts?: (
    | ({
        type: "geo";
      } & GeoPart)
    | ({
        type: "link";
      } & LinkPart)
  )[];
};
export type NodeErrorRuntimeEvent = {
  error_message: string;
  kind?: "node_error";
  node_id: string;
  routed_to: string;
  sequence?: number;
};
export type StatusRuntimeEvent = {
  detail?: string | null;
  kind?: "status";
  sequence?: number;
  status: string;
};
export type ToolCallRuntimeEvent = {
  arguments?: {
    [key: string]: any;
  };
  call_id: string;
  kind?: "tool_call";
  sequence?: number;
  tool_name: string;
};
export type ToolResultRuntimeEvent = {
  call_id: string;
  content?: string;
  is_error?: boolean;
  kind?: "tool_result";
  sequence?: number;
  sources?: VectorSearchHit[];
  tool_name?: string | null;
  ui_parts?: (
    | ({
        type: "geo";
      } & GeoPart)
    | ({
        type: "link";
      } & LinkPart)
  )[];
};
export type TurnPersistedEvent = {
  exchange_id?: string | null;
  kind?: "turn_persisted";
  sequence?: number;
  session_id: string;
};
export type RuntimeErrorPayload = {
  error: string;
};
export type ExecutionGrantAction = "execute" | "resume";
export type ExecutionGrant = {
  action: ExecutionGrantAction;
  agent_instance_id: string;
  /** Intended runtime service/endpoint URL or identifier. */
  audience: string;
  correlation_id?: string | null;
  /** Grant expiry time as a Unix timestamp. */
  expires_at: number;
  /** Grant issuance time as a Unix timestamp. */
  issued_at: number;
  /** Optional permission scopes granted for this execution. */
  scopes?: string[];
  /** Optional logical storage scope name for session state. MUST NOT be a raw connection string, secret, or infrastructure credential. */
  storage_scope?: string | null;
  team_id: string;
  trace_id?: string | null;
  user_id: string;
};
export type RuntimeExecuteRequest = {
  /** Direct template agent_id. For internal/dev use only. */
  agent_id?: string | null;
  /** Managed agent instance ID (preferred). Requires execution_grant. */
  agent_instance_id?: string | null;
  /** Checkpoint identifier for precise graph-state resume. */
  checkpoint_id?: string | null;
  /** Authorization envelope issued by control-plane. Required when agent_instance_id is set. Runtime MUST reject requests with a missing or invalid grant. */
  execution_grant?: ExecutionGrant | null;
  /** User turn input. Ignored when resume_payload is set (HITL resume). */
  input?: string;
  /** HITL resume data returned by the user after an AwaitingHumanRuntimeEvent. When set, input is ignored and the graph resumes from its checkpointed state. */
  resume_payload?: any | null;
  /** Optional per-request context passthrough (language, user_groups, etc.). Kept for transitional compatibility; prefer execution_grant for identity fields. */
  runtime_context?: {
    [key: string]: any;
  } | null;
  /** Session identifier for multi-turn continuity. Keep stable across turns. */
  session_id?: string | null;
};
export type Channel =
  | "final"
  | "plan"
  | "thought"
  | "observation"
  | "tool_call"
  | "tool_result"
  | "error"
  | "system_note";
export type ChatTokenUsage = {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
};
export type ChatMetadata = {
  agent_id?: string | null;
  finish_reason?: string | null;
  latency_ms?: number | null;
  model?: string | null;
  sources?: VectorSearchHit[];
  token_usage?: ChatTokenUsage | null;
  [key: string]: any;
};
export type CodePart = {
  code: string;
  language?: string | null;
  type?: "code";
};
export type ImageUrlPart = {
  alt?: string | null;
  type?: "image_url";
  url: string;
};
export type TextPart = {
  text: string;
  type?: "text";
};
export type ToolCallPart = {
  args: {
    [key: string]: any;
  };
  call_id: string;
  name: string;
  type?: "tool_call";
};
export type ToolResultPart = {
  call_id: string;
  content: string;
  latency_ms?: number | null;
  ok?: boolean | null;
  type?: "tool_result";
};
export type Role = "user" | "assistant" | "tool" | "system";
export type ChatMessage = {
  channel: Channel;
  exchange_id: string;
  metadata?: ChatMetadata;
  parts: (
    | ({
        type: "code";
      } & CodePart)
    | ({
        type: "image_url";
      } & ImageUrlPart)
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
  rank: number;
  role: Role;
  session_id: string;
  timestamp: string;
};
export type ClientAuthMode = "user_token" | "no_token";
export type McpServerConfiguration = {
  /** Args to give the command as a list. */
  args?: string[] | null;
  /** Client authentication mode. */
  auth_mode?: ClientAuthMode;
  /** Command to run for stdio transport. */
  command?: string | null;
  /** react-i18next key for the description of the MCP server. */
  description?: string | null;
  /** If false, this MCP server is ignored. */
  enabled?: boolean;
  /** Environment variables to give the MCP server */
  env?: {
    [key: string]: string;
  } | null;
  id: string;
  /** react-i18next key for the name of the MCP server. */
  name: string;
  /** Local provider key when transport=inprocess. */
  provider?: string | null;
  /** How long (in seconds) the client will wait for a new event before disconnecting */
  sse_read_timeout?: number | null;
  /** MCP server transport. Can be sse, stdio, websocket, streamable_http, or inprocess (local toolkit provider exposed in the MCP catalog). */
  transport?: string | null;
  /** URL and endpoint of the MCP server */
  url?: string | null;
};
export type UiHints = {
  group?: string | null;
  hide?: boolean;
  markdown?: boolean;
  max_lines?: number;
  multiline?: boolean;
  placeholder?: string | null;
  textarea?: boolean;
};
export type FieldSpec = {
  default?: any | null;
  description?: string | null;
  enum?: string[] | null;
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
  key: string;
  max?: number | null;
  min?: number | null;
  pattern?: string | null;
  required?: boolean;
  title: string;
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
  ui?: UiHints;
};
export type McpServerRef = {
  id: string;
  require_tools?: string[];
};
export type AgentTuning = {
  /** The agent's mandatory description for the UI. */
  description: string;
  fields?: FieldSpec[];
  mcp_servers?: McpServerRef[];
  /** The agent's mandatory role for discovery. */
  role: string;
  tags?: string[];
};
export type ExecutionCategory = "graph" | "react" | "deep" | "proxy";
export type AgentTemplateSummary = {
  available_mcp_servers?: McpServerConfiguration[];
  default_tuning: AgentTuning;
  description: string;
  kind: ExecutionCategory;
  template_agent_id: string;
  title: string;
};
export type OpenAiMessage = {
  content: string;
  role: "system" | "user" | "assistant";
};
export type OpenAiChatRequest = {
  messages: OpenAiMessage[];
  model: string;
  stream?: boolean;
};
export type OpenAiModelCard = {
  created: number;
  id: string;
  object?: "model";
  owned_by?: string;
};
export type OpenAiModelList = {
  data?: OpenAiModelCard[];
  object?: "list";
};
export const {
  useListAgentsPodV1AgentsGetQuery,
  useLazyListAgentsPodV1AgentsGetQuery,
  useListCheckpointThreadsPodV1AgentsCheckpointsGetQuery,
  useLazyListCheckpointThreadsPodV1AgentsCheckpointsGetQuery,
  useGetCheckpointStorageStatsPodV1AgentsCheckpointsStatsGetQuery,
  useLazyGetCheckpointStorageStatsPodV1AgentsCheckpointsStatsGetQuery,
  useDeleteCheckpointThreadPodV1AgentsCheckpointsSessionIdDeleteMutation,
  useGetCheckpointThreadPodV1AgentsCheckpointsSessionIdGetQuery,
  useLazyGetCheckpointThreadPodV1AgentsCheckpointsSessionIdGetQuery,
  useExecutePodV1AgentsExecutePostMutation,
  useExecuteStreamPodV1AgentsExecuteStreamPostMutation,
  useListSessionsPodV1AgentsSessionsGetQuery,
  useLazyListSessionsPodV1AgentsSessionsGetQuery,
  useGetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetQuery,
  useLazyGetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetQuery,
  useListAgentTemplatesPodV1AgentsTemplatesGetQuery,
  useLazyListAgentTemplatesPodV1AgentsTemplatesGetQuery,
  useChatCompletionsV1ChatCompletionsPostMutation,
  useListModelsV1ModelsGetQuery,
  useLazyListModelsV1ModelsGetQuery,
} = injectedRtkApi;
