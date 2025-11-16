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

import { Box, Chip, Divider, Paper, Stack, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import React, { useMemo } from "react";
import { ResponsiveContainer, Sankey, Tooltip as RechartsTooltip } from "recharts";
import { useTranslation } from "react-i18next";

import {
  ProcessingGraph,
  ProcessingGraphEdge,
  ProcessingGraphNode,
  useGetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetQuery,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

type SankeyNode = { name: string; kind: string; id: string };
type SankeyLink = { source: number; target: number; value: number; kind: string };

function buildSankeyData(graph: ProcessingGraph | undefined): { nodes: SankeyNode[]; links: SankeyLink[] } {
  if (!graph) {
    return { nodes: [], links: [] };
  }

  const nodes: SankeyNode[] = graph.nodes.map((n) => ({
    id: n.id,
    name: n.label,
    kind: n.kind,
  }));

  const indexById = new Map<string, number>();
  nodes.forEach((n, idx) => indexById.set(n.id, idx));

  const edges: ProcessingGraphEdge[] = graph.edges || [];

  const links: SankeyLink[] = edges
    .map((e) => {
      const sourceIndex = indexById.get(e.source);
      const targetIndex = indexById.get(e.target);
      if (sourceIndex === undefined || targetIndex === undefined) {
        return null;
      }

      const targetNode = nodes[targetIndex];
      let value = 1;

      if (targetNode.kind === "vector_index") {
        const node = graph.nodes.find((n) => n.id === targetNode.id);
        if (node && node.vector_count && node.vector_count > 0) {
          value = node.vector_count;
        }
      } else if (targetNode.kind === "table") {
        const node = graph.nodes.find((n) => n.id === targetNode.id);
        if (node && node.row_count && node.row_count > 0) {
          value = node.row_count;
        }
      }

      return {
        source: sourceIndex,
        target: targetIndex,
        value,
        kind: e.kind,
      };
    })
    .filter((l): l is SankeyLink => l !== null);

  return { nodes, links };
}

export default function DataHub() {
  const { t } = useTranslation();
  const theme = useTheme();
  const { data, isLoading, isError, refetch } =
    useGetProcessingGraphKnowledgeFlowV1DocumentsProcessingGraphGetQuery();

  const { nodes, links } = useMemo(() => buildSankeyData(data), [data]);
  const hasData = nodes.length > 0 && links.length > 0;

  return (
    <Box p={2} sx={{ display: "flex", justifyContent: "center" }}>
      <Paper sx={{ p: 2, width: "min(1100px, 100%)" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">
            {t("dataHub.title", "Data Hub - Document Lineage")}
          </Typography>
          <Chip
            label={t("common.refresh", "Refresh")}
            size="small"
            onClick={() => refetch()}
            variant="outlined"
          />
        </Stack>
        <Divider sx={{ my: 1.5 }} />
        {isLoading && (
          <Typography>{t("common.loading", "Loading...")}</Typography>
        )}
        {isError && (
          <Stack direction="row" gap={1} alignItems="center">
            <Typography color="error">
              {t("dataHub.error", "Failed to load processing graph")}
            </Typography>
            <Chip
              label={t("common.retry", "Retry")}
              onClick={() => refetch()}
              size="small"
            />
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
          <Box sx={{ width: "100%", height: 400, mt: 1 }}>
            <ResponsiveContainer width="100%" height="100%">
              <Sankey
                data={{ nodes, links }}
                nodePadding={24}
                margin={{ left: 20, right: 20, top: 20, bottom: 20 }}
              >
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 8,
                    color: theme.palette.text.primary,
                    boxShadow: theme.shadows[2] as any,
                    padding: 8,
                  }}
                  formatter={(val: any, _name, props: any) => {
                    const link = props?.payload as SankeyLink | undefined;
                    if (!link) return [val, ""];
                    const target = nodes[link.target];
                    if (target?.kind === "vector_index") {
                      return [val, t("dataHub.vectors", "vectors")];
                    }
                    if (target?.kind === "table") {
                      return [val, t("dataHub.rows", "rows")];
                    }
                    return [val, ""];
                  }}
                />
              </Sankey>
            </ResponsiveContainer>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
