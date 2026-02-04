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

import HubIcon from "@mui/icons-material/Hub";
import PaletteIcon from "@mui/icons-material/Palette";
import SendIcon from "@mui/icons-material/Send";
import { Box, CircularProgress, IconButton, InputAdornment, Menu, MenuItem, TextField } from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D, { ForceGraphMethods } from "react-force-graph-3d";
import { useTranslation } from "react-i18next";
import { useLocalStorageState } from "../../hooks/useLocalStorageState.ts";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips.tsx";
import {
  GraphPoint,
  useProjectTextKnowledgeFlowV1ModelsUmapRefTagUidProjectTextPostMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { buildOverlapMap, getNodeId, isAdditiveEvent, makePosKey } from "./selectionUtils";

export type ColorMode = "none" | "3d" | "vector" | "distance";

type Props = {
  points: GraphPoint[];
  darkMode: boolean;
  tagUid?: string; // Add tagUid to props for API calls
  onSelectionChange?: (selectedIds: string[]) => void;
  // When this counter changes, the graph will perform a zoomToFit.
  // Useful to fit only on new projections, but not on local deletions.
  fitVersion?: number;
  // If true, perform a zoomToFit when the container is resized (e.g., layout changes).
  // Default is false to avoid unintended de-zoom on data updates.
  fitOnResize?: boolean;
  // When clicking a node, also select all nodes that are at the same position (overlapped).
  // Defaults to true.
  selectOverlaps?: boolean;
  // Precision used to consider two nodes as overlapped (by rounding coordinates).
  // Example: 6 means rounding to 1e-6. Defaults to 6.
  overlapPrecision?: number;
};

export default function Graph3DView({
  points,
  darkMode,
  tagUid,
  onSelectionChange,
  fitVersion,
  fitOnResize,
  selectOverlaps = true,
  overlapPrecision = 6,
}: Props) {
  const { t } = useTranslation();
  const fgRef = useRef<ForceGraphMethods | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Multi-selection state (chunk_id values)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Internal UI state with localStorage persistence
  const [showLinks, setShowLinks] = useLocalStorageState<boolean>("graph.showLinks", false);
  const [colorMode, setColorMode] = useLocalStorageState<ColorMode>("graph.colorMode", "3d");
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  // Question input state
  const [question, setQuestion] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [questionPoint, setQuestionPoint] = useState<any | null>(null);

  // API mutation for projecting question
  const [projectQuestion] = useProjectTextKnowledgeFlowV1ModelsUmapRefTagUidProjectTextPostMutation();

  const { nodes, links } = useMemo(() => {
    const nodes: any[] = points.map((p, i) => {
      const id = p.metadata?.chunk_uid ?? i;
      const name = p.metadata?.chunk_uid ?? String(i);
      const docId = p.metadata?.document_uid ?? String(i);
      const x = p.point_3d?.x ?? 0;
      const y = p.point_3d?.y ?? 0;
      const z = p.point_3d?.z ?? 0;
      // Extract clusters from new structure
      const clusterD3 = p.clusters?.d3 ?? null;
      const clusterVector = p.clusters?.vector ?? null;
      const clusterDistance = p.clusters?.distance ?? null;
      const text = p.metadata?.text ?? undefined;
      return {
        id,
        name,
        doc_id: docId,
        cluster_d3: clusterD3,
        cluster_vector: clusterVector,
        cluster_distance: clusterDistance,
        text,
        // Fix positions (no simulation drift)
        fx: x,
        fy: y,
        fz: z,
        // Also set initial positions for zoomToFit accessor
        x,
        y,
        z,
      };
    });
    // Add question point if it exists
    if (questionPoint) {
      nodes.push({
        id: "question",
        name: "Question",
        doc_id: "question",
        cluster_d3: null,
        cluster_vector: null,
        cluster_distance: null,
        text: questionPoint.text,
        fx: questionPoint.x,
        fy: questionPoint.y,
        fz: questionPoint.z,
        x: questionPoint.x,
        y: questionPoint.y,
        z: questionPoint.z,
        isQuestion: true,
      });
    }
    // Build lightweight links between chunks of the same document.
    // Use a star topology (first node in the doc as hub) to avoid O(n^2) links.
    const byDoc = new Map<string, any[]>();
    for (const n of nodes) {
      const d = n.doc_id;
      if (!d) continue;
      const arr = byDoc.get(d);
      if (arr) arr.push(n);
      else byDoc.set(d, [n]);
    }
    const links: any[] = [];
    for (const arr of byDoc.values()) {
      if (arr.length <= 1) continue;
      const hub = arr[0];
      for (let i = 1; i < arr.length; i++) {
        const leaf = arr[i];
        links.push({ source: hub.id, target: leaf.id, doc_id: hub.doc_id });
      }
    }
    return { nodes, links };
  }, [points, questionPoint]);

  // Group nodes by quantized position to detect overlaps
  const posKey = useMemo(() => makePosKey(overlapPrecision), [overlapPrecision]);

  const overlapMap = useMemo(() => buildOverlapMap(nodes, posKey), [nodes, posKey]);

  // Clear question point when points array becomes empty (graph is cleared)
  useEffect(() => {
    if (points.length === 0 && questionPoint !== null) {
      setQuestionPoint(null);
      setQuestion("");
    }
  }, [points.length, questionPoint]);

  // Controlled fit: only when fitVersion increments (e.g., on a new projection)
  // NOTE: Do NOT depend on nodes.length here, otherwise every deletion would retrigger a fit.
  useEffect(() => {
    const fit = () => {
      const api = fgRef.current;
      if (api && nodes.length) {
        try {
          api.zoomToFit(400, 0);
        } catch {
          /* ignore */
        }
      }
    };
    // Trigger only when requested (on fitVersion change)
    const t1 = setTimeout(fit, 0);
    return () => clearTimeout(t1);
  }, [fitVersion]);

  // Observe container resizes (e.g., side panel open/close) and refit
  useEffect(() => {
    if (!fitOnResize) return;
    if (!containerRef.current) return;
    const el = containerRef.current;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const api = fgRef.current;
        if (api && nodes.length) {
          try {
            api.zoomToFit(400, 0);
          } catch {
            /* ignore */
          }
        }
      });
    });
    ro.observe(el);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [fitOnResize]);

  // Build tooltip HTML from node
  const getNodeTooltip = (n: any) => {
    const escapeHtml = (s: any) =>
      String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");

    const id = n?.name ?? n?.id ?? "";
    if (!id) return "";
    const body = n?.text ?? "";

    const idSafe = escapeHtml(id);
    const bodySafe = escapeHtml(body);

    // Render like the accordion's <pre>: monospace, preserved newlines, scrollable, max height
    return `
      <div style="max-width: 560px;">
        <div style="margin-bottom: 4px;"><b>${idSafe}</b></div>
        <pre style="margin: 0; max-height: 240px; overflow: auto; white-space: pre; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; font-size: 13px; line-height: 1.5; word-break: normal; overflow-wrap: normal;">
${bodySafe}
        </pre>
      </div>
    `;
  };

  // Handle node click for selection
  const handleNodeClick = (node: any, event: MouseEvent) => {
    const id = getNodeId(node);
    if (!id) return;
    // Compute group of overlapped ids at this node position
    const k = selectOverlaps ? posKey(node) : null;
    const groupIds = (k && overlapMap.get(k)) || [id];
    const additive = isAdditiveEvent(event);
    setSelectedIds((prev) => {
      if (!additive) return new Set(groupIds);
      const next = new Set(prev);
      for (const gid of groupIds) {
        if (next.has(gid)) next.delete(gid);
        else next.add(gid);
      }
      return next;
    });
  };

  const clearSelection = () => setSelectedIds((prev) => (prev.size ? new Set() : prev));

  // Notify parent about selection changes (if callback provided)
  useEffect(() => {
    if (!onSelectionChange) return;
    onSelectionChange(Array.from(selectedIds));
  }, [selectedIds, onSelectionChange]);

  // UI handlers
  const handleToggleLinks = () => setShowLinks(!showLinks);
  const handleColorMenuClick = (event: React.MouseEvent<HTMLElement>) => setAnchorEl(event.currentTarget);
  const handleColorMenuClose = () => setAnchorEl(null);
  const handleColorModeSelect = (mode: ColorMode) => {
    setColorMode(mode);
    handleColorMenuClose();
  };

  const handleSubmitQuestion = async () => {
    if (!question.trim() || isSubmitting || !tagUid) return;
    setIsSubmitting(true);
    try {
      const result = await projectQuestion({
        refTagUid: tagUid,
        projectTextRequest: { text: question.trim() },
      }).unwrap();

      setQuestionPoint({
        x: result.graph_point.point_3d.x,
        y: result.graph_point.point_3d.y,
        z: result.graph_point.point_3d.z,
        text: result.graph_point.metadata?.text || question.trim(),
      });
      setQuestion("");
    } catch (error) {
      console.error("Error submitting question:", error);
      // TODO: Show error toast/notification to user
    } finally {
      setIsSubmitting(false);
    }
  };

  const getColorModeLabel = (mode: ColorMode): string => {
    switch (mode) {
      case "none":
        return t("graph3DView.colorMode.none", "No coloring");
      case "3d":
        return t("graph3DView.colorMode.3d", "3D coloring");
      case "vector":
        return t("graph3DView.colorMode.vector", "Vector coloring");
      case "distance":
        return t("graph3DView.colorMode.distance", "Distance coloring");
    }
  };

  // Color calculation based on mode
  const getNodeColorByMode = (node: any): string => {
    // Special color for question node
    if (node.isQuestion) {
      return darkMode ? "#FFFFFF" : "#000000"; // White in dark mode, black in light mode
    }

    if (selectedIds.has(getNodeId(node))) {
      if (colorMode !== "none") return darkMode ? "#EEEEEE" : "#444444";
      return darkMode ? "#4FC3F7" : "#1976D2";
    }

    switch (colorMode) {
      case "none":
        return darkMode ? "#EEEEEE" : "#444444";
      case "3d":
        return getClusterColor(node.cluster_d3);
      case "vector":
        return getClusterColor(node.cluster_vector);
      case "distance": {
        // Use cluster_distance [0-100] for continuous heatmap coloring
        const distanceValue = node.cluster_distance;
        if (distanceValue === null || distanceValue === undefined) {
          return darkMode ? "#EEEEEE" : "#444444";
        }
        // Normalize to [0, 1] range (linear scale)
        const normalized = Math.min(Math.max(distanceValue / 100, 0), 1);

        // Classic heatmap: blue (cold/close) -> cyan -> green -> yellow -> red (hot/far)
        // Using HSL with hue going from 240° (blue) through 180° (cyan), 120° (green), 60° (yellow) to 0° (red)
        const hue = (1 - normalized) * 240; // Inverted: 0=close=blue, 100=far=red
        const saturation = 90; // High saturation for vivid colors
        const lightness = darkMode ? 55 : 45;

        return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
      }
    }
  };

  // Deterministic cluster color palette (max 10 clusters)
  const clusterPaletteLight = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
  ];
  const clusterPaletteDark = [
    "#4FC3F7",
    "#FFB74D",
    "#81C784",
    "#E57373",
    "#BA68C8",
    "#A1887F",
    "#F48FB1",
    "#BDBDBD",
    "#DCE775",
    "#4DD0E1",
  ];
  const getClusterColor = (c: any): string => {
    const pal = darkMode ? clusterPaletteDark : clusterPaletteLight;
    if (c === null || c === undefined) return darkMode ? "#EEEEEE" : "#222222";
    // numeric or string key
    const key = Number.isFinite(c) ? Number(c) : String(c);
    let idx: number;
    if (typeof key === "number") idx = Math.abs(key) % pal.length;
    else {
      // basic string hash
      let h = 0;
      for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
      idx = Math.abs(h) % pal.length;
    }
    return pal[idx];
  };

  return (
    <Box ref={containerRef} sx={{ position: "relative", width: "100%", height: "100%" }}>
      {/* Control buttons */}
      <Box
        sx={{
          position: "absolute",
          top: 12,
          right: 12,
          zIndex: 10,
          display: "flex",
          gap: 1,
        }}
      >
        <SimpleTooltip title={t("graph3DView.toggleLinks", "Afficher/masquer les liens")}>
          <IconButton
            size="small"
            onClick={handleToggleLinks}
            color={showLinks ? "primary" : "default"}
            sx={{
              bgcolor: (theme) => theme.palette.background.paper,
              "&:hover": { bgcolor: (theme) => theme.palette.action.hover },
            }}
          >
            <HubIcon fontSize="small" />
          </IconButton>
        </SimpleTooltip>

        <SimpleTooltip title={t("graph3DView.colorMode.title", "Mode de coloration")}>
          <IconButton
            size="small"
            onClick={handleColorMenuClick}
            color={colorMode !== "none" ? "primary" : "default"}
            sx={{
              bgcolor: (theme) => theme.palette.background.paper,
              "&:hover": { bgcolor: (theme) => theme.palette.action.hover },
            }}
          >
            <PaletteIcon fontSize="small" />
          </IconButton>
        </SimpleTooltip>

        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={handleColorMenuClose}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          transformOrigin={{ vertical: "top", horizontal: "right" }}
        >
          <MenuItem selected={colorMode === "none"} onClick={() => handleColorModeSelect("none")}>
            {getColorModeLabel("none")}
          </MenuItem>
          <MenuItem selected={colorMode === "3d"} onClick={() => handleColorModeSelect("3d")}>
            {getColorModeLabel("3d")}
          </MenuItem>
          <MenuItem selected={colorMode === "vector"} onClick={() => handleColorModeSelect("vector")}>
            {getColorModeLabel("vector")}
          </MenuItem>
          <MenuItem selected={colorMode === "distance"} onClick={() => handleColorModeSelect("distance")}>
            {getColorModeLabel("distance")}
          </MenuItem>
        </Menu>
      </Box>

      {/* 3D Graph */}
      <ForceGraph3D
        ref={fgRef as any}
        graphData={{ nodes, links: showLinks ? links : [] }}
        backgroundColor="rgba(0,0,0,0)"
        enableNodeDrag={false}
        showNavInfo={false}
        nodeLabel={(n: any) => getNodeTooltip(n)}
        onNodeClick={handleNodeClick}
        onBackgroundClick={() => clearSelection()}
        nodeRelSize={0.05}
        nodeOpacity={0.9}
        nodeVal={(n: any) => (n.isQuestion ? 8 : selectedIds.has(getNodeId(n)) ? 3 : 1)}
        nodeColor={(n: any) => getNodeColorByMode(n)}
        linkColor={() => (darkMode ? "#888888" : "#BBBBBB")}
        linkOpacity={0.35}
        linkWidth={0}
      />

      {/* Question Input */}
      <Box
        sx={{
          position: "absolute",
          bottom: 16,
          left: "50%",
          transform: "translateX(-50%)",
          width: "90%",
          maxWidth: 600,
          zIndex: 10,
        }}
      >
        <TextField
          fullWidth
          size="small"
          multiline
          minRows={1}
          maxRows={4}
          placeholder={t("graph3DView.testPromptPlaceholder", "Saisir un prompt de test...")}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !isSubmitting && question.trim()) {
              e.preventDefault();
              handleSubmitQuestion();
            }
          }}
          disabled={isSubmitting}
          InputProps={{
            sx: {
              bgcolor: (theme) => theme.palette.background.paper,
              backdropFilter: "blur(10px)",
            },
            endAdornment: (
              <InputAdornment position="end">
                {isSubmitting ? (
                  <CircularProgress size={20} />
                ) : (
                  <IconButton size="small" onClick={handleSubmitQuestion} disabled={!question.trim()} color="primary">
                    <SendIcon fontSize="small" />
                  </IconButton>
                )}
              </InputAdornment>
            ),
          }}
        />
      </Box>
    </Box>
  );
}
