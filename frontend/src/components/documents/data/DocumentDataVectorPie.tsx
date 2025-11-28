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

import { Box, Typography } from "@mui/material";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { useTranslation } from "react-i18next";
import { useTheme } from "@mui/material/styles";
import { distributionColors, DocumentDataPieProps } from "./DocumentDataCommon.tsx";

export const DocumentDataVectorPie = (
  { slices }: DocumentDataPieProps,
) => {
  const { t } = useTranslation();
  const theme = useTheme();

  const showVectorLegend = slices.length > 0 && slices.length <= 15;

  const dc = distributionColors(theme)

  return (
    <Box
      sx={{
        flex: 1,
        p: 1.5,
        borderRadius: 2,
        border: (th) => `1px solid ${th.palette.divider}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        minHeight: 110,
        gap: 1.5,
      }}
    >
      <Box flex={1} minWidth={0}>
        <Typography variant="subtitle2">
          {t("dataHub.vectorDistributionTitle", "Vectors per document")}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {t("dataHub.vectorDistributionSubtitle", {
            count: slices.length,
          }) || `${slices.length} documents with vectors`}
        </Typography>
        <Box mt={1} display="flex" flexWrap="wrap" gap={1}>
          {showVectorLegend ? (
            slices.map((entry, idx) => (
              <Box key={entry.key} display="flex" alignItems="center" gap={0.5}>
                <Box
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    bgcolor: distributionColors[idx % distributionColors.length],
                  }}
                />
                <Typography variant="caption" noWrap>
                  {entry.label} ({entry.value})
                </Typography>
              </Box>
            ))
          ) : (
            <Typography variant="caption" color="text.secondary">
              {t("dataHub.vectorDistributionMany", "{{count}} documents", {
                count: slices.length,
              })}
            </Typography>
          )}
        </Box>
      </Box>
      <Box width={120} height={80} flexShrink={0}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="label"
              innerRadius={22}
              outerRadius={34}
              paddingAngle={1}
            >
              {slices.map((entry, idx) => (
                <Cell
                  key={entry.key}
                  fill={
                    entry.key === "empty"
                      ? theme.palette.grey[300]
                      : dc[idx % dc.length]
                  }
                />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}