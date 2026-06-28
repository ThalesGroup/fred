import { runtimeApi as api } from "./runtimeApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    listAgentsPodV1AgentsGet: build.query<ListAgentsPodV1AgentsGetApiResponse, ListAgentsPodV1AgentsGetApiArg>({
      query: () => ({ url: `/pod/v1/agents` }),
    }),
    getAuditEventsPodV1AgentsAuditEventsGet: build.query<
      GetAuditEventsPodV1AgentsAuditEventsGetApiResponse,
      GetAuditEventsPodV1AgentsAuditEventsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/pod/v1/agents/audit-events`,
        params: {
          limit: queryArg.limit,
        },
      }),
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
    evaluatePodV1AgentsEvaluatePost: build.mutation<
      EvaluatePodV1AgentsEvaluatePostApiResponse,
      EvaluatePodV1AgentsEvaluatePostApiArg
    >({
      query: (queryArg) => ({ url: `/pod/v1/agents/evaluate`, method: "POST", body: queryArg.runtimeExecuteRequest }),
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
    getKpiTurnsPodV1AgentsKpiTurnsGet: build.query<
      GetKpiTurnsPodV1AgentsKpiTurnsGetApiResponse,
      GetKpiTurnsPodV1AgentsKpiTurnsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/pod/v1/agents/kpi-turns`,
        params: {
          limit: queryArg.limit,
        },
      }),
    }),
    getMcpCatalogPodV1AgentsMcpCatalogGet: build.query<
      GetMcpCatalogPodV1AgentsMcpCatalogGetApiResponse,
      GetMcpCatalogPodV1AgentsMcpCatalogGetApiArg
    >({
      query: () => ({ url: `/pod/v1/agents/mcp-catalog` }),
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
    deleteSessionHistoryPodV1AgentsSessionsSessionIdDelete: build.mutation<
      DeleteSessionHistoryPodV1AgentsSessionsSessionIdDeleteApiResponse,
      DeleteSessionHistoryPodV1AgentsSessionsSessionIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/pod/v1/agents/sessions/${queryArg.sessionId}`, method: "DELETE" }),
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
      query: (queryArg) => ({
        url: `/pod/v1/agents/templates`,
        params: {
          include_non_public: queryArg.includeNonPublic,
        },
      }),
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
export type GetAuditEventsPodV1AgentsAuditEventsGetApiResponse =
  /** status 200 Successful Response */ AuditEventRecord[];
export type GetAuditEventsPodV1AgentsAuditEventsGetApiArg = {
  limit?: number;
};
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
export type EvaluatePodV1AgentsEvaluatePostApiResponse = /** status 200 Successful Response */ EvalTrace;
export type EvaluatePodV1AgentsEvaluatePostApiArg = {
  runtimeExecuteRequest: RuntimeExecuteRequest;
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
          kind: "execution_error";
        } & RuntimeErrorEvent)
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
          kind: "thought_delta";
        } & ThoughtDeltaEvent)
      | ({
          kind: "thought_end";
        } & ThoughtEndEvent)
      | ({
          kind: "thought_start";
        } & ThoughtStartEvent)
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
export type GetKpiTurnsPodV1AgentsKpiTurnsGetApiResponse = /** status 200 Successful Response */ KpiTurnRecord[];
export type GetKpiTurnsPodV1AgentsKpiTurnsGetApiArg = {
  limit?: number;
};
export type GetMcpCatalogPodV1AgentsMcpCatalogGetApiResponse = /** status 200 Successful Response */ McpCatalogResponse;
export type GetMcpCatalogPodV1AgentsMcpCatalogGetApiArg = void;
export type ListSessionsPodV1AgentsSessionsGetApiResponse = /** status 200 Successful Response */ string[];
export type ListSessionsPodV1AgentsSessionsGetApiArg = {
  userId?: string | null;
};
export type DeleteSessionHistoryPodV1AgentsSessionsSessionIdDeleteApiResponse = /** status 200 Successful Response */ {
  [key: string]: number;
};
export type DeleteSessionHistoryPodV1AgentsSessionsSessionIdDeleteApiArg = {
  sessionId: string;
};
export type GetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetApiResponse =
  /** status 200 Successful Response */ ChatMessage[];
export type GetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetApiArg = {
  sessionId: string;
};
export type ListAgentTemplatesPodV1AgentsTemplatesGetApiResponse =
  /** status 200 Successful Response */ AgentTemplateSummary[];
export type ListAgentTemplatesPodV1AgentsTemplatesGetApiArg = {
  includeNonPublic?: boolean;
};
export type ChatCompletionsV1ChatCompletionsPostApiResponse = /** status 200 Successful Response */ any;
export type ChatCompletionsV1ChatCompletionsPostApiArg = {
  openAiChatRequest: OpenAiChatRequest;
};
export type ListModelsV1ModelsGetApiResponse = /** status 200 Successful Response */ OpenAiModelList;
export type ListModelsV1ModelsGetApiArg = void;
export type AuditEventRecord = {
  agent_id?: string | null;
  agent_instance_id?: string | null;
  audit_event: string;
  team_id?: string | null;
  ts: string;
  user_id?: string;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
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
export type EvalStep = {
  arguments?: {
    [key: string]: any;
  } | null;
  call_id?: string | null;
  content?: string | null;
  error_message?: string | null;
  is_error?: boolean | null;
  kind: string;
  node_id?: string | null;
  tool_name?: string | null;
};
export type EvalTrace = {
  agent_id: string;
  agent_tags?: string[];
  error?: string | null;
  finish_reason?: string | null;
  input: string;
  latency_ms: number;
  model_name?: string | null;
  output?: string | null;
  retrieval_context?: string[];
  session_id: string;
  steps?: EvalStep[];
  token_usage?: {
    [key: string]: number;
  } | null;
  tools_called?: string[];
};
export type ConversationTurn = {
  agent_name?: string | null;
  agent_response: string;
  user_message: string;
};
export type RuntimeContext = {
  access_token?: string | null;
  access_token_expires_at?: number | null;
  agent_instance_id?: string | null;
  attachments_markdown?: string | null;
  checkpoint_id?: string | null;
  context_prompt_text?: string | null;
  correlation_id?: string | null;
  deep_search?: boolean | null;
  exchange_id?: string | null;
  execution_action?: ("execute" | "resume") | null;
  include_corpus_scope?: boolean | null;
  include_session_scope?: boolean | null;
  language?: string | null;
  refresh_token?: string | null;
  search_policy?: ("strict" | "hybrid" | "semantic") | null;
  search_rag_scope?: ("corpus_only" | "hybrid" | "general_only") | null;
  selected_chat_context_ids?: string[] | null;
  selected_document_libraries_ids?: string[] | null;
  selected_document_uids?: string[] | null;
  session_id?: string | null;
  team_id?: string | null;
  template_agent_id?: string | null;
  trace_id?: string | null;
  user_groups?: string[] | null;
  user_id?: string | null;
};
export type RuntimeExecuteRequest = {
  /** Direct template agent_id. For internal/dev use only. */
  agent_id?: string | null;
  /** Managed agent instance ID (preferred). The pod authorizes the caller (Keycloak JWT + OpenFGA) on runtime_context.team_id. */
  agent_instance_id?: string | null;
  /** Checkpoint identifier for precise graph-state resume. */
  checkpoint_id?: string | null;
  /** Optional tuning value overrides for direct template execution (agent_id mode). Ignored when agent_instance_id is set. Intended for CLI and dev tooling — not for production frontend calls. */
  inline_tuning?: {
    [key: string]:
      | string
      | number
      | number
      | boolean
      | (string | number | number | boolean)[]
      | {
          [key: string]: string | number | number | boolean;
        };
  } | null;
  /** User turn input. Ignored when resume_payload is set (HITL resume). */
  input?: string;
  /** Prior conversation turns forwarded by the calling agent. Used to seed memory in sub-agents invoked via context.invoke_agent(). Graph sub-agents receive history through build_turn_state; ReAct sub-agents receive it as a leading SystemMessage. */
  invocation_turns?: ConversationTurn[];
  /** HITL resume data returned by the user after an AwaitingHumanRuntimeEvent. When set, input is ignored and the graph resumes from its checkpointed state. */
  resume_payload?: any | null;
  /** Per-request execution context carrying per-turn user retrieval selections (library IDs, search policy, context prompt text) and user auth delegation. Group A identity fields (user_id, team_id, session_id): for managed execution the pod authorizes the caller against OpenFGA on team_id, so team_id MUST be set. Group B auth fields (access_token, refresh_token) are required when the runtime calls knowledge-flow backend on behalf of the user. */
  runtime_context?: RuntimeContext | null;
  /** Session identifier for multi-turn continuity. Keep stable across turns. */
  session_id?: string | null;
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
export type RuntimeErrorEvent = {
  kind?: "execution_error";
  message: string;
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
export type ThoughtDeltaEvent = {
  delta: string;
  kind?: "thought_delta";
  sequence?: number;
  thought_id: string;
};
export type ThoughtEndEvent = {
  conclusion?: string | null;
  duration_ms?: number | null;
  kind?: "thought_end";
  sequence?: number;
  thought_id: string;
};
export type ThoughtStartEvent = {
  kind?: "thought_start";
  phase: "planning" | "tool_use" | "observation" | "reflection" | "synthesis";
  sequence?: number;
  source?: "authored" | "model_native";
  thought_id: string;
  title?: string | null;
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
export type KpiTurnRecord = {
  exchange_id: string;
  finish_reason?: string;
  input_tokens?: number | null;
  is_error: boolean;
  model_name?: string | null;
  output_tokens?: number | null;
  runtime_id?: string | null;
  session_id: string | null;
  team_id?: string | null;
  template_agent_id?: string | null;
  tool_count?: number;
  total_ms: number;
  ts: string;
  user_id: string;
};
export type McpCatalogEntry = {
  description?: string | null;
  enabled: boolean;
  id: string;
  name: string;
  transport?: string | null;
};
export type McpCatalogResponse = {
  servers: McpCatalogEntry[];
};
export type Channel =
  | "final"
  | "plan"
  | "thought"
  | "observation"
  | "tool_call"
  | "tool_result"
  | "error"
  | "system_note"
  | "hitl_request"
  | "hitl_response";
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
export type HitlChoiceRecord = {
  id: string;
  label: string;
};
export type HitlRequestPart = {
  choices: HitlChoiceRecord[];
  question: string;
  stage?: string | null;
  title?: string | null;
  type?: "hitl_request";
};
export type HitlResponsePart = {
  choice_id: string;
  label?: string | null;
  type?: "hitl_response";
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
        type: "hitl_request";
      } & HitlRequestPart)
    | ({
        type: "hitl_response";
      } & HitlResponsePart)
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
  default?:
    | string
    | number
    | number
    | boolean
    | (string | number | number | boolean)[]
    | {
        [key: string]: string | number | number | boolean;
      }
    | null;
  default_by_lang?: {
    [key: string]: string;
  } | null;
  description?: string | null;
  description_by_lang?: {
    [key: string]: string;
  } | null;
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
export type McpServerConfiguration = {
  /** Non-negotiable behavioral instructions enforced whenever this server is active. The runtime appends them to the effective system prompt after any operator override. */
  agent_instructions?: string | null;
  /** Args to give the command as a list. */
  args?: string[] | null;
  /** Client authentication mode. */
  auth_mode?: ClientAuthMode;
  /** Command to run for stdio transport. */
  command?: string | null;
  /** User-facing configuration options declared by this server. Rendered in the agent form beneath the server's activation checkbox. Values flow into RuntimeContext as tuning field values at execution time. */
  config_fields?: FieldSpec[];
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
export type McpServerRef = {
  id: string;
  /** When True the server is displayed in the enrollment form but its toggle is read-only. The operator can see and configure the server but cannot remove it. Used by specialized templates to protect their canonical tool set. */
  locked?: boolean;
  require_tools?: string[];
};
export type AgentTuning = {
  /** The agent's mandatory description for the UI. */
  description: string;
  fields?: FieldSpec[];
  /** Per-server MCP configuration values keyed first by server id and then by FieldSpec.key. This stays distinct from generic agent tuning so tool-owned options do not masquerade as prompts or runtime settings. */
  mcp_config_values?: {
    [key: string]: {
      [key: string]:
        | string
        | number
        | number
        | boolean
        | (string | number | number | boolean)[]
        | {
            [key: string]: string | number | number | boolean;
          };
    };
  };
  mcp_servers?: McpServerRef[];
  /** The agent's mandatory role for discovery. */
  role: string;
  /** Admin-chosen MCP server activation policy. None means inherit the template default selection (all declared servers active); [] means activate no MCP servers; a non-empty list means activate exactly that subset. */
  selected_mcp_server_ids?: string[] | null;
  tags?: string[];
  /** User-set agent tuning values keyed by FieldSpec.key, forwarded from control-plane. This surface is reserved for agent-authored fields such as prompts.* and settings.*. */
  values?: {
    [key: string]:
      | string
      | number
      | number
      | boolean
      | (string | number | number | boolean)[]
      | {
          [key: string]: string | number | number | boolean;
        };
  };
};
export type ExecutionCategory = "graph" | "react" | "deep" | "proxy";
export type AgentTemplateSummary = {
  available_mcp_servers?: McpServerConfiguration[];
  default_tuning: AgentTuning;
  description: string;
  description_by_lang?: {
    [key: string]: string;
  } | null;
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
  useGetAuditEventsPodV1AgentsAuditEventsGetQuery,
  useLazyGetAuditEventsPodV1AgentsAuditEventsGetQuery,
  useListCheckpointThreadsPodV1AgentsCheckpointsGetQuery,
  useLazyListCheckpointThreadsPodV1AgentsCheckpointsGetQuery,
  useGetCheckpointStorageStatsPodV1AgentsCheckpointsStatsGetQuery,
  useLazyGetCheckpointStorageStatsPodV1AgentsCheckpointsStatsGetQuery,
  useDeleteCheckpointThreadPodV1AgentsCheckpointsSessionIdDeleteMutation,
  useGetCheckpointThreadPodV1AgentsCheckpointsSessionIdGetQuery,
  useLazyGetCheckpointThreadPodV1AgentsCheckpointsSessionIdGetQuery,
  useEvaluatePodV1AgentsEvaluatePostMutation,
  useExecutePodV1AgentsExecutePostMutation,
  useExecuteStreamPodV1AgentsExecuteStreamPostMutation,
  useGetKpiTurnsPodV1AgentsKpiTurnsGetQuery,
  useLazyGetKpiTurnsPodV1AgentsKpiTurnsGetQuery,
  useGetMcpCatalogPodV1AgentsMcpCatalogGetQuery,
  useLazyGetMcpCatalogPodV1AgentsMcpCatalogGetQuery,
  useListSessionsPodV1AgentsSessionsGetQuery,
  useLazyListSessionsPodV1AgentsSessionsGetQuery,
  useDeleteSessionHistoryPodV1AgentsSessionsSessionIdDeleteMutation,
  useGetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetQuery,
  useLazyGetSessionMessagesPodV1AgentsSessionsSessionIdMessagesGetQuery,
  useListAgentTemplatesPodV1AgentsTemplatesGetQuery,
  useLazyListAgentTemplatesPodV1AgentsTemplatesGetQuery,
  useChatCompletionsV1ChatCompletionsPostMutation,
  useListModelsV1ModelsGetQuery,
  useLazyListModelsV1ModelsGetQuery,
} = injectedRtkApi;
