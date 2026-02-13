import { agenticApi as api } from "./agenticApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    listAgentsAgenticV1AgentsGet: build.query<
      ListAgentsAgenticV1AgentsGetApiResponse,
      ListAgentsAgenticV1AgentsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/agents`,
        params: {
          owner_filter: queryArg.ownerFilter,
          team_id: queryArg.teamId,
        },
      }),
    }),
    createAgentAgenticV1AgentsCreatePost: build.mutation<
      CreateAgentAgenticV1AgentsCreatePostApiResponse,
      CreateAgentAgenticV1AgentsCreatePostApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/create`, method: "POST", body: queryArg.createAgentRequest }),
    }),
    updateAgentAgenticV1AgentsUpdatePut: build.mutation<
      UpdateAgentAgenticV1AgentsUpdatePutApiResponse,
      UpdateAgentAgenticV1AgentsUpdatePutApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/update`, method: "PUT", body: queryArg.agentSettings }),
    }),
    deleteAgentAgenticV1AgentsAgentIdDelete: build.mutation<
      DeleteAgentAgenticV1AgentsAgentIdDeleteApiResponse,
      DeleteAgentAgenticV1AgentsAgentIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/${queryArg.agentId}`, method: "DELETE" }),
    }),
    restoreAgentsAgenticV1AgentsRestorePost: build.mutation<
      RestoreAgentsAgenticV1AgentsRestorePostApiResponse,
      RestoreAgentsAgenticV1AgentsRestorePostApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/agents/restore`,
        method: "POST",
        params: {
          force_overwrite: queryArg.forceOverwrite,
        },
      }),
    }),
    listMcpServersAgenticV1AgentsMcpServersGet: build.query<
      ListMcpServersAgenticV1AgentsMcpServersGetApiResponse,
      ListMcpServersAgenticV1AgentsMcpServersGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/agents/mcp-servers` }),
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
    listMcpServersAgenticV1McpServersGet: build.query<
      ListMcpServersAgenticV1McpServersGetApiResponse,
      ListMcpServersAgenticV1McpServersGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/mcp/servers` }),
    }),
    createMcpServerAgenticV1McpServersPost: build.mutation<
      CreateMcpServerAgenticV1McpServersPostApiResponse,
      CreateMcpServerAgenticV1McpServersPostApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/mcp/servers`, method: "POST", body: queryArg.saveMcpServerRequest }),
    }),
    updateMcpServerAgenticV1McpServersServerIdPut: build.mutation<
      UpdateMcpServerAgenticV1McpServersServerIdPutApiResponse,
      UpdateMcpServerAgenticV1McpServersServerIdPutApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/mcp/servers/${queryArg.serverId}`,
        method: "PUT",
        body: queryArg.saveMcpServerRequest,
      }),
    }),
    deleteMcpServerAgenticV1McpServersServerIdDelete: build.mutation<
      DeleteMcpServerAgenticV1McpServersServerIdDeleteApiResponse,
      DeleteMcpServerAgenticV1McpServersServerIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/mcp/servers/${queryArg.serverId}`, method: "DELETE" }),
    }),
    restoreMcpServersFromConfigAgenticV1McpServersRestorePost: build.mutation<
      RestoreMcpServersFromConfigAgenticV1McpServersRestorePostApiResponse,
      RestoreMcpServersFromConfigAgenticV1McpServersRestorePostApiArg
    >({
      query: () => ({ url: `/agentic/v1/mcp/servers/restore`, method: "POST" }),
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
    getSessionsAgenticV1ChatbotSessionsGet: build.query<
      GetSessionsAgenticV1ChatbotSessionsGetApiResponse,
      GetSessionsAgenticV1ChatbotSessionsGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/chatbot/sessions` }),
    }),
    createSessionAgenticV1ChatbotSessionPost: build.mutation<
      CreateSessionAgenticV1ChatbotSessionPostApiResponse,
      CreateSessionAgenticV1ChatbotSessionPostApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/chatbot/session`,
        method: "POST",
        body: queryArg.createSessionPayload,
      }),
    }),
    getSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGet: build.query<
      GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiResponse,
      GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/chatbot/session/${queryArg.sessionId}/history`,
        params: {
          limit: queryArg.limit,
          offset: queryArg.offset,
          text_limit: queryArg.textLimit,
          text_offset: queryArg.textOffset,
        },
      }),
    }),
    getSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGet: build.query<
      GetSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGetApiResponse,
      GetSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/chatbot/session/${queryArg.sessionId}/message/${queryArg.rank}`,
        params: {
          text_limit: queryArg.textLimit,
          text_offset: queryArg.textOffset,
        },
      }),
    }),
    getSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGet: build.query<
      GetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetApiResponse,
      GetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/chatbot/session/${queryArg.sessionId}/preferences` }),
    }),
    updateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPut: build.mutation<
      UpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutApiResponse,
      UpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/chatbot/session/${queryArg.sessionId}/preferences`,
        method: "PUT",
        body: queryArg.sessionPreferencesPayload,
      }),
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
    getFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGet: build.query<
      GetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetApiResponse,
      GetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/chatbot/upload/${queryArg.attachmentId}/summary`,
        params: {
          session_id: queryArg.sessionId,
        },
      }),
    }),
    deleteFileAgenticV1ChatbotUploadAttachmentIdDelete: build.mutation<
      DeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteApiResponse,
      DeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/chatbot/upload/${queryArg.attachmentId}`,
        method: "DELETE",
        params: {
          session_id: queryArg.sessionId,
        },
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
    getRuntimeSummaryAgenticV1MetricsChatbotSummaryGet: build.query<
      GetRuntimeSummaryAgenticV1MetricsChatbotSummaryGetApiResponse,
      GetRuntimeSummaryAgenticV1MetricsChatbotSummaryGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/metrics/chatbot/summary` }),
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
    submitAgentTaskAgenticV1V1AgentTasksPost: build.mutation<
      SubmitAgentTaskAgenticV1V1AgentTasksPostApiResponse,
      SubmitAgentTaskAgenticV1V1AgentTasksPostApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/v1/agent-tasks`,
        method: "POST",
        body: queryArg.submitAgentTaskRequest,
      }),
    }),
    listAgentTasksAgenticV1V1AgentTasksGet: build.query<
      ListAgentTasksAgenticV1V1AgentTasksGetApiResponse,
      ListAgentTasksAgenticV1V1AgentTasksGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/v1/agent-tasks`,
        params: {
          limit: queryArg.limit,
          status: queryArg.status,
          target_agent: queryArg.targetAgent,
        },
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as agenticApi };
export type ListAgentsAgenticV1AgentsGetApiResponse = /** status 200 Successful Response */ (
  | ({
      type: "agent";
    } & Agent)
  | ({
      type: "leader";
    } & Leader)
)[];
export type ListAgentsAgenticV1AgentsGetApiArg = {
  ownerFilter?: OwnerFilter | null;
  teamId?: string | null;
};
export type CreateAgentAgenticV1AgentsCreatePostApiResponse = /** status 200 Successful Response */ any;
export type CreateAgentAgenticV1AgentsCreatePostApiArg = {
  createAgentRequest: CreateAgentRequest;
};
export type UpdateAgentAgenticV1AgentsUpdatePutApiResponse = /** status 200 Successful Response */ any;
export type UpdateAgentAgenticV1AgentsUpdatePutApiArg = {
  agentSettings:
    | ({
        type: "agent";
      } & Agent2)
    | ({
        type: "leader";
      } & Leader2);
};
export type DeleteAgentAgenticV1AgentsAgentIdDeleteApiResponse = unknown;
export type DeleteAgentAgenticV1AgentsAgentIdDeleteApiArg = {
  agentId: string;
};
export type RestoreAgentsAgenticV1AgentsRestorePostApiResponse = /** status 200 Successful Response */ any;
export type RestoreAgentsAgenticV1AgentsRestorePostApiArg = {
  forceOverwrite?: boolean;
};
export type ListMcpServersAgenticV1AgentsMcpServersGetApiResponse =
  /** status 200 Successful Response */ McpServerConfiguration[];
export type ListMcpServersAgenticV1AgentsMcpServersGetApiArg = void;
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
export type ListMcpServersAgenticV1McpServersGetApiResponse =
  /** status 200 Successful Response */ McpServerConfiguration[];
export type ListMcpServersAgenticV1McpServersGetApiArg = void;
export type CreateMcpServerAgenticV1McpServersPostApiResponse = /** status 200 Successful Response */ any;
export type CreateMcpServerAgenticV1McpServersPostApiArg = {
  saveMcpServerRequest: SaveMcpServerRequest;
};
export type UpdateMcpServerAgenticV1McpServersServerIdPutApiResponse = /** status 200 Successful Response */ any;
export type UpdateMcpServerAgenticV1McpServersServerIdPutApiArg = {
  serverId: string;
  saveMcpServerRequest: SaveMcpServerRequest;
};
export type DeleteMcpServerAgenticV1McpServersServerIdDeleteApiResponse = /** status 200 Successful Response */ any;
export type DeleteMcpServerAgenticV1McpServersServerIdDeleteApiArg = {
  serverId: string;
};
export type RestoreMcpServersFromConfigAgenticV1McpServersRestorePostApiResponse =
  /** status 200 Successful Response */ any;
export type RestoreMcpServersFromConfigAgenticV1McpServersRestorePostApiArg = void;
export type EchoSchemaAgenticV1SchemasEchoPostApiResponse = /** status 200 Successful Response */ null;
export type EchoSchemaAgenticV1SchemasEchoPostApiArg = {
  echoEnvelope: EchoEnvelope;
};
export type GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiResponse =
  /** status 200 Successful Response */ FrontendConfigDto;
export type GetFrontendConfigAgenticV1ConfigFrontendSettingsGetApiArg = void;
export type GetUserPermissionsAgenticV1ConfigPermissionsGetApiResponse = /** status 200 Successful Response */ string[];
export type GetUserPermissionsAgenticV1ConfigPermissionsGetApiArg = void;
export type GetSessionsAgenticV1ChatbotSessionsGetApiResponse =
  /** status 200 Successful Response */ SessionWithFiles[];
export type GetSessionsAgenticV1ChatbotSessionsGetApiArg = void;
export type CreateSessionAgenticV1ChatbotSessionPostApiResponse = /** status 200 Successful Response */ SessionSchema;
export type CreateSessionAgenticV1ChatbotSessionPostApiArg = {
  createSessionPayload: CreateSessionPayload;
};
export type GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiResponse =
  /** status 200 Successful Response */ ChatMessage2[];
export type GetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetApiArg = {
  sessionId: string;
  limit?: number | null;
  offset?: number;
  textLimit?: number | null;
  textOffset?: number;
};
export type GetSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGetApiResponse =
  /** status 200 Successful Response */ ChatMessage2;
export type GetSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGetApiArg = {
  sessionId: string;
  rank: number;
  textLimit?: number | null;
  textOffset?: number;
};
export type GetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetApiResponse =
  /** status 200 Successful Response */ {
    [key: string]: any;
  };
export type GetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetApiArg = {
  sessionId: string;
};
export type UpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutApiResponse =
  /** status 200 Successful Response */ {
    [key: string]: any;
  };
export type UpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutApiArg = {
  sessionId: string;
  sessionPreferencesPayload: SessionPreferencesPayload;
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
export type GetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetApiResponse =
  /** status 200 Successful Response */ {
    [key: string]: any;
  };
export type GetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetApiArg = {
  attachmentId: string;
  sessionId: string;
};
export type DeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteApiResponse = /** status 200 Successful Response */ null;
export type DeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteApiArg = {
  attachmentId: string;
  sessionId: string;
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
export type GetRuntimeSummaryAgenticV1MetricsChatbotSummaryGetApiResponse =
  /** status 200 Successful Response */ ChatbotRuntimeSummary;
export type GetRuntimeSummaryAgenticV1MetricsChatbotSummaryGetApiArg = void;
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
export type SubmitAgentTaskAgenticV1V1AgentTasksPostApiResponse =
  /** status 200 Successful Response */ SubmitAgentTaskResponse;
export type SubmitAgentTaskAgenticV1V1AgentTasksPostApiArg = {
  submitAgentTaskRequest: SubmitAgentTaskRequest;
};
export type ListAgentTasksAgenticV1V1AgentTasksGetApiResponse =
  /** status 200 Successful Response */ AgentTaskRecordV1[];
export type ListAgentTasksAgenticV1V1AgentTasksGetApiArg = {
  limit?: number;
  status?: AgentTaskStatus | null;
  targetAgent?: string | null;
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
export type McpServerRef = {
  id: string;
  require_tools?: string[];
};
export type AgentTuning = {
  /** The agent's mandatory role for discovery. */
  role: string;
  /** The agent's mandatory description for the UI. */
  description: string;
  tags?: string[];
  fields?: FieldSpec[];
  mcp_servers?: McpServerRef[];
};
export type AgentChatOptions = {
  /** Show a selector to choose the retrieval/search policy (e.g., hybrid, semantic, strict) before sending a message. */
  search_policy_selection?: boolean;
  /** Display a picker to include document libraries/knowledge sources that the agent can use for this message (session-scoped context). */
  libraries_selection?: boolean;
  /** Allow vector search on corpus documents. If false, corpus retrieval is disabled for this agent even when the client requests it. */
  include_corpus_in_search?: boolean;
  /** Add a microphone control to record a short audio clip and attach it to the message. */
  record_audio_files?: boolean;
  /** Allow attaching local files (e.g., PDFs, images, text) to the message and show existing attachments. */
  attach_files?: boolean;
  /** Expose a selector to decide how the agent should use the corpus: documents only, hybrid, or general knowledge only. */
  search_rag_scoping?: boolean;
  /** Expose a toggle to delegate RAG retrieval to a senior agent (deep search) when available. */
  deep_search_delegate?: boolean;
  /** Display a picker to restrict retrieval to specific documents for this message. */
  documents_selection?: boolean;
};
export type ClientAuthMode = "user_token" | "no_token";
export type McpServerConfiguration = {
  id: string;
  /** react-i18next key for the name of the MCP server. */
  name: string;
  /** react-i18next key for the description of the MCP server. */
  description?: string | null;
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
  /** If false, this MCP server is ignored. */
  enabled?: boolean;
  /** Client authentication mode. */
  auth_mode?: ClientAuthMode;
};
export type Agent = {
  id: string;
  name: string;
  enabled?: boolean;
  class_path?: string | null;
  tuning?: AgentTuning | null;
  chat_options?: AgentChatOptions;
  /** Optional arbitrary metadata for integrations (e.g., A2A proxy config). */
  metadata?: {
    [key: string]: any;
  } | null;
  /** DEPRECATED: Use the global 'mcp' catalog and the 'mcp_servers' field in AgentTuning with references instead. */
  mcp_servers?: McpServerConfiguration[];
  type?: "agent";
};
export type Leader = {
  id: string;
  name: string;
  enabled?: boolean;
  class_path?: string | null;
  tuning?: AgentTuning | null;
  chat_options?: AgentChatOptions;
  /** Optional arbitrary metadata for integrations (e.g., A2A proxy config). */
  metadata?: {
    [key: string]: any;
  } | null;
  /** DEPRECATED: Use the global 'mcp' catalog and the 'mcp_servers' field in AgentTuning with references instead. */
  mcp_servers?: McpServerConfiguration[];
  type?: "leader";
  /** IDs of agents in this leader's crew (if any). */
  crew?: string[];
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type OwnerFilter = "personal" | "team";
export type CreateAgentRequest = {
  name: string;
  type?: string;
  team_id?: string | null;
  a2a_base_url?: string | null;
  a2a_token?: string | null;
};
export type AgentTuning2 = {
  /** The agent's mandatory role for discovery. */
  role: string;
  /** The agent's mandatory description for the UI. */
  description: string;
  tags?: string[];
  fields?: FieldSpec[];
  mcp_servers?: McpServerRef[];
};
export type Agent2 = {
  id: string;
  name: string;
  enabled?: boolean;
  class_path?: string | null;
  tuning?: AgentTuning2 | null;
  chat_options?: AgentChatOptions;
  /** Optional arbitrary metadata for integrations (e.g., A2A proxy config). */
  metadata?: {
    [key: string]: any;
  } | null;
  /** DEPRECATED: Use the global 'mcp' catalog and the 'mcp_servers' field in AgentTuning with references instead. */
  mcp_servers?: McpServerConfiguration[];
  type?: "agent";
};
export type Leader2 = {
  id: string;
  name: string;
  enabled?: boolean;
  class_path?: string | null;
  tuning?: AgentTuning2 | null;
  chat_options?: AgentChatOptions;
  /** Optional arbitrary metadata for integrations (e.g., A2A proxy config). */
  metadata?: {
    [key: string]: any;
  } | null;
  /** DEPRECATED: Use the global 'mcp' catalog and the 'mcp_servers' field in AgentTuning with references instead. */
  mcp_servers?: McpServerConfiguration[];
  type?: "leader";
  /** IDs of agents in this leader's crew (if any). */
  crew?: string[];
};
export type SaveMcpServerRequest = {
  server: McpServerConfiguration;
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
export type LinkKind = "citation" | "download" | "external" | "dashboard" | "related" | "view";
export type LinkPart = {
  type?: "link";
  href?: string | null;
  title?: string | null;
  kind?: LinkKind;
  rel?: string | null;
  mime?: string | null;
  source_id?: string | null;
  document_uid?: string | null;
  file_name?: string | null;
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
export type RuntimeContext = {
  language?: string | null;
  session_id?: string | null;
  user_id?: string | null;
  user_groups?: string[] | null;
  selected_document_libraries_ids?: string[] | null;
  selected_document_uids?: string[] | null;
  selected_chat_context_ids?: string[] | null;
  search_policy?: string | null;
  access_token?: string | null;
  refresh_token?: string | null;
  access_token_expires_at?: number | null;
  attachments_markdown?: string | null;
  search_rag_scope?: ("corpus_only" | "hybrid" | "general_only") | null;
  deep_search?: boolean | null;
  include_session_scope?: boolean | null;
  include_corpus_scope?: boolean | null;
};
export type ChatMetadata = {
  model?: string | null;
  token_usage?: ChatTokenUsage | null;
  sources?: VectorSearchHit[];
  agent_id?: string | null;
  latency_ms?: number | null;
  finish_reason?: FinishReason | null;
  runtime_context?: RuntimeContext | null;
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
export type HitlChoice = {
  id: string;
  label: string;
  description?: string | null;
  default?: boolean | null;
};
export type HitlPayload = {
  stage?: string | null;
  title?: string | null;
  question?: string | null;
  choices?: HitlChoice[] | null;
  free_text?: boolean | null;
  metadata?: {
    [key: string]: any;
  } | null;
  checkpoint_id?: string | null;
  [key: string]: any;
};
export type AwaitingHumanEvent = {
  type?: "awaiting_human";
  session_id: string;
  exchange_id: string;
  payload:
    | HitlPayload
    | {
        [key: string]: any;
      };
};
export type ChatAskInput = {
  agent_id: string;
  runtime_context?: RuntimeContext | null;
  access_token?: string | null;
  refresh_token?: string | null;
  type?: "ask";
  session_id: string;
  message: string;
  client_exchange_id?: string | null;
};
export type StreamEvent = {
  type?: "stream";
  message: ChatMessage;
};
export type SessionSchema = {
  id: string;
  user_id: string;
  agent_id?: string | null;
  title: string;
  updated_at: string;
  next_rank?: number | null;
  preferences?: {
    [key: string]: any;
  } | null;
};
export type SessionEvent = {
  type?: "session";
  session: SessionSchema;
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
export type AgentRef = {
  id: string;
  name: string;
};
export type AttachmentRef = {
  id: string;
  name: string;
};
export type SessionWithFiles = {
  id: string;
  user_id: string;
  agent_id?: string | null;
  title: string;
  updated_at: string;
  next_rank?: number | null;
  preferences?: {
    [key: string]: any;
  } | null;
  agents: AgentRef[];
  file_names?: string[];
  attachments?: AttachmentRef[];
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
export type ChatbotRuntimeSummary = {
  sessions_total: number;
  agents_active_total: number;
  attachments_total: number;
  attachments_sessions: number;
  max_attachments_per_session: number;
};
export type EchoEnvelope = {
  kind:
    | "ChatMessage"
    | "AwaitingHumanEvent"
    | "MessagePart"
    | "HitlPayload"
    | "HitlChoice"
    | "StreamEvent"
    | "SessionEvent"
    | "FinalEvent"
    | "ErrorEvent"
    | "SessionSchema"
    | "SessionWithFiles"
    | "MetricsResponse"
    | "MetricsBucket"
    | "VectorSearchHit"
    | "RuntimeContext"
    | "ChatbotRuntimeSummary";
  /** Schema payload being echoed */
  payload:
    | ChatMessage
    | AwaitingHumanEvent
    | (
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
      )
    | HitlPayload
    | HitlChoice
    | ChatAskInput
    | StreamEvent
    | SessionEvent
    | FinalEvent
    | ErrorEvent
    | SessionSchema
    | SessionWithFiles
    | MetricsResponse
    | MetricsBucket
    | VectorSearchHit
    | RuntimeContext
    | ChatbotRuntimeSummary;
};
export type FrontendFlags = {
  enableK8Features?: boolean;
  enableElecWarfare?: boolean;
};
export type Properties = {
  logoName?: string;
  logoNameDark?: string;
  logoHeight?: string;
  logoWidth?: string;
  faviconName?: string | null;
  faviconNameDark?: string | null;
  siteDisplayName?: string;
  /** Optional brand slug used to resolve brand-specific assets (e.g., release notes). Defaults to 'fred'. */
  releaseBrand?: string | null;
  agentsNicknameSingular?: string;
  agentsNicknamePlural?: string;
  agentIconPath?: string | null;
  contactSupportLink?: string | null;
  /** Name of the SVG icon for agents. The svg should handle colors via 'currentColor' to switch between light and dark theme. */
  agentIconName?: string | null;
  showAgentRegisterA2A?: boolean;
  showAgentRestoreFromConfiguration?: boolean;
  showAgentCode?: boolean;
  allowAgentSwitchInOneConversation?: boolean;
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
  is_rebac_enabled: boolean;
};
export type CreateSessionPayload = {
  agent_id?: string | null;
  title?: string | null;
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
export type SessionPreferencesPayload = {
  preferences?: {
    [key: string]: any;
  };
};
export type BodyUploadFileAgenticV1ChatbotUploadPost = {
  session_id: string;
  file: Blob;
};
export type FeedbackRecord = {
  id: string;
  /** Session ID associated with the feedback */
  session_id: string;
  /** Message ID the feedback refers to */
  message_id: string;
  /** Name of the agent that generated the message */
  agent_id: string;
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
export type AgentTaskStatus = "QUEUED" | "RUNNING" | "BLOCKED" | "COMPLETED" | "FAILED" | "CANCELED";
export type SubmitAgentTaskResponse = {
  task_id: string;
  status: AgentTaskStatus;
  workflow_id: string;
  run_id?: string | null;
};
export type AgentContextRefsV1 = {
  session_id?: string | null;
  profile_id?: string | null;
  project_id?: string | null;
  tag_ids?: string[];
  document_uids?: string[];
};
export type SubmitAgentTaskRequest = {
  target_agent: string;
  request_text: string;
  context?: AgentContextRefsV1;
  parameters?: {
    [key: string]: any;
  };
  task_id?: string | null;
};
export type AgentTaskRecordV1 = {
  task_id: string;
  user_id: string;
  target_agent: string;
  status?: AgentTaskStatus;
  request_text: string;
  context?: AgentContextRefsV1;
  parameters?: {
    [key: string]: any;
  };
  workflow_id: string;
  run_id?: string | null;
  last_message?: string | null;
  percent_complete?: number;
  artifacts?: string[];
  error_details?: {
    [key: string]: any;
  } | null;
  blocked_details?: {
    [key: string]: any;
  } | null;
  created_at: string;
  updated_at: string;
};
export const {
  useListAgentsAgenticV1AgentsGetQuery,
  useLazyListAgentsAgenticV1AgentsGetQuery,
  useCreateAgentAgenticV1AgentsCreatePostMutation,
  useUpdateAgentAgenticV1AgentsUpdatePutMutation,
  useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation,
  useRestoreAgentsAgenticV1AgentsRestorePostMutation,
  useListMcpServersAgenticV1AgentsMcpServersGetQuery,
  useLazyListMcpServersAgenticV1AgentsMcpServersGetQuery,
  useListRuntimeSourceKeysAgenticV1AgentsSourceKeysGetQuery,
  useLazyListRuntimeSourceKeysAgenticV1AgentsSourceKeysGetQuery,
  useRuntimeSourceByObjectAgenticV1AgentsSourceByObjectGetQuery,
  useLazyRuntimeSourceByObjectAgenticV1AgentsSourceByObjectGetQuery,
  useRuntimeSourceByModuleAgenticV1AgentsSourceByModuleGetQuery,
  useLazyRuntimeSourceByModuleAgenticV1AgentsSourceByModuleGetQuery,
  useListMcpServersAgenticV1McpServersGetQuery,
  useLazyListMcpServersAgenticV1McpServersGetQuery,
  useCreateMcpServerAgenticV1McpServersPostMutation,
  useUpdateMcpServerAgenticV1McpServersServerIdPutMutation,
  useDeleteMcpServerAgenticV1McpServersServerIdDeleteMutation,
  useRestoreMcpServersFromConfigAgenticV1McpServersRestorePostMutation,
  useEchoSchemaAgenticV1SchemasEchoPostMutation,
  useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery,
  useLazyGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery,
  useGetUserPermissionsAgenticV1ConfigPermissionsGetQuery,
  useLazyGetUserPermissionsAgenticV1ConfigPermissionsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useLazyGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useCreateSessionAgenticV1ChatbotSessionPostMutation,
  useGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
  useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
  useGetSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGetQuery,
  useLazyGetSessionMessageAgenticV1ChatbotSessionSessionIdMessageRankGetQuery,
  useGetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetQuery,
  useLazyGetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetQuery,
  useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
  useUploadFileAgenticV1ChatbotUploadPostMutation,
  useGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery,
  useLazyGetFileSummaryAgenticV1ChatbotUploadAttachmentIdSummaryGetQuery,
  useDeleteFileAgenticV1ChatbotUploadAttachmentIdDeleteMutation,
  useHealthzAgenticV1HealthzGetQuery,
  useLazyHealthzAgenticV1HealthzGetQuery,
  useReadyAgenticV1ReadyGetQuery,
  useLazyReadyAgenticV1ReadyGetQuery,
  useGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery,
  useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery,
  useGetRuntimeSummaryAgenticV1MetricsChatbotSummaryGetQuery,
  useLazyGetRuntimeSummaryAgenticV1MetricsChatbotSummaryGetQuery,
  useGetFeedbackAgenticV1ChatbotFeedbackGetQuery,
  useLazyGetFeedbackAgenticV1ChatbotFeedbackGetQuery,
  usePostFeedbackAgenticV1ChatbotFeedbackPostMutation,
  useDeleteFeedbackAgenticV1ChatbotFeedbackFeedbackIdDeleteMutation,
  useQueryLogsAgenticV1LogsQueryPostMutation,
  useSubmitAgentTaskAgenticV1V1AgentTasksPostMutation,
  useListAgentTasksAgenticV1V1AgentTasksGetQuery,
  useLazyListAgentTasksAgenticV1V1AgentTasksGetQuery,
} = injectedRtkApi;
