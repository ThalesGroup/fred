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

import React, { useEffect, useMemo, useRef, useLayoutEffect, useState } from "react";
import {
  ProcessingGraphNode,
  useDocumentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGetQuery,
  useDocumentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGetQuery
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { useDrawer } from "../../DrawerProvider.tsx";
import {
  Box,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import ChunksAccordion from "./ChunksAccordion.tsx";

/**
 * Hook to open/close a Drawer displaying the content of a vector document.
 * Must be used inside a React component.
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

// Component that automatically adjusts font size to fit on a single line
const AutoFitOneLine: React.FC<{
  text: string;
  maxFontSize?: number; // in px
  minFontSize?: number; // in px
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

    // Start from max at each recalculation
    let size = maxFontSize;
    el.style.fontSize = `${size}px`;
    el.style.whiteSpace = "nowrap";
    el.style.display = "block";

    // Adjust gradually, limited to 10 iterations
    let guard = 0;
    while (guard < 10 && el.scrollWidth > cw && size > minFontSize) {
      const scale = cw / Math.max(1, el.scrollWidth);
      size = Math.max(minFontSize, Math.floor(size * Math.max(0.5, Math.min(1, scale))));
      el.style.fontSize = `${size}px`;
      guard++;
    }
    setFontSize(size);
  };

  // Recalculate when text changes
  useLayoutEffect(() => {
    fitOnce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, maxFontSize, minFontSize]);

  // Recalculate on container resize
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

  // Normalize the ID expected by the backend: prefer document_uid otherwise remove the "doc:" prefix
  const backendDocId = useMemo(() => {
    const preferred = doc.document_uid?.trim();
    if (preferred) return preferred;
    const id = (doc.id || "").trim();
    return id.startsWith("doc:") ? id.slice(4) : id;
  }, [doc.document_uid, doc.id]);

  const {
    data: vectorsData,
    isLoading: vectorsLoading,
    error: vectorsError,
  } = useDocumentVectorsKnowledgeFlowV1DocumentsDocumentUidVectorsGetQuery(
    { documentUid: backendDocId },
    { skip: !backendDocId },
  );
  const {
    data: chunksData,
    isLoading: chunksLoading,
    error: chunksError,
  } = useDocumentChunksKnowledgeFlowV1DocumentsDocumentUidChunksGetQuery(
    { documentUid: backendDocId },
    { skip: !backendDocId },
  );

  const vectors = useMemo(() => {
    if (!vectorsData) return [];
    return Array.isArray(vectorsData) ? vectorsData : (vectorsData as any)?.items ?? [];
  }, [vectorsData]);

  const chunks = useMemo(() => {
    if (!chunksData) return [];
    return Array.isArray(chunksData) ? chunksData : (chunksData as any)?.items ?? [];
  }, [chunksData]);

  const formatError = (err: unknown): string => {
    if (!err) return "";
    if (typeof err === "string") return err;
    if (err && typeof err === "object" && "status" in err) {
      const anyErr = err as any;
      const detail = anyErr?.data?.detail ?? anyErr?.data;
      const detailStr =
        detail == null ? "" : typeof detail === "string" ? detail : JSON.stringify(detail);
      return `Error ${anyErr.status}${detailStr ? `: ${detailStr}` : ""}`;
    }
    if (err instanceof Error) return err.message;
    return "Unknown error";
  };

  const error = vectorsError ? formatError(vectorsError) : chunksError ? formatError(chunksError) : null;
  const loading = vectorsLoading || chunksLoading;

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
              Loading data…
            </Typography>
          </Stack>
        )}
        {error && (
          <Typography color="error" variant="body2">
            {error}
          </Typography>
        )}
        {!loading && !error && vectors.length === 0 && chunks.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No data available for this document.
          </Typography>
        )}
        {!loading && !error && (
          <ChunksAccordion vectors={vectors} chunks={chunks} />
        )}
      </Box>
    </Box>
  );
};
