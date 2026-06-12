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
  verdict: "passed" | "failed" | "skipped" | "error";
  explanation: string | null;
  error: string | null;
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
  started_at: string | null;
  completed_at: string | null;
};
export type EvaluationCaseListResponse = {
  cases: EvaluationCaseResponse[];
  total: number;
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
  useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery,
  useLazyListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery,
  useGetCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGetQuery,
  useLazyGetCaseEvaluationV1CampaignsCampaignIdCasesCaseIdGetQuery,
  useStreamEventsEvaluationV1CampaignsCampaignIdEventsGetQuery,
  useLazyStreamEventsEvaluationV1CampaignsCampaignIdEventsGetQuery,
  useCancelCampaignEvaluationV1CampaignsCampaignIdCancelPostMutation,
} = injectedRtkApi;
