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

import { useEffect, useMemo, useState } from "react";
import { Box, Grid2 } from "@mui/material";
import dayjs, { Dayjs } from "dayjs";
import "dayjs/locale/fr";

// Fred: global controls (single Paper at top)
import DashboardCard from "../DashboardCard";

// Fred: shared time axis utilities — single source of truth
import { TimePrecision, getPrecisionForRange, alignDateRangeToPrecision, precisionToInterval } from "../timeAxis";

// Theme-driven chart styling (no time logic here)

// Existing token chart (pure presentational)
import { TokenUsageChart } from "./TokenUsageChart";
import { useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery } from "../../../slices/agentic/agenticOpenApi";

// KPI query client
import { FramelessTile } from "../FramelessTile";
import { KpiStatusMini } from "./KpiStatusMini";
import { KpiLatencyMini } from "./KpiLatencyMini";
import {
  FilterTerm,
  KpiQuery,
  KpiQueryResult,
  useQueryKnowledgeFlowV1KpiQueryPostMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import DateRangeControl from "../common/DateRangeControl";
import { FULL_QUICK_RANGES } from "../common/dateRangeControlPresets";

/**
 *
 * Why (Fred): a single top-level page that owns date range + precision, renders many compact KPI tiles
 * without nesting Papers (no Paper-in-Paper). Tiles are *frameless* and receive shared xDomain + precision.
 *
 * How to extend: add another <Grid2> with a frameless tile component below. Tiles should accept
 * { start, end, precision, xDomain, viewingMode?, userId?, agentId? } and stay presentational.
 */
export default function KpiDashboard() {
  const now = dayjs();

  // Range state (top-level owns it)
  const [startDate, setStartDate] = useState<Dayjs>(now.subtract(12, "hours"));
  const [endDate, setEndDate] = useState<Dayjs>(now);

  // Shared precision + aligned range + shared xDomain (UTC numeric)
  const precision: TimePrecision = useMemo(
    () => getPrecisionForRange(startDate.toDate(), endDate.toDate()),
    [startDate, endDate],
  );
  const [alignedStartIso, alignedEndIso] = useMemo(
    () => alignDateRangeToPrecision(startDate, endDate, precision),
    [startDate, endDate, precision],
  );
  const alignedStart = useMemo(() => new Date(alignedStartIso), [alignedStartIso]);
  const alignedEnd = useMemo(() => new Date(alignedEndIso), [alignedEndIso]);
  const xDomain: [number, number] = useMemo(
    () => [alignedStart.getTime(), alignedEnd.getTime()],
    [alignedStart, alignedEnd],
  );

  // Token usage (example non-KPI datasource) fetched once here, passed to its frameless tile
  const [triggerTokens, { data: tokenMetrics }] =
    useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery();

  useEffect(() => {
    triggerTokens({ start: alignedStartIso, end: alignedEndIso, precision, agg: ["total_tokens:sum"], groupby: [] });
  }, [alignedStartIso, alignedEndIso, precision, triggerTokens]);

  /* ---------------------------------------------------------------------- */
  /* KPI: chat.exchange_latency_ms p50/p95  */
  /* ---------------------------------------------------------------------- */
  const [fetchLatency, latencyState] = useQueryKnowledgeFlowV1KpiQueryPostMutation();

  const latencyBody: KpiQuery = useMemo(
    () => ({
      since: alignedStartIso,
      until: alignedEndIso,
      select: [
        { field: "metric.value", op: "percentile", alias: "p50", p: 50 } as any,
        { field: "metric.value", op: "percentile", alias: "p95", p: 95 } as any,
      ],
      group_by: [],
      time_bucket: { interval: precisionToInterval[precision] } as any,
      filters: [{ field: "metric.name", value: "chat.exchange_latency_ms" } as FilterTerm],
      limit: 1000,
    }),
    [alignedStartIso, alignedEndIso, precision],
  );

  useEffect(() => {
    fetchLatency({ kpiQuery: latencyBody })
      .unwrap()
      .then((d) => console.debug("[KPI parent] latency ok", d))
      .catch((e) => console.warn("[KPI parent] latency error", e));
  }, [fetchLatency, latencyBody]);

  const latencyRows = (latencyState.data as KpiQueryResult | undefined)?.rows ?? [];
  /* ---------------------------------------------------------------------- */
  /* ---------------------------------------------------------------------- */
  /* KPI: chat.exchange_total by dims.status (range totals)                 */
  /* Fetch at top-level; pass rows to the mini (presentational only).       */
  /* ---------------------------------------------------------------------- */
  const [fetchStatus, statusState] = useQueryKnowledgeFlowV1KpiQueryPostMutation();

  const statusBody: KpiQuery = useMemo(
    () => ({
      since: alignedStartIso,
      until: alignedEndIso,
      select: [{ field: "metric.value", op: "sum", alias: "exchanges" } as any],
      group_by: ["dims.status"],
      // No time_bucket: we want totals over the selected window
      filters: [{ field: "metric.name", value: "chat.exchange_total" } as FilterTerm],
      limit: 10,
      // If you want to sort bars by the metric instead of doc_count:
      // order_by: { by: "metric", metric_alias: "exchanges", direction: "desc" } as any,
    }),
    [alignedStartIso, alignedEndIso],
  );

  useEffect(() => {
    fetchStatus({ kpiQuery: statusBody })
      .unwrap()
      .catch(() => {});
  }, [fetchStatus, statusBody]);

  const statusRows = (statusState.data as KpiQueryResult | undefined)?.rows ?? [];

  return (
    <Box display="flex" flexDirection="column" gap={2} p={2}>
      {/* Single Paper host: global filters only */}
      <DashboardCard>
        <DateRangeControl
          startDate={startDate}
          endDate={endDate}
          setStartDate={setStartDate}
          setEndDate={setEndDate}
          quickRanges={FULL_QUICK_RANGES}
          toleranceMs={90_000} // tighter match for short windows
        />
      </DashboardCard>

      {/* Compact grid; frameless tiles (Boxes) to avoid Paper-in-Paper */}
      <Grid2 container spacing={2}>
        <Grid2 size={{ xs: 12, md: 12, lg: 12 }}>
          <FramelessTile
            title="Token usage"
            subtitle={`Sum of tokens per ${precision} bucket — all agents`}
            help="Aggregates total tokens across exchanges for the selected range. Spikes may indicate long outputs, retries, or loops."
          >
            <TokenUsageChart
              start={alignedStart}
              end={alignedEnd}
              precision={precision}
              metrics={tokenMetrics as any}
              height={150}
              xDomain={xDomain}
            />
          </FramelessTile>
        </Grid2>

        <Grid2 size={{ xs: 12, md: 6, lg: 6 }}>
          <FramelessTile
            title="Chat exchange latency (ms) — median & p95"
            subtitle={`End-to-end time to answer per ${precision} bucket — lower is better`}
            help="chat.exchange_latency_ms measured from exchange start to completion. p50 = typical, p95 = slow tail. Includes model and tools invoked during the exchange."
          >
            <KpiLatencyMini
              start={alignedStart}
              end={alignedEnd}
              precision={precision}
              xDomain={xDomain}
              height={150}
              showLegend={false}
              rows={latencyRows}
            />
          </FramelessTile>
        </Grid2>
        <Grid2 size={{ xs: 12, md: 6, lg: 6 }}>
          <FramelessTile
            title="Exchanges by status"
            subtitle="Range totals in the selected window"
            help="Sums of chat.exchange_total per dims.status (ok, error, timeout, filtered)."
          >
            <KpiStatusMini rows={statusRows} height={150} showLegend={false} />
          </FramelessTile>
        </Grid2>
      </Grid2>
    </Box>
  );
}
