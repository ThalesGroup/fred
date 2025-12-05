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

import { Accordion, AccordionDetails, AccordionSummary, Box, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import React, { useMemo } from "react";
import { ChunkItem, VectorItem } from "./DocumentDataCommon.tsx";
import { VectorHeatmap } from "./VectorHeatmap.tsx";

function fallbackChunkText(c: ChunkItem | undefined): string {
  if (!c) return "(vide)";
  const keys = Object.keys(c);
  if (!keys.length) return "(vide)";
  // Tente de trouver un champ text-like
  const k = keys.find((k) => /content|text|chunk/i.test(k));
  return k ? String((c as any)[k]) : JSON.stringify(c, null, 2);
}

type Props = {
  vectors?: VectorItem[];
  chunks: ChunkItem[];
};

export const ChunksAccordion: React.FC<Props> = ({ vectors, chunks }) => {

  const pairs = useMemo(() => {
    const v = vectors ?? [];
    const len = Math.max(v.length, chunks.length);
    return new Array(len).fill(0).map((_, i) => ({
      index: i,
      vector: v[i],
      chunk: chunks[i],
    }));
  }, [vectors, chunks]);

  return (
    <>
      {
        pairs.map(({ index, vector, chunk }) => (
          <Box key={index} sx={{ mb: 1.5 }}>
            { vector && (
              <Accordion disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="subtitle2">Vecteur #{index + 1}</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <VectorHeatmap vector={vector} />
                </AccordionDetails>
              </Accordion>
            )}

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
        ))
      }
    </>
  );
};

export default ChunksAccordion;
