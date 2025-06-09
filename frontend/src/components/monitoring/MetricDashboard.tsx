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

import { Box, Grid2 } from "@mui/material";
import { useEffect, useState } from "react";
import { LLMMetric } from "./metricsType";
import MetricChart from "./MetricChart";
import MetricTable from "./MetricTable";

// Mock fallback
function getMockMetrics(): LLMMetric[] {
  const now = Date.now() / 1000;
  return Array.from({ length: 20 }, (_, i) => {
    const timestamp = now - i * 60;
    return {
      timestamp,
      latency: +(Math.random() * 6).toFixed(2),
      model_type: "gpt-4o",
      user_id: i % 2 === 0 ? "admin@mail.com" : "user@example.com",
      session_id: `sess-${i}`,
      token_usage: {
        prompt_tokens: 1000 + Math.floor(Math.random() * 300),
        completion_tokens: 200 + Math.floor(Math.random() * 100),
        total_tokens: 0,
        prompt_tokens_details: { cached_tokens: 0 },
        completion_tokens_details: { accepted_prediction_tokens: 0 },
      },
    };
  }).map(m => ({
    ...m,
    token_usage: {
      ...m.token_usage,
      total_tokens: m.token_usage.prompt_tokens + m.token_usage.completion_tokens,
    },
  }));
}

export default function MetricsDashboard() {
  const [metrics, setMetrics] = useState<LLMMetric[]>([]);

  const fetchMetrics = async () => {
    const data = await new Promise<LLMMetric[]>(resolve =>
      setTimeout(() => resolve(getMockMetrics()), 500)
    );
    setMetrics(data);
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Box p={2}>
      <Grid2 container spacing={3}>
        <Grid2 size={{xs:12}}>
          <MetricChart metrics={metrics} />
        </Grid2>
        <Grid2 size={{xs:12}}>
          <MetricTable metrics={metrics} />
        </Grid2>
        {/* Additional components can be added below */}
      </Grid2>
    </Box>
  );
}
