import React, { useMemo } from "react";
import { Box } from "@mui/material";
import { interpolateTurbo } from "d3-scale-chromatic";
import { VectorItem } from "./DocumentDataCommon.tsx";


function formatVector(v: VectorItem): string {
  try {
    if (v == null) return "(vide)";
    if (Array.isArray(v)) return JSON.stringify(v, null, 2);
    if (typeof v === "object") return JSON.stringify(v, null, 2);
    return String(v);
  } catch {
    return "[formatting error]";
  }
}

function toNumberArray(v: VectorItem): number[] | null {
  if (Array.isArray(v)) {
    const nums = v.map((x) => (typeof x === "number" ? x : Number(x))).filter((n) => Number.isFinite(n));
    return nums.length ? nums : null;
  }
  if (v && typeof v === "object") {
    const arr = (v as any).vector;
    if (Array.isArray(arr)) {
      const nums = arr.map((x) => (typeof x === "number" ? x : Number(x))).filter((n) => Number.isFinite(n));
      return nums.length ? nums : null;
    }
  }
  return null;
}

export const VectorHeatmap: React.FC<{
  vector: VectorItem;
  columns?: number; // nombre de blocs par ligne (défaut 32)
  cellSize?: number; // taille d'un bloc (px)
  gap?: number; // espace entre blocs (px)
}> = ({ vector, columns = 64, cellSize = 6, gap = 1 }) => {
  const nums = useMemo(() => toNumberArray(vector), [vector]);

  if (!nums || nums.length === 0) {
    return (
      <Box
        component="pre"
        sx={{
          m: 0,
          maxHeight: 200,
          overflow: "auto",
          fontFamily:
            'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
          fontSize: 12,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {formatVector(vector)}
      </Box>
    );
  }

  const n = nums.length;
  const rows = Math.ceil(n / columns);
  const width = columns * cellSize + (columns - 1) * gap;
  const height = rows * cellSize + (rows - 1) * gap;
  const gain = 10  // Amplifying factor for better color distribution

  // Mappe numeric value to [-1,1] => [gain*-1,gain*1] => [0,1] for color interpolation (symmetrically around 0)
  const mapToPalette = (v: number) => {
    return Math.abs(Math.max(-1, Math.min(1, v * gain)));
  };
  const color = (v: number) => interpolateTurbo(mapToPalette(v));

  return (
    <Box
      sx={{
        maxHeight: 220,
        overflowY: "auto",
        overflowX: "hidden",
        pr: 1,
        width: "100%",
        maxWidth: width,
      }}
    >
      <svg
        role="img"
        aria-label="Vector heatmap"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMin meet"
        style={{ width: "100%", height: "auto", display: "block" }}
      >
        {nums.map((v, i) => {
          const r = Math.floor(i / columns);
          const c = i % columns;
          const x = c * (cellSize + gap);
          const y = r * (cellSize + gap);
          const cx = x + cellSize / 2;
          const cy = y + cellSize / 2;
          const dotR = Math.max(1, Math.floor(cellSize * 0.18));
          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={cellSize}
                height={cellSize}
                fill={color(v)}
                rx={1}
                ry={1}
              />
              {v < 0 && (
                <circle cx={cx} cy={cy} r={dotR} fill="#000" />
              )}
            </g>
          );
        })}
      </svg>
    </Box>
  );
};