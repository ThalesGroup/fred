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

import { Box, IconButton, LinearProgress, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import React from "react";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { useTranslation } from "react-i18next";

import RefreshIcon from "@mui/icons-material/Refresh";
import { ProcessDocumentsProgressResponse } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

interface DocumentOperationsStatusProps {
  progress: ProcessDocumentsProgressResponse | null;
  onRefresh: () => void;
}

export const DocumentOperationsStatus: React.FC<DocumentOperationsStatusProps> = ({ progress, onRefresh }) => {
  const { t } = useTranslation();
  const theme = useTheme();

  const totalInProgress = progress?.total_documents ?? 0;
  const doneCount = progress?.documents_fully_processed ?? 0;
  const failedCount = progress?.documents_failed ?? 0;
  const withPreviewCount = progress?.documents_with_preview ?? 0;
  const vectorizedCount = progress?.documents_vectorized ?? 0;
  const sqlIndexedCount = progress?.documents_sql_indexed ?? 0;
  const percentComplete = totalInProgress > 0 ? Math.round((doneCount / totalInProgress) * 100) : 0;
  const hasProgress = totalInProgress > 0;

  const remaining = Math.max(totalInProgress - doneCount - failedCount, 0);

  const chartData =
    hasProgress
      ? [
          { key: "done", label: t("scheduler.processingStatusDoneLabel"), value: doneCount },
          { key: "failed", label: t("scheduler.processingStatusFailedOnlyLabel"), value: failedCount },
          { key: "remaining", label: t("scheduler.processingStatusRemainingLabel"), value: remaining },
        ]
      : [];

  const chartDataForChart =
    chartData.length > 0
      ? chartData
      : [
          {
            key: "empty",
            label: "",
            value: 1,
          },
        ];

  const colors: Record<string, string> = {
    done: theme.palette.success.main,
    failed: theme.palette.error.main,
    remaining: theme.palette.info.main,
    empty: theme.palette.grey[300],
  };

  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        border: (theme) => `1px solid ${theme.palette.divider}`,
        bgcolor: "background.default",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 2,
        minHeight: 130,
        position: "relative",
      }}
    >
      <Box sx={{ position: "absolute", top: 4, right: 4 }}>
        <Tooltip title={t("scheduler.refreshProgress")}>
          <IconButton size="small" onClick={onRefresh}>
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
      <Box flex={1} minWidth={0}>
        <Typography variant="subtitle2">{t("scheduler.processingStatusTitle")}</Typography>
        <Typography variant="caption" color="text.secondary">
          {hasProgress
            ? t("scheduler.processingStatusSummary", {
                done: doneCount,
                total: totalInProgress,
                failed: failedCount,
              }) || `Processed ${doneCount}/${totalInProgress}${failedCount > 0 ? ` (failed: ${failedCount})` : ""}`
            : t("scheduler.processingStatusIdle")}
        </Typography>
        <Box mt={1}>
          <LinearProgress
            variant="determinate"
            value={hasProgress ? percentComplete : 0}
            sx={{ height: 6, borderRadius: 3 }}
          />
        </Box>
        <Box mt={1} display="flex" flexWrap="wrap" gap={1}>
          <Typography variant="caption">
            {t("scheduler.processingStatusPreview", { count: withPreviewCount }) ||
              `Preview ready: ${withPreviewCount}`}
          </Typography>
          <Typography variant="caption">
            • {t("scheduler.processingStatusVector", { count: vectorizedCount })}
          </Typography>
          <Typography variant="caption">• {t("scheduler.processingStatusSql", { count: sqlIndexedCount })}</Typography>
          {hasProgress && (
            <Box display="flex" flexWrap="wrap" gap={1} ml={0.5}>
              {chartData.map((entry) => (
                <Box key={entry.key} display="flex" alignItems="center" gap={0.5}>
                  <Box
                    sx={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      bgcolor: colors[entry.key] || theme.palette.grey[300],
                    }}
                  />
                  <Typography variant="caption">{entry.label}</Typography>
                </Box>
              ))}
            </Box>
          )}
        </Box>
      </Box>
      <Box display="flex" flexDirection="column" alignItems="flex-end" gap={1} flexShrink={0}>
        <Box width={120} height={80}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={chartDataForChart} dataKey="value" nameKey="key" innerRadius={22} outerRadius={34} paddingAngle={1}>
                {chartDataForChart.map((entry) => (
                  <Cell key={entry.key} fill={colors[entry.key] || theme.palette.grey[300]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </Box>
      </Box>
    </Box>
  );
};
