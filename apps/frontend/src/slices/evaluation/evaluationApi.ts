import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../../common/dynamicBaseQuery";

export type OperationalState = "pending" | "running" | "succeeded" | "failed" | "cancelled";
export type Verdict = "pending" | "passed" | "failed" | "inconclusive";
export type CaseOutcome = "success" | "execution_error" | "degraded" | "hitl_blocked" | "unknown";
export type MetricVerdict = "passed" | "failed" | "skipped" | "error";

export type ManagedInstanceTarget = { kind: "managed_instance"; agent_instance_id: string };
export type RuntimeAgentTarget = { kind: "runtime_agent"; runtime_id: string; agent_id: string };

export interface EvaluationMetricResult {
  name: string;
  provider: string;
  score?: number;
  threshold?: number;
  verdict: MetricVerdict;
  explanation?: string;
  error?: string;
}

export interface EvaluationCaseResult {
  case_id: string;
  campaign_id: string;
  external_id?: string;
  status: "pending" | "running" | "completed" | "error" | "cancelled";
  outcome: CaseOutcome;
  verdict: Verdict;
  input: string;
  expected_output?: string;
  actual_output?: string;
  metrics: EvaluationMetricResult[];
  latency_ms?: number;
  execution_error?: string;
}

export interface EvaluationCampaign {
  campaign_id: string;
  run_id: string;
  name: string;
  team_id: string;
  created_by: string;
  target: ManagedInstanceTarget | RuntimeAgentTarget;
  dataset_name: string;
  dataset_version?: string;
  profile: string;
  judge_profile_id: string;
  operational_state: OperationalState;
  verdict: Verdict;
  total_cases: number;
  completed_cases: number;
  passed_cases: number;
  failed_cases: number;
  execution_error_cases: number;
  scoring_error_cases: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export const evaluationApi = createApi({
  reducerPath: "evaluationApi",
  baseQuery: createDynamicBaseQuery(),
  tagTypes: ["EvaluationCampaign", "EvaluationCase"],
  endpoints: () => ({}),
});

export const {
  useListCampaignsQuery,
  useGetCampaignQuery,
  useListCasesQuery,
  useCreateCampaignMutation,
  useCancelCampaignMutation,
  useGetTelemetryQuery,
  useGetTelemetrySessionQuery,
} = evaluationApi.injectEndpoints({
  endpoints: (builder) => ({
    listCampaigns: builder.query<
      { campaigns: EvaluationCampaign[]; total: number },
      { team_id?: string; state?: OperationalState }
    >({
      query: ({ team_id, state }) => {
        const params = new URLSearchParams();
        if (team_id) params.set("team_id", team_id);
        if (state) params.set("state", state);
        return `/evaluation/v1/campaigns?${params.toString()}`;
      },
      providesTags: ["EvaluationCampaign"],
    }),
    getCampaign: builder.query<EvaluationCampaign, string>({
      query: (campaignId) => `/evaluation/v1/campaigns/${campaignId}`,
      providesTags: (_r, _e, id) => [{ type: "EvaluationCampaign", id }],
    }),
    listCases: builder.query<{ cases: EvaluationCaseResult[]; total: number }, string>({
      query: (campaignId) => `/evaluation/v1/campaigns/${campaignId}/cases`,
      providesTags: (_r, _e, id) => [{ type: "EvaluationCase", id }],
    }),
    createCampaign: builder.mutation<EvaluationCampaign, Partial<EvaluationCampaign> & Record<string, unknown>>({
      query: (body) => ({ url: "/evaluation/v1/campaigns", method: "POST", body }),
      invalidatesTags: ["EvaluationCampaign"],
    }),
    cancelCampaign: builder.mutation<void, string>({
      query: (campaignId) => ({ url: `/evaluation/v1/campaigns/${campaignId}/cancel`, method: "POST" }),
      invalidatesTags: ["EvaluationCampaign"],
    }),
    getTelemetry: builder.query<{ enabled: boolean; langfuse_session_url: string | null }, void>({
      query: () => "/evaluation/v1/telemetry",
    }),
    getTelemetrySession: builder.query<{ available: boolean; url: string | null }, string>({
      query: (campaignId) => `/evaluation/v1/telemetry/session/${campaignId}`,
    }),
  }),
});
