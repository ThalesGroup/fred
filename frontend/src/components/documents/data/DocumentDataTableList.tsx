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
import TableChartIcon from "@mui/icons-material/TableChart";
import { getDocumentIcon } from "../common/DocumentIcon.tsx";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import { useTranslation } from "react-i18next";
import { useTheme } from "@mui/material/styles";
import { useMemo, useState } from "react";
import { DocumentDataRowsProps, LimitOption, RowSortMode } from "./DocumentDataCommon.tsx";

export const DocumentDataTableList = (
  { rows, search }: DocumentDataRowsProps,
) => {
  const { t } = useTranslation();
  const theme = useTheme();

  const [rowSortMode, setRowSortMode] = useState<RowSortMode>("rowsDesc");
  const [showRowsTable, setShowRowsTable] = useState(true);
  const [rowLimit, setRowLimit] = useState<LimitOption>(10);
  const tableRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    let current = rows.filter((r) => (r.tableNode?.row_count ?? 0) > 0);

    if (query) {
      current = current.filter((row) => {
        const docLabel = row.document.label?.toLowerCase() ?? "";
        const tableLabel = row.tableNode?.label?.toLowerCase() ?? "";
        return docLabel.includes(query) || tableLabel.includes(query);
      });
    }

    const sorted = [...current];
    sorted.sort((a, b) => {
      if (rowSortMode === "name") {
        const aName = a.document.label ?? "";
        const bName = b.document.label ?? "";
        return aName.localeCompare(bName);
      }
      const aRows = a.tableNode?.row_count ?? 0;
      const bRows = b.tableNode?.row_count ?? 0;
      if (rowSortMode === "rowsDesc") {
        return bRows - aRows;
      }
      if (rowSortMode === "rowsAsc") {
        return aRows - bRows;
      }
      return 0;
    });

    return sorted;
  }, [rows, search, rowSortMode]);

  const limitedTableRows =
    rowLimit === "all" ? tableRows : tableRows.slice(0, typeof rowLimit === "number" ? rowLimit : 10);

  return (
    <Box sx={{ mt: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 1.5, py: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <TableChartIcon fontSize="small" color="secondary" />
          <Typography variant="subtitle2">{t("dataHub.rowTableTitle", "Documents with tables")}</Typography>
        </Stack>
        <Stack direction="row" alignItems="center" spacing={1.5}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel id="datahub-row-sort-label">{t("dataHub.sortLabel", "Sort by")}</InputLabel>
            <Select
              labelId="datahub-row-sort-label"
              label={t("dataHub.sortLabel", "Sort by")}
              value={rowSortMode}
              onChange={(e) => setRowSortMode(e.target.value as RowSortMode)}
            >
              <MenuItem value="rowsDesc">{t("dataHub.sortRowsDesc", "Rows (high to low)")}</MenuItem>
              <MenuItem value="rowsAsc">{t("dataHub.sortRowsAsc", "Rows (low to high)")}</MenuItem>
              <MenuItem value="name">{t("dataHub.sortName", "Name (A–Z)")}</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel id="datahub-row-limit-label">{t("dataHub.limitLabel", "Show")}</InputLabel>
            <Select
              labelId="datahub-row-limit-label"
              label={t("dataHub.limitLabel", "Show")}
              value={rowLimit}
              onChange={(e) =>
                setRowLimit(e.target.value === "all" ? "all" : (Number(e.target.value) as LimitOption))
              }
            >
              <MenuItem value={10}>10</MenuItem>
              <MenuItem value={20}>20</MenuItem>
              <MenuItem value={50}>50</MenuItem>
              <MenuItem value="all">{t("dataHub.limitAll", "All")}</MenuItem>
            </Select>
          </FormControl>
          <Chip
            label={showRowsTable ? t("dataHub.hideSection", "Hide") : t("dataHub.showSection", "Show")}
            size="small"
            variant="outlined"
            onClick={() => setShowRowsTable((v) => !v)}
          />
        </Stack>
      </Stack>

      {showRowsTable && (
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
              <Typography variant="caption">{t("dataHub.rowsColumn", "Rows")}</Typography>
              <TableChartIcon fontSize="inherit" color="secondary" />
            </Box>
          </Box>

          {limitedTableRows.map((row) => {
            const doc = row.document;
            const rowCount = row.tableNode?.row_count ?? null;

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
                }}
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
                  <Typography variant="body2">{rowCount !== null ? rowCount : "–"}</Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}