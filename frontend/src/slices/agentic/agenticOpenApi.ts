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
    createV2AgentAgenticV1AgentsV2CreatePost: build.mutation<
      CreateV2AgentAgenticV1AgentsV2CreatePostApiResponse,
      CreateV2AgentAgenticV1AgentsV2CreatePostApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/agents/v2/create`,
        method: "POST",
        body: queryArg.createV2AgentRequest,
      }),
    }),
    createV1AgentAgenticV1AgentsV1CreatePost: build.mutation<
      CreateV1AgentAgenticV1AgentsV1CreatePostApiResponse,
      CreateV1AgentAgenticV1AgentsV1CreatePostApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/agents/v1/create`,
        method: "POST",
        body: queryArg.createV1AgentRequest,
      }),
    }),
    listReactAgentProfilesAgenticV1AgentsReactProfilesGet: build.query<
      ListReactAgentProfilesAgenticV1AgentsReactProfilesGetApiResponse,
      ListReactAgentProfilesAgenticV1AgentsReactProfilesGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/agents/react-profiles` }),
    }),
    analyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePost: build.mutation<
      AnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostApiResponse,
      AnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/agents/ppt-filler/analyze`,
        method: "POST",
        body: queryArg.bodyAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePost,
      }),
    }),
    listToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGet: build.query<
      ListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetApiResponse,
      ListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/agents/toolkit-asset-metadata` }),
    }),
    inspectV2AgentAgenticV1AgentsAgentIdInspectGet: build.query<
      InspectV2AgentAgenticV1AgentsAgentIdInspectGetApiResponse,
      InspectV2AgentAgenticV1AgentsAgentIdInspectGetApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/${queryArg.agentId}/inspect` }),
    }),
    listDeclaredAgentClassPathsAgenticV1AgentsClassPathsGet: build.query<
      ListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetApiResponse,
      ListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/agents/class-paths` }),
    }),
    listV2DefinitionRefsAgenticV1AgentsV2DefinitionRefsGet: build.query<
      ListV2DefinitionRefsAgenticV1AgentsV2DefinitionRefsGetApiResponse,
      ListV2DefinitionRefsAgenticV1AgentsV2DefinitionRefsGetApiArg
    >({
      query: () => ({ url: `/agentic/v1/agents/v2/definition-refs` }),
    }),
    getClassPathTuningAgenticV1AgentsClassPathsTuningGet: build.query<
      GetClassPathTuningAgenticV1AgentsClassPathsTuningGetApiResponse,
      GetClassPathTuningAgenticV1AgentsClassPathsTuningGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/agents/class-paths/tuning`,
        params: {
          class_path: queryArg.classPath,
          definition_ref: queryArg.definitionRef,
        },
      }),
    }),
    updateAgentAgenticV1AgentsUpdatePut: build.mutation<
      UpdateAgentAgenticV1AgentsUpdatePutApiResponse,
      UpdateAgentAgenticV1AgentsUpdatePutApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/agents/update`, method: "PUT", body: queryArg.agentInput }),
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
    getTeamModelRoutingConfigAgenticV1ConfigModelRoutingTeamsTeamIdGet: build.query<
      GetTeamModelRoutingConfigAgenticV1ConfigModelRoutingTeamsTeamIdGetApiResponse,
      GetTeamModelRoutingConfigAgenticV1ConfigModelRoutingTeamsTeamIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/config/model-routing/teams/${queryArg.teamId}` }),
    }),
    getSessionsAgenticV1ChatbotSessionsGet: build.query<
      GetSessionsAgenticV1ChatbotSessionsGetApiResponse,
      GetSessionsAgenticV1ChatbotSessionsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/chatbot/sessions`,
        params: {
          team_id: queryArg.teamId,
        },
      }),
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
    listWritableDocumentsAgenticV1WritableDocumentsSessionIdGet: build.query<
      ListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetApiResponse,
      ListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/writable-documents/${queryArg.sessionId}` }),
    }),
    getWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdGet: build.query<
      GetWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdGetApiResponse,
      GetWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/agentic/v1/writable-documents/${queryArg.sessionId}/${queryArg.documentId}` }),
    }),
    updateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPut: build.mutation<
      UpdateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPutApiResponse,
      UpdateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPutApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/writable-documents/${queryArg.sessionId}/${queryArg.documentId}`,
        method: "PUT",
        body: queryArg.writableDocumentUpdate,
      }),
    }),
    exportWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdExportGet: build.query<
      ExportWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdExportGetApiResponse,
      ExportWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdExportGetApiArg
    >({
      query: (queryArg) => ({
        url: `/agentic/v1/writable-documents/${queryArg.sessionId}/${queryArg.documentId}/export`,
        params: {
          format: queryArg.format,
        },
      }),
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
export type ListAgentsAgenticV1AgentsGetApiResponse = /** status 200 Successful Response */ Agent[];
export type ListAgentsAgenticV1AgentsGetApiArg = {
  ownerFilter?: OwnerFilter | null;
  teamId?: string | null;
};
export type CreateV2AgentAgenticV1AgentsV2CreatePostApiResponse = /** status 200 Successful Response */ Agent;
export type CreateV2AgentAgenticV1AgentsV2CreatePostApiArg = {
  createV2AgentRequest: CreateV2AgentRequest;
};
export type CreateV1AgentAgenticV1AgentsV1CreatePostApiResponse = /** status 200 Successful Response */ Agent;
export type CreateV1AgentAgenticV1AgentsV1CreatePostApiArg = {
  createV1AgentRequest: CreateV1AgentRequest;
};
export type ListReactAgentProfilesAgenticV1AgentsReactProfilesGetApiResponse =
  /** status 200 Successful Response */ ReActProfileSummary[];
export type ListReactAgentProfilesAgenticV1AgentsReactProfilesGetApiArg = void;
export type AnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostApiResponse =
  /** status 200 Successful Response */ PptFillerAnalyzeResponse;
export type AnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostApiArg = {
  bodyAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePost: BodyAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePost;
};
export type ListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetApiResponse =
  /** status 200 Successful Response */ {
    [key: string]: ToolkitAssetMetadata;
  };
export type ListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetApiArg = void;
export type InspectV2AgentAgenticV1AgentsAgentIdInspectGetApiResponse =
  /** status 200 Successful Response */ AgentInspection;
export type InspectV2AgentAgenticV1AgentsAgentIdInspectGetApiArg = {
  agentId: string;
};
export type ListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetApiResponse =
  /** status 200 Successful Response */ string[];
export type ListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetApiArg = void;
export type ListV2DefinitionRefsAgenticV1AgentsV2DefinitionRefsGetApiResponse =
  /** status 200 Successful Response */ string[];
export type ListV2DefinitionRefsAgenticV1AgentsV2DefinitionRefsGetApiArg = void;
export type GetClassPathTuningAgenticV1AgentsClassPathsTuningGetApiResponse =
  /** status 200 Successful Response */ AgentTuning;
export type GetClassPathTuningAgenticV1AgentsClassPathsTuningGetApiArg = {
  classPath?: string | null;
  definitionRef?: string | null;
};
export type UpdateAgentAgenticV1AgentsUpdatePutApiResponse = /** status 200 Successful Response */ any;
export type UpdateAgentAgenticV1AgentsUpdatePutApiArg = {
  agentInput: Agent2;
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
export type GetTeamModelRoutingConfigAgenticV1ConfigModelRoutingTeamsTeamIdGetApiResponse =
  /** status 200 Successful Response */ TeamModelRoutingConfigDto;
export type GetTeamModelRoutingConfigAgenticV1ConfigModelRoutingTeamsTeamIdGetApiArg = {
  teamId: string;
};
export type GetSessionsAgenticV1ChatbotSessionsGetApiResponse =
  /** status 200 Successful Response */ SessionWithFiles[];
export type GetSessionsAgenticV1ChatbotSessionsGetApiArg = {
  teamId: string;
};
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
export type ListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetApiResponse =
  /** status 200 Successful Response */ WritableDocumentResponse[];
export type ListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetApiArg = {
  sessionId: string;
};
export type GetWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdGetApiResponse =
  /** status 200 Successful Response */ WritableDocumentResponse;
export type GetWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdGetApiArg = {
  sessionId: string;
  documentId: string;
};
export type UpdateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPutApiResponse =
  /** status 200 Successful Response */ WritableDocumentResponse;
export type UpdateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPutApiArg = {
  sessionId: string;
  documentId: string;
  writableDocumentUpdate: WritableDocumentUpdate;
};
export type ExportWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdExportGetApiResponse =
  /** status 200 Successful Response */ any;
export type ExportWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdExportGetApiArg = {
  sessionId: string;
  documentId: string;
  format?: WritableDocumentExportFormat;
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
  hide?: boolean;
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
export type KfVectorSearchParams = {
  provider?: "kf_vector_search";
  /** Hard library binding set at agent creation time. When non-empty, the agent searches ONLY these libraries regardless of any runtime user selection — the library picker is hidden in the chat bar. Empty (default) means no restriction: the user can pick libraries at runtime. */
  document_library_tags_ids?: string[];
  /** When True, expose the file-attachment control in the chat bar so users can attach local files (PDFs, images, text) to their messages. */
  attach_files?: boolean;
  /** When True, expose the document-library picker in the chat bar so users can narrow retrieval to specific libraries at message time. */
  libraries_selection?: boolean;
  /** Default retrieval strategy for this agent. hybrid combines BM25 and vector search (RRF); semantic uses vector search only; strict applies a high-precision similarity threshold. Overridden at runtime by the user's chat-bar selection when search_policy_selection is True. */
  search_policy?: ("hybrid" | "semantic" | "strict") | null;
  /** Maximum number of document chunks returned per search call. When set, overrides the model's dynamic choice. Leave unset to let the model decide (default: 10). Increase for large heterogeneous corpora where relevant documents are sparse. */
  top_k?: number | null;
  /** Maximum length, in characters, of an on-demand document summary (summarize_document tool). Acts as both the default when the model does not request a specific length and a hard cap on what it may request: the effective limit is min(model_requested, this). Leave unset to use the built-in default (5000) and let the model choose freely. */
  summarize_max_chars?: number | null;
  /** When True, expose the search-policy selector in the chat bar so users can switch retrieval strategy per message. */
  search_policy_selection?: boolean;
};
export type KeyField = {
  key: string;
  description?: string;
  type?: "text" | "image";
  folder?: string | null;
  folder_tag_id?: string | null;
};
export type SlideSchema = {
  slide: number;
  keys?: KeyField[];
};
export type PptFillerParams = {
  provider?: "ppt_filler";
  /** Fixed per-agent storage key for the uploaded .pptx template (one template per agent). Conventional and not user-editable — the creator never chooses it; replacing the template swaps the file under this same key. */
  template_key?: string;
  /** Derived per-slide template schema (the parser output), persisted with the agent. Each entry is one slide's 1-based number and its {{key}} fields with their note descriptions. Recomputed server-side from the actual .pptx whenever the template is (re)uploaded. */
  schema?: SlideSchema[];
  /** TRANSIENT base64-encoded .pptx bytes, used ONLY to transport a newly (re)uploaded template from the form to the backend on save. The toolkit asset processor (PPTFILL-03 / #1833) re-parses these bytes, writes the schema, and STRIPS this field before persistence — it must never reach the store. Absent on ordinary edits (template unchanged). */
  template_upload_b64?: string | null;
};
export type McpServerRef = {
  id: string;
  require_tools?: string[];
  /** Typed agent-level parameters for inprocess tools, discriminated by `provider`. Example: KfVectorSearchParams(document_library_tags_ids=['lib-123']) */
  params?:
    | (
        | ({
            provider: "kf_vector_search";
          } & KfVectorSearchParams)
        | ({
            provider: "ppt_filler";
          } & PptFillerParams)
      )
    | null;
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
  /** MCP server transport. Can be sse, stdio, websocket, streamable_http, or inprocess (local toolkit provider exposed in the MCP catalog). */
  transport?: string | null;
  /** Local provider key when transport=inprocess (e.g. 'web_github_readonly'). */
  provider?: string | null;
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
  /** Owning team id when this is a team-owned agent. */
  team_id?: string | null;
  enabled?: boolean;
  class_path?: string | null;
  /** Stable v2 definition identifier (preferred for v2 agents). Example: 'v2.react.basic'. */
  definition_ref?: string | null;
  tuning?: AgentTuning | null;
  chat_options?: AgentChatOptions;
  /** Optional arbitrary metadata for integrations. */
  metadata?: {
    [key: string]: any;
  } | null;
  /** DEPRECATED: Use the global 'mcp' catalog and the 'mcp_servers' field in AgentTuning with references instead. */
  mcp_servers?: McpServerConfiguration[];
  type?: "agent";
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
export type CreateV2AgentRequest = {
  name: string;
  team_id?: string | null;
  definition_ref?: string | null;
  profile_id?: string | null;
};
export type CreateV1AgentRequest = {
  name: string;
  team_id?: string | null;
  class_path: string;
};
export type ReActProfileSummary = {
  profile_id: string;
  title: string;
  description: string;
  agent_description: string;
  tags: string[];
};
export type TemplateError = {
  slide: number;
  key: string;
  code: string;
  message: string;
};
export type PptFillerAnalyzeResponse = {
  /** Per-slide template schema extracted from the uploaded .pptx. */
  schema?: SlideSchema[];
  /** Per-slide validation errors (each carries slide, key, code, message). May be non-empty even on a 200 response — analyze shows schema and errors together; the 422-on-errors behavior is for SAVE (#1833). */
  errors?: TemplateError[];
};
export type BodyAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePost = {
  file: Blob;
  team_id?: string | null;
};
export type ToolkitAssetMetadata = {
  /** Whether the toolkit cannot be saved without its uploaded asset. */
  asset_required: boolean;
  /** Accepted upload types (extensions and/or MIME) for the asset. */
  accepted_file_types?: string[];
};
export type ExecutionCategory = "graph" | "react" | "proxy";
export type ToolRefRequirement = {
  kind?: "tool_ref";
  required?: boolean;
  description?: string | null;
  tool_ref: string;
};
export type PreviewKind = "none" | "mermaid" | "dag" | "text";
export type AgentPreview = {
  kind: PreviewKind;
  content?: string;
  note?: string | null;
};
export type AgentInspection = {
  agent_id: string;
  role: string;
  description: string;
  tags?: string[];
  fields?: FieldSpec[];
  execution_category: ExecutionCategory;
  /** Exact Fred runtime tools declared by the agent author. This exists so inspection and UIs can explain what the agent expects before runtime binding happens. */
  declared_tool_refs?: ToolRefRequirement[];
  /** Default MCP servers Fred should attach for this agent. These are runtime tool providers, not substitutes for first-class Fred declared tool refs. */
  default_mcp_servers?: McpServerRef[];
  preview?: AgentPreview;
};
export type PptFillerParams2 = {
  provider?: "ppt_filler";
  /** Fixed per-agent storage key for the uploaded .pptx template (one template per agent). Conventional and not user-editable — the creator never chooses it; replacing the template swaps the file under this same key. */
  template_key?: string;
  /** Derived per-slide template schema (the parser output), persisted with the agent. Each entry is one slide's 1-based number and its {{key}} fields with their note descriptions. Recomputed server-side from the actual .pptx whenever the template is (re)uploaded. */
  schema?: SlideSchema[];
  /** TRANSIENT base64-encoded .pptx bytes, used ONLY to transport a newly (re)uploaded template from the form to the backend on save. The toolkit asset processor (PPTFILL-03 / #1833) re-parses these bytes, writes the schema, and STRIPS this field before persistence — it must never reach the store. Absent on ordinary edits (template unchanged). */
  template_upload_b64?: string | null;
};
export type McpServerRef2 = {
  id: string;
  require_tools?: string[];
  /** Typed agent-level parameters for inprocess tools, discriminated by `provider`. Example: KfVectorSearchParams(document_library_tags_ids=['lib-123']) */
  params?:
    | (
        | ({
            provider: "kf_vector_search";
          } & KfVectorSearchParams)
        | ({
            provider: "ppt_filler";
          } & PptFillerParams2)
      )
    | null;
};
export type AgentTuning2 = {
  /** The agent's mandatory role for discovery. */
  role: string;
  /** The agent's mandatory description for the UI. */
  description: string;
  tags?: string[];
  fields?: FieldSpec[];
  mcp_servers?: McpServerRef2[];
};
export type Agent2 = {
  id: string;
  name: string;
  /** Owning team id when this is a team-owned agent. */
  team_id?: string | null;
  enabled?: boolean;
  class_path?: string | null;
  /** Stable v2 definition identifier (preferred for v2 agents). Example: 'v2.react.basic'. */
  definition_ref?: string | null;
  tuning?: AgentTuning2 | null;
  chat_options?: AgentChatOptions;
  /** Optional arbitrary metadata for integrations. */
  metadata?: {
    [key: string]: any;
  } | null;
  /** DEPRECATED: Use the global 'mcp' catalog and the 'mcp_servers' field in AgentTuning with references instead. */
  mcp_servers?: McpServerConfiguration[];
  type?: "agent";
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
export type ChartType = "bar" | "line" | "pie" | "area" | "table";
export type ChartPart = {
  type?: "chart";
  chart_type?: ChartType;
  rows?: {
    [key: string]: any;
  }[];
  x_key: string;
  y_keys?: string[];
  series_key?: string | null;
  title?: string | null;
  sql?: string | null;
};
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
export type PptPreviewPart = {
  type?: "ppt_preview";
  preview_id: string;
  title: string;
  pdf_presign_url: string;
  version: string;
  pptx_download_url?: string | null;
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
export type WritableDocumentAuthor = "agent" | "user";
export type WritableDocumentPart = {
  type?: "writable_document";
  document_id: string;
  title: string;
  content_md: string;
  updated_at: string;
  updated_by?: WritableDocumentAuthor;
};
export type ChatTokenUsage = {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
};
export type TokenUsageSource = "updates" | "messages" | "messages_backfill" | "unavailable";
export type VectorSearchHit = {
  content: string;
  page?: number | null;
  section?: string | null;
  viewer_fragment?: string | null;
  slide_id?: number | null;
  has_visual_evidence?: boolean | null;
  slide_image_uri?: string | null;
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
  token_usage_source?: TokenUsageSource | null;
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
        type: "chart";
      } & ChartPart)
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
        type: "ppt_preview";
      } & PptPreviewPart)
    | ({
        type: "text";
      } & TextPart)
    | ({
        type: "tool_call";
      } & ToolCallPart)
    | ({
        type: "tool_result";
      } & ToolResultPart)
    | ({
        type: "writable_document";
      } & WritableDocumentPart)
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
  agent_id?: string | null;
  internal_profile_id?: string | null;
  internal_capability?: string | null;
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
  team_id?: string | null;
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
  team_id?: string | null;
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
            type: "chart";
          } & ChartPart)
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
            type: "ppt_preview";
          } & PptPreviewPart)
        | ({
            type: "text";
          } & TextPart)
        | ({
            type: "tool_call";
          } & ToolCallPart)
        | ({
            type: "tool_result";
          } & ToolResultPart)
        | ({
            type: "writable_document";
          } & WritableDocumentPart)
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
export type UploadWarning = {
  /** MUI Alert severity level. */
  severity?: "info" | "warning" | "error" | "success";
  /** Locale → message map (e.g. {"en": "...", "fr": "..."}). */
  messages?: {
    [key: string]: string;
  };
};
export type Properties = {
  logoName?: string;
  logoNameDark?: string;
  logoHeight?: string;
  logoWidth?: string;
  faviconName?: string | null;
  faviconNameDark?: string | null;
  siteDisplayName?: string;
  siteTitle?: string;
  siteSubtitle?: string | null;
  /** Optional brand slug used to resolve brand-specific assets (e.g., release notes). Defaults to 'fred'. */
  releaseBrand?: string | null;
  agentsNicknameSingular?: string;
  agentsNicknamePlural?: string;
  agentIconName?: string;
  contactSupportLink?: string | null;
  agentDocumentationLink?: string | null;
  showAgentRestoreFromConfiguration?: boolean;
  showAgentDisableButton?: boolean;
  showAgentCode?: boolean;
  allowAgentSwitchInOneConversation?: boolean;
  defaultTeamBannerFile?: string;
  defaultPersonalBannerFile?: string;
  defaultTeamAvatarFile?: string;
  defaultPersonalAvatarFile?: string;
  gcuVersion?: string | null;
  /** Optional alert shown in the document upload drawer. Omit to show nothing. */
  uploadWarning?: UploadWarning | null;
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
export type TeamModelRoutingProfileDto = {
  profile_id: string;
  capability: string;
  provider: string;
  model_name: string;
  description?: string | null;
  is_default?: boolean;
};
export type TeamModelRoutingRuleDto = {
  rule_id: string;
  capability: string;
  operation?: string | string[] | null;
  purpose?: string | string[] | null;
  agent_id?: string | string[] | null;
  user_id?: string | string[] | null;
  target_profile_id: string;
  target_model_name?: string | null;
  scope: "global" | "team";
};
export type TeamModelRoutingConfigDto = {
  team_id: string;
  catalog_path: string;
  catalog_exists: boolean;
  catalog_version?: string | null;
  default_profile_by_capability?: {
    [key: string]: string;
  };
  profiles?: TeamModelRoutingProfileDto[];
  rules?: TeamModelRoutingRuleDto[];
};
export type CreateSessionPayload = {
  agent_id?: string | null;
  title?: string | null;
  team_id?: string | null;
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
        type: "chart";
      } & ChartPart)
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
        type: "ppt_preview";
      } & PptPreviewPart)
    | ({
        type: "text";
      } & TextPart)
    | ({
        type: "tool_call";
      } & ToolCallPart)
    | ({
        type: "tool_result";
      } & ToolResultPart)
    | ({
        type: "writable_document";
      } & WritableDocumentPart)
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
  message_id: string;
  session_id: string;
  agent_id: string;
};
export type WritableDocumentResponse = {
  session_id: string;
  document_id: string;
  title: string;
  content_md: string;
  updated_by: WritableDocumentAuthor;
  created_at?: string | null;
  updated_at?: string | null;
};
export type WritableDocumentUpdate = {
  content_md: string;
  title?: string | null;
};
export type WritableDocumentExportFormat = "docx" | "md";
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
  useCreateV2AgentAgenticV1AgentsV2CreatePostMutation,
  useCreateV1AgentAgenticV1AgentsV1CreatePostMutation,
  useListReactAgentProfilesAgenticV1AgentsReactProfilesGetQuery,
  useLazyListReactAgentProfilesAgenticV1AgentsReactProfilesGetQuery,
  useAnalyzePptFillerTemplateAgenticV1AgentsPptFillerAnalyzePostMutation,
  useListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetQuery,
  useLazyListToolkitAssetMetadataAgenticV1AgentsToolkitAssetMetadataGetQuery,
  useInspectV2AgentAgenticV1AgentsAgentIdInspectGetQuery,
  useLazyInspectV2AgentAgenticV1AgentsAgentIdInspectGetQuery,
  useListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetQuery,
  useLazyListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetQuery,
  useListV2DefinitionRefsAgenticV1AgentsV2DefinitionRefsGetQuery,
  useLazyListV2DefinitionRefsAgenticV1AgentsV2DefinitionRefsGetQuery,
  useGetClassPathTuningAgenticV1AgentsClassPathsTuningGetQuery,
  useLazyGetClassPathTuningAgenticV1AgentsClassPathsTuningGetQuery,
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
  useGetTeamModelRoutingConfigAgenticV1ConfigModelRoutingTeamsTeamIdGetQuery,
  useLazyGetTeamModelRoutingConfigAgenticV1ConfigModelRoutingTeamsTeamIdGetQuery,
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
  useListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetQuery,
  useLazyListWritableDocumentsAgenticV1WritableDocumentsSessionIdGetQuery,
  useGetWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdGetQuery,
  useLazyGetWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdGetQuery,
  useUpdateWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdPutMutation,
  useExportWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdExportGetQuery,
  useLazyExportWritableDocumentAgenticV1WritableDocumentsSessionIdDocumentIdExportGetQuery,
  useQueryLogsAgenticV1LogsQueryPostMutation,
  useSubmitAgentTaskAgenticV1V1AgentTasksPostMutation,
  useListAgentTasksAgenticV1V1AgentTasksGetQuery,
  useLazyListAgentTasksAgenticV1V1AgentTasksGetQuery,
} = injectedRtkApi;
