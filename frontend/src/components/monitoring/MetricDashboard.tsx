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

import { Box, Grid2, Typography } from "@mui/material";
import { useEffect } from "react";
import { subMinutes } from "date-fns";
import { useFetchNumericalMetricsMutation } from "../../slices/monitoringApi";
import MetricChart from "./MetricChart";
import { PageBodyWrapper } from "../../common/PageBodyWrapper";
import LoadingWithProgress from "../LoadingWithProgress";

export default function MetricsDashboard() {
  const [fetchNumericalMetrics, { data: numericalMetrics, isLoading, isError }] =
    useFetchNumericalMetricsMutation();

  useEffect(() => {
    const start = subMinutes(new Date(), 60).toISOString();
    const end = new Date().toISOString();
    fetchNumericalMetrics({ start, end, precision: "minute", agg: "max" });
  }, []);

  if (isError) {
    return (
      <Box p={4}>
        <Typography variant="h6" color="error">❌ Failed to load metrics</Typography>
      </Box>
    );
  }

  if (isLoading || !numericalMetrics) {
      return (
        <PageBodyWrapper>
          <LoadingWithProgress />
        </PageBodyWrapper>
      );
    }
  return (
    <Box p={2}>
      <Grid2 container spacing={3} justifyContent="center">
        <Grid2 size={{ xs: 8 }}>
           <MetricChart metrics={numericalMetrics} />
        </Grid2>
      </Grid2>
    </Box>
  );
}
