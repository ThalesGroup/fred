// Custom RTK endpoints for persisted benchmark runs
import { knowledgeFlowApi } from "./knowledgeFlowOpenApi";
import type { BenchmarkResponse } from "./knowledgeFlowOpenApi";

export type SavedRunSummary = {
  id: string;
  input_filename: string;
  file_type: string;
  processors_count: number;
  size?: number;
  modified?: string | null;
};

export const benchPersistApi = knowledgeFlowApi.injectEndpoints({
  endpoints: (build) => ({
    listBenchRuns: build.query<SavedRunSummary[], void>({
      query: () => ({ url: `/knowledge-flow/v1/dev/bench/runs` }),
      providesTags: (res) =>
        res
          ? [
              ...res.map((r) => ({ type: "BenchRun" as const, id: r.id })),
              { type: "BenchRun" as const, id: "LIST" },
            ]
          : [{ type: "BenchRun" as const, id: "LIST" }],
    }),
    getBenchRun: build.query<BenchmarkResponse, { runId: string }>({
      query: ({ runId }) => ({ url: `/knowledge-flow/v1/dev/bench/runs/${encodeURIComponent(runId)}` }),
      providesTags: (_res, _err, arg) => [{ type: "BenchRun" as const, id: arg.runId }],
    }),
    deleteBenchRun: build.mutation<{ status: string }, { runId: string }>({
      query: ({ runId }) => ({
        url: `/knowledge-flow/v1/dev/bench/runs/${encodeURIComponent(runId)}`,
        method: "DELETE",
      }),
      invalidatesTags: (_res, _err, arg) => [
        { type: "BenchRun" as const, id: arg.runId },
        { type: "BenchRun" as const, id: "LIST" },
      ],
    }),
  }),
});

export const {
  useListBenchRunsQuery,
  useGetBenchRunQuery,
  useLazyGetBenchRunQuery,
  useDeleteBenchRunMutation,
} = benchPersistApi;
