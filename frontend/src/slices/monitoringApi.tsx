// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../common/dynamicBaseQuery.tsx";

export type NumericalMetric = {
  time_bucket: string;
  values: Record<string, number>;
} & Record<string, any>;

export interface CategoricalMetric {
  timestamp: number;
  user_id?: string;
  session_id?: string;
  agent_name?: string;
  model_name?: string;
  model_type?: string;
  finish_reason?: string;
  id?: string | null;
  system_fingerprint?: string;
  service_tier?: string;
}

export type Precision = "sec" | "min" | "hour" | "day";

/**
 * API Slice for Monitoring Metrics
 */
export const monitoringApi = createApi({
  reducerPath: "monitoringApi",
  baseQuery: createDynamicBaseQuery({ backend: "api" }),
  endpoints: (builder) => ({

    fetchNumericalMetrics: builder.mutation<NumericalMetric[], {
      start: string;
      end: string;
      precision?: Precision;
      agg: string[];          // Ex: ["latency:avg", "total_tokens:sum"]
      groupby?: string[];       // Ex: "agent_name"
    }>({
      query: ({ start, end, precision = "min", agg, groupby }) => ({
        url: `/fred/metrics/nodes/numerical`,
        method: "GET",
        params: {
          start,
          end,
          precision,
          ...(groupby ? { groupby } : {}),
          agg,  // Will serialize to multiple &agg=... in query
        },
      }),
    }),

    fetchCategoricalMetrics: builder.mutation<CategoricalMetric[], {
      start: string;
      end: string;
    }>({
      query: ({ start, end }) => ({
        url: `/fred/metrics/nodes/categorical`,
        method: "GET",
        params: { start, end },
      }),
    }),
  }),
});

export const {
  useFetchNumericalMetricsMutation,
  useFetchCategoricalMetricsMutation,
} = monitoringApi;

export const {
  reducer: monitoringApiReducer,
  middleware: monitoringApiMiddleware,
} = monitoringApi;
