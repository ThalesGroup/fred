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
    startRunEvaluationV1EvaluationsEvaluationIdRunsPost: build.mutation<
      StartRunEvaluationV1EvaluationsEvaluationIdRunsPostApiResponse,
      StartRunEvaluationV1EvaluationsEvaluationIdRunsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/evaluation/v1/evaluations/${queryArg.evaluationId}/runs`,
        method: "POST",
        body: queryArg.startRunRequest,
      }),
    }),
    listRunsEvaluationV1EvaluationsEvaluationIdRunsGet: build.query<
      ListRunsEvaluationV1EvaluationsEvaluationIdRunsGetApiResponse,
      ListRunsEvaluationV1EvaluationsEvaluationIdRunsGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/evaluations/${queryArg.evaluationId}/runs` }),
    }),
    getRunEvaluationV1RunsRunIdGet: build.query<
      GetRunEvaluationV1RunsRunIdGetApiResponse,
      GetRunEvaluationV1RunsRunIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/runs/${queryArg.runId}` }),
    }),
    deleteRunEvaluationV1RunsRunIdDelete: build.mutation<
      DeleteRunEvaluationV1RunsRunIdDeleteApiResponse,
      DeleteRunEvaluationV1RunsRunIdDeleteApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/runs/${queryArg.runId}`, method: "DELETE" }),
    }),
    listRunCasesEvaluationV1RunsRunIdCasesGet: build.query<
      ListRunCasesEvaluationV1RunsRunIdCasesGetApiResponse,
      ListRunCasesEvaluationV1RunsRunIdCasesGetApiArg
    >({
      query: (queryArg) => ({
        url: `/evaluation/v1/runs/${queryArg.runId}/cases`,
        params: {
          offset: queryArg.offset,
          limit: queryArg.limit,
        },
      }),
    }),
    getRunCaseEvaluationV1RunsRunIdCasesCaseIdGet: build.query<
      GetRunCaseEvaluationV1RunsRunIdCasesCaseIdGetApiResponse,
      GetRunCaseEvaluationV1RunsRunIdCasesCaseIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/runs/${queryArg.runId}/cases/${queryArg.caseId}` }),
    }),
    streamRunEventsEvaluationV1RunsRunIdEventsGet: build.query<
      StreamRunEventsEvaluationV1RunsRunIdEventsGetApiResponse,
      StreamRunEventsEvaluationV1RunsRunIdEventsGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/runs/${queryArg.runId}/events` }),
    }),
    cancelRunEvaluationV1RunsRunIdCancelPost: build.mutation<
      CancelRunEvaluationV1RunsRunIdCancelPostApiResponse,
      CancelRunEvaluationV1RunsRunIdCancelPostApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/runs/${queryArg.runId}/cancel`, method: "POST" }),
    }),
    getTelemetrySessionEvaluationV1TelemetrySessionRunIdGet: build.query<
      GetTelemetrySessionEvaluationV1TelemetrySessionRunIdGetApiResponse,
      GetTelemetrySessionEvaluationV1TelemetrySessionRunIdGetApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/telemetry/session/${queryArg.runId}` }),
    }),
    getTelemetryEvaluationV1TelemetryGet: build.query<
      GetTelemetryEvaluationV1TelemetryGetApiResponse,
      GetTelemetryEvaluationV1TelemetryGetApiArg
    >({
      query: () => ({ url: `/evaluation/v1/telemetry` }),
    }),
    analyzeRunEvaluationV1RunsRunIdAnalyzePost: build.mutation<
      AnalyzeRunEvaluationV1RunsRunIdAnalyzePostApiResponse,
      AnalyzeRunEvaluationV1RunsRunIdAnalyzePostApiArg
    >({
      query: (queryArg) => ({ url: `/evaluation/v1/runs/${queryArg.runId}/analyze`, method: "POST" }),
    }),
    createEvaluationEvaluationV1EvaluationsPost: build.mutation<
      CreateEvaluationEvaluationV1EvaluationsPostApiResponse,
      CreateEvaluationEvaluationV1EvaluationsPostApiArg
    >({
      query: (queryArg) => ({
        url: `/evaluation/v1/evaluations`,
        method: "POST",
        body: queryArg.createEvaluationRequest,
      }),
    }),
    listEvaluationsEvaluationV1EvaluationsGet: build.query<
      ListEvaluationsEvaluationV1EvaluationsGetApiResponse,
      ListEvaluationsEvaluationV1EvaluationsGetApiArg
    >({
      query: (queryArg) => ({
        url: `/evaluation/v1/evaluations`,
        params: {
          team_id: queryArg.teamId,
        },
      }),
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
export type StartRunEvaluationV1EvaluationsEvaluationIdRunsPostApiResponse =
  /** status 202 Successful Response */ RunCreatedResponse;
export type StartRunEvaluationV1EvaluationsEvaluationIdRunsPostApiArg = {
  evaluationId: string;
  startRunRequest: StartRunRequest;
};
export type ListRunsEvaluationV1EvaluationsEvaluationIdRunsGetApiResponse =
  /** status 200 Successful Response */ EvaluationRun[];
export type ListRunsEvaluationV1EvaluationsEvaluationIdRunsGetApiArg = {
  evaluationId: string;
};
export type GetRunEvaluationV1RunsRunIdGetApiResponse = /** status 200 Successful Response */ EvaluationRun;
export type GetRunEvaluationV1RunsRunIdGetApiArg = {
  runId: string;
};
export type DeleteRunEvaluationV1RunsRunIdDeleteApiResponse = unknown;
export type DeleteRunEvaluationV1RunsRunIdDeleteApiArg = {
  runId: string;
};
export type ListRunCasesEvaluationV1RunsRunIdCasesGetApiResponse =
  /** status 200 Successful Response */ EvaluationCaseListResponse;
export type ListRunCasesEvaluationV1RunsRunIdCasesGetApiArg = {
  runId: string;
  offset?: number;
  limit?: number;
};
export type GetRunCaseEvaluationV1RunsRunIdCasesCaseIdGetApiResponse =
  /** status 200 Successful Response */ EvaluationCaseResponse;
export type GetRunCaseEvaluationV1RunsRunIdCasesCaseIdGetApiArg = {
  runId: string;
  caseId: string;
};
export type StreamRunEventsEvaluationV1RunsRunIdEventsGetApiResponse = /** status 200 Successful Response */ any;
export type StreamRunEventsEvaluationV1RunsRunIdEventsGetApiArg = {
  runId: string;
};
export type CancelRunEvaluationV1RunsRunIdCancelPostApiResponse = /** status 202 Successful Response */ {
  [key: string]: any;
};
export type CancelRunEvaluationV1RunsRunIdCancelPostApiArg = {
  runId: string;
};
export type GetTelemetrySessionEvaluationV1TelemetrySessionRunIdGetApiResponse =
  /** status 200 Successful Response */ TelemetrySessionResponse;
export type GetTelemetrySessionEvaluationV1TelemetrySessionRunIdGetApiArg = {
  runId: string;
};
export type GetTelemetryEvaluationV1TelemetryGetApiResponse =
  /** status 200 Successful Response */ TelemetryInfoResponse;
export type GetTelemetryEvaluationV1TelemetryGetApiArg = void;
export type AnalyzeRunEvaluationV1RunsRunIdAnalyzePostApiResponse =
  /** status 200 Successful Response */ RunAnalysisResponse;
export type AnalyzeRunEvaluationV1RunsRunIdAnalyzePostApiArg = {
  runId: string;
};
export type CreateEvaluationEvaluationV1EvaluationsPostApiResponse =
  /** status 201 Successful Response */ EvaluationDetailResponse;
export type CreateEvaluationEvaluationV1EvaluationsPostApiArg = {
  createEvaluationRequest: CreateEvaluationRequest;
};
export type ListEvaluationsEvaluationV1EvaluationsGetApiResponse =
  /** status 200 Successful Response */ EvaluationListResponse;
export type ListEvaluationsEvaluationV1EvaluationsGetApiArg = {
  teamId: string;
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
  [key: string]: string;
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
export type RunCreatedResponse = {
  run_id: string;
  evaluation_id: string;
  task_id: string | null;
  state: string;
};
export type EvaluatorErrorDetail = {
  code:
    | "authentication_required"
    | "access_forbidden"
    | "control_plane_authentication_failed"
    | "target_forbidden"
    | "target_not_found"
    | "target_unavailable"
    | "target_invalid"
    | "control_plane_unavailable"
    | "control_plane_invalid_response"
    | "evaluation_not_found";
  message: string;
};
export type EvaluatorErrorResponse = {
  detail: EvaluatorErrorDetail;
};
export type ManagedInstanceTarget = {
  kind: "managed_instance";
  agent_instance_id: string;
};
export type StartRunRequest = {
  team_id: string;
  target: ManagedInstanceTarget;
};
export type RuntimeAgentTarget = {
  kind: "runtime_agent";
  runtime_id: string;
  agent_id: string;
};
export type RunSnapshot = {
  schema_version?: "1";
  evaluation_name: string;
  evaluation_version: string;
  target: ManagedInstanceTarget | RuntimeAgentTarget;
  resolved_target_config?: {
    [key: string]: string;
  } | null;
  profile: string;
  judge_profile_id: string;
  execution?: {
    [key: string]: number;
  } | null;
};
export type EvaluationRun = {
  schema_version?: "1";
  run_id: string;
  evaluation_id: string;
  task_id: string | null;
  target: ManagedInstanceTarget | RuntimeAgentTarget;
  profile: string;
  judge_profile_id: string;
  operational_state: string;
  verdict: "pending" | "passed" | "failed" | "inconclusive";
  total_cases: number;
  completed_cases: number;
  passed_cases: number;
  failed_cases: number;
  execution_error_cases: number;
  scoring_error_cases: number;
  snapshot: RunSnapshot;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
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
export type RunAnalysisResult = {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
  risk_level: string;
};
export type RunAnalysisResponse = {
  run_id: string;
  analysis: RunAnalysisResult;
  cached: boolean;
};
export type EvaluationCompleteness = "minimal" | "complete";
export type EvaluationCase = {
  external_id?: string | null;
  input: string;
  expected_output?: string | null;
  tags?: string[];
  source_candidate_id?: string | null;
  source_session_id?: string | null;
};
export type EvaluationDetailResponse = {
  evaluation_id: string;
  name: string;
  version: string;
  author: string;
  team_id: string;
  origin: "capture" | "upload" | "manual";
  completeness: EvaluationCompleteness;
  case_count: number;
  created_at: string;
  cases: EvaluationCase[];
};
export type CreateEvaluationRequest = {
  team_id: string;
  name: string;
  origin: "upload" | "manual";
  source_filename?: string | null;
  cases: EvaluationCase[];
};
export type EvaluationSummaryResponse = {
  evaluation_id: string;
  name: string;
  version: string;
  author: string;
  team_id: string;
  origin: "capture" | "upload" | "manual";
  completeness: EvaluationCompleteness;
  case_count: number;
  created_at: string;
};
export type EvaluationListResponse = {
  evaluations: EvaluationSummaryResponse[];
  total: number;
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
  scheduled_for?: string | null;
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
  task_id: string;
  state: TaskState;
  seq: number;
  timestamp: string;
  progress?: number | null;
  step?: string | null;
  error?: string | null;
  target?: TaskTarget | null;
  owner?: string | null;
  kind?: "evaluation";
  detail?: EvaluationDetail | null;
};
export const {
  useHealthzEvaluationV1HealthzGetQuery,
  useLazyHealthzEvaluationV1HealthzGetQuery,
  useReadyEvaluationV1ReadyGetQuery,
  useLazyReadyEvaluationV1ReadyGetQuery,
  useStartRunEvaluationV1EvaluationsEvaluationIdRunsPostMutation,
  useListRunsEvaluationV1EvaluationsEvaluationIdRunsGetQuery,
  useLazyListRunsEvaluationV1EvaluationsEvaluationIdRunsGetQuery,
  useGetRunEvaluationV1RunsRunIdGetQuery,
  useLazyGetRunEvaluationV1RunsRunIdGetQuery,
  useDeleteRunEvaluationV1RunsRunIdDeleteMutation,
  useListRunCasesEvaluationV1RunsRunIdCasesGetQuery,
  useLazyListRunCasesEvaluationV1RunsRunIdCasesGetQuery,
  useGetRunCaseEvaluationV1RunsRunIdCasesCaseIdGetQuery,
  useLazyGetRunCaseEvaluationV1RunsRunIdCasesCaseIdGetQuery,
  useStreamRunEventsEvaluationV1RunsRunIdEventsGetQuery,
  useLazyStreamRunEventsEvaluationV1RunsRunIdEventsGetQuery,
  useCancelRunEvaluationV1RunsRunIdCancelPostMutation,
  useGetTelemetrySessionEvaluationV1TelemetrySessionRunIdGetQuery,
  useLazyGetTelemetrySessionEvaluationV1TelemetrySessionRunIdGetQuery,
  useGetTelemetryEvaluationV1TelemetryGetQuery,
  useLazyGetTelemetryEvaluationV1TelemetryGetQuery,
  useAnalyzeRunEvaluationV1RunsRunIdAnalyzePostMutation,
  useCreateEvaluationEvaluationV1EvaluationsPostMutation,
  useListEvaluationsEvaluationV1EvaluationsGetQuery,
  useLazyListEvaluationsEvaluationV1EvaluationsGetQuery,
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
