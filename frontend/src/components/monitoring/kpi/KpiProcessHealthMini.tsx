// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { Box, Typography } from "@mui/material";
import { alpha, useTheme } from "@mui/material/styles";

type HealthMetric = {
  label: string;
  avg?: number | null;
  max?: number | null;
};

type KpiProcessHealthMiniProps = {
  cpu: HealthMetric;
  memory: HealthMetric;
  height?: number;
};

const formatPct = (value?: number | null) => (value == null || Number.isNaN(value) ? "n/a" : `${value.toFixed(1)}%`);

const getLevel = (value?: number | null) => {
  if (value == null || Number.isNaN(value)) return "neutral";
  if (value >= 90) return "error";
  if (value >= 80) return "warning";
  if (value >= 60) return "info";
  return "success";
};

const HealthCard = ({ label, avg, max }: HealthMetric) => {
  const theme = useTheme();
  const primary = max ?? avg ?? null;
  const level = getLevel(primary);
  const palette = theme.palette;
  const color =
    level === "error"
      ? palette.error.main
      : level === "warning"
        ? palette.warning.main
        : level === "info"
          ? palette.info.main
          : level === "success"
            ? palette.success.main
            : palette.text.secondary;

  return (
    <Box
      sx={{
        borderRadius: 2,
        border: `1px solid ${alpha(color, 0.35)}`,
        bgcolor: alpha(color, 0.12),
        px: 1.5,
        py: 1,
        minHeight: 76,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: 0.25,
      }}
    >
      <Typography variant="caption" sx={{ color: theme.palette.text.secondary, textTransform: "uppercase" }}>
        {label}
      </Typography>
      <Typography variant="h6" sx={{ color, fontWeight: 700, lineHeight: 1.1 }}>
        {formatPct(primary)}
      </Typography>
      <Typography variant="caption" sx={{ color: theme.palette.text.secondary }}>
        avg {formatPct(avg)} · max {formatPct(max)}
      </Typography>
    </Box>
  );
};

export const KpiProcessHealthMini = ({ cpu, memory, height = 150 }: KpiProcessHealthMiniProps) => {
  const theme = useTheme();
  const hasData = cpu.avg != null || cpu.max != null || memory.avg != null || memory.max != null;

  if (!hasData) {
    return (
      <Box sx={{ p: 1, fontSize: 12, color: theme.palette.text.secondary, height }}>
        No data in the selected range.
      </Box>
    );
  }

  return (
    <Box sx={{ width: "100%", height, display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 1 }}>
      <HealthCard {...cpu} />
      <HealthCard {...memory} />
    </Box>
  );
};
