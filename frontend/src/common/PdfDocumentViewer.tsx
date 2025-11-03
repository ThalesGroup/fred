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

// This is the old PdfDocumentViewer component, kept for reference.
// The new component is PdfStreamingDocumentViewer.tsx, which uses react-pdf.
import CloseIcon from "@mui/icons-material/Close";
import DownloadIcon from "@mui/icons-material/Download";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  AppBar,
  Box,
  CircularProgress,
  IconButton,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Document, Page } from 'react-pdf';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';
//import BugReportIcon from "@mui/icons-material/BugReport";
import { useLazyDownloadRawContentBlobQuery } from '../slices/knowledgeFlow/knowledgeFlowApi.blob';
import { downloadFile } from '../utils/downloadUtils';

interface PdfDocumentViewerProps {
  document: {
    document_uid: string;
    file_name?: string;
  } | null;
  onClose: () => void;
}

type RenderMode = 'arraybuffer' | 'blob' | 'objecturl';

const DEBUG = false; // flip to false to silence logs in production quickly
const TAG = '[PdfViewer]';
const PDF_SCALE_FACTOR = 0.8; // Set to 1.0 for 100% width, 0.8 for 80%, etc.

const log = (...args: any[]) => DEBUG && console.log(TAG, ...args);
const warn = (...args: any[]) => DEBUG && console.warn(TAG, ...args);
const error = (...args: any[]) => console.error(TAG, ...args);

export const PdfDocumentViewer: React.FC<PdfDocumentViewerProps> = ({ document: doc, onClose }) => {
  const [triggerDownloadBlob] = useLazyDownloadRawContentBlobQuery();

  // Data states
  const [blob, setBlob] = useState<Blob | null>(null);
  const [arrayBuffer, setArrayBuffer] = useState<ArrayBuffer | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  // UI states
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [serverPreview, setServerPreview] = useState<string | null>(null); // show HTML/JSON if not a PDF
  const [numPages, setNumPages] = useState<number | null>(null);
  const [renderMode, setRenderMode] = useState<RenderMode>('arraybuffer');

  // Fit-to-width
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [pageWidth, setPageWidth] = useState<number>(800);

  // Compute the "file" prop for <Document/> from the selected render mode
  const reactPdfFile = useMemo(() => {
    if (renderMode === 'arraybuffer' && arrayBuffer) return { data: arrayBuffer };
    if (renderMode === 'blob' && blob) return blob;
    if (renderMode === 'objecturl' && objectUrl) return objectUrl;
    return null;
  }, [renderMode, arrayBuffer, blob, objectUrl]);

  // ResizeObserver to fit page to drawer width
  useEffect(() => {
    if (!contentRef.current) return;
    const el = contentRef.current;
    const ro = new ResizeObserver(() => {
      const baseW = Math.max(320, Math.floor(el.clientWidth - 24)); 
      const scaledW = Math.floor(baseW * PDF_SCALE_FACTOR);
      setPageWidth(scaledW);
      log('ResizeObserver -> pageWidth', scaledW);
    });
    ro.observe(el);
    const initialBaseW = Math.max(320, Math.floor(el.clientWidth - 24));
    setPageWidth(Math.floor(initialBaseW * PDF_SCALE_FACTOR));
    return () => ro.disconnect();
  }, []);

  const clearData = useCallback(() => {
    setBlob(null);
    setArrayBuffer(null);
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      log('Revoked ObjectURL');
    }
    setObjectUrl(null);
    setNumPages(null);
    setServerPreview(null);
  }, [objectUrl]);

  const fetchPdf = useCallback(async () => {
    if (!doc?.document_uid) {
      setLoadError('No document UID provided.');
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setLoadError(null);
    clearData();
    setRenderMode('arraybuffer');

    const uid = doc.document_uid;
    const assumedUrl = `/knowledge-flow/v1/raw_content/${uid}`; // informational only
    log('Fetching PDF…', { uid, assumedUrl });

    try {
      const pdfBlob = await triggerDownloadBlob({ documentUid: uid }).unwrap();

      log('Fetch OK. Blob info:', {
        instanceOfBlob: pdfBlob instanceof Blob,
        size: pdfBlob.size,
        type: pdfBlob.type || '(unset)',
      });

      // Sanity checks
      if (!(pdfBlob instanceof Blob)) {
        throw new Error('Endpoint did not return a Blob');
      }
      if (pdfBlob.size === 0) {
        // often indicates 401/403 HTML body filtered out by fetch, or server issue
        const txt = await pdfBlob.text().catch(() => '');
        setServerPreview(txt.slice(0, 4000));
        throw new Error('Empty file received from server (0 bytes).');
      }

      // Peek header to confirm PDF
      const head = await pdfBlob.slice(0, 8).text();
      const isPdf = head.startsWith('%PDF-');
      log('Header peek:', JSON.stringify(head), 'isPdf?', isPdf);

      if (!isPdf) {
        const preview = await pdfBlob.text().catch(() => '(non-text payload)');
        setServerPreview(preview.slice(0, 4000));
        throw new Error('Server did not return a PDF (no %PDF- header).');
      }

      // Prepare all render strategies
      setBlob(pdfBlob);
      const ab = await pdfBlob.arrayBuffer();
      setArrayBuffer(ab);
      const url = URL.createObjectURL(pdfBlob);
      setObjectUrl(url);
      log('Prepared render modes: arrayBuffer, blob, objectUrl');

    } catch (e: any) {
      error('Fetch error:', e);
      setLoadError(e?.message || 'Failed to load PDF.');
    } finally {
      setIsLoading(false);
    }
  }, [doc?.document_uid, triggerDownloadBlob, clearData]);

  // Initial + UID changes
  useEffect(() => {
    fetchPdf();
    // Cleanup objectURL on unmount or uid change
    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        log('Cleanup: revoked ObjectURL');
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc?.document_uid]);

  // react-pdf callbacks
  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    log('Document loaded. Pages:', numPages, 'renderMode:', renderMode);
  };

  const onDocumentLoadError = (err: any) => {
    warn('react-pdf onLoadError:', err?.message || err);
    // Fallback chain: arraybuffer → blob → objecturl → give up
    setRenderMode(prev => {
      if (prev === 'arraybuffer' && blob) {
        log('Falling back: arraybuffer → blob');
        return 'blob';
      }
      if (prev === 'blob' && objectUrl) {
        log('Falling back: blob → objecturl');
        return 'objecturl';
      }
      error('All render strategies failed.');
      setLoadError(err?.message || 'Failed to render PDF.');
      return prev;
    });
  };

  const handleRetry = () => {
    log('Manual retry requested.');
    fetchPdf();
  };

  return (
     <Box
      sx={{
        width: "80vw",
        height: "100%",      // let Drawer control height
        maxHeight: "100vh",  // never exceed viewport
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        minHeight: 0,        // ✅ critical for scrollable flex children
      }}
    >
      <AppBar position="static" color="default" elevation={0}>
        <Toolbar>
          <Typography variant="h6" sx={{ flex: 1, pr: 1 }}>
            {doc?.file_name || "PDF Document"}
          </Typography>

          <Tooltip title="Download">
            <span>
              <IconButton
                aria-label="Download"
                disabled={!blob}
                onClick={() => blob && downloadFile(blob, doc?.file_name || `${doc?.document_uid}.pdf`)}
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
          flex: 1,
          minHeight: 0,          // ✅ allow this flex child to actually scroll
          overflowY: "auto",
          overflowX: "hidden",
          p: 2,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',  // horizontal centering only
          justifyContent: 'flex-start', // ✅ start at top
          boxSizing: "border-box",
          width: "100%",
        }}
      >  
            {isLoading ? (
          <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
            <CircularProgress />
          </Box>
        ) : loadError ? (
          <>
            <Typography color="error" sx={{ mt: 4, mb: 2 }}>
              {loadError}
            </Typography>
            {serverPreview && (
              <Box sx={{ textAlign: 'left', mx: 'auto', maxWidth: 900, p: 2, bgcolor: 'background.paper', borderRadius: 1 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Server response preview (first 4KB):
                </Typography>
                <Box component="pre" sx={{ whiteSpace: 'pre-wrap', m: 0, fontFamily: 'monospace', fontSize: 12 }}>
                  {serverPreview}
                </Box>
              </Box>
            )}
          </>
        ) : reactPdfFile ? (
          <Document
            file={reactPdfFile}
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
                renderTextLayer
              />
            ))}
          </Document>
        ) : (
          <Typography color="error" sx={{ mt: 4 }}>
            Document content is unavailable.
          </Typography>
        )}

        {/* Debug footer */}
        {/* <Divider sx={{ my: 2 }} />
        <Box sx={{ textAlign: 'left', mx: 'auto', maxWidth: 900 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <BugReportIcon fontSize="small" />
            <Typography variant="subtitle2">Debug</Typography>
          </Box>
          <Box component="pre" sx={{ whiteSpace: 'pre-wrap', m: 0, fontFamily: 'monospace', fontSize: 12 }}>
            {JSON.stringify({
              uid: doc?.document_uid,
              fileName: doc?.file_name,
              isLoading,
              loadError,
              renderMode,
              numPages,
              blob: blob ? { size: blob.size, type: blob.type } : null,
              arrayBuffer: arrayBuffer ? { bytes: arrayBuffer.byteLength } : null,
              objectUrl: Boolean(objectUrl),
              pageWidth,
            }, null, 2)}
          </Box>
        </Box> */}
      </Box>
    </Box>
  );
};

export default PdfDocumentViewer;
