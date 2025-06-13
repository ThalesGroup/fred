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

import { Box, Typography } from "@mui/material";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { DateTimePicker } from "@mui/x-date-pickers/DateTimePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import dayjs, { Dayjs } from "dayjs";
import { useEffect, useState } from "react";
import { PageBodyWrapper } from "../../common/PageBodyWrapper";
import { Aggregation, Precision, useFetchNumericalMetricsMutation } from "../../slices/monitoringApi";
import LoadingWithProgress from "../LoadingWithProgress";
import DashboardCard from "./DashboardCard";
import { TokenUsageChart } from "./TokenUsageChart";

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

function getRangeLabel(startDate: Dayjs, endDate: Dayjs): string {
  const diffMs = endDate.diff(startDate);
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays >= 1) {
    return `viewing data from last ${diffDays} day${diffDays > 1 ? "s" : ""}`;
  }
  if (diffHours >= 1) {
    return `viewing data from last ${diffHours} hour${diffHours > 1 ? "s" : ""}`;
  }
  if (diffMinutes >= 1) {
    return `viewing data from last ${diffMinutes} minute${diffMinutes > 1 ? "s" : ""}`;
  }
  return "viewing data from less than last a minute";
}

export default function MetricsDashboard() {
  const [fetchNumericalMetrics, { data: numericalSum, isLoading, isError }] = useFetchNumericalMetricsMutation();

  const now = dayjs();
  const [startDate, setStartDate] = useState<Dayjs>(now.subtract(3, "hours"));
  const [endDate, setEndDate] = useState<Dayjs>(now);

  // Fetch metrics when startDate or endDate changes
  useEffect(() => {
    fetchNumericalSumAggregation(startDate, endDate);
  }, [startDate, endDate]);

  function fetchNumericalSumAggregation(start: Dayjs, end: Dayjs) {
    const param = {
      start: start.toISOString(),
      end: end.toISOString(),
      precision: getPrecisionForRange(start, end),
      agg: "sum" as Aggregation,
    };

    console.log("Fetching numerical metrics", param);
    fetchNumericalMetrics(param);
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

  if (isLoading || !numericalSum) {
    return (
      <PageBodyWrapper>
        <LoadingWithProgress />
      </PageBodyWrapper>
    );
  }

  return (
    <Box display="flex" flexDirection="column" gap={4} p={4}>
      {/* Filters */}
      <DashboardCard>
        <Box display="flex" gap={2} alignItems="center">
          <LocalizationProvider dateAdapter={AdapterDayjs}>
            <DateTimePicker
              label="From"
              value={startDate}
              onChange={(newValue) => setStartDate(newValue)}
              slotProps={{ textField: { size: "small", sx: { minWidth: 180 } } }}
              maxDateTime={endDate}
            />
            <DateTimePicker
              label="To"
              value={endDate}
              onChange={(newValue) => setEndDate(newValue)}
              slotProps={{ textField: { size: "small", sx: { minWidth: 180 } } }}
              minDateTime={startDate}
              maxDate={dayjs()}
            />
            <Typography variant="body2" color="text.secondary" sx={{ ml: 2, fontStyle: "italic" }}>
              {getRangeLabel(startDate, endDate)}
            </Typography>
          </LocalizationProvider>
        </Box>
      </DashboardCard>

      {/* Charts */}
      <DashboardCard title="Token usage over time">
        <TokenUsageChart
          start={startDate.toDate()}
          end={endDate.toDate()}
          precision={getPrecisionForRange(startDate, endDate)}
          metrics={numericalSum}
        />
      </DashboardCard>
    </Box>
  );
}
