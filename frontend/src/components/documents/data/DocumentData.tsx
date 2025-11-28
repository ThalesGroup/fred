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

import { Box, Chip, Stack, Typography } from "@mui/material";
import { DocumentDataSearch } from "./DocumentDataSearch.tsx";
import { DocumentDataTablePie } from "./DocumentDataTablePie.tsx";
import { DocumentDataVectorPie } from "./DocumentDataVectorPie.tsx";
import { DocumentDataVectorList } from "./DocumentDataVectorList.tsx";
import { DocumentDataTableList } from "./DocumentDataTableList.tsx";
import {
  ProcessingGraph,
  ProcessingGraphEdge,
  ProcessingGraphNode,
  useGetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetQuery
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { useTranslation } from "react-i18next";
import { useMemo, useState } from "react";
import { DocumentFlowRow } from "./DocumentDataCommon.tsx";

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

    rows.push({ document: node, vectorNode: vectorNode, tableNode: tableNode });
  }

  return rows;
}

export const DocumentData = () => {
  const { t } = useTranslation();

  const { data, isLoading, isError, refetch } = useGetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetQuery();

  const rows = useMemo(() => buildDocumentFlows(data), [data]);
  const vectorSlices = useMemo(() => {
    return (
      rows
        .filter((r) => (r.vectorNode?.vector_count ?? 0) > 0)
        .map((r) => ({
          key: r.document.id,
          label: r.document.label,
          value: r.vectorNode?.vector_count ?? 0,
        })) ?? []
    );
  }, [rows]);
  const tableSlices = useMemo(() => {
    return (
      rows
        .filter((r) => (r.tableNode?.row_count ?? 0) > 0)
        .map((r) => ({
          key: r.document.id,
          label: r.document.label,
          value: r.tableNode?.row_count ?? 0,
        })) ?? []
    );
  }, [rows]);

  const hasData = rows.length > 0;
  const hasVectorData = vectorSlices.length > 0;
  const hasTableData = tableSlices.length > 0;

  const [search, setSearch] = useState("");

  return <>
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
        <Stack
          direction="row"
          justifyContent="flex-end"
          alignItems="center"
          sx={{
            position: "relative",
            mb: -3,
            zIndex: 2,
          }}
        >
          <Chip label={t("common.refresh")} size="small" onClick={() => refetch()} variant="outlined"/>
        </Stack>
        <DocumentDataSearch search={search} setSearch={setSearch} />
        {(hasVectorData || hasTableData) && (
          <Box sx={{
            mb: 1,
            display: "flex",
            flexDirection: { xs: "column", md: "row" },
            gap: 2,
          }}>
            {hasVectorData && <DocumentDataVectorPie slices={vectorSlices} />}
            {hasTableData && <DocumentDataTablePie slices={tableSlices}/>}
          </Box>
        )}
        {hasVectorData && <DocumentDataVectorList rows={rows} search={search} />}
        {hasTableData && <DocumentDataTableList rows={rows} search={search} />}
      </Box>
    )}
  </>
}