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

import { Box, Chip, FormControl, InputLabel, MenuItem, Select, Stack, Typography } from "@mui/material";
import ScatterPlotIcon from "@mui/icons-material/ScatterPlot";
import { getDocumentIcon } from "../common/DocumentIcon.tsx";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import { useTranslation } from "react-i18next";
import { useTheme } from "@mui/material/styles";
import { useMemo, useState } from "react";
import { DocumentDataRowsProps, LimitOption, VectorSortMode } from "./DocumentDataCommon.tsx";
import { useVectorDocumentViewer } from "./DocumentDataDrawer.tsx";



export const DocumentDataVectorList = (
  { rows, search }: DocumentDataRowsProps,
) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { openVectorDocument } = useVectorDocumentViewer();

  const [vectorSortMode, setVectorSortMode] = useState<VectorSortMode>("vectorsDesc");
  const vectorRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    let current = rows.filter((r) => (r.vectorNode?.vector_count ?? 0) > 0);

    if (query) {
      current = current.filter((row) => {
        const docLabel = row.document.label?.toLowerCase() ?? "";
        const vectorLabel = row.vectorNode?.label?.toLowerCase() ?? "";
        return docLabel.includes(query) || vectorLabel.includes(query);
      });
    }

    const sorted = [...current];
    sorted.sort((a, b) => {
      if (vectorSortMode === "name") {
        const aName = a.document.label ?? "";
        const bName = b.document.label ?? "";
        return aName.localeCompare(bName);
      }
      const aVectors = a.vectorNode?.vector_count ?? 0;
      const bVectors = b.vectorNode?.vector_count ?? 0;
      if (vectorSortMode === "vectorsDesc") {
        return bVectors - aVectors;
      }
      if (vectorSortMode === "vectorsAsc") {
        return aVectors - bVectors;
      }
      return 0;
    });

    return sorted;
  }, [rows, search, vectorSortMode]);

  const [vectorLimit, setVectorLimit] = useState<LimitOption>(10);
  const [showVectorsTable, setShowVectorsTable] = useState(true);

  const limitedVectorRows =
    vectorLimit === "all" ? vectorRows : vectorRows.slice(0, typeof vectorLimit === "number" ? vectorLimit : 10);

  return (
    <Box sx={{ mt: 1 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 1.5, py: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <ScatterPlotIcon fontSize="small" color="primary" />
          <Typography variant="subtitle2">
            {t("dataHub.vectorTableTitle", "Documents with vectors")}
          </Typography>
        </Stack>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel id="datahub-vector-sort-label">{t("dataHub.sortLabel", "Sort by")}</InputLabel>
            <Select
              labelId="datahub-vector-sort-label"
              label={t("dataHub.sortLabel", "Sort by")}
              value={vectorSortMode}
              onChange={(e) => setVectorSortMode(e.target.value as VectorSortMode)}
            >
              <MenuItem value="vectorsDesc">{t("dataHub.sortVectorsDesc", "Vectors (high to low)")}</MenuItem>
              <MenuItem value="vectorsAsc">{t("dataHub.sortVectorsAsc", "Vectors (low to high)")}</MenuItem>
              <MenuItem value="name">{t("dataHub.sortName", "Name (A–Z)")}</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel id="datahub-vector-limit-label">{t("dataHub.limitLabel", "Show")}</InputLabel>
            <Select
              labelId="datahub-vector-limit-label"
              label={t("dataHub.limitLabel", "Show")}
              value={vectorLimit}
              onChange={(e) =>
                setVectorLimit(e.target.value === "all" ? "all" : (Number(e.target.value) as LimitOption))
              }
            >
              <MenuItem value={10}>10</MenuItem>
              <MenuItem value={20}>20</MenuItem>
              <MenuItem value={50}>50</MenuItem>
              <MenuItem value="all">{t("dataHub.limitAll", "All")}</MenuItem>
            </Select>
          </FormControl>
          <Chip
            label={showVectorsTable ? t("dataHub.hideSection", "Hide") : t("dataHub.showSection", "Show")}
            size="small"
            variant="outlined"
            onClick={() => setShowVectorsTable((v) => !v)}
          />
        </Stack>
      </Stack>

      {showVectorsTable && (
        <Box>
          <Box
            sx={{
              px: 1.5,
              py: 0.5,
              display: "flex",
              alignItems: "center",
              borderBottom: `1px solid ${theme.palette.divider}`,
              color: theme.palette.text.secondary,
            }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="caption">{t("dataHub.documentColumn", "Document")}</Typography>
            </Box>
            <Box
              sx={{ width: 120, textAlign: "right", display: "flex", justifyContent: "flex-end", gap: 0.5 }}
            >
              <Typography variant="caption">{t("dataHub.vectorsColumn", "Vectors")}</Typography>
              <ScatterPlotIcon fontSize="inherit" color="primary" />
            </Box>
          </Box>

          {limitedVectorRows.map((row) => {
            const doc = row.document;
            const vectorCount = row.vectorNode?.vector_count ?? null;

            return (
              <Box
                key={doc.id}
                sx={{
                  px: 1.5,
                  py: 0.5,
                  display: "flex",
                  alignItems: "center",
                  borderBottom: `1px solid ${theme.palette.divider}`,
                  bgcolor: theme.palette.background.default,
                  cursor: "pointer",
                  "&:hover": {
                    bgcolor: theme.palette.action.hover,
                  },
                }}
                onClick={() => openVectorDocument(doc)}
              >
                <Box
                  sx={{
                    flex: 1,
                    minWidth: 0,
                    display: "flex",
                    alignItems: "center",
                    gap: 0.75,
                  }}
                >
                  {getDocumentIcon(doc.label) || <InsertDriveFileOutlinedIcon fontSize="small" />}
                  <Typography variant="body2" noWrap>
                    {doc.label}
                  </Typography>
                </Box>
                <Box
                  sx={{
                    width: 120,
                    textAlign: "right",
                    display: "flex",
                    justifyContent: "flex-end",
                    alignItems: "center",
                    gap: 0.5,
                  }}
                >
                  <Typography variant="body2">{vectorCount !== null ? vectorCount : "–"}</Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}