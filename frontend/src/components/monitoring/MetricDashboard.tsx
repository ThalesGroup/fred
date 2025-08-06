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

import { Box, Button, ButtonGroup, Typography } from "@mui/material";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { DateTimePicker } from "@mui/x-date-pickers/DateTimePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import dayjs, { Dayjs } from "dayjs";
import "dayjs/locale/fr";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Precision } from "../../slices/monitoringApi";
import LoadingWithProgress from "../LoadingWithProgress";
import DashboardCard from "./DashboardCard";
import { TokenUsageChart } from "./TokenUsageChart";
import { useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery } from "../../slices/agentic/agenticOpenApi";
import { alignDateRangeToPrecision } from "./alignDateRangeToPrecision";

type QuickRangeType =
  | "today"
  | "yesterday"
  | "thisWeek"
  | "thisMonth"
  | "thisYear"
  | "last12h"
  | "last24h"
  | "last7d"
  | "last30d";

function getPrecisionForRange(start: Dayjs, end: Dayjs): Precision {
  const diffMs = end.valueOf() - start.valueOf();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  const diffHours = diffMs / (1000 * 60 * 60);

  // less than 10 minutes -> use second precision
  if (diffMs <= 10000) {
    return "sec";
  }

  // 10 minutes to 10 hours -> use minute precision
  if (diffHours < 10) {
    return "min";
  }

  // 10 hours to 3 days -> use hour precision
  if (diffDays <= 3) {
    return "hour";
  }

  // more than 3 days -> use day precision
  return "day";
}

export default function MetricsDashboard() {
  const [triggerMetricsFetch, { data: metrics, isLoading, isError }] =
    useLazyGetNodeNumericalMetricsAgenticV1MetricsChatbotNumericalGetQuery();
  const { t } = useTranslation();

  const now = dayjs();
  const [startDate, setStartDate] = useState<Dayjs>(now.subtract(12, "hours"));
  const [endDate, setEndDate] = useState<Dayjs>(now);
  // Fetch metrics when startDate or endDate changes
  useEffect(() => {
    fetchNumericalSumAggregation(startDate, endDate);
  }, [startDate, endDate]);

  function fetchNumericalSumAggregation(start: Dayjs, end: Dayjs) {
    const precision = getPrecisionForRange(start, end);
    const [alignedStart, alignedEnd] = alignDateRangeToPrecision(start, end, precision);

    triggerMetricsFetch({
      start: alignedStart,
      end: alignedEnd,
      precision,
      agg: ["total_tokens:sum"],
      groupby: [],
    });
  }
  // Helper to check if a quick range is selected
  function isRangeSelected(type: QuickRangeType): boolean {
    const today = dayjs();
    const graceMs = 5 * 60 * 1000; // 5 minutes in ms

    switch (type) {
      case "today":
        return startDate.isSame(today.startOf("day")) && endDate.isSame(today.endOf("day"));
      case "yesterday":
        return (
          startDate.isSame(today.subtract(1, "day").startOf("day")) &&
          endDate.isSame(today.subtract(1, "day").endOf("day"))
        );
      case "thisWeek":
        return startDate.isSame(today.startOf("week")) && endDate.isSame(today.endOf("week"));
      case "thisMonth":
        return startDate.isSame(today.startOf("month")) && endDate.isSame(today.endOf("month"));
      case "thisYear":
        return startDate.isSame(today.startOf("year")) && endDate.isSame(today.endOf("year"));
      case "last12h": {
        const expectedStart = today.subtract(12, "hour");
        const expectedEnd = today;
        return Math.abs(startDate.diff(expectedStart)) < graceMs && Math.abs(endDate.diff(expectedEnd)) < graceMs;
      }
      case "last24h": {
        const expectedStart = today.subtract(24, "hour");
        const expectedEnd = today;
        return Math.abs(startDate.diff(expectedStart)) < graceMs && Math.abs(endDate.diff(expectedEnd)) < graceMs;
      }
      case "last7d": {
        const expectedStart = today.subtract(7, "day");
        const expectedEnd = today;
        return Math.abs(startDate.diff(expectedStart)) < graceMs && Math.abs(endDate.diff(expectedEnd)) < graceMs;
      }
      case "last30d": {
        const expectedStart = today.subtract(30, "day");
        const expectedEnd = today;
        return Math.abs(startDate.diff(expectedStart)) < graceMs && Math.abs(endDate.diff(expectedEnd)) < graceMs;
      }
      default:
        return false;
    }
  }

  function setSelectedRange(type: QuickRangeType) {
    const now = dayjs();
    const ranges: Record<QuickRangeType, [Dayjs, Dayjs]> = {
      today: [now.startOf("day"), now.endOf("day")],
      yesterday: [now.subtract(1, "day").startOf("day"), now.subtract(1, "day").endOf("day")],
      thisWeek: [now.startOf("week"), now.endOf("week")],
      thisMonth: [now.startOf("month"), now.endOf("month")],
      thisYear: [now.startOf("year"), now.endOf("year")],
      last24h: [now.subtract(24, "hour").startOf("hour"), now.endOf("hour")],
      last12h: [now.subtract(12, "hour").startOf("hour"), now.endOf("hour")],
      last7d: [now.subtract(7, "day").startOf("day"), now.endOf("day")],
      last30d: [now.subtract(30, "day").startOf("day"), now.endOf("day")],
    };

    const [start, end] = ranges[type];
    setStartDate(start);
    setEndDate(end);
  }

  if (isError) {
    return (
      <Box p={4}>
        <Typography variant="h6" color="error">
          ❌ Failed to load metrics
        </Typography>
      </Box>
    );
  }

  if (isLoading || !metrics) {
    return <LoadingWithProgress />;
  }

  return (
    <Box display="flex" flexDirection="column" gap={4} p={4}>
      {/* Filters */}
      <DashboardCard>
        <Box display="flex" flexDirection="column" gap={2}>
          <ButtonGroup variant="outlined" size="small" sx={{ mb: 1, flexWrap: "wrap" }}>
            <Button
              onClick={() => setSelectedRange("today")}
              variant={isRangeSelected("today") ? "contained" : "outlined"}
            >
              {t("metrics.range.today")}
            </Button>
            <Button
              onClick={() => setSelectedRange("yesterday")}
              variant={isRangeSelected("yesterday") ? "contained" : "outlined"}
            >
              {t("metrics.range.yesterday")}
            </Button>
            <Button
              onClick={() => setSelectedRange("thisWeek")}
              variant={isRangeSelected("thisWeek") ? "contained" : "outlined"}
            >
              {t("metrics.range.thisWeek")}
            </Button>
            <Button
              onClick={() => setSelectedRange("thisMonth")}
              variant={isRangeSelected("thisMonth") ? "contained" : "outlined"}
            >
              {t("metrics.range.thisMonth")}
            </Button>
            <Button
              onClick={() => setSelectedRange("thisYear")}
              variant={isRangeSelected("thisYear") ? "contained" : "outlined"}
            >
              {t("metrics.range.thisYear")}
            </Button>
            <Button
              onClick={() => setSelectedRange("last12h")}
              variant={isRangeSelected("last12h") ? "contained" : "outlined"}
            >
              {t("metrics.range.last12h")}
            </Button>
            <Button
              onClick={() => setSelectedRange("last24h")}
              variant={isRangeSelected("last24h") ? "contained" : "outlined"}
            >
              {t("metrics.range.last24h")}
            </Button>
            <Button
              onClick={() => setSelectedRange("last7d")}
              variant={isRangeSelected("last7d") ? "contained" : "outlined"}
            >
              {t("metrics.range.last7d")}
            </Button>
            <Button
              onClick={() => setSelectedRange("last30d")}
              variant={isRangeSelected("last30d") ? "contained" : "outlined"}
            >
              {t("metrics.range.last30d")}
            </Button>
          </ButtonGroup>
          <Box display="flex" gap={2} alignItems="center">
            <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="fr">
              <DateTimePicker
                label={t("metrics.from")}
                value={startDate}
                onChange={(newValue) => setStartDate(newValue)}
                slotProps={{ textField: { size: "small", sx: { minWidth: 180 } } }}
                maxDateTime={endDate}
              />
              <DateTimePicker
                label={t("metrics.to")}
                value={endDate}
                onChange={(newValue) => setEndDate(newValue)}
                slotProps={{ textField: { size: "small", sx: { minWidth: 180 } } }}
                minDateTime={startDate}
              />
            </LocalizationProvider>
          </Box>
        </Box>
      </DashboardCard>

      {/* Charts */}
      <DashboardCard title={t("metrics.tokenUsage")}>
        <TokenUsageChart
          start={startDate.toDate()}
          end={endDate.toDate()}
          precision={getPrecisionForRange(startDate, endDate)}
          metrics={metrics}
        />
      </DashboardCard>
    </Box>
  );
}
