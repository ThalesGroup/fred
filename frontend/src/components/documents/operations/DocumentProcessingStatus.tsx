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

import { Box, IconButton, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import React from "react";
import { Pie, PieChart, Cell, ResponsiveContainer } from "recharts";
import { useTranslation } from "react-i18next";

import RefreshIcon from "@mui/icons-material/Refresh";
import { useGetProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGetQuery } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

interface DocumentProcessingStatusProps {
  pollIntervalMs?: number;
}

export const DocumentProcessingStatus: React.FC<DocumentProcessingStatusProps> = ({ pollIntervalMs = 10000 }) => {
  const { t } = useTranslation();
  const theme = useTheme();

  const { data, isLoading, isError, refetch } = useGetProcessingSummaryKnowledgeFlowV1DocumentsProcessingSummaryGetQuery(
    undefined,
    {
      pollInterval: pollIntervalMs,
    },
  );

  const totalDocuments = data?.total_documents ?? 0;
  const fullyProcessed = data?.fully_processed ?? 0;
  const inProgress = data?.in_progress ?? 0;
  const failed = data?.failed ?? 0;
  const notStarted = data?.not_started ?? 0;

  const hasDocuments = totalDocuments > 0;
  if (isError) return null;

  const chartData =
    hasDocuments && (fullyProcessed || inProgress || failed || notStarted)
      ? [
          { key: "processed", label: t("scheduler.globalStatusProcessedLabelShort"), value: fullyProcessed },
          { key: "in_progress", label: t("scheduler.globalStatusInProgressLabelShort"), value: inProgress },
          { key: "failed", label: t("scheduler.globalStatusFailedLabelShort"), value: failed },
          { key: "not_started", label: t("scheduler.globalStatusNotStartedLabelShort"), value: notStarted },
        ]
      : [];

  const colors: Record<string, string> = {
    processed: theme.palette.success.main,
    in_progress: theme.palette.info.main,
    failed: theme.palette.error.main,
    not_started: theme.palette.grey[400],
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
          <IconButton size="small" onClick={() => refetch()}>
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
      <Box flex={1} minWidth={0}>
        <Typography variant="subtitle2">{t("scheduler.globalStatusTitle")}</Typography>
        <Typography variant="caption" color="text.secondary">
          {isLoading && !data
            ? t("scheduler.globalStatusLoading")
            : hasDocuments
              ? t("scheduler.globalStatusSummary", {
                  total: totalDocuments,
                  processed: fullyProcessed,
                  in_progress: inProgress,
                  failed,
                  not_started: notStarted,
                })
              : t("scheduler.globalStatusEmpty")}
        </Typography>
        {hasDocuments && (
          <Box mt={1} display="flex" flexWrap="wrap" gap={2}>
            <Box display="flex" alignItems="center" gap={0.5}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: colors.processed,
                }}
              />
              <Typography variant="caption">{t("scheduler.globalStatusProcessedLabelShort")}</Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={0.5}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: colors.in_progress,
                }}
              />
              <Typography variant="caption">{t("scheduler.globalStatusInProgressLabelShort")}</Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={0.5}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: colors.failed,
                }}
              />
              <Typography variant="caption">{t("scheduler.globalStatusFailedLabelShort")}</Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={0.5}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  bgcolor: colors.not_started,
                }}
              />
              <Typography variant="caption">{t("scheduler.globalStatusNotStartedLabelShort")}</Typography>
            </Box>
          </Box>
        )}
      </Box>
      <Box width={120} height={80} flexShrink={0}>
        {chartData.length > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="key"
                innerRadius={24}
                outerRadius={36}
                paddingAngle={1}
              >
                {chartData.map((entry) => (
                  <Cell key={entry.key} fill={colors[entry.key] || theme.palette.grey[300]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        )}
      </Box>
    </Box>
  );
};
