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

export interface NumericalMetric {
  bucket: string;
  values: Record<string, number>;
}

export interface CategoricalMetric {
  timestamp: number;
  user_id?: string;
  session_id?: string;
  model_name?: string;
  model_type?: string;
  finish_reason?: string;
  id?: string | null;
  system_fingerprint?: string;
  service_tier?: string;
}
export type Precision = "sec" | "min" | "hour" | "day";
export type Aggregation = "avg" | "min" | "max" | "sum";

/**
 * API Slice for Monitoring Metrics (using `mutation` instead of `query`)
 */
export const monitoringApi = createApi({
  reducerPath: "monitoringApi",
  baseQuery: createDynamicBaseQuery({ backend: "api" }),
  endpoints: (builder) => ({
    fetchNumericalMetrics: builder.mutation<NumericalMetric[], {
      start: string;
      end: string;
      precision?: Precision;
      agg?: Aggregation;
    }>({
      query: ({ start, end, precision = "min", agg = "avg" }) => ({
        url: `/fred/metrics/numerical`,
        method: "GET",
        params: { start, end, precision, agg },
      }),
    }),

    fetchCategoricalMetrics: builder.mutation<CategoricalMetric[], {
      start: string;
      end: string;
    }>({
      query: ({ start, end }) => ({
        url: `/fred/metrics/categorical`,
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
