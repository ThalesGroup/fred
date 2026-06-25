import { evaluationApi as api } from "./evaluationApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    healthzEvaluationV1HealthzGet: build.query<
      HealthzEvaluationV1HealthzGetApiResponse,
      HealthzEvaluationV1HealthzGetApiArg
    >({
      query: () => ({ url: `/evaluation/v1/healthz` }),
    }),
    readyEvaluationV1ReadyGet: build.query<ReadyEvaluationV1ReadyGetApiResponse, ReadyEvaluationV1ReadyGetApiArg>({
      query: () => ({ url: `/evaluation/v1/ready` }),
    }),
    createCampaignEvaluationV1CampaignsPost: build.mutation<
      CreateCampaignEvaluationV1CampaignsPostApiResponse,
      CreateCampaignEvaluationV1CampaignsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/evaluation/v1/campaigns`,
        method: "POST",
        body: queryArg.createEvaluationCampaignRequest,
      }),
    }),
    listCampaignsEvaluationV1CampaignsGet: build.query<
      ListCampaignsEvaluationV1CampaignsGetApiResponse,
      ListCampaignsEvaluationV1CampaignsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/evaluation/v1/campaigns`,
        params: {
          team_id: queryArg.teamId,
        },
      }),
    }),
    getCampaignEvaluationV1CampaignsCampaignIdGet: build.query<
      GetCampaignEvaluationV1CampaignsCampaignIdGetApiResponse,
      GetCampaignEvaluationV1CampaignsCampaignIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/campaigns/${queryArg.campaignId}` }),
    }),
    deleteCampaignEvaluationV1CampaignsCampaignIdDelete: build.mutation<
      DeleteCampaignEvaluationV1CampaignsCampaignIdDeleteApiResponse,
      DeleteCampaignEvaluationV1CampaignsCampaignIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/campaigns/${queryArg.campaignId}`, method: "DELETE" }),
    }),
    listCasesEvaluationV1CampaignsCampaignIdCasesGet: build.query<
      ListCasesEvaluationV1CampaignsCampaignIdCasesGetApiResponse,
      ListCasesEvaluationV1CampaignsCampaignIdCasesGetApiArg
    >({
      query: (queryArg) => ({
        url: `/evaluation/v1/campaigns/${queryArg.campaignId}/cases`,
        params: {
          offset: queryArg.offset,
          limit: queryArg.limit,
        },
      }),
    }),
    getCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGet: build.query<
      GetCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGetApiResponse,
      GetCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/campaigns/${queryArg.campaignId}/cases/${queryArg.caseId}` }),
    }),
    streamEventsEvaluationV1CampaignsCampaignIdEventsGet: build.query<
      StreamEventsEvaluationV1CampaignsCampaignIdEventsGetApiResponse,
      StreamEventsEvaluationV1CampaignsCampaignIdEventsGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/campaigns/${queryArg.campaignId}/events` }),
    }),
    cancelCampaignEvaluationV1CampaignsCampaignIdCancelPost: build.mutation<
      CancelCampaignEvaluationV1CampaignsCampaignIdCancelPostApiResponse,
      CancelCampaignEvaluationV1CampaignsCampaignIdCancelPostApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/campaigns/${queryArg.campaignId}/cancel`, method: "POST" }),
    }),
    getTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGet: build.query<
      GetTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGetApiResponse,
      GetTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/telemetry/session/${queryArg.campaignId}` }),
    }),
    getTelemetryEvaluationV1TelemetryGet: build.query<
      GetTelemetryEvaluationV1TelemetryGetApiResponse,
      GetTelemetryEvaluationV1TelemetryGetApiArg
    >({
      query: () => ({ url: `/evaluation/v1/telemetry` }),
    }),
    analyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePost: build.mutation<
      AnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostApiResponse,
      AnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/campaigns/${queryArg.campaignId}/analyze`, method: "POST" }),
    }),
    listTasksEvaluationV1TasksGet: build.query<
      ListTasksEvaluationV1TasksGetApiResponse,
      ListTasksEvaluationV1TasksGetApiArg
    >({
      query: (queryArg) => ({
        url: `/evaluation/v1/tasks`,
        params: {
          scope: queryArg.scope,
          team_id: queryArg.teamId,
          exclude_terminal: queryArg.excludeTerminal,
        },
      }),
    }),
    getTaskEvaluationV1TasksTaskIdGet: build.query<
      GetTaskEvaluationV1TasksTaskIdGetApiResponse,
      GetTaskEvaluationV1TasksTaskIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/tasks/${queryArg.taskId}` }),
    }),
    getLatestEventEvaluationV1TasksTaskIdLatestGet: build.query<
      GetLatestEventEvaluationV1TasksTaskIdLatestGetApiResponse,
      GetLatestEventEvaluationV1TasksTaskIdLatestGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/tasks/${queryArg.taskId}/latest` }),
    }),
    streamTaskEventsEvaluationV1TasksTaskIdEventsGet: build.query<
      StreamTaskEventsEvaluationV1TasksTaskIdEventsGetApiResponse,
      StreamTaskEventsEvaluationV1TasksTaskIdEventsGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/tasks/${queryArg.taskId}/events` }),
    }),
    cancelTaskEvaluationV1TasksTaskIdCancelPost: build.mutation<
      CancelTaskEvaluationV1TasksTaskIdCancelPostApiResponse,
      CancelTaskEvaluationV1TasksTaskIdCancelPostApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/tasks/${queryArg.taskId}/cancel`, method: "POST" }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as evaluationApi };
export type HealthzEvaluationV1HealthzGetApiResponse = /** status 200 Successful Response */ HealthResponse;
export type HealthzEvaluationV1HealthzGetApiArg = void;
export type ReadyEvaluationV1ReadyGetApiResponse = /** status 200 Successful Response */ ReadyResponse;
export type ReadyEvaluationV1ReadyGetApiArg = void;
export type CreateCampaignEvaluationV1CampaignsPostApiResponse =
  /** status 202 Successful Response */ CampaignCreatedResponse;
export type CreateCampaignEvaluationV1CampaignsPostApiArg = {
  createEvaluationCampaignRequest: CreateEvaluationCampaignRequest;
};
export type ListCampaignsEvaluationV1CampaignsGetApiResponse =
  /** status 200 Successful Response */ EvaluationCampaignListResponse;
export type ListCampaignsEvaluationV1CampaignsGetApiArg = {
  teamId: string;
};
export type GetCampaignEvaluationV1CampaignsCampaignIdGetApiResponse =
  /** status 200 Successful Response */ EvaluationCampaignResponse;
export type GetCampaignEvaluationV1CampaignsCampaignIdGetApiArg = {
  campaignId: string;
};
export type DeleteCampaignEvaluationV1CampaignsCampaignIdDeleteApiResponse = unknown;
export type DeleteCampaignEvaluationV1CampaignsCampaignIdDeleteApiArg = {
  campaignId: string;
};
export type ListCasesEvaluationV1CampaignsCampaignIdCasesGetApiResponse =
  /** status 200 Successful Response */ EvaluationCaseListResponse;
export type ListCasesEvaluationV1CampaignsCampaignIdCasesGetApiArg = {
  campaignId: string;
  offset?: number;
  limit?: number;
};
export type GetCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGetApiResponse =
  /** status 200 Successful Response */ EvaluationCaseResponse;
export type GetCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGetApiArg = {
  campaignId: string;
  caseId: string;
};
export type StreamEventsEvaluationV1CampaignsCampaignIdEventsGetApiResponse = /** status 200 Successful Response */ any;
export type StreamEventsEvaluationV1CampaignsCampaignIdEventsGetApiArg = {
  campaignId: string;
};
export type CancelCampaignEvaluationV1CampaignsCampaignIdCancelPostApiResponse = /** status 202 Successful Response */ {
  [key: string]: any;
};
export type CancelCampaignEvaluationV1CampaignsCampaignIdCancelPostApiArg = {
  campaignId: string;
};
export type GetTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGetApiResponse =
  /** status 200 Successful Response */ TelemetrySessionResponse;
export type GetTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGetApiArg = {
  campaignId: string;
};
export type GetTelemetryEvaluationV1TelemetryGetApiResponse =
  /** status 200 Successful Response */ TelemetryInfoResponse;
export type GetTelemetryEvaluationV1TelemetryGetApiArg = void;
export type AnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostApiResponse =
  /** status 200 Successful Response */ CampaignAnalysisResponse;
export type AnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostApiArg = {
  campaignId: string;
};
export type ListTasksEvaluationV1TasksGetApiResponse = /** status 200 Successful Response */ TaskListResponse;
export type ListTasksEvaluationV1TasksGetApiArg = {
  scope?: "user" | "team";
  teamId?: string | null;
  excludeTerminal?: boolean;
};
export type GetTaskEvaluationV1TasksTaskIdGetApiResponse = /** status 200 Successful Response */ TaskSummary;
export type GetTaskEvaluationV1TasksTaskIdGetApiArg = {
  taskId: string;
};
export type GetLatestEventEvaluationV1TasksTaskIdLatestGetApiResponse =
  /** status 200 Successful Response */ EvaluationTaskEvent;
export type GetLatestEventEvaluationV1TasksTaskIdLatestGetApiArg = {
  taskId: string;
};
export type StreamTaskEventsEvaluationV1TasksTaskIdEventsGetApiResponse = /** status 200 Successful Response */ any;
export type StreamTaskEventsEvaluationV1TasksTaskIdEventsGetApiArg = {
  taskId: string;
};
export type CancelTaskEvaluationV1TasksTaskIdCancelPostApiResponse = /** status 202 Successful Response */ {
  [key: string]: any;
};
export type CancelTaskEvaluationV1TasksTaskIdCancelPostApiArg = {
  taskId: string;
};
export type HealthResponse = {
  status?: "ok";
  service?: "fred-evaluation";
};
export type ReadyResponse = {
  status?: "ready";
  service?: "fred-evaluation";
};
export type CampaignCreatedResponse = {
  campaign_id: string;
  run_id: string;
  task_id: string | null;
  state: string;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type ManagedInstanceTarget = {
  kind: "managed_instance";
  agent_instance_id: string;
};
export type RuntimeAgentTarget = {
  kind: "runtime_agent";
  runtime_id: string;
  agent_id: string;
};
export type EvaluationCaseInput = {
  external_id?: string | null;
  input: string;
  expected_output?: string | null;
  tags?: string[];
};
export type EvaluationDataset = {
  name: string;
  version?: string | null;
  cases: EvaluationCaseInput[];
};
export type EvaluationExecutionOptions = {
  max_concurrency?: number;
  case_timeout_seconds?: number;
};
export type CreateEvaluationCampaignRequest = {
  name: string;
  team_id: string;
  target: ManagedInstanceTarget | RuntimeAgentTarget;
  dataset: EvaluationDataset;
  profile?: string;
  judge_profile_id: string;
  execution?: EvaluationExecutionOptions;
};
export type EvaluationCampaignResponse = {
  schema_version?: "1";
  campaign_id: string;
  run_id: string | null;
  task_id: string | null;
  name: string;
  team_id: string;
  created_by: string;
  target: ManagedInstanceTarget | RuntimeAgentTarget;
  dataset_name: string;
  dataset_version: string | null;
  profile: string;
  judge_profile_id: string;
  operational_state: string;
  verdict: string;
  total_cases: number;
  completed_cases: number;
  passed_cases: number;
  failed_cases: number;
  execution_error_cases: number;
  scoring_error_cases: number;
  metric_averages: {
    [key: string]: number;
  } | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};
export type EvaluationCampaignListResponse = {
  campaigns: EvaluationCampaignResponse[];
  total: number;
};
export type EvaluationMetricResultResponse = {
  name: string;
  provider: string;
  score: number | null;
  threshold: number | null;
  verdict: "passed" | "insufficient" | "failed" | "skipped" | "error";
  explanation: string | null;
  error: string | null;
};
export type StructuralCheckResponse = {
  name: string;
  passed: boolean | null;
};
export type EvaluationCaseResponse = {
  case_id: string;
  campaign_id: string;
  run_id: string | null;
  external_id: string | null;
  status: string;
  outcome: string | null;
  verdict: string;
  input: string;
  expected_output: string | null;
  actual_output: string | null;
  profile: string | null;
  latency_ms: number | null;
  execution_error: string | null;
  scoring_errors: string[];
  metrics: EvaluationMetricResultResponse[];
  structural_checks: StructuralCheckResponse[];
  started_at: string | null;
  completed_at: string | null;
};
export type EvaluationCaseListResponse = {
  cases: EvaluationCaseResponse[];
  total: number;
};
export type TelemetrySessionResponse = {
  available: boolean;
  url?: string | null;
};
export type TelemetryInfoResponse = {
  enabled: boolean;
  langfuse_session_url?: string | null;
};
export type CampaignAnalysisResult = {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
  risk_level: string;
};
export type CampaignAnalysisResponse = {
  campaign_id: string;
  analysis: CampaignAnalysisResult;
  cached: boolean;
};
export type TaskState = "pending" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled";
export type TaskTarget = {
  type: string;
  id: string;
  label: string;
};
export type TaskSummary = {
  task_id: string;
  kind: string;
  state: TaskState;
  progress?: number | null;
  step?: string | null;
  error?: string | null;
  target?: TaskTarget | null;
  created_by?: string | null;
  team_id?: string | null;
  created_at: string;
  updated_at: string;
};
export type TaskListResponse = {
  tasks: TaskSummary[];
};
export type EvaluationDetail = {
  campaign_id: string;
  completed: number;
  total: number;
  passed: number;
  failed: number;
  execution_errors: number;
  scoring_errors: number;
};
export type EvaluationTaskEvent = {
  kind?: "evaluation";
  task_id: string;
  state: TaskState;
  seq: number;
  timestamp: string;
  progress?: number | null;
  step?: string | null;
  error?: string | null;
  target?: TaskTarget | null;
  owner?: string | null;
  detail?: EvaluationDetail | null;
};
export const {
  useHealthzEvaluationV1HealthzGetQuery,
  useLazyHealthzEvaluationV1HealthzGetQuery,
  useReadyEvaluationV1ReadyGetQuery,
  useLazyReadyEvaluationV1ReadyGetQuery,
  useCreateCampaignEvaluationV1CampaignsPostMutation,
  useListCampaignsEvaluationV1CampaignsGetQuery,
  useLazyListCampaignsEvaluationV1CampaignsGetQuery,
  useGetCampaignEvaluationV1CampaignsCampaignIdGetQuery,
  useLazyGetCampaignEvaluationV1CampaignsCampaignIdGetQuery,
  useDeleteCampaignEvaluationV1CampaignsCampaignIdDeleteMutation,
  useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery,
  useLazyListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery,
  useGetCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGetQuery,
  useLazyGetCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGetQuery,
  useStreamEventsEvaluationV1CampaignsCampaignIdEventsGetQuery,
  useLazyStreamEventsEvaluationV1CampaignsCampaignIdEventsGetQuery,
  useCancelCampaignEvaluationV1CampaignsCampaignIdCancelPostMutation,
  useGetTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGetQuery,
  useLazyGetTelemetrySessionEvaluationV1TelemetrySessionCampaignIdGetQuery,
  useGetTelemetryEvaluationV1TelemetryGetQuery,
  useLazyGetTelemetryEvaluationV1TelemetryGetQuery,
  useAnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostMutation,
  useListTasksEvaluationV1TasksGetQuery,
  useLazyListTasksEvaluationV1TasksGetQuery,
  useGetTaskEvaluationV1TasksTaskIdGetQuery,
  useLazyGetTaskEvaluationV1TasksTaskIdGetQuery,
  useGetLatestEventEvaluationV1TasksTaskIdLatestGetQuery,
  useLazyGetLatestEventEvaluationV1TasksTaskIdLatestGetQuery,
  useStreamTaskEventsEvaluationV1TasksTaskIdEventsGetQuery,
  useLazyStreamTaskEventsEvaluationV1TasksTaskIdEventsGetQuery,
  useCancelTaskEvaluationV1TasksTaskIdCancelPostMutation,
} = injectedRtkApi;
