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

import { Box, FormControl, Grid2, InputLabel, MenuItem, Select } from "@mui/material";
import dayjs, { Dayjs } from "dayjs";
import "dayjs/locale/fr";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

// Fred: global controls (single Paper at top)
import DashboardCard from "../DashboardCard";

// Fred: shared time axis utilities — single source of truth
import { TimePrecision, alignDateRangeToPrecision, getPrecisionForRange, precisionToInterval } from "../timeAxis";

// Theme-driven chart styling (no time logic here)

// Existing token chart (pure presentational)
import { useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery } from "../../../slices/agentic/agenticOpenApi";
import { TokenUsageChart } from "./TokenUsageChart";

// to allow admin to have a view all KPIs mode
import { FormControlLabel, Switch, Typography } from "@mui/material";
import { useAuth } from "../../../security/AuthContext";

// KPI query client
import {
  FilterTerm,
  KpiQuery,
  SelectMetric,
  TimeBucket,
  useQueryKnowledgeFlowV1KpiQueryPostMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import DateRangeControl from "../common/DateRangeControl";
import { FULL_QUICK_RANGES } from "../common/dateRangeControlPresets";
import { FramelessTile } from "../FramelessTile";
import { KpiGroupedBarMini } from "./KpiGroupedBarMini";
import { KpiHeatStripMini } from "./KpiHeatStripMini";
import { KpiLatencyMini } from "./KpiLatencyMini";
import { KpiStatusMini } from "./KpiStatusMini";

const UI = {
  controlHeight: 32,
  buttonFontSize: 13,
  compactLabelFontSize: 11,
  compactLabelMinWidth: 90,
  compactPadding: 1.5,
  compactRowGap: 0.5,
  compactColumnGap: 0.25,
  compactHeaderGap: 0,
  heatStripHeight: 16,
  tileChartHeight: 135,
} as const;

const METRIC_VALUE_FIELD: SelectMetric["field"] = "metric.value";

const filterTerm = (field: FilterTerm["field"] | "dims.service", value: string) =>
  ({ field: field as FilterTerm["field"], value }) as FilterTerm;

const selectMetric = (
  alias: string,
  op: SelectMetric["op"],
  field?: SelectMetric["field"],
  p?: number,
): SelectMetric => ({
  alias,
  op,
  field,
  p,
});

const percentiles = (alias: string, p: number): SelectMetric =>
  selectMetric(alias, "percentile", METRIC_VALUE_FIELD, p);
const selectMax = (alias: string): SelectMetric => selectMetric(alias, "max", METRIC_VALUE_FIELD);
const selectAvg = (alias: string): SelectMetric => selectMetric(alias, "avg", METRIC_VALUE_FIELD);
const selectSum = (alias: string): SelectMetric => selectMetric(alias, "sum", METRIC_VALUE_FIELD);
const selectCount = (alias: string): SelectMetric => selectMetric(alias, "count");

const timeBucketFor = (precision: TimePrecision): TimeBucket => ({
  interval: precisionToInterval[precision],
});

const agenticPrecisionFor = (precision: TimePrecision) => {
  if (precision === "sec" || precision === "min") return "minute";
  if (precision === "hour") return "hour";
  return "day";
};

const useKpiRows = (query: KpiQuery) => {
  const [trigger, state] = useQueryKnowledgeFlowV1KpiQueryPostMutation();

  useEffect(() => {
    trigger({ kpiQuery: query })
      .unwrap()
      .catch(() => {});
  }, [trigger, query]);

  return state.data?.rows ?? [];
};

const useProcessHistoryRows = ({
  metricName,
  service,
  since,
  until,
  precision,
  viewGlobal,
}: {
  metricName: string;
  service: string;
  since: string;
  until: string;
  precision: TimePrecision;
  viewGlobal: boolean;
}) => {
  const query = useMemo<KpiQuery>(
    () => ({
      since,
      until,
      view_global: viewGlobal,
      select: [selectMax("max_pct")],
      group_by: [],
      time_bucket: timeBucketFor(precision),
      filters: [filterTerm("metric.name", metricName), filterTerm("dims.service", service)],
      limit: 1000,
    }),
    [since, until, precision, viewGlobal, metricName, service],
  );

  return useKpiRows(query);
};

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
  const isAdmin = useAuth().roles.includes("admin");
  const { t } = useTranslation();
  const [viewGlobal, setViewGlobal] = useState(false);
  // Range state (top-level owns it)
  const [startDate, setStartDate] = useState<Dayjs>(now.subtract(12, "hours"));
  const [endDate, setEndDate] = useState<Dayjs>(now);
  const [agentFilter, setAgentFilter] = useState<string>("");
  const dateRangeProps = { startDate, endDate, setStartDate, setEndDate, quickRanges: FULL_QUICK_RANGES };

  // Shared precision + aligned range + shared xDomain (UTC numeric)
  const precision: TimePrecision = useMemo(
    () => getPrecisionForRange(startDate.toDate(), endDate.toDate()),
    [startDate, endDate],
  );
  const agenticPrecision = useMemo(() => agenticPrecisionFor(precision), [precision]);
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
    triggerTokens({
      start: alignedStartIso,
      end: alignedEndIso,
      precision: agenticPrecision,
      agg: ["total_tokens:sum"],
      groupby: [],
    });
  }, [alignedStartIso, alignedEndIso, agenticPrecision, triggerTokens]);

  /* ---------------------------------------------------------------------- */
  /* KPI: chat.exchange_latency_ms p50/p95  */
  /* ---------------------------------------------------------------------- */
  const latencyBody: KpiQuery = useMemo(
    () => ({
      since: alignedStartIso,
      until: alignedEndIso,
      view_global: viewGlobal,
      select: [percentiles("p50", 50), percentiles("p95", 95)],
      group_by: [],
      time_bucket: timeBucketFor(precision),
      filters: [
        filterTerm("metric.name", "chat.exchange_latency_ms"),
        ...(agentFilter ? [filterTerm("dims.agent_id", agentFilter)] : []),
      ],
      limit: 1000,
    }),
    [alignedStartIso, alignedEndIso, precision, agentFilter, viewGlobal],
  );

  const latencyRows = useKpiRows(latencyBody);
  /* ---------------------------------------------------------------------- */
  /* ---------------------------------------------------------------------- */
  /* KPI: process CPU/memory history (max per bucket)                        */
  /* ---------------------------------------------------------------------- */
  const processViewGlobal = viewGlobal || isAdmin;

  const cpuHistoryRowsAgentic = useProcessHistoryRows({
    metricName: "process.cpu.percent",
    service: "agentic",
    since: alignedStartIso,
    until: alignedEndIso,
    precision,
    viewGlobal: processViewGlobal,
  });
  const memHistoryRowsAgentic = useProcessHistoryRows({
    metricName: "process.memory.rss_percent",
    service: "agentic",
    since: alignedStartIso,
    until: alignedEndIso,
    precision,
    viewGlobal: processViewGlobal,
  });
  const cpuHistoryRowsKf = useProcessHistoryRows({
    metricName: "process.cpu.percent",
    service: "knowledge-flow",
    since: alignedStartIso,
    until: alignedEndIso,
    precision,
    viewGlobal: processViewGlobal,
  });
  const memHistoryRowsKf = useProcessHistoryRows({
    metricName: "process.memory.rss_percent",
    service: "knowledge-flow",
    since: alignedStartIso,
    until: alignedEndIso,
    precision,
    viewGlobal: processViewGlobal,
  });

  /* ---------------------------------------------------------------------- */
  /* KPI: chat.exchange_total by dims.status (range totals)                 */
  /* Fetch at top-level; pass rows to the mini (presentational only).       */
  /* ---------------------------------------------------------------------- */
  const statusBody: KpiQuery = useMemo(
    () => ({
      since: alignedStartIso,
      until: alignedEndIso,
      view_global: viewGlobal,
      select: [selectSum("exchanges")],
      group_by: ["dims.status"],
      // No time_bucket: we want totals over the selected window
      filters: [
        filterTerm("metric.name", "chat.exchange_total"),
        ...(agentFilter ? [filterTerm("dims.agent_id", agentFilter)] : []),
      ],
      limit: 10,
      // If you want to sort bars by the metric instead of doc_count:
      // order_by: { by: "metric", metric_alias: "exchanges", direction: "desc" } as any,
    }),
    [alignedStartIso, alignedEndIso, agentFilter, viewGlobal],
  );
  const statusRows = useKpiRows(statusBody);

  /* ---------------------------------------------------------------------- */
  /* KPI: agent_id options (range totals)                                    */
  /* ---------------------------------------------------------------------- */
  const agentIdsBody: KpiQuery = useMemo(
    () => ({
      since: alignedStartIso,
      until: alignedEndIso,
      select: [selectCount("events")],
      group_by: ["dims.agent_id"],
      filters: [filterTerm("metric.name", "chat.exchange_total")],
      limit: 50,
    }),
    [alignedStartIso, alignedEndIso],
  );
  const agentIdsRows = useKpiRows(agentIdsBody);
  const agentOptions = useMemo(() => {
    const ids = new Set<string>();
    for (const row of agentIdsRows) {
      const value = (row.group as any)?.["dims.agent_id"];
      if (typeof value === "string" && value.trim()) {
        ids.add(value);
      }
    }
    return Array.from(ids).sort();
  }, [agentIdsRows]);

  /* ---------------------------------------------------------------------- */
  /* KPI: agent.step_latency_ms by dims.step (range avg)                     */
  /* ---------------------------------------------------------------------- */
  const stepLatencyBody: KpiQuery = useMemo(
    () => ({
      since: alignedStartIso,
      until: alignedEndIso,
      view_global: viewGlobal,
      select: [selectAvg("avg_ms")],
      group_by: ["dims.agent_step"],
      filters: [
        filterTerm("metric.name", "agent.step_latency_ms"),
        ...(agentFilter ? [filterTerm("dims.agent_id", agentFilter)] : []),
      ],
      limit: 50,
    }),
    [alignedStartIso, alignedEndIso, agentFilter, viewGlobal],
  );
  const stepLatencyRows = useKpiRows(stepLatencyBody);

  /* ---------------------------------------------------------------------- */
  /* KPI: agent.tool_latency_ms by dims.tool (range avg)                     */
  /* ---------------------------------------------------------------------- */
  const toolLatencyBody: KpiQuery = useMemo(
    () => ({
      since: alignedStartIso,
      until: alignedEndIso,
      view_global: viewGlobal,
      select: [selectAvg("avg_ms")],
      group_by: ["dims.tool_name"],
      filters: [
        filterTerm("metric.name", "agent.tool_latency_ms"),
        ...(agentFilter ? [filterTerm("dims.agent_id", agentFilter)] : []),
      ],
      limit: 50,
    }),
    [alignedStartIso, alignedEndIso, agentFilter, viewGlobal],
  );
  const toolLatencyRows = useKpiRows(toolLatencyBody);

  return (
    <Box display="flex" flexDirection="column" gap={1} p={2} mt={1}>
      {/* Single Paper host: global filters only */}
      <DashboardCard>
        <Box display="flex" flexDirection="column" gap={1.5}>
          <Box display="flex" flexWrap="wrap" alignItems="center" justifyContent="space-between" gap={1}>
            <Box flex="1 1 520px" minWidth={320}>
              <DateRangeControl
                {...dateRangeProps}
                toleranceMs={90_000} // tighter match for short windows
                showPickers={false}
              />
            </Box>
            <Typography
              sx={{
                fontSize: UI.buttonFontSize,
                fontWeight: 600,
                color: "text.secondary",
                whiteSpace: "nowrap",
              }}
            >
              {t("kpis.title")}
            </Typography>
          </Box>
          <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
            <Box flex="1 1 520px" minWidth={320} display="flex" justifyContent="flex-start">
              <DateRangeControl {...dateRangeProps} showQuickRanges={false} />
            </Box>
            <Box flex="1 1 220px" display="flex" justifyContent="center">
              <FormControl
                size="small"
                sx={{
                  minWidth: 220,
                  "& .MuiOutlinedInput-root": { height: UI.controlHeight },
                  "& .MuiSelect-select": {
                    fontSize: UI.buttonFontSize,
                    paddingTop: 0,
                    paddingBottom: 0,
                    display: "flex",
                    alignItems: "center",
                  },
                }}
              >
                <InputLabel id="kpi-agent-filter-label" sx={{ fontSize: UI.buttonFontSize }}>
                  Agent
                </InputLabel>
                <Select
                  labelId="kpi-agent-filter-label"
                  label="Agent"
                  value={agentFilter}
                  onChange={(event) => setAgentFilter(event.target.value)}
                >
                  <MenuItem value="">All agents</MenuItem>
                  {agentOptions.map((agentId) => (
                    <MenuItem key={agentId} value={agentId}>
                      {agentId}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
            <Box flex="1 1 240px" display="flex" justifyContent="flex-end">
              {isAdmin && (
                <FormControlLabel
                  control={
                    <Switch
                      checked={viewGlobal}
                      onChange={(e) => setViewGlobal(e.target.checked)}
                      name="viewGlobalToggle"
                      size="small"
                    />
                  }
                  label={<Typography sx={{ fontSize: UI.buttonFontSize }}>View Global KPIs</Typography>}
                  sx={{ ".MuiFormControlLabel-label": { fontSize: UI.buttonFontSize } }}
                />
              )}
            </Box>
          </Box>
        </Box>
      </DashboardCard>

      {/* Compact grid; frameless tiles (Boxes) to avoid Paper-in-Paper */}
      <Grid2 container spacing={1}>
        <Grid2 size={{ xs: 12, md: 12, lg: 12 }}>
          <Box
            sx={{
              p: UI.compactPadding,
              borderRadius: 2,
              border: (theme) => `1px solid ${theme.palette.divider}`,
              bgcolor: (theme) => theme.palette.background.default,
              display: "flex",
              flexDirection: "column",
              gap: UI.compactRowGap,
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Box sx={{ minWidth: UI.compactLabelMinWidth }} />
              <Box sx={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: UI.compactHeaderGap }}>
                <Typography
                  variant="caption"
                  sx={{
                    textAlign: "center",
                    fontWeight: 600,
                    color: "text.secondary",
                    fontSize: UI.compactLabelFontSize,
                  }}
                >
                  Agentic
                </Typography>
                <Typography
                  variant="caption"
                  sx={{
                    textAlign: "center",
                    fontWeight: 600,
                    color: "text.secondary",
                    fontSize: UI.compactLabelFontSize,
                  }}
                >
                  Knowledge Flow
                </Typography>
              </Box>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography
                variant="caption"
                sx={{
                  minWidth: UI.compactLabelMinWidth,
                  fontWeight: 600,
                  color: "text.secondary",
                  fontSize: UI.compactLabelFontSize,
                }}
              >
                CPU %
              </Typography>
              <Box sx={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: UI.compactColumnGap }}>
                <KpiHeatStripMini
                  label=""
                  labelMinWidth={0}
                  rows={cpuHistoryRowsAgentic}
                  metricKey="max_pct"
                  height={UI.heatStripHeight}
                  start={alignedStart}
                  end={alignedEnd}
                  precision={precision}
                  xDomain={xDomain}
                  frame={false}
                  dense={true}
                />
                <KpiHeatStripMini
                  label=""
                  labelMinWidth={0}
                  rows={cpuHistoryRowsKf}
                  metricKey="max_pct"
                  height={UI.heatStripHeight}
                  start={alignedStart}
                  end={alignedEnd}
                  precision={precision}
                  xDomain={xDomain}
                  frame={false}
                  dense={true}
                />
              </Box>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography
                variant="caption"
                sx={{
                  minWidth: UI.compactLabelMinWidth,
                  fontWeight: 600,
                  color: "text.secondary",
                  fontSize: UI.compactLabelFontSize,
                }}
              >
                Memory %
              </Typography>
              <Box sx={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: UI.compactColumnGap }}>
                <KpiHeatStripMini
                  label=""
                  labelMinWidth={0}
                  rows={memHistoryRowsAgentic}
                  metricKey="max_pct"
                  height={UI.heatStripHeight}
                  start={alignedStart}
                  end={alignedEnd}
                  precision={precision}
                  xDomain={xDomain}
                  frame={false}
                  dense={true}
                />
                <KpiHeatStripMini
                  label=""
                  labelMinWidth={0}
                  rows={memHistoryRowsKf}
                  metricKey="max_pct"
                  height={UI.heatStripHeight}
                  start={alignedStart}
                  end={alignedEnd}
                  precision={precision}
                  xDomain={xDomain}
                  frame={false}
                  dense={true}
                />
              </Box>
            </Box>
          </Box>
        </Grid2>

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
              height={UI.tileChartHeight}
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
              height={UI.tileChartHeight}
              showLegend={false}
              rows={latencyRows}
            />
          </FramelessTile>
        </Grid2>
        <Grid2 size={{ xs: 12, md: 6, lg: 6 }}>
          <FramelessTile
            title="Exchanges by status"
            subtitle="Range totals in the selected window"
            help="Sums of chat.exchange_total per dims.status (ok, error, timeout, filtered, cancelled). Filtered = blocked by policy/guardrails; cancelled = client aborted."
          >
            <KpiStatusMini rows={statusRows} height={UI.tileChartHeight} showLegend={false} />
          </FramelessTile>
        </Grid2>

        <Grid2 size={{ xs: 12, md: 6, lg: 6 }}>
          <FramelessTile
            title="Agent step latency (avg ms)"
            subtitle="Average latency per agent step over the selected range"
            help="agent.step_latency_ms grouped by dims.agent_step. Values include keyword expansion, vector search, and LLM generation steps."
          >
            <KpiGroupedBarMini
              rows={stepLatencyRows}
              height={UI.tileChartHeight}
              metricKey="avg_ms"
              metricLabel="avg ms"
              groupKey="dims.agent_step"
            />
          </FramelessTile>
        </Grid2>
        <Grid2 size={{ xs: 12, md: 6, lg: 6 }}>
          <FramelessTile
            title="Tool latency (avg ms)"
            subtitle="Average MCP/tool call latency over the selected range"
            help="agent.tool_latency_ms grouped by dims.tool. Each bar represents a wrapped tool invocation."
          >
            <KpiGroupedBarMini
              rows={toolLatencyRows}
              height={UI.tileChartHeight}
              metricKey="avg_ms"
              metricLabel="avg ms"
              groupKey="dims.tool_name"
            />
          </FramelessTile>
        </Grid2>
      </Grid2>
    </Box>
  );
}
