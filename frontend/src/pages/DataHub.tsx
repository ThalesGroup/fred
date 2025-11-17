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

import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import ScatterPlotIcon from "@mui/icons-material/ScatterPlot";
import TableChartIcon from "@mui/icons-material/TableChart";
import { Box, Chip, Divider, FormControl, InputLabel, MenuItem, Paper, Select, Stack, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

import { getDocumentIcon } from "../components/documents/common/DocumentIcon";
import {
  ProcessingGraph,
  ProcessingGraphEdge,
  ProcessingGraphNode,
  useGetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetQuery,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

type DocumentFlowRow = {
  document: ProcessingGraphNode;
  vectorNode?: ProcessingGraphNode;
  tableNode?: ProcessingGraphNode;
};
type VectorSortMode = "name" | "vectorsDesc" | "vectorsAsc";
type RowSortMode = "name" | "rowsDesc" | "rowsAsc";
type LimitOption = 10 | 20 | 50 | "all";

function buildDocumentFlows(graph: ProcessingGraph | undefined): DocumentFlowRow[] {
  if (!graph) {
    return [];
  }

  const nodesById = new Map<string, ProcessingGraphNode>();
  for (const node of graph.nodes) {
    nodesById.set(node.id, node);
  }

  const edgesBySource = new Map<string, ProcessingGraphEdge[]>();
  for (const edge of graph.edges ?? []) {
    const list = edgesBySource.get(edge.source) ?? [];
    list.push(edge);
    edgesBySource.set(edge.source, list);
  }

  const rows: DocumentFlowRow[] = [];

  for (const node of graph.nodes) {
    if (node.kind !== "document") {
      continue;
    }
    const outgoing = edgesBySource.get(node.id) ?? [];
    let vectorNode: ProcessingGraphNode | undefined;
    let tableNode: ProcessingGraphNode | undefined;

    for (const edge of outgoing) {
      if (edge.kind === "vectorized") {
        const target = nodesById.get(edge.target);
        if (target && target.kind === "vector_index") {
          vectorNode = target;
        }
      } else if (edge.kind === "sql_indexed") {
        const target = nodesById.get(edge.target);
        if (target && target.kind === "table") {
          tableNode = target;
        }
      }
    }

    rows.push({ document: node, vectorNode, tableNode });
  }

  return rows;
}

export default function DataHub() {
  const { t } = useTranslation();
  const theme = useTheme();
  const { data, isLoading, isError, refetch } = useGetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetQuery();

  const [search, setSearch] = useState("");
  const [vectorSortMode, setVectorSortMode] = useState<VectorSortMode>("vectorsDesc");
  const [rowSortMode, setRowSortMode] = useState<RowSortMode>("rowsDesc");
  const [vectorLimit, setVectorLimit] = useState<LimitOption>(10);
  const [rowLimit, setRowLimit] = useState<LimitOption>(10);
  const [showVectorsTable, setShowVectorsTable] = useState(true);
  const [showRowsTable, setShowRowsTable] = useState(true);

  const rows = useMemo(() => buildDocumentFlows(data), [data]);
  const hasData = rows.length > 0;

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

  const vectorSlices = useMemo(() => {
    const slices =
      rows
        .filter((r) => (r.vectorNode?.vector_count ?? 0) > 0)
        .map((r) => ({
          key: r.document.id,
          label: r.document.label,
          value: r.vectorNode?.vector_count ?? 0,
        })) ?? [];
    return slices;
  }, [rows]);

  const tableSlices = useMemo(() => {
    const slices =
      rows
        .filter((r) => (r.tableNode?.row_count ?? 0) > 0)
        .map((r) => ({
          key: r.document.id,
          label: r.document.label,
          value: r.tableNode?.row_count ?? 0,
        })) ?? [];
    return slices;
  }, [rows]);

  const hasVectorData = vectorSlices.length > 0;
  const hasTableData = tableSlices.length > 0;

  const vectorSlicesForChart = hasVectorData
    ? vectorSlices
    : [
        {
          key: "empty",
          label: "",
          value: 1,
        },
      ];

  const tableSlicesForChart = hasTableData
    ? tableSlices
    : [
        {
          key: "empty",
          label: "",
          value: 1,
        },
      ];

  const distributionColors = [
    theme.palette.primary.main,
    theme.palette.secondary.main,
    theme.palette.success.main,
    theme.palette.info.main,
    theme.palette.warning.main,
    theme.palette.error.main,
  ];
  const showVectorLegend = vectorSlices.length > 0 && vectorSlices.length <= 15;
  const showTableLegend = tableSlices.length > 0 && tableSlices.length <= 15;

  const limitedVectorRows =
    vectorLimit === "all" ? vectorRows : vectorRows.slice(0, typeof vectorLimit === "number" ? vectorLimit : 10);
  const limitedTableRows =
    rowLimit === "all" ? tableRows : tableRows.slice(0, typeof rowLimit === "number" ? rowLimit : 10);

  return (
    <Box p={2} sx={{ display: "flex", justifyContent: "center" }}>
      <Paper sx={{ p: 2, width: "min(1100px, 100%)" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">{t("dataHub.title")}</Typography>
          <Chip label={t("common.refresh")} size="small" onClick={() => refetch()} variant="outlined" />
        </Stack>
        <Divider sx={{ my: 1.5 }} />
        {isLoading && <Typography>{t("common.loading")}</Typography>}
        {isError && (
          <Stack direction="row" gap={1} alignItems="center">
            <Typography color="error">{t("dataHub.error", "Failed to load processing graph")}</Typography>
            <Chip label={t("common.retry", "Retry")} onClick={() => refetch()} size="small" />
          </Stack>
        )}
        {!isLoading && !isError && !hasData && (
          <Typography variant="body2" color="text.secondary">
            {t(
              "dataHub.empty",
              "No processing graph data available yet. Ingest and process documents to populate this view.",
            )}
          </Typography>
        )}
        {hasData && (
          <Box sx={{ width: "100%", mt: 1, display: "flex", flexDirection: "column", gap: 1 }}>
            <Box
              sx={{
                mb: 1,
                display: "flex",
                flexDirection: { xs: "column", md: "row" },
                gap: 1.5,
              }}
            >
              <Box sx={{ flex: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  {t("dataHub.searchHelp", "Filter documents by name or source")}
                </Typography>
                <Box
                  component="input"
                  type="text"
                  value={search}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
                  placeholder={t("dataHub.searchPlaceholder", "Search documents...")}
                  style={{
                    marginTop: 4,
                    width: "100%",
                    padding: "6px 8px",
                    borderRadius: 4,
                    border: `1px solid ${theme.palette.divider}`,
                    fontSize: "0.8rem",
                    fontFamily: "inherit",
                  }}
                />
              </Box>
            </Box>

            {(hasVectorData || hasTableData) && (
              <Box
                sx={{
                  mb: 1,
                  display: "flex",
                  flexDirection: { xs: "column", md: "row" },
                  gap: 2,
                }}
              >
                {hasVectorData && (
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
                          count: vectorSlices.length,
                        }) || `${vectorSlices.length} documents with vectors`}
                      </Typography>
                      <Box mt={1} display="flex" flexWrap="wrap" gap={1}>
                        {showVectorLegend ? (
                          vectorSlices.map((entry, idx) => (
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
                              count: vectorSlices.length,
                            })}
                          </Typography>
                        )}
                      </Box>
                    </Box>
                    <Box width={120} height={80} flexShrink={0}>
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={vectorSlicesForChart}
                            dataKey="value"
                            nameKey="label"
                            innerRadius={22}
                            outerRadius={34}
                            paddingAngle={1}
                          >
                            {vectorSlicesForChart.map((entry, idx) => (
                              <Cell
                                key={entry.key}
                                fill={
                                  entry.key === "empty"
                                    ? theme.palette.grey[300]
                                    : distributionColors[idx % distributionColors.length]
                                }
                              />
                            ))}
                          </Pie>
                        </PieChart>
                      </ResponsiveContainer>
                    </Box>
                  </Box>
                )}

                {hasTableData && (
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
                        {t("dataHub.rowDistributionTitle", "Rows per document")}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t("dataHub.rowDistributionSubtitle", {
                          count: tableSlices.length,
                        }) || `${tableSlices.length} documents with tables`}
                      </Typography>
                      <Box mt={1} display="flex" flexWrap="wrap" gap={1}>
                        {showTableLegend ? (
                          tableSlices.map((entry, idx) => (
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
                            {t("dataHub.rowDistributionMany", "{{count}} documents", {
                              count: tableSlices.length,
                            })}
                          </Typography>
                        )}
                      </Box>
                    </Box>
                    <Box width={120} height={80} flexShrink={0}>
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={tableSlicesForChart}
                            dataKey="value"
                            nameKey="label"
                            innerRadius={22}
                            outerRadius={34}
                            paddingAngle={1}
                          >
                            {tableSlicesForChart.map((entry, idx) => (
                              <Cell
                                key={entry.key}
                                fill={
                                  entry.key === "empty"
                                    ? theme.palette.grey[300]
                                    : distributionColors[idx % distributionColors.length]
                                }
                              />
                            ))}
                          </Pie>
                        </PieChart>
                      </ResponsiveContainer>
                    </Box>
                  </Box>
                )}
              </Box>
            )}

            {/* Vectors table */}
            {hasVectorData && (
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
                            <Typography variant="body2">{vectorCount !== null ? vectorCount : "–"}</Typography>
                          </Box>
                        </Box>
                      );
                    })}
                  </Box>
                )}
              </Box>
            )}

            {/* Rows (tables) table */}
            {hasTableData && (
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
            )}
          </Box>
        )}
      </Paper>
    </Box>
  );
}
