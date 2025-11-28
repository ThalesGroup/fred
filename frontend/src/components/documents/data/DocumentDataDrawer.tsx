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

import React, { useEffect, useMemo, useState, useRef, useLayoutEffect } from "react";
import { ProcessingGraphNode } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { useDrawer } from "../../DrawerProvider.tsx";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { interpolateTurbo } from "d3-scale-chromatic";

/**
 * Hook pour ouvrir/fermer un Drawer affichant le contenu d'un document vecteur.
 * Doit être utilisé à l'intérieur d'un composant React.
 */
export const useVectorDocumentViewer = () => {
  const { openDrawer, closeDrawer } = useDrawer();

  const openVectorDocument = (doc: ProcessingGraphNode) => {
    openDrawer({
      content: <DocumentDataDrawerContent doc={doc} />,
      anchor: "right",
    });
  };

  const closeVectorDocument = () => {
    closeDrawer();
  };

  return {
    openVectorDocument,
    closeVectorDocument,
  };
};

type VectorItem = number[] | Record<string, any> | string | number | null;

type ChunkItem = {
  text?: string;
  [key: string]: any;
};

// Composant qui ajuste automatiquement la taille de police pour tenir sur une seule ligne
const AutoFitOneLine: React.FC<{
  text: string;
  maxFontSize?: number; // en px
  minFontSize?: number; // en px
  colorVariant?: "primary" | "secondary";
}> = ({ text, maxFontSize = 14, minFontSize = 10, colorVariant = "secondary" }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const textRef = useRef<HTMLSpanElement | null>(null);
  const [fontSize, setFontSize] = useState<number>(maxFontSize);

  const fitOnce = () => {
    const container = containerRef.current;
    const el = textRef.current as HTMLElement | null;
    if (!container || !el) return;
    const cw = container.clientWidth;
    if (cw <= 0) return;

    // Commence depuis max à chaque recalcul
    let size = maxFontSize;
    el.style.fontSize = `${size}px`;
    el.style.whiteSpace = "nowrap";
    el.style.display = "block";

    // Ajuste progressivement, borné à 10 itérations
    let guard = 0;
    while (guard < 10 && el.scrollWidth > cw && size > minFontSize) {
      const scale = cw / Math.max(1, el.scrollWidth);
      size = Math.max(minFontSize, Math.floor(size * Math.max(0.5, Math.min(1, scale))));
      el.style.fontSize = `${size}px`;
      guard++;
    }
    setFontSize(size);
  };

  // Recalcule quand le texte change
  useLayoutEffect(() => {
    fitOnce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, maxFontSize, minFontSize]);

  // Recalcule sur redimensionnement du conteneur
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(() => {
      fitOnce();
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  const color = colorVariant === "secondary" ? "text.secondary" : "text.primary";

  return (
    <Box ref={containerRef} sx={{ width: "100%", overflow: "hidden" }}>
      <Typography
        ref={textRef as any}
        variant="body2"
        color={color as any}
        noWrap
        sx={{ fontSize: `${fontSize}px`, lineHeight: 1.4, display: "block" }}
        title={text}
      >
        {text}
      </Typography>
    </Box>
  );
};

const DocumentDataDrawerContent: React.FC<{ doc: ProcessingGraphNode }> = ({ doc }) => {
  const docId = doc.id;
  const title = doc.label || doc.document_uid || docId;

  // Normalise l'ID attendu par le backend: préférer document_uid sinon enlever le préfixe "doc:"
  const backendDocId = useMemo(() => {
    const preferred = doc.document_uid?.trim();
    if (preferred) return preferred;
    const id = (doc.id || "").trim();
    return id.startsWith("doc:") ? id.slice(4) : id;
  }, [doc.document_uid, doc.id]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [vectors, setVectors] = useState<VectorItem[]>([]);
  const [chunks, setChunks] = useState<ChunkItem[]>([]);

  useEffect(() => {
    let aborted = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    async function load() {
      try {
        const [vecRes, chkRes] = await Promise.all([
          fetch(`/knowledge-flow/v1/document/${encodeURIComponent(backendDocId)}/vectors`, {
            signal: controller.signal,
          }),
          fetch(`/knowledge-flow/v1/document/${encodeURIComponent(backendDocId)}/chunks`, {
            signal: controller.signal,
          }),
        ]);

        if (!vecRes.ok) {
          throw new Error(`Erreur chargement vecteurs: ${vecRes.status}`);
        }
        if (!chkRes.ok) {
          throw new Error(`Erreur chargement chunks: ${chkRes.status}`);
        }
        const vecJson = await vecRes.json();
        const chkJson = await chkRes.json();

        // Assumer que l'API renvoie soit une liste brute, soit un objet { items: [...] }
        const vecItems: VectorItem[] = Array.isArray(vecJson) ? vecJson : vecJson?.items ?? [];
        const chkItems: ChunkItem[] = Array.isArray(chkJson) ? chkJson : chkJson?.items ?? [];

        if (!aborted) {
          setVectors(vecItems);
          setChunks(chkItems);
          setLoading(false);
        }
      } catch (e: any) {
        if (aborted) return;
        setError(e?.message || "Erreur inconnue");
        setLoading(false);
      }
    }

    load();
    return () => {
      aborted = true;
      controller.abort();
    };
  }, [backendDocId]);

  const pairs = useMemo(() => {
    const len = Math.max(vectors.length, chunks.length);
    return new Array(len).fill(0).map((_, i) => ({
      index: i,
      vector: vectors[i],
      chunk: chunks[i],
    }));
  }, [vectors, chunks]);

  return (
    <Box sx={{ width: 520, maxWidth: '100vw' }}>
      <Box sx={{ px: 2, py: 1.5 }}>
        <Typography variant="h6" noWrap>{title}</Typography>
        <AutoFitOneLine
          text={`ID: ${backendDocId}`}
          colorVariant="secondary"
          maxFontSize={14}
          minFontSize={10}
        />
      </Box>
      <Divider />
      <Box sx={{ p: 2 }}>
        {loading && (
          <Stack alignItems="center" justifyContent="center" sx={{ py: 6 }}>
            <CircularProgress size={24} />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Chargement des données…
            </Typography>
          </Stack>
        )}
        {error && (
          <Typography color="error" variant="body2">
            {error}
          </Typography>
        )}
        {!loading && !error && pairs.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            Aucune donnée disponible pour ce document.
          </Typography>
        )}

        {!loading && !error && pairs.map(({ index, vector, chunk }) => (
          <Box key={index} sx={{ mb: 1.5 }}>
            <Accordion disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography variant="subtitle2">Vecteur #{index + 1}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <VectorHeatmap vector={vector} />
              </AccordionDetails>
            </Accordion>

            <Accordion disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', alignItems: 'center', width: '100%', gap: 1, minWidth: 0 }}>
                  <Typography variant="subtitle2" noWrap>
                    Chunk #{index + 1}
                  </Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  {chunk?.chunk_uid != null && (
                    <Typography variant="caption" color="text.secondary" noWrap title={String(chunk.chunk_uid)}>
                      {String(chunk.chunk_uid)}
                    </Typography>
                  )}
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Box
                  component="pre"
                  sx={{
                    m: 0,
                    maxHeight: 240,
                    overflowX: "auto",
                    overflowY: "auto",
                    whiteSpace: "pre", // respecte les retours à la ligne sans wrapping
                    fontFamily:
                      'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
                    fontSize: 13,
                    lineHeight: 1.5,
                    wordBreak: "normal",
                    overflowWrap: "normal",
                  }}
               >
                  {chunk?.text ?? fallbackChunkText(chunk)}
                </Box>
              </AccordionDetails>
            </Accordion>
          </Box>
        ))}
      </Box>
    </Box>
  );
};

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

function fallbackChunkText(c: ChunkItem | undefined): string {
  if (!c) return "(vide)";
  const keys = Object.keys(c);
  if (!keys.length) return "(vide)";
  // Tente de trouver un champ text-like
  const k = keys.find((k) => /content|text|chunk/i.test(k));
  return k ? String((c as any)[k]) : JSON.stringify(c, null, 2);
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

const VectorHeatmap: React.FC<{
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
  const gain = 10

  // Amplification et échelle fixe symétrique autour de 0
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