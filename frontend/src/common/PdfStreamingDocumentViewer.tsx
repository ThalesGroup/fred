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

import CloseIcon from "@mui/icons-material/Close";
import DownloadIcon from "@mui/icons-material/Download";
import RefreshIcon from "@mui/icons-material/Refresh";
import { AppBar, Box, CircularProgress, IconButton, Toolbar, Tooltip, Typography } from "@mui/material";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/esm/Page/AnnotationLayer.css";
import "react-pdf/dist/esm/Page/TextLayer.css";
import { useAuthToken } from "../security/AuthContext";
import PdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?worker"; // Vite turns this into a Worker

pdfjs.GlobalWorkerOptions.workerPort = new PdfWorker();

type Props = {
  document: { document_uid: string; file_name?: string } | null;
  onClose: () => void;
};

const PDF_SCALE = 0.8;

export const PdfStreamingDocumentViewer: React.FC<Props> = ({ document: doc, onClose }) => {
  const token = useAuthToken();               // ← decoupled
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

  const pdfUrl = useMemo(
    () => (doc?.document_uid ? `/knowledge-flow/v1/raw_content/stream/${doc.document_uid}` : null),
    [doc?.document_uid]
  );

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
  }, [doc?.document_uid]);

  const handleRetry = () => {
    setIsLoading(true);
    setLoadError(null);
    setNumPages(null);
    setReloadKey((k) => k + 1);
  };

  return (
    <Box sx={{ width: "80vw", height: "100%", maxHeight: "100vh", display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 0 }}>
      <AppBar position="static" color="default" elevation={0}>
        <Toolbar>
          <Typography variant="h6" sx={{ flex: 1, pr: 1 }}>{doc?.file_name || "PDF Document"}</Typography>

          {/* Download keeps using the non-streaming endpoint */}
          <Tooltip title="Download">
            <span>
              <IconButton
                aria-label="Download"
                disabled={!doc?.document_uid}
                onClick={() => {
                  if (!doc?.document_uid) return;
                  window.open(`/knowledge-flow/v1/raw_content/${doc.document_uid}`, "_blank");
                }}
              >
                <DownloadIcon />
              </IconButton>
            </span>
          </Tooltip>

          <Tooltip title="Retry">
            <IconButton onClick={handleRetry} aria-label="Retry">
              <RefreshIcon />
            </IconButton>
          </Tooltip>

          <IconButton onClick={onClose} aria-label="Close">
            <CloseIcon />
          </IconButton>
        </Toolbar>
      </AppBar>

      <Box
        ref={contentRef}
        sx={{
          flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden", p: 2,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-start", boxSizing: "border-box", width: "100%",
        }}
      >
        {!isLoading && loadError && (
          <Typography color="error" sx={{ mt: 4 }}>{loadError}</Typography>
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
          <Typography color="error" sx={{ mt: 4 }}>Document content is unavailable.</Typography>
        )}
      </Box>
    </Box>
  );
};

export default PdfStreamingDocumentViewer;
