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
import { useEffect, useState } from "react";
import { Aggregation, Precision, useFetchNumericalMetricsMutation } from "../../slices/monitoringApi";
import LoadingWithProgress from "../LoadingWithProgress";
import DashboardCard from "./DashboardCard";
import { TokenUsageChart } from "./TokenUsageChart";
import "dayjs/locale/fr";

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
  const [fetchNumericalMetrics, { data: numericalSum, isLoading, isError }] = useFetchNumericalMetricsMutation();

  const now = dayjs();
  const [startDate, setStartDate] = useState<Dayjs>(now.subtract(12, "hours"));
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
    const today = dayjs();
    switch (type) {
      case "today":
        setStartDate(today.startOf("day"));
        setEndDate(today.endOf("day"));
        break;
      case "yesterday":
        setStartDate(today.subtract(1, "day").startOf("day"));
        setEndDate(today.subtract(1, "day").endOf("day"));
        break;
      case "thisWeek":
        setStartDate(today.startOf("week"));
        setEndDate(today.endOf("week"));
        break;
      case "thisMonth":
        setStartDate(today.startOf("month"));
        setEndDate(today.endOf("month"));
        break;
      case "thisYear":
        setStartDate(today.startOf("year"));
        setEndDate(today.endOf("year"));
        break;
      case "last12h":
        setStartDate(today.subtract(12, "hour"));
        setEndDate(today);
        break;
      case "last24h":
        setStartDate(today.subtract(24, "hour"));
        setEndDate(today);
        break;
      case "last7d":
        setStartDate(today.subtract(7, "day"));
        setEndDate(today);
        break;
      case "last30d":
        setStartDate(today.subtract(30, "day"));
        setEndDate(today);
        break;
      default:
        break;
    }
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
              Today
            </Button>
            <Button
              onClick={() => setSelectedRange("yesterday")}
              variant={isRangeSelected("yesterday") ? "contained" : "outlined"}
            >
              Yesterday
            </Button>
            <Button
              onClick={() => setSelectedRange("thisWeek")}
              variant={isRangeSelected("thisWeek") ? "contained" : "outlined"}
            >
              This week
            </Button>
            <Button
              onClick={() => setSelectedRange("thisMonth")}
              variant={isRangeSelected("thisMonth") ? "contained" : "outlined"}
            >
              This month
            </Button>
            <Button
              onClick={() => setSelectedRange("thisYear")}
              variant={isRangeSelected("thisYear") ? "contained" : "outlined"}
            >
              This year
            </Button>
            <Button
              onClick={() => setSelectedRange("last12h")}
              variant={isRangeSelected("last12h") ? "contained" : "outlined"}
            >
              Last 12 hours
            </Button>
            <Button
              onClick={() => setSelectedRange("last24h")}
              variant={isRangeSelected("last24h") ? "contained" : "outlined"}
            >
              Last 24 hours
            </Button>
            <Button
              onClick={() => setSelectedRange("last7d")}
              variant={isRangeSelected("last7d") ? "contained" : "outlined"}
            >
              Last 7 days
            </Button>
            <Button
              onClick={() => setSelectedRange("last30d")}
              variant={isRangeSelected("last30d") ? "contained" : "outlined"}
            >
              Last 30 days
            </Button>
          </ButtonGroup>
          <Box display="flex" gap={2} alignItems="center">
            <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="fr">
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
              />
            </LocalizationProvider>
          </Box>
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
