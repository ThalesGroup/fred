// Copyright Thales 2025
// Apache-2.0

import { Box, Typography } from "@mui/material";
import dayjs, { Dayjs } from "dayjs";
import "dayjs/locale/fr";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import LoadingWithProgress from "../LoadingWithProgress";
import DashboardCard from "./DashboardCard";
import DateRangeControls from "./DateRangeControl";
import { TokenUsageChart } from "./TokenUsageChart";
import {
  useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery,
} from "../../slices/agentic/agenticOpenApi";
import { alignDateRangeToPrecision } from "./alignDateRangeToPrecision";
import { getPrecisionForRange } from "./metricChartUtils";

export default function MetricsDashboard() {
  const [triggerNodeFetch, { data: nodeMetrics, isLoading: isNodeLoading, isError: isNodeError }] =
    useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery();

  const { t } = useTranslation();

  // Range state
  const now = dayjs();
  const [startDate, setStartDate] = useState<Dayjs>(now.subtract(12, "hours"));
  const [endDate, setEndDate] = useState<Dayjs>(now);

  // Shared precision + aligned range + shared xDomain
  const precision = useMemo(() => getPrecisionForRange(startDate.toDate(), endDate.toDate()), [startDate, endDate]);
  const [alignedStart, alignedEnd] = useMemo(
    () => alignDateRangeToPrecision(startDate, endDate, precision as "sec" | "min" | "hour" | "day"),
    [startDate, endDate, precision]
  );
  const xDomain: [number, number] = useMemo(
    () => [new Date(alignedStart).getTime(), new Date(alignedEnd).getTime()],
    [alignedStart, alignedEnd]
  );

  // Fetch when aligned range changes
  useEffect(() => {
    triggerNodeFetch({ start: alignedStart, end: alignedEnd, precision, agg: ["total_tokens:sum"], groupby: [] });
    // triggerAppFetch({
    //   start: alignedStart,
    //   end: alignedEnd,
    //   precision,
    //   agg: ["store_size_bytes:sum", "docs_count:sum"],
    //   groupby: ["category"],
    // });
  }, [alignedStart, alignedEnd, precision, triggerNodeFetch]);

  // Errors / loading
  if (isNodeError) {
    return (
      <Box p={2}>
        <Typography variant="body1" color="error">❌ {t("metrics.loadError", "Failed to load metrics")}</Typography>
      </Box>
    );
  }
  if (isNodeLoading || !nodeMetrics) return <LoadingWithProgress />;

  return (
    <Box display="flex" flexDirection="column" gap={2} p={2}>
      {/* Filters */}
      <DashboardCard>
        <DateRangeControls
          startDate={startDate}
          endDate={endDate}
          setStartDate={setStartDate}
          setEndDate={setEndDate}
        />
      </DashboardCard>

      {/* Tokens (clamped and aligned to xDomain) */}
      <DashboardCard title={t("metrics.tokenUsage")}>
        <Box sx={{ width: "100%", height: 180, position: "relative", overflow: "hidden" }}>
          <TokenUsageChart
            start={new Date(xDomain[0])}
            end={new Date(xDomain[1])}
            precision={precision}
            metrics={nodeMetrics}
            height={180}
            xDomain={xDomain}
          />
        </Box>
      </DashboardCard>

      {/* App metrics in a thin row */}
      {/* <Box display="grid" gridTemplateColumns={{ xs: "1fr", md: "1fr 1fr" }} gap={2}>
        <DashboardCard title={t("metrics.app.storeSizeByCategory", "Store size by category")}>
          <AppCategoryArea
            metrics={appMetrics}
            valueKey="store_size_bytes_sum"
            height={220}
            xDomain={xDomain}
            tsFmt={tsFmt}
            yTickFormatter={formatBytes}
          />
        </DashboardCard>

        <DashboardCard title={t("metrics.app.docsByCategory", "Documents by category")}>
          <AppCategoryArea
            metrics={appMetrics}
            valueKey="docs_count_sum"
            height={220}
            xDomain={xDomain}
            tsFmt={tsFmt}
          />
        </DashboardCard>
      </Box> */}
    </Box>
  );
}
