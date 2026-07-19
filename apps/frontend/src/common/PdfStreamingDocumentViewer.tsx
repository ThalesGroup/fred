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

import { Box, CircularProgress, Typography } from "@mui/material";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { useAuthToken } from "../security/AuthContext";

type Props = {
  documentUid: string;
};

// React-PDF requires workerSrc to be configured in the same module that renders
// <Document>/<Page>; otherwise its default bare specifier can win at runtime.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);
if (typeof Worker !== "undefined") {
  pdfjs.GlobalWorkerOptions.workerPort = new Worker(pdfWorkerUrl, { type: "module" });
} else {
  pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
}

const PDF_SCALE = 0.8;

// Header-less by design: the two hosting contexts (DocumentViewerPage's own
// top bar, InlineDrawer's own title+close) already provide chrome, so this
// component owns only the PDF surface itself.
export const PdfStreamingDocumentViewer: React.FC<Props> = ({ documentUid }) => {
  const token = useAuthToken();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const contentRef = useRef<HTMLDivElement | null>(null);
  const [pageWidth, setPageWidth] = useState<number>(800);
  useEffect(() => {
    if (!contentRef.current) return;
    const el = contentRef.current;
    const ro = new ResizeObserver(() => {
      const base = Math.max(320, Math.floor(el.clientWidth - 24));
      setPageWidth(Math.floor(base * PDF_SCALE));
    });
    ro.observe(el);
    const base = Math.max(320, Math.floor(el.clientWidth - 24));
    setPageWidth(Math.floor(base * PDF_SCALE));
    return () => ro.disconnect();
  }, []);

  const pdfUrl = useMemo(() => {
    if (!documentUid) return null;
    return `/knowledge-flow/v1/raw_content/stream/${documentUid}`;
  }, [documentUid]);

  const fileProp = useMemo(() => {
    if (!pdfUrl) return null;
    // If we have a bearer, send it; otherwise allow cookies (same-site backend).
    return token
      ? { url: pdfUrl, httpHeaders: { Authorization: token.startsWith("Bearer ") ? token : `Bearer ${token}` } }
      : { url: pdfUrl, withCredentials: true };
  }, [pdfUrl, token]);

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setIsLoading(false);
  };
  const onDocumentLoadError = (err: any) => {
    setLoadError(err?.message || "Failed to load PDF.");
    setIsLoading(false);
  };

  useEffect(() => {
    setIsLoading(true);
    setLoadError(null);
    setNumPages(null);
    setReloadKey((k) => k + 1); // remount Document to reset PDF.js
  }, [documentUid]);

  return (
    <Box
      ref={contentRef}
      sx={{
        width: "100%",
        height: "100%",
        minHeight: 0,
        overflowY: "auto",
        overflowX: "hidden",
        p: 2,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-start",
        boxSizing: "border-box",
      }}
    >
      {!isLoading && loadError && (
        <Typography color="error" sx={{ mt: 4 }}>
          {loadError}
        </Typography>
      )}

      {fileProp && !loadError && (
        <Document
          key={reloadKey}
          file={fileProp}
          onLoadSuccess={onDocumentLoadSuccess}
          onLoadError={onDocumentLoadError}
          loading={<CircularProgress />}
          error={<Typography color="error">Failed to load PDF document.</Typography>}
        >
          {Array.from({ length: numPages ?? 0 }, (_, i) => (
            <Page
              key={`page_${i + 1}`}
              pageNumber={i + 1}
              width={pageWidth}
              renderAnnotationLayer
              renderTextLayer={false} // faster by default
            />
          ))}
        </Document>
      )}

      {!fileProp && !loadError && (
        <Typography color="error" sx={{ mt: 4 }}>
          Document content is unavailable.
        </Typography>
      )}
    </Box>
  );
};

export default PdfStreamingDocumentViewer;
