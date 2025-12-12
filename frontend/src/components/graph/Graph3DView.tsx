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

import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D, { ForceGraphMethods } from "react-force-graph-3d";
import {
  GraphPoint,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { buildOverlapMap, getNodeId, isAdditiveEvent, makePosKey } from "./selectionUtils";

type Props = {
  points: GraphPoint[];
  darkMode: boolean;
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
  // If true, color nodes by cluster number (from point_3d.cluster). Defaults to false.
  colorByCluster?: boolean;
  // If true, show document links between chunks; defaults to false.
  showLinks?: boolean;
};

export default function Graph3DView({ points, darkMode, onSelectionChange, fitVersion, fitOnResize, selectOverlaps = true, overlapPrecision = 6, colorByCluster = false, showLinks = false }: Props) {
  const fgRef = useRef<ForceGraphMethods | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Multi-selection state (chunk_uid values)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { nodes, links } = useMemo(() => {
    const nodes = points.map((p, i) => {
      const id = p.metadata?.chunk_uid ?? i;
      const name = p.metadata?.chunk_uid ?? String(i);
      const docId = p.metadata?.document_uid ?? String(i);
      const x = p.point_3d?.x ?? 0;
      const y = p.point_3d?.y ?? 0;
      const z = p.point_3d?.z ?? 0;
      const cluster = (p as any)?.point_3d?.cluster ?? null;
      const text = p.metadata?.text ?? undefined;
      return {
        id,
        name,
        doc_id: docId,
        cluster,
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
    // Build lightweight links between chunks of the same document.
    // Use a star topology (first node in the doc as hub) to avoid O(n^2) links.
    const byDoc = new Map<string, any[]>();
    for (const n of nodes) {
      const d = n.doc_id;
      if (!d) continue;
      const arr = byDoc.get(d);
      if (arr) arr.push(n); else byDoc.set(d, [n]);
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
  }, [points]);

  // Group nodes by quantized position to detect overlaps
  const posKey = useMemo(() => makePosKey(overlapPrecision), [overlapPrecision]);

  const overlapMap = useMemo(() => buildOverlapMap(nodes, posKey), [nodes, posKey]);

  // Controlled fit: only when fitVersion increments (e.g., on a new projection)
  // NOTE: Do NOT depend on nodes.length here, otherwise every deletion would retrigger a fit.
  useEffect(() => {
    const fit = () => {
      const api = fgRef.current;
      if (api && nodes.length) {
        try {
          api.zoomToFit(400, 0);
        } catch { /* ignore */ }
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
          } catch { /* ignore */ }
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
        if (next.has(gid)) next.delete(gid); else next.add(gid);
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

  // Deterministic cluster color palette (max 10 clusters)
  const clusterPaletteLight = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
  ];
  const clusterPaletteDark = [
    "#4FC3F7", "#FFB74D", "#81C784", "#E57373", "#BA68C8",
    "#A1887F", "#F48FB1", "#BDBDBD", "#DCE775", "#4DD0E1"
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
    <div ref={containerRef} style={{ width: "100%", height: "100%" }}>
      <ForceGraph3D
        ref={fgRef as any}
        graphData={{ nodes, links: showLinks ? links : [] }}
        backgroundColor="rgba(0,0,0,0)"
        enableNodeDrag={false}
        showNavInfo={false}
        // Tooltip on hover: chunk_uid + fetched chunk text
        nodeLabel={(n: any) => getNodeTooltip(n)}
        onNodeClick={handleNodeClick}
        onBackgroundClick={() => clearSelection()}
        nodeRelSize={0.05}
        nodeOpacity={0.9}
        nodeVal={(n: any) => (selectedIds.has(getNodeId(n)) ? 3 : 1)}
        nodeColor={(n: any) => {
          if (selectedIds.has(getNodeId(n))) {
            // When color-by-cluster is enabled, selection color should be
            // white in dark mode and black in light mode for maximum contrast.
            if (colorByCluster) return darkMode ? "#EEEEEE" : "#444444";
            // Otherwise keep the previous theme selection colors
            return darkMode ? "#4FC3F7" : "#1976D2";
          }
          if (colorByCluster) return getClusterColor((n as any).cluster);
          return darkMode ? "#EEEEEE" : "#444444";
        }}
        // Document links styling
        linkColor={() => (darkMode ? "#888888" : "#BBBBBB")}
        linkOpacity={0.35}
        linkWidth={0}
      />
    </div>
  );
}
