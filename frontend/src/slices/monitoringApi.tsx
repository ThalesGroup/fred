// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../common/dynamicBaseQuery.tsx";

interface Metric {
  timestamp: string;
  type: string;
  value: number | string;
  [key: string]: any;
}

interface NumericalMetric {
  timestamp: string;
  metrics: Record<string, number>;
}

interface CategoricalMetric {
  timestamp: string;
  categories: Record<string, string>;
}

type Precision = "second" | "minute" | "hour" | "day";

/**
 * API Slice for Monitoring Metrics
 */
export const monitoringApi = createApi({
  reducerPath: "monitoringApi",
  baseQuery: createDynamicBaseQuery({ backend: "api" }),
  endpoints: (builder) => ({
    getAllMetrics: builder.query<Metric[], { start: string; end: string }>({
      query: ({ start, end }) => ({
        url: `/fred/metrics/all`,
        method: "GET",
        params: { start, end },
      }),
    }),
    getNumericalMetrics: builder.query<NumericalMetric[], { start: string; end: string; precision?: Precision }>({
      query: ({ start, end, precision = "minute" }) => ({
        url: `/fred/metrics/numerical`,
        method: "GET",
        params: { start, end, precision },
      }),
    }),
    getCategoricalMetrics: builder.query<CategoricalMetric[], { start: string; end: string }>({
      query: ({ start, end }) => ({
        url: `/fred/metrics/categorical`,
        method: "GET",
        params: { start, end },
      }),
    }),
  }),
});

export const {
  useGetAllMetricsQuery,
  useGetNumericalMetricsQuery,
  useGetCategoricalMetricsQuery,
} = monitoringApi;

export const { reducer: monitoringApiReducer, middleware: monitoringApiMiddleware } = monitoringApi;
